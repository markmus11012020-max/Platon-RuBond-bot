from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.config import Settings
from app.demo import DEMO_FREELANCE_ORDERS
from app.schemas import FreelanceOrder, FreelanceResponse


def _load_json_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if not raw:
        return []
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _from_demo() -> FreelanceResponse:
    orders = [
        FreelanceOrder(
            id=item["id"],
            title=item["title"],
            source=item["source"],
            budget_text=item["budget_text"],
            score=item["score"],
            url=item["url"],
            published_at=item.get("published_at"),
            category=item.get("category", ""),
            matched_keywords=item.get("matched_keywords", []),
            red_flags=item.get("red_flags", []),
        )
        for item in DEMO_FREELANCE_ORDERS
    ]
    return FreelanceResponse(
        orders=orders,
        summary={
            "count": len(orders),
            "top_score": max((item.score for item in orders), default=0),
            "source": "demo",
        },
    )


def _from_sqlite(path: str, limit: int = 20) -> FreelanceResponse:
    connection = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT id, title, source, budget_text, score, url, published_at,
                   category, matched_keywords, red_flags
            FROM orders
            ORDER BY score DESC, published_at DESC
            LIMIT ?
            """,
            (max(1, min(limit, 50)),),
        ).fetchall()
    finally:
        connection.close()

    orders = [
        FreelanceOrder(
            id=int(row["id"]),
            title=str(row["title"] or ""),
            source=str(row["source"] or ""),
            budget_text=str(row["budget_text"] or ""),
            score=int(row["score"] or 0),
            url=str(row["url"] or ""),
            published_at=str(row["published_at"]) if row["published_at"] else None,
            category=str(row["category"] or ""),
            matched_keywords=_load_json_list(row["matched_keywords"]),
            red_flags=_load_json_list(row["red_flags"]),
        )
        for row in rows
    ]
    return FreelanceResponse(
        orders=orders,
        summary={
            "count": len(orders),
            "top_score": max((item.score for item in orders), default=0),
            "source": "sqlite",
        },
    )


def build_freelance_feed(settings: Settings, limit: int = 20) -> FreelanceResponse:
    if settings.freelance_db_available:
        try:
            return _from_sqlite(settings.freelance_db_path, limit=limit)
        except Exception:
            pass
    return _from_demo()


__all__ = ["build_freelance_feed"]
