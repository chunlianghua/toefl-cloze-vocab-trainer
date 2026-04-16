from __future__ import annotations

from contextlib import contextmanager
import random
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Iterator

from .config import DB_PATH, DATA_DIR
from .errors import AppError
from .utils import check_answer, mask_sentence, normalize_prefix


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    conn = connect_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word_key TEXT NOT NULL UNIQUE,
                display_word TEXT NOT NULL,
                chinese_meaning TEXT NOT NULL,
                proficiency INTEGER NOT NULL DEFAULT 0,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS examples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word_id INTEGER NOT NULL,
                sentence TEXT NOT NULL,
                visible_prefix TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE,
                UNIQUE (word_id, sentence)
            );

            CREATE INDEX IF NOT EXISTS idx_words_updated_at ON words(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_examples_word_id ON examples(word_id);
            """
        )
        word_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(words)").fetchall()
        }
        if "proficiency" not in word_columns:
            conn.execute(
                "ALTER TABLE words ADD COLUMN proficiency INTEGER NOT NULL DEFAULT 0"
            )
        conn.execute(
            """
            UPDATE words
            SET proficiency = CASE
                WHEN proficiency < 0 THEN 0
                WHEN proficiency > 10 THEN 10
                ELSE proficiency
            END
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_words_proficiency ON words(proficiency ASC)"
        )

        example_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(examples)").fetchall()
        }
        if "visible_prefix" not in example_columns:
            conn.execute(
                "ALTER TABLE examples ADD COLUMN visible_prefix TEXT NOT NULL DEFAULT ''"
            )


def save_generated_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    saved: list[dict[str, Any]] = []
    now = utc_now()
    with db_session() as conn:
        for item in items:
            word = item["word"].strip()
            key = word.lower()
            meaning = item["chinese_meaning"] or "（模型未返回中文含义）"
            model = item["model"]
            existing = conn.execute(
                "SELECT id, proficiency FROM words WHERE word_key = ?", (key,)
            ).fetchone()
            if existing:
                word_id = int(existing["id"])
                proficiency = int(existing["proficiency"])
                conn.execute(
                    """
                    UPDATE words
                    SET display_word = ?, chinese_meaning = ?, model = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (word, meaning, model, now, word_id),
                )
                conn.execute("DELETE FROM examples WHERE word_id = ?", (word_id,))
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO words (
                        word_key,
                        display_word,
                        chinese_meaning,
                        proficiency,
                        model,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, 0, ?, ?, ?)
                    """,
                    (key, word, meaning, model, now, now),
                )
                word_id = int(cursor.lastrowid)
                proficiency = 0

            for example in item["examples"]:
                prefix = normalize_prefix(example["visible_prefix"], word)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO examples
                        (word_id, sentence, visible_prefix, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (word_id, example["sentence"], prefix, now),
                )

            saved.append(
                {
                    "id": word_id,
                    "word": word,
                    "chinese_meaning": meaning,
                    "proficiency": proficiency,
                    "example_count": len(item["examples"]),
                    "model": model,
                    "updated_at": now,
                }
            )
    return saved


def get_counts() -> dict[str, int]:
    with db_session() as conn:
        word_count = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
        example_count = conn.execute("SELECT COUNT(*) FROM examples").fetchone()[0]
    return {"word_count": int(word_count), "example_count": int(example_count)}


def list_words() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT
                w.id,
                w.display_word AS word,
                w.chinese_meaning,
                w.proficiency,
                w.model,
                w.created_at,
                w.updated_at,
                COUNT(e.id) AS example_count
            FROM words w
            LEFT JOIN examples e ON e.word_id = w.id
            GROUP BY w.id
            ORDER BY w.updated_at DESC, w.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def start_practice(mode: str, n: int) -> dict[str, Any]:
    safe_n = max(1, min(int(n or 10), 200))
    if mode not in {"recent", "random", "weak"}:
        raise AppError(HTTPStatus.BAD_REQUEST, "练习模式必须是 recent、random 或 weak")

    order_clauses = {
        "recent": "w.updated_at DESC, w.id DESC",
        "random": "RANDOM()",
        "weak": "w.proficiency ASC, w.updated_at ASC, w.id ASC",
    }
    order_clause = order_clauses[mode]
    with db_session() as conn:
        words = conn.execute(
            f"""
            SELECT w.id, w.display_word AS word, w.chinese_meaning, w.proficiency
            FROM words w
            WHERE EXISTS (SELECT 1 FROM examples e WHERE e.word_id = w.id)
            ORDER BY {order_clause}
            LIMIT ?
            """,
            (safe_n,),
        ).fetchall()

        questions: list[dict[str, Any]] = []
        for row in words:
            example = conn.execute(
                """
                SELECT id, sentence, visible_prefix
                FROM examples
                WHERE word_id = ?
                ORDER BY RANDOM()
                LIMIT 1
                """,
                (row["id"],),
            ).fetchone()
            if not example:
                continue
            masked = mask_sentence(
                example["sentence"], row["word"], example["visible_prefix"]
            )
            questions.append(
                {
                    "example_id": int(example["id"]),
                    "masked_sentence": masked["masked_sentence"],
                    "visible_prefix": masked["visible_prefix"],
                    "proficiency": int(row["proficiency"]),
                    "parts": masked["parts"],
                }
            )

    random.shuffle(questions)
    return {"mode": mode, "requested": safe_n, "count": len(questions), "questions": questions}


def check_question(example_id: int, answer: str, visible_prefix: str) -> dict[str, Any]:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT
                e.sentence,
                e.visible_prefix,
                w.id AS word_id,
                w.display_word AS word,
                w.chinese_meaning,
                w.proficiency
            FROM examples e
            JOIN words w ON w.id = e.word_id
            WHERE e.id = ?
            """,
            (example_id,),
        ).fetchone()
        if not row:
            raise AppError(HTTPStatus.NOT_FOUND, "找不到这道题")

        prefix = visible_prefix or row["visible_prefix"]
        correct = check_answer(answer, row["word"], prefix)
        current = int(row["proficiency"])
        delta = 1 if correct else -5
        new_proficiency = min(10, max(0, current + delta))
        conn.execute(
            "UPDATE words SET proficiency = ? WHERE id = ?",
            (new_proficiency, int(row["word_id"])),
        )

    return {
        "correct": correct,
        "word": row["word"],
        "chinese_meaning": row["chinese_meaning"],
        "sentence": row["sentence"],
        "visible_prefix": normalize_prefix(prefix, row["word"]),
        "proficiency": new_proficiency,
    }


def delete_word(word_id: int) -> dict[str, Any]:
    with db_session() as conn:
        cursor = conn.execute("DELETE FROM words WHERE id = ?", (word_id,))
    if cursor.rowcount == 0:
        raise AppError(HTTPStatus.NOT_FOUND, "找不到这个单词")
    return {"deleted": True, "id": word_id}
