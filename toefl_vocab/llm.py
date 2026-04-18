from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
from http import HTTPStatus
from typing import Any

from .config import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_PROTOCOL
from .errors import AppError
from .utils import normalize_prefix, word_pattern


SUPPORTED_PROTOCOLS = ("openai", "genai", "anthropic")


def env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(minimum, value)


def build_request_config(data: dict[str, Any]) -> dict[str, str]:
    protocol = str(data.get("protocol") or DEFAULT_PROTOCOL).strip().lower()
    if protocol not in SUPPORTED_PROTOCOLS:
        raise AppError(
            HTTPStatus.BAD_REQUEST,
            "协议类型必须是 openai、genai 或 anthropic",
        )

    model = str(data.get("model") or DEFAULT_MODEL).strip()
    if not model:
        raise AppError(HTTPStatus.BAD_REQUEST, "请输入模型名称")

    raw_base_url = data.get("base_url")
    if raw_base_url is None:
        base_url = DEFAULT_BASE_URL if protocol == DEFAULT_PROTOCOL else ""
    else:
        base_url = str(raw_base_url).strip()

    api_key = str(data.get("api_key") or "").strip()
    if not api_key:
        raise AppError(HTTPStatus.BAD_REQUEST, "请输入 API Key")

    return {
        "protocol": protocol,
        "model": model,
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
    }


def build_prompt(word: str) -> tuple[str, str]:
    system_prompt = (
        "你是熟悉 2026 年新托福改革方向的英语命题老师，"
        "专门制作 vocabulary-in-context 填词练习。"
        "只返回严格 JSON，不要 Markdown，不要解释。"
    )
    user_payload = {
        "task": "为这个英文单词生成中文含义和 10 道新托福风格填词素材。",
        "word": word,
        "exam_style": [
            "例句要像 2026 年新托福填词题：学术、校园、讲座、阅读段落或讨论语境。",
            "句子必须提供足够上下文线索，让考生可以根据语义、搭配或逻辑关系补出目标词。",
            "不要写成单纯词典例句；避免过短、过直白或只有一个孤立定义的句子。",
            "每句只考一个目标词。",
            "允许为保证句子自然和语法正确，对答案做时态、单复数、三单、分词等屈折变化。",
            "例如输入 travel，例句中的正确答案可以是 traveled、travels 或 traveling。",
            "answer 必须是句子里实际出现、且需要考生填入的那个单词形式。",
        ],
        "prefix_design": [
            "为每条例句设计 visible_prefix，即考试中显示的目标词开头部分。",
            "visible_prefix 必须是 answer 从第一个字母开始的连续前缀。",
            "visible_prefix 不能等于完整 answer，也不能让答案显得过于明显。",
            "不要机械固定字母数；请按 answer 的长度、词根、音节、拼写难度和相近词混淆度判断。",
            "目标是模拟真实填词题里自然、合理的字母提示结构。",
        ],
        "output_schema": {
            "word": "travel",
            "chinese_meaning": "旅行；行进",
            "examples": [
                {
                    "sentence": "Many graduate students traveled abroad during the summer to collect field data.",
                    "answer": "traveled",
                    "visible_prefix": "trave",
                }
            ],
        },
    }
    return system_prompt, json.dumps(user_payload, ensure_ascii=False)


