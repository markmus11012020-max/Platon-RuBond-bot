from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import aiohttp
import feedparser
from bs4 import BeautifulSoup

from bondbot.config import Settings
from bondbot.db import Database
from bondbot.models import Bond, to_msk, utcnow

log = logging.getLogger(__name__)

DEFAULT_FEEDS = {
    "Интерфакс": "https://www.interfax.ru/rss.asp",
    "РБК": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "Коммерсантъ": "https://www.kommersant.ru/RSS/news.xml",
    "Ведомости": "https://www.vedomosti.ru/rss/news",
    "Banki.ru": "https://www.banki.ru/xml/news.rss",
    "smart-lab": "https://smart-lab.ru/rss/",
}

KEYWORDS = {
    "ключевая ставка": 4,
    "ставка цб": 4,
    "инфляция": 3,
    "офз": 3,
    "облигац": 2,
    "рейтинг": 3,
    "дефолт": 5,
    "оферта": 3,
    "купон": 2,
    "эмитент": 2,
    "доходность": 1,
    "размещ": 2,
}


@dataclass(frozen=True, slots=True)
class NewsResult:
    feeds: int
    fetched: int
    saved: int
    errors: tuple[str, ...] = ()


def configured_feeds(settings: Settings) -> dict[str, str]:
    raw = (settings.news_feeds or "").strip()
    if not raw:
        return dict(DEFAULT_FEEDS)
    feeds: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            name, _, url = part.partition("=")
            feeds[name.strip() or urlparse(url).netloc] = url.strip()
        else:
            feeds[urlparse(part).netloc or part] = part
    return feeds or dict(DEFAULT_FEEDS)


def _parse_published(entry: Any) -> str:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    return utcnow().isoformat()


def _clean_html(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", BeautifulSoup(value, "lxml").get_text(" ", strip=True)).strip()


def parse_feed(raw: bytes | str, source: str) -> list[dict[str, Any]]:
    parsed = feedparser.parse(raw)
    items: list[dict[str, Any]] = []
    for entry in parsed.entries:
        title = _clean_html(entry.get("title"))
        if not title:
            continue
        url = str(entry.get("link") or "").strip()
        summary = _clean_html(entry.get("summary") or entry.get("description"))
        published_at = _parse_published(entry)
        key = url or f"{source}:{title}"
        items.append(
            {
                "source": source,
                "title": title[:500],
                "url": url,
                "published_at": published_at,
                "summary": summary[:2000],
                "hash": hashlib.sha1(key.encode("utf-8")).hexdigest(),
            }
        )
    return items


def enrich_news(
    items: list[dict[str, Any]],
    bonds: list[Bond],
    position_isins: set[str],
    watch_isins: set[str],
) -> list[dict[str, Any]]:
    for item in items:
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        entities: list[str] = []
        for bond in bonds:
            if bond.isin.lower() in text or (
                len(bond.name) >= 6 and bond.name.lower() in text
            ):
                entities.append(bond.isin)
                if len(entities) >= 20:
                    break
        relevance = 0
        if set(entities) & (position_isins | watch_isins):
            relevance = 3
        elif entities:
            relevance = 2
        elif any(keyword in text for keyword in KEYWORDS):
            relevance = 1
        keyword_score = sum(weight for keyword, weight in KEYWORDS.items() if keyword in text)
        item["entities"] = entities
        item["relevance"] = relevance
        item["importance"] = relevance * 10 + min(10, keyword_score)
    return items


async def _fetch_feed(
    session: aiohttp.ClientSession,
    source: str,
    url: str,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        async with session.get(url) as response:
            if response.status >= 400:
                return [], f"{source}: HTTP {response.status}"
            raw = await response.read()
        return parse_feed(raw, source), None
    except Exception as exc:
        log.warning("news feed %s failed: %s", source, exc)
        return [], f"{source}: {exc}"


async def refresh_news(settings: Settings, db: Database) -> NewsResult:
    if not settings.news_enabled:
        return NewsResult(feeds=0, fetched=0, saved=0, errors=("news disabled",))
    feeds = configured_feeds(settings)
    bonds = db.list_bonds()
    position_isins = {position.isin for position in db.positions()}
    watch_isins = {str(row["isin"]) for row in db.watchlist()}
    all_items: list[dict[str, Any]] = []
    errors: list[str] = []

    timeout = aiohttp.ClientTimeout(total=settings.request_timeout)
    async with aiohttp.ClientSession(
        timeout=timeout,
        headers={
            "User-Agent": settings.user_agent,
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9",
        },
    ) as session:
        tasks = [
            _fetch_feed(session, source, url)
            for source, url in feeds.items()
        ]
        results = await asyncio.gather(*tasks)
    for items, error in results:
        all_items.extend(items)
        if error:
            errors.append(error)

    enrich_news(all_items, bonds, position_isins, watch_isins)
    saved = db.save_news(all_items)
    db.kv_set("last_news_refresh", utcnow().isoformat())
    log.info("news refreshed: feeds=%s fetched=%s saved=%s errors=%s", len(feeds), len(all_items), saved, len(errors))
    return NewsResult(feeds=len(feeds), fetched=len(all_items), saved=saved, errors=tuple(errors))


def build_news_digest(
    settings: Settings,
    db: Database,
    *,
    isin: str | None = None,
    limit: int = 5,
) -> str:
    items = db.recent_news(hours=settings.news_hours, limit=60)
    if isin:
        target = isin.upper()
        items = [item for item in items if target in (item.get("entities") or [])]
    items = items[:limit]
    if not items:
        suffix = f" по {isin.upper()}" if isin else ""
        return f"📰 За последние {settings.news_hours} ч новостей{suffix} не найдено."

    bonds = {bond.isin: bond for bond in db.list_bonds()}
    positions = {position.isin for position in db.positions()}
    watch = {str(row["isin"]) for row in db.watchlist()}
    lines = [f"📰 Новости за {settings.news_hours} ч", ""]
    for index, item in enumerate(items, start=1):
        published = item.get("published_at")
        try:
            stamp = to_msk(datetime.fromisoformat(published)) if published else None
        except ValueError:
            stamp = None
        lines.append(f"{index}. {item['title']}")
        lines.append(f"   {item['source']} · {stamp:%d.%m %H:%M}" if stamp else f"   {item['source']}")
        entities = item.get("entities") or []
        if entities:
            names = ", ".join(
                f"{bonds[entity].name} ({entity})" if entity in bonds else entity
                for entity in entities[:3]
            )
            relation = "портфель" if set(entities) & positions else "наблюдение" if set(entities) & watch else "рынок"
            lines.append(f"   Касается: {names} · {relation}")
        if item.get("url"):
            lines.append(f"   {item['url']}")
        lines.append("")
    lines.append("Это подборка источников, не инвестиционная рекомендация.")
    return "\n".join(lines).strip()


__all__ = [
    "DEFAULT_FEEDS",
    "NewsResult",
    "build_news_digest",
    "configured_feeds",
    "enrich_news",
    "parse_feed",
    "refresh_news",
]
