from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "vocab.sqlite3"

DEFAULT_PROTOCOL = os.environ.get("LLM_PROTOCOL", "openai").strip().lower()
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "qwen3.5-plus").strip()
DEFAULT_BASE_URL = os.environ.get(
    "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
).strip()
