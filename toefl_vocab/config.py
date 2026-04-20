from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "vocab.sqlite3"

DEFAULT_API_KEY_ENV = "AIHUBMIX_API_KEY"
DEFAULT_PROTOCOL = os.environ.get("LLM_PROTOCOL", "genai").strip().lower()
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gemini-3-flash-preview-free").strip()
DEFAULT_BASE_URL = os.environ.get("LLM_BASE_URL", "https://aihubmix.com/v1").strip()
DEFAULT_API_KEY = os.environ.get(DEFAULT_API_KEY_ENV, "").strip()
