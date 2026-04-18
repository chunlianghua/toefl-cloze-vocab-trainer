from __future__ import annotations

import json
import mimetypes
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from .config import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_PROTOCOL, STATIC_DIR
from .errors import AppError
from .llm import build_request_config, generate_words
from .store import (
    check_question,
    delete_word,
    get_counts,
    list_words,
    save_generated_items,
    start_practice,
)
from .utils import parse_word_input


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length).decode("utf-8") if length else "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(HTTPStatus.BAD_REQUEST, "请求体不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise AppError(HTTPStatus.BAD_REQUEST, "请求体 JSON 顶层必须是对象")
    return data


class VocabHandler(BaseHTTPRequestHandler):
    server_version = "TOEFLVocab/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.client_address[0], self.log_date_time_string(), format % args)
        )

    def send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, error: AppError) -> None:
        payload = {"error": error.message}
        if error.details:
            payload["details"] = error.details
        self.send_json(payload, error.status)

    def do_GET(self) -> None:
        try:
            if self.path == "/" or self.path.startswith("/?"):
                self.serve_static(STATIC_DIR / "index.html")
                return
            if self.path.startswith("/static/"):
                relative = self.path.split("?", 1)[0].removeprefix("/static/")
                target = (STATIC_DIR / relative).resolve()
                target.relative_to(STATIC_DIR.resolve())
                self.serve_static(target)
                return
            if self.path.startswith("/api/status"):
                self.send_json(
                    {
                        "default_protocol": DEFAULT_PROTOCOL,
                        "default_model": DEFAULT_MODEL,
                        "default_base_url": DEFAULT_BASE_URL,
                        "supported_protocols": ["openai", "genai", "anthropic"],
                        **get_counts(),
                    }
                )
                return
            if self.path.startswith("/api/words"):
                self.send_json({"words": list_words()})
                return
            raise AppError(HTTPStatus.NOT_FOUND, "找不到页面或接口")
        except ValueError as exc:
            self.send_error_json(AppError(HTTPStatus.FORBIDDEN, "静态文件路径不合法", str(exc)))
        except AppError as exc:
            self.send_error_json(exc)
        except Exception as exc:  # pragma: no cover
            self.send_error_json(AppError(HTTPStatus.INTERNAL_SERVER_ERROR, "服务器内部错误", str(exc)))

    def do_POST(self) -> None:
        try:
            if self.path == "/api/generate":
                data = read_json_body(self)
                words = parse_word_input(str(data.get("words", "")))
                if not words:
                    raise AppError(HTTPStatus.BAD_REQUEST, "请输入至少一个单词")
                request_config = build_request_config(data)
                generated, skipped = generate_words(words, request_config)
                self.send_json(
                    {
                        "saved": save_generated_items(generated),
                        "skipped": skipped,
                        **get_counts(),
                    }
                )
                return

            if self.path == "/api/practice/start":
                data = read_json_body(self)
                self.send_json(
                    start_practice(str(data.get("mode") or "recent"), int(data.get("n") or 10))
                )
                return

            if self.path == "/api/practice/check":
                data = read_json_body(self)
                self.send_json(
                    check_question(
                        int(data.get("example_id")),
                        str(data.get("answer") or ""),
                        str(data.get("visible_prefix") or ""),
                    )
                )
                return

            raise AppError(HTTPStatus.NOT_FOUND, "找不到接口")
        except AppError as exc:
            self.send_error_json(exc)
        except Exception as exc:  # pragma: no cover
            self.send_error_json(AppError(HTTPStatus.INTERNAL_SERVER_ERROR, "服务器内部错误", str(exc)))

    def do_DELETE(self) -> None:
        try:
            match = re.fullmatch(r"/api/words/(\d+)", self.path.split("?", 1)[0])
            if not match:
                raise AppError(HTTPStatus.NOT_FOUND, "找不到接口")
            self.send_json(delete_word(int(match.group(1))))
        except AppError as exc:
            self.send_error_json(exc)
        except Exception as exc:  # pragma: no cover
            self.send_error_json(AppError(HTTPStatus.INTERNAL_SERVER_ERROR, "服务器内部错误", str(exc)))

    def serve_static(self, target: Path) -> None:
        if not target.exists() or not target.is_file():
            raise AppError(HTTPStatus.NOT_FOUND, "找不到静态文件")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