def generate_words(
    words: list[str], request_config: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not words:
        return [], []

    max_workers = min(env_int("LLM_MAX_WORKERS", 20), len(words))
    results: list[dict[str, Any] | None] = [None] * len(words)
    skipped_with_index: list[tuple[int, dict[str, str]]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(generate_one_word, word, request_config): (index, word)
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


def generate_one_word(word: str, request_config: dict[str, str]) -> dict[str, Any]:
    system_prompt, user_prompt = build_prompt(word)
    content = request_text(system_prompt, user_prompt, request_config)
    parsed = extract_json_object(content)
    if isinstance(parsed.get("items"), list) and parsed["items"]:
        item = parsed["items"][0]
    else:
        item = parsed
    if not isinstance(item, dict):
        raise AppError(HTTPStatus.BAD_GATEWAY, "模型返回的 JSON 结构不符合预期", content[:1200])
    return normalize_item(word, item, request_config["model"], content)


def request_text(system_prompt: str, user_prompt: str, request_config: dict[str, str]) -> str:
    protocol = request_config["protocol"]
    if protocol == "openai":
        return request_openai(system_prompt, user_prompt, request_config)
    if protocol == "genai":
        return request_genai(system_prompt, user_prompt, request_config)
    if protocol == "anthropic":
        return request_anthropic(system_prompt, user_prompt, request_config)
    raise AppError(HTTPStatus.BAD_REQUEST, f"不支持的协议类型：{protocol}")


def request_openai(
    system_prompt: str, user_prompt: str, request_config: dict[str, str]
) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise AppError(HTTPStatus.INTERNAL_SERVER_ERROR, "未安装 openai 库") from exc

    timeout_seconds = env_int("LLM_TIMEOUT_SECONDS", 600)
    client = OpenAI(
        api_key=request_config["api_key"],
        base_url=request_config["base_url"] or None,
        timeout=timeout_seconds,
    )
    request_kwargs = {
        "model": request_config["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.72,
    }
    try:
        response = client.chat.completions.create(
            **request_kwargs,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
    except Exception as exc:
        if "response_format" in str(exc):
            try:
                response = client.chat.completions.create(**request_kwargs)
                content = response.choices[0].message.content
            except Exception as retry_exc:
                raise AppError(
                    HTTPStatus.BAD_GATEWAY,
                    "OpenAI 协议请求失败",
                    str(retry_exc)[:1200],
                ) from retry_exc
        else:
            raise AppError(
                HTTPStatus.BAD_GATEWAY,
                "OpenAI 协议请求失败",
                str(exc)[:1200],
            ) from exc

    if not content:
        raise AppError(HTTPStatus.BAD_GATEWAY, "OpenAI 协议没有返回文本内容")
    return str(content)


def request_anthropic(
    system_prompt: str, user_prompt: str, request_config: dict[str, str]
) -> str:
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise AppError(HTTPStatus.INTERNAL_SERVER_ERROR, "未安装 anthropic 库") from exc

    timeout_seconds = env_int("LLM_TIMEOUT_SECONDS", 600)
    client = Anthropic(
        api_key=request_config["api_key"],
        base_url=request_config["base_url"] or None,
        timeout=timeout_seconds,
    )
    try:
        response = client.messages.create(
            model=request_config["model"],
            max_tokens=4096,
            temperature=0.72,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        content = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
    except Exception as exc:
        raise AppError(HTTPStatus.BAD_GATEWAY, "Anthropic 协议请求失败", str(exc)[:1200]) from exc

    if not content:
        raise AppError(HTTPStatus.BAD_GATEWAY, "Anthropic 协议没有返回文本内容")
    return str(content)


def request_genai(
    system_prompt: str, user_prompt: str, request_config: dict[str, str]
) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover
        raise AppError(HTTPStatus.INTERNAL_SERVER_ERROR, "未安装 google-genai 库") from exc

    client: Any
    if request_config["base_url"]:
        http_options = types.HttpOptions(
            baseUrl=request_config["base_url"],
            baseUrlResourceScope=types.ResourceScope.COLLECTION,
            headers={
                "Authorization": f"Bearer {request_config['api_key']}",
                "x-goog-api-key": request_config["api_key"],
            },
        )
        client = genai.Client(vertexai=True, http_options=http_options)
    else:
        client = genai.Client(api_key=request_config["api_key"])

    try:
        response = client.models.generate_content(
            model=request_config["model"],
            contents=user_prompt,
            config=types.GenerateContentConfig(
                systemInstruction=system_prompt,
                temperature=0.72,
                maxOutputTokens=4096,
                responseMimeType="application/json",
            ),
        )
        content = getattr(response, "text", None) or extract_genai_text(response)
    except Exception as exc:
        raise AppError(HTTPStatus.BAD_GATEWAY, "GenAI 协议请求失败", str(exc)[:1200]) from exc

    if not content:
        raise AppError(HTTPStatus.BAD_GATEWAY, "GenAI 协议没有返回文本内容")
    return str(content)


def extract_genai_text(response: Any) -> str:
    chunks: list[str] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            text = getattr(part, "text", None)
            if text:
                chunks.append(str(text))
    return "".join(chunks)


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


def normalize_item(
    expected_word: str, item: dict[str, Any], model: str, raw_content: str
) -> dict[str, Any]:
    examples = item.get("examples", [])
    if not isinstance(examples, list):
        examples = []

    clean_examples: list[dict[str, str]] = []
    seen_sentences: set[str] = set()
    for example in examples:
        if not isinstance(example, dict):
            continue

        sentence = " ".join(str(example.get("sentence") or "").split())
        raw_answer = " ".join(str(example.get("answer") or expected_word).split())
        if not sentence or sentence in seen_sentences:
            continue

        answer = sentence_answer(sentence, raw_answer)
        if not answer:
            continue

        prefix = normalize_prefix(str(example.get("visible_prefix") or ""), answer)
        clean_examples.append(
            {
                "sentence": sentence,
                "answer": answer,
                "visible_prefix": prefix,
            }
        )
        seen_sentences.add(sentence)
        if len(clean_examples) >= 10:
            break

    if len(clean_examples) < 10:
        raise AppError(
            HTTPStatus.BAD_GATEWAY,
            f"模型为 {expected_word} 只返回了 {len(clean_examples)} 个可用例句",
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


def sentence_answer(sentence: str, raw_answer: str) -> str:
    candidate = re.sub(r"[^A-Za-z'-]", "", raw_answer)
    if not candidate:
        return ""

    pattern = word_pattern(candidate)
    match = pattern.search(sentence)
    if not match:
        loose = re.compile(rf"({re.escape(candidate)})", re.IGNORECASE)
        match = loose.search(sentence)
    if not match:
        return ""
    return match.group(1)
