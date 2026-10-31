from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import aiohttp
from bs4 import BeautifulSoup

from bondbot.config import Settings
from bondbot.db import Database

log = logging.getLogger(__name__)

DDG_URL = "https://html.duckduckgo.com/html/"
CACHE_PREFIX = "websearch:"

SOURCE_DOMAINS = {
    "smart-lab.ru": "smart-lab",
    "interfax.ru": "Интерфакс",
    "rbc.ru": "РБК",
    "kommersant.ru": "Коммерсантъ",
    "vedomosti.ru": "Ведомости",
    "banki.ru": "Banki.ru",
    "moex.com": "MOEX",
    "finam.ru": "Финам",
    "dohod.ru": "Dohod",
    "investfunds.ru": "Investfunds",
    "bondradar.pro": "БондРадар",
    "megabonds.ru": "MegaBonds",
    "e-disclosure.ru": "e-disclosure",
}


def _source_for(url: str) -> str:
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    for suffix, name in SOURCE_DOMAINS.items():
        if domain == suffix or domain.endswith("." + suffix):
            return name
    return domain or "web"


def _clean(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def _decode_ddg_link(href: str) -> str:
    if href.startswith("//duckduckgo.com/l/?"):
        query = parse_qs(urlparse("https:" + href).query)
        target = query.get("uddg", [""])[0]
        return unquote(target)
    if href.startswith("/l/?"):
        query = parse_qs(urlparse(href).query)
        return unquote(query.get("uddg", [""])[0])
    return href


def parse_ddg_html(html: str, limit: int = 8) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in soup.select(".result"):
        link = block.select_one(".result__a")
        if link is None:
            continue
        url = _decode_ddg_link(link.get("href") or "")
        if not url.startswith(("http://", "https://")):
            continue
        if "duckduckgo.com" in url:
            continue
        if url in seen:
            continue
        seen.add(url)
        snippet_el = block.select_one(".result__snippet")
        results.append(
            {
                "source": _source_for(url),
                "title": _clean(link.get_text(" ", strip=True))[:300],
                "url": url,
                "snippet": _clean(snippet_el.get_text(" ", strip=True) if snippet_el else "")[:600],
                "published_at": None,
                "live": True,
            }
        )
        if len(results) >= max(1, min(limit, 15)):
            break
    return results


async def live_search(
    settings: Settings,
    db: Database,
    query: str,
    *,
    limit: int = 6,
    ttl_hours: int = 6,
) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not settings.live_search_enabled or len(query) < 2:
        return []
    cache_key = CACHE_PREFIX + hashlib.sha1(query.lower().encode("utf-8")).hexdigest()
    raw = db.kv_get(cache_key)
    if raw:
        try:
            cached = json.loads(raw)
            fetched = datetime.fromisoformat(cached.get("fetched_at", ""))
            if datetime.now(timezone.utc) - fetched < timedelta(hours=ttl_hours):
                return list(cached.get("results") or [])[:limit]
        except (ValueError, TypeError, json.JSONDecodeError):
            pass

    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }
    params = {"q": query, "kl": "ru-ru"}
    try:
        timeout = aiohttp.ClientTimeout(total=settings.live_search_timeout)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(DDG_URL, params=params) as response:
                if response.status >= 400:
                    log.warning("live search HTTP %s for %s", response.status, query)
                    return []
                html = await response.text()
        results = parse_ddg_html(html, limit=limit)
    except Exception as exc:
        log.warning("live search failed for %s: %s", query, exc)
        return []

    if results:
        db.kv_set(
            cache_key,
            json.dumps(
                {
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "results": results,
                },
                ensure_ascii=False,
            ),
        )
    return results


__all__ = ["live_search", "parse_ddg_html"]
