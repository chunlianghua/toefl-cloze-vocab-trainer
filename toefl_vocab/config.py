from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "vocab.sqlite3"

ALIYUN_API_KEY_ENV = "ALIYUN_API_KEY"
ALIYUN_BASE_URL = os.environ.get(
    "ALIYUN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
).rstrip("/")
DEFAULT_MODEL = os.environ.get("ALIYUN_MODEL", "qwen3.5-plus")
