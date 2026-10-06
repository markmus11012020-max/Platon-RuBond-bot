"""
Хронологическая память сессий диалога в SQLite (history.db).

Совместима с LangChain BaseChatMessageHistory-паттерном.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.memory.sql")


class SQLiteHistoryManager:
    """Управление историей диалогов агента в SQLite."""

    def __init__(self, db_path: str = "history.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session ON chat_history(session_id)"
        )
        self._conn.commit()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Добавление сообщения в историю сессии (role: human|ai|system|tool)."""
        self._conn.execute(
            "INSERT INTO chat_history (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def get_history(self, session_id: str, limit: int = 50) -> List[Dict[str, str]]:
        """Получение истории диалога (от старых к новым)."""
        rows = self._conn.execute(
            """
            SELECT role, content, created_at FROM chat_history
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [
            {"role": r["role"], "content": r["content"], "created_at": r["created_at"]}
            for r in rows
        ]

    def clear_session(self, session_id: str) -> None:
        self._conn.execute(
            "DELETE FROM chat_history WHERE session_id = ?", (session_id,)
        )
        self._conn.commit()

    def get_langchain_messages(self, session_id: str, limit: int = 20) -> list:
        """
        Преобразует историю в объекты LangChain BaseMessage (если langchain установлен).
        Иначе возвращает список dict.
        """
        history = self.get_history(session_id, limit=limit)
        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

            mapping = {
                "human": HumanMessage,
                "user": HumanMessage,
                "ai": AIMessage,
                "assistant": AIMessage,
                "system": SystemMessage,
            }
            messages = []
            for h in history:
                cls = mapping.get(h["role"].lower())
                if cls:
                    messages.append(cls(content=h["content"]))
            return messages
        except ImportError:
            return history

    def close(self) -> None:
        self._conn.close()


class SessionChatHistory:
    """
    Адаптер под интерфейс LangChain chat history для одной сессии.
    Использование:
        history = SessionChatHistory(manager, session_id="user-1")
        history.add_user_message("...")
        history.messages  # list of BaseMessage
    """

    def __init__(self, manager: SQLiteHistoryManager, session_id: str) -> None:
        self.manager = manager
        self.session_id = session_id

    def add_user_message(self, content: str) -> None:
        self.manager.add_message(self.session_id, "human", content)

    def add_ai_message(self, content: str) -> None:
        self.manager.add_message(self.session_id, "ai", content)

    def add_message(self, role: str, content: str) -> None:
        self.manager.add_message(self.session_id, role, content)

    @property
    def messages(self) -> list:
        return self.manager.get_langchain_messages(self.session_id)

    def clear(self) -> None:
        self.manager.clear_session(self.session_id)
