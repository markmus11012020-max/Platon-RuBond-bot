"""
Оценка качества RAG: логирование score + user feedback (улучшение 6).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.rag_quality")


class RAGQualityTracker:
    """
    Сохраняет результаты similarity_search и пользовательский feedback.
    Позволяет выявлять низкорелевантные чанки и планировать re-embed.
    """

    def __init__(self, db_path: str = "rag_quality.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rag_queries (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                query      TEXT NOT NULL,
                top_k      INTEGER,
                avg_score  REAL,
                min_score  REAL,
                hit_count  INT,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rag_hits (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id   INTEGER NOT NULL,
                text_preview TEXT,
                score      REAL,
                metadata   TEXT,
                FOREIGN KEY(query_id) REFERENCES rag_queries(id)
            );
            CREATE TABLE IF NOT EXISTS rag_feedback (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id   INTEGER,
                hit_id     INTEGER,
                rating     INTEGER NOT NULL,  -- 1..5 или -1/+1
                comment    TEXT,
                created_at REAL NOT NULL
            );
            """
        )
        self._conn.commit()

    def log_search(
        self,
        query: str,
        hits: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> int:
        """Логирует поисковый запрос и hits. Возвращает query_id."""
        scores = [h.get("score") for h in hits if h.get("score") is not None]
        avg_s = sum(scores) / len(scores) if scores else None
        min_s = min(scores) if scores else None
        cur = self._conn.execute(
            """
            INSERT INTO rag_queries (query, top_k, avg_score, min_score, hit_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (query, top_k, avg_s, min_s, len(hits), time.time()),
        )
        query_id = cur.lastrowid
        for h in hits:
            self._conn.execute(
                """
                INSERT INTO rag_hits (query_id, text_preview, score, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (
                    query_id,
                    (h.get("text") or "")[:500],
                    h.get("score"),
                    json.dumps(h.get("metadata") or {}, ensure_ascii=False, default=str),
                ),
            )
        self._conn.commit()
        if avg_s is not None and avg_s < 0.3:
            logger.warning(
                "RAG low relevance: query=%r avg_score=%.3f hits=%d",
                query[:80],
                avg_s,
                len(hits),
            )
        return int(query_id)

    def add_feedback(
        self,
        query_id: int,
        rating: int,
        hit_id: Optional[int] = None,
        comment: str = "",
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO rag_feedback (query_id, hit_id, rating, comment, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (query_id, hit_id, rating, comment, time.time()),
        )
        self._conn.commit()
        logger.info("RAG feedback query_id=%s rating=%s", query_id, rating)

    def low_score_queries(self, threshold: float = 0.35, limit: int = 20) -> List[Dict]:
        rows = self._conn.execute(
            """
            SELECT id, query, avg_score, hit_count, created_at
            FROM rag_queries
            WHERE avg_score IS NOT NULL AND avg_score < ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (threshold, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        row = self._conn.execute(
            """
            SELECT COUNT(*) as n, AVG(avg_score) as avg_s, MIN(avg_score) as min_s
            FROM rag_queries WHERE avg_score IS NOT NULL
            """
        ).fetchone()
        fb = self._conn.execute("SELECT COUNT(*) FROM rag_feedback").fetchone()[0]
        return {
            "queries": row["n"] or 0,
            "avg_score": round(row["avg_s"], 4) if row["avg_s"] is not None else None,
            "min_score": round(row["min_s"], 4) if row["min_s"] is not None else None,
            "feedback_count": fb,
        }

    def close(self) -> None:
        self._conn.close()


_tracker: Optional[RAGQualityTracker] = None


def get_rag_tracker(db_path: str = "rag_quality.db") -> RAGQualityTracker:
    global _tracker
    if _tracker is None:
        _tracker = RAGQualityTracker(db_path=db_path)
    return _tracker
