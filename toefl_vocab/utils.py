from __future__ import annotations

import re
from typing import Any


def parse_word_input(raw: str) -> list[str]:
    pieces = re.split(r"[\s,，;；、]+", raw.strip())
    words: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        word = piece.strip().strip(".:：()[]{}\"'")
        if not word:
            continue
        key = word.lower()
        if key not in seen:
            seen.add(key)
            words.append(word)
    return words


def word_pattern(word: str) -> re.Pattern[str]:
    escaped = re.escape(word)
    return re.compile(rf"(?<![A-Za-z])({escaped})(?![A-Za-z])", re.IGNORECASE)


def fallback_prefix(word: str) -> str:
    length = len(word)
    if length <= 2:
        return word[:1]
    if length <= 5:
        return word[: max(2, length - 2)]
    if length <= 8:
        return word[: min(length - 1, max(2, length // 2))]
    return word[: min(length - 1, min(6, max(4, length // 2)))]


def normalize_prefix(prefix: str, answer: str) -> str:
    clean = re.sub(r"[^A-Za-z'-]", "", str(prefix or "")).lower()
    answer_lower = answer.lower()
    if 1 <= len(clean) < len(answer) and answer_lower.startswith(clean):
        return answer[: len(clean)]
    return fallback_prefix(answer)


def target_text(prefix: str, missing_count: int) -> str:
    blanks = " ".join("_" for _ in range(max(1, missing_count)))
    return f"{prefix} {blanks}"


def mask_sentence(sentence: str, answer: str, visible_prefix: str) -> dict[str, Any]:
    prefix = normalize_prefix(visible_prefix, answer)
    pattern = word_pattern(answer)

    match = pattern.search(sentence)
    if not match:
        loose = re.compile(rf"({re.escape(answer)})", re.IGNORECASE)
        match = loose.search(sentence)

    if not match:
        missing_count = max(1, len(answer) - len(prefix))
        return {
            "masked_sentence": f"{sentence}  [{target_text(prefix, missing_count)}]",
            "visible_prefix": prefix,
            "parts": [
                {"type": "text", "text": f"{sentence}  ["},
                {"type": "target", "prefix": prefix, "missing_count": missing_count},
                {"type": "text", "text": "]"},
            ],
        }

    actual = match.group(1)
    shown = actual[: len(prefix)]
    missing_count = max(1, len(actual) - len(shown))
    before = sentence[: match.start(1)]
    after = sentence[match.end(1) :]
    masked = f"{before}{target_text(shown, missing_count)}{after}"
    return {
        "masked_sentence": masked,
        "visible_prefix": prefix,
        "parts": [
            {"type": "text", "text": before},
            {"type": "target", "prefix": shown, "missing_count": missing_count},
            {"type": "text", "text": after},
        ],
    }


def normalize_answer(text: str) -> str:
    return re.sub(r"[^a-zA-Z'-]", "", text).lower()


def check_answer(answer: str, solution: str, visible_prefix: str) -> bool:
    normalized_answer = normalize_answer(answer)
    normalized_solution = normalize_answer(solution)
    if normalized_answer == normalized_solution:
        return True

    prefix = normalize_prefix(visible_prefix, solution).lower()
    suffix = normalized_solution[len(prefix) :]
    return bool(suffix) and normalized_answer == suffix
