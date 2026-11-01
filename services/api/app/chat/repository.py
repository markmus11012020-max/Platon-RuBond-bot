from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    state_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
    ON chat_messages(session_id, id);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChatRepository:
    def __init__(self, path: str, ttl_minutes: int = 120) -> None:
        self.path = Path(path)
        self.ttl_minutes = max(5, ttl_minutes)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _expires(self) -> str:
        return (_now() + timedelta(minutes=self.ttl_minutes)).isoformat()

    def cleanup(self) -> None:
        cutoff = _now().isoformat()
        with self._connect() as connection:
            expired = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM chat_sessions WHERE expires_at <= ?", (cutoff,)
                ).fetchall()
            ]
            if not expired:
                return
            placeholders = ",".join("?" for _ in expired)
            connection.execute(
                f"DELETE FROM chat_messages WHERE session_id IN ({placeholders})",
                expired,
            )
            connection.execute(
                f"DELETE FROM chat_sessions WHERE id IN ({placeholders})",
                expired,
            )

    def create_session(self, user_id: str = "") -> dict[str, Any]:
        self.cleanup()
        session_id = secrets.token_urlsafe(32)
        now = _now().isoformat()
        expires = self._expires()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_sessions
                (id, user_id, created_at, updated_at, expires_at, state_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, user_id, now, now, expires, "{}"),
            )
        return {
            "session_id": session_id,
            "messages": [],
            "state": {},
            "expires_at": expires,
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        self.cleanup()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not row:
                return None
            messages = connection.execute(
                """
                SELECT role, content FROM chat_messages
                WHERE session_id = ? ORDER BY id
                """,
                (session_id,),
            ).fetchall()
        try:
            state = json.loads(row["state_json"] or "{}")
        except json.JSONDecodeError:
            state = {}
        return {
            "session_id": row["id"],
            "messages": [dict(item) for item in messages],
            "state": state,
            "expires_at": row["expires_at"],
        }

    def append_message(self, session_id: str, role: str, content: str) -> None:
        now = _now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, now),
            )
            connection.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?, expires_at = ?
                WHERE id = ?
                """,
                (now, self._expires(), session_id),
            )
        self._trim(session_id)

    def append_many(self, session_id: str, messages: list[dict[str, str]]) -> None:
        for message in messages[-20:]:
            role = str(message.get("role") or "")
            content = str(message.get("content") or "")
            if role in {"user", "assistant"} and content:
                self.append_message(session_id, role, content)

    def _trim(self, session_id: str, keep: int = 40) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM chat_messages
                WHERE session_id = ? AND id NOT IN (
                    SELECT id FROM chat_messages
                    WHERE session_id = ?
                    ORDER BY id DESC LIMIT ?
                )
                """,
                (session_id, session_id, keep),
            )

    def update_state(self, session_id: str, state: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE chat_sessions SET state_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(state, ensure_ascii=False), _now().isoformat(), session_id),
            )

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE session_id = ?", (session_id,)
            )
            cursor = connection.execute(
                "DELETE FROM chat_sessions WHERE id = ?", (session_id,)
            )
        return cursor.rowcount > 0


__all__ = ["ChatRepository"]
