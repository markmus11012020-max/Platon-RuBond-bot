"""
Кэш результатов tool-вызовов в SQLite с TTL (улучшение 3).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.agent.cache")

# TTL по умолчанию (секунды)
DEFAULT_TTL = {
    "get_bond_info_tool": 300,       # 5 мин — рыночные данные
    "analyze_bond_finance_tool": 300,
    "search_bond_news_tool": 600,    # 10 мин — новости
    "get_key_rate_tool": 3600,       # 1 час — ставка ЦБ
}


class ToolCache:
    """SQLite TTL-кэш для результатов инструментов агента."""

    def __init__(self, db_path: str = "tool_cache.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_cache (
                cache_key   TEXT PRIMARY KEY,
                tool_name   TEXT NOT NULL,
                value       TEXT NOT NULL,
                created_at  REAL NOT NULL,
                expires_at  REAL NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expires ON tool_cache(expires_at)"
        )
        self._conn.commit()

    @staticmethod
    def make_key(tool_name: str, **kwargs: Any) -> str:
        payload = json.dumps({"tool": tool_name, **kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, tool_name: str, **kwargs: Any) -> Optional[str]:
        key = self.make_key(tool_name, **kwargs)
        row = self._conn.execute(
            "SELECT value, expires_at FROM tool_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if not row:
            return None
        value, expires_at = row
        if time.time() > expires_at:
            self._conn.execute("DELETE FROM tool_cache WHERE cache_key = ?", (key,))
            self._conn.commit()
            return None
        logger.debug("cache HIT %s", tool_name)
        return value

    def set(
        self,
        tool_name: str,
        value: str,
        ttl: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        key = self.make_key(tool_name, **kwargs)
        ttl_sec = ttl if ttl is not None else DEFAULT_TTL.get(tool_name, 300)
        now = time.time()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO tool_cache (cache_key, tool_name, value, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key, tool_name, value, now, now + ttl_sec),
        )
        self._conn.commit()
        logger.debug("cache SET %s ttl=%s", tool_name, ttl_sec)

    def invalidate(self, tool_name: Optional[str] = None) -> int:
        if tool_name:
            cur = self._conn.execute(
                "DELETE FROM tool_cache WHERE tool_name = ?", (tool_name,)
            )
        else:
            cur = self._conn.execute("DELETE FROM tool_cache")
        self._conn.commit()
        return cur.rowcount

    def cleanup_expired(self) -> int:
        cur = self._conn.execute(
            "DELETE FROM tool_cache WHERE expires_at < ?", (time.time(),)
        )
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()


# Глобальный синглтон
_cache: Optional[ToolCache] = None


def get_tool_cache(db_path: str = "tool_cache.db") -> ToolCache:
    global _cache
    if _cache is None:
        _cache = ToolCache(db_path=db_path)
    return _cache
