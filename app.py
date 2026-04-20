from __future__ import annotations

import argparse
import time
from http.server import ThreadingHTTPServer

from toefl_vocab.config import (
    DB_PATH,
    DEFAULT_API_KEY,
    DEFAULT_API_KEY_ENV,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_PROTOCOL,
)
from toefl_vocab.server import VocabHandler
from toefl_vocab.store import init_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地托福填词记单词网页")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> None:
    init_db()
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), VocabHandler)
    server.daemon_threads = True
    print(f"TOEFL vocab trainer: http://{args.host}:{args.port}")
    print(f"Database: {DB_PATH}")
    print(f"Default protocol: {DEFAULT_PROTOCOL}")
    print(f"Default model: {DEFAULT_MODEL}")
    print(f"Default base URL: {DEFAULT_BASE_URL or '(provider default)'}")
    print(
        f"Default API key: {DEFAULT_API_KEY_ENV} "
        f"({'ok' if DEFAULT_API_KEY else 'missing'})"
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
        time.sleep(0.1)


if __name__ == "__main__":
    main()
