from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import urllib.error
import urllib.request
from http import HTTPStatus
from typing import Any

from .config import ALIYUN_API_KEY_ENV, ALIYUN_BASE_URL, DEFAULT_MODEL
from .errors import AppError
from .utils import normalize_prefix


def api_key_status() -> bool:
    return bool(os.environ.get(ALIYUN_API_KEY_ENV))


def env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(minimum, value)


def request_bailian(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    timeout_seconds = env_int("ALIYUN_TIMEOUT_SECONDS", 600)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{ALIYUN_BASE_URL}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise AppError(exc.code, "百炼接口返回错误", error_body[:1200]) from exc
    except urllib.error.URLError as exc:
        raise AppError(
            HTTPStatus.BAD_GATEWAY,
            "无法连接百炼接口，请检查网络或 ALIYUN_BASE_URL",
            str(exc.reason),
        ) from exc
    except TimeoutError as exc:
        raise AppError(HTTPStatus.GATEWAY_TIMEOUT, "百炼接口请求超时") from exc


def extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise AppError(
                HTTPStatus.BAD_GATEWAY,
                "模型没有返回可解析的 JSON",
                content[:1200],
            )
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise AppError(HTTPStatus.BAD_GATEWAY, "模型返回的 JSON 顶层不是对象")
    return value


def build_prompt(words: list[str]) -> tuple[str, str]:
    system_prompt = (
        "你是熟悉 2026 年新托福改革方向的英语命题老师，"
        "专门制作 vocabulary-in-context 填词练习。"
        "只返回严格 JSON，不要 Markdown，不要解释。"
    )
    user_payload = {
        "task": "为每个英文单词生成中文含义和 10 道新托福风格填词素材。",
        "exam_style": [
            "例句要像 2026 年新托福填词题：学术、校园、讲座、阅读段落或讨论语境。",
            "句子必须提供足够上下文线索，让考生可以根据语义、搭配或逻辑关系补出目标词。",
            "不要写成单纯词典例句；避免过短、过直白或只有一个孤立定义的句子。",
            "每句只考一个目标词，并且必须包含目标词原形，大小写不限。",
            "不要把目标词改成复数、过去式、比较级、派生词或短语变体。",
        ],
        "prefix_design": [
            "为每条例句设计 visible_prefix，即考试中显示的目标词开头部分。",
            "visible_prefix 必须是目标词从第一个字母开始的连续前缀。",
            "visible_prefix 不能等于完整单词，也不能让答案显得过于明显。",
            "不要机械固定为 2 到 4 个字母；请按词长、词根、音节、拼写难度和相近词混淆度判断。",
            "例如 competition 这类较长词可以显示 compe，短词可以显示更少字母。",
            "目标是模拟真实填词题里自然、合理的字母提示结构。",
        ],
        "output_schema": {
            "items": [
                {
                    "word": "abandon",
                    "chinese_meaning": "放弃；抛弃",
                    "examples": [
                        {
                            "sentence": "The researchers decided to abandon the method after repeated trials produced unreliable data.",
                            "visible_prefix": "aba",
                        }
                    ],
                }
            ]
        },
        "words": words,
    }
    return system_prompt, json.dumps(user_payload, ensure_ascii=False)


def generate_words(
    words: list[str], model: str
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not words:
        return [], []

    api_key = os.environ.get(ALIYUN_API_KEY_ENV)
    if not api_key:
        raise AppError(
            HTTPStatus.BAD_REQUEST,
            f"未读取到环境变量 {ALIYUN_API_KEY_ENV}",
            "请先在系统环境变量或当前终端中设置百炼 API Key。",
        )

    clean_model = model.strip() or DEFAULT_MODEL
    max_workers = min(env_int("ALIYUN_MAX_WORKERS", 20), len(words))
    results: list[dict[str, Any] | None] = [None] * len(words)
    skipped_with_index: list[tuple[int, dict[str, str]]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(generate_one_word, word, clean_model, api_key): (index, word)
            for index, word in enumerate(words)
        }
        for future in as_completed(futures):
            index, word = futures[future]
            try:
                results[index] = future.result()
            except AppError as exc:
                skipped_with_index.append(
                    (
                        index,
                        {
                            "word": word,
                            "error": exc.message,
                            "details": (exc.details or "")[:500],
                        },
                    )
                )
            except Exception as exc:  # pragma: no cover
                skipped_with_index.append(
                    (index, {"word": word, "error": str(exc), "details": ""})
                )

    skipped = [item for _, item in sorted(skipped_with_index, key=lambda entry: entry[0])]
    return [item for item in results if item is not None], skipped


def generate_one_word(word: str, model: str, api_key: str) -> dict[str, Any]:
    items = request_generated_items([word], model, api_key)
    return items[0]


def request_generated_items(
    words: list[str], model: str, api_key: str
) -> list[dict[str, Any]]:
    system_prompt, user_prompt = build_prompt(words)
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.72,
        "response_format": {"type": "json_object"},
    }

    try:
        response = request_bailian(payload, api_key)
    except AppError as exc:
        if exc.status == HTTPStatus.BAD_REQUEST and "response_format" in (exc.details or ""):
            fallback_payload = dict(payload)
            fallback_payload.pop("response_format", None)
            response = request_bailian(fallback_payload, api_key)
        else:
            raise

    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AppError(
            HTTPStatus.BAD_GATEWAY,
            "百炼返回结构不符合预期",
            json.dumps(response, ensure_ascii=False)[:1200],
        ) from exc

    parsed = extract_json_object(str(content))
    items = parsed.get("items", [])
    if not isinstance(items, list):
        raise AppError(HTTPStatus.BAD_GATEWAY, "模型返回的 items 不是数组")

    by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and item.get("word"):
            by_key[str(item["word"]).lower()] = item

    normalized: list[dict[str, Any]] = []
    for expected_word in words:
        item = by_key.get(expected_word.lower())
        if not item:
            raise AppError(
                HTTPStatus.BAD_GATEWAY,
                f"模型没有返回单词 {expected_word} 的结果",
                content[:1200],
            )
        normalized.append(normalize_item(expected_word, item, model, content))
    return normalized


def normalize_item(
    expected_word: str, item: dict[str, Any], model: str, raw_content: str
) -> dict[str, Any]:
    examples = item.get("examples", [])
    if not isinstance(examples, list):
        examples = []

    clean_examples: list[dict[str, str]] = []
    seen_sentences: set[str] = set()
    for example in examples:
        if isinstance(example, dict):
            sentence = " ".join(str(example.get("sentence") or "").split())
            prefix = str(example.get("visible_prefix") or "")
        else:
            sentence = " ".join(str(example).split())
            prefix = ""
        if not sentence or sentence in seen_sentences:
            continue
        clean_examples.append(
            {
                "sentence": sentence,
                "visible_prefix": normalize_prefix(prefix, expected_word),
            }
        )
        seen_sentences.add(sentence)
        if len(clean_examples) >= 10:
            break

    if len(clean_examples) < 10:
        raise AppError(
            HTTPStatus.BAD_GATEWAY,
            f"模型为 {expected_word} 只返回了 {len(clean_examples)} 个例句",
            raw_content[:1200],
        )

    return {
        "word": expected_word,
        "chinese_meaning": str(
            item.get("chinese_meaning") or item.get("meaning") or ""
        ).strip(),
        "examples": clean_examples,
        "model": model,
    }
