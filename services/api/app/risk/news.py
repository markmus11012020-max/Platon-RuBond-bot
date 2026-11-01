from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

NEGATIVE_TERMS: dict[str, tuple[str, str]] = {
    "технический дефолт": ("critical", "технический дефолт"),
    "дефолт": ("critical", "дефолт"),
    "не исполнил": ("critical", "неисполнение обязательств"),
    "просроч": ("critical", "просрочка"),
    "реструктуризац": ("critical", "реструктуризация"),
    "банкрот": ("critical", "банкротство"),
    "отзыв лицензии": ("critical", "отзыв лицензии"),
    "приостановк": ("critical", "приостановка торгов"),
    "снизил рейтинг": ("warning", "снижение рейтинга"),
    "снижение рейтинга": ("warning", "снижение рейтинга"),
    "рейтинговое действие": ("warning", "рейтинговое действие"),
    "распродаж": ("warning", "аномальная распродажа"),
    "обвал": ("warning", "обвал цены"),
    "падение": ("warning", "падение цены"),
    "иск ": ("warning", "судебный иск"),
    "наруш": ("warning", "нарушение"),
}


@dataclass(slots=True)
class NewsFlag:
    severity: str
    term: str
    title: str
    source: str
    url: str
    published_at: str


def _tokens(isin: str, name: str, issuer: str) -> list[str]:
    text = f"{isin} {name} {issuer}".lower()
    result = {isin.lower()}
    for token in re.split(r"[^a-zA-Zа-яА-Я0-9]+", text):
        if len(token) >= 4 and token not in {
            "облигац",
            "выпуск",
            "бумага",
            "банк",
            "финанс",
        }:
            result.add(token)
    return list(result)


def scan_news(
    db_path: str,
    isin: str,
    name: str,
    issuer: str = "",
    *,
    days: int = 30,
    limit: int = 400,
) -> tuple[list[NewsFlag], str]:
    path = Path(db_path)
    if not path.exists():
        return [], "news database not found"
    cutoff = (date.today() - timedelta(days=max(1, days))).isoformat()
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT source, title, url, published_at, summary
                FROM news
                WHERE published_at IS NULL OR published_at >= ?
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (cutoff, max(1, limit)),
            ).fetchall()
        finally:
            connection.close()
    except Exception as exc:
        log.warning("news scan %s failed: %s", isin, exc)
        return [], str(exc)

    tokens = _tokens(isin, name, issuer)
    flags: list[NewsFlag] = []
    for row in rows:
        haystack = f"{row['title'] or ''} {row['summary'] or ''}".lower()
        if not any(token in haystack for token in tokens):
            continue
        for term, (severity, label) in NEGATIVE_TERMS.items():
            if term in haystack:
                flags.append(
                    NewsFlag(
                        severity=severity,
                        term=label,
                        title=str(row["title"] or ""),
                        source=str(row["source"] or ""),
                        url=str(row["url"] or ""),
                        published_at=str(row["published_at"] or ""),
                    )
                )
                break
    return flags[:20], ""


__all__ = ["NewsFlag", "scan_news"]
