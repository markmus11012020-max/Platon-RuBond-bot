from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from bondbot.config import Settings
from bondbot.db import Database
from bondbot.models import utcnow

log = logging.getLogger(__name__)

CBR_KEY_RATE_URL = "https://www.cbr.ru/hd_base/KeyRate/"
CACHE_KEY = "cbr_key_rate"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = value.replace("\xa0", " ").replace("%", "").replace(" ", "").replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class KeyRateSnapshot:
    value_pct: float
    as_of: date
    source_url: str = CBR_KEY_RATE_URL
    fetched_at: datetime = field(default_factory=utcnow)
    stale: bool = False

    def to_json(self) -> str:
        return json.dumps(
            {
                "value_pct": self.value_pct,
                "as_of": self.as_of.isoformat(),
                "source_url": self.source_url,
                "fetched_at": self.fetched_at.isoformat(),
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> "KeyRateSnapshot | None":
        try:
            data: dict[str, Any] = json.loads(raw)
            fetched_at = datetime.fromisoformat(str(data["fetched_at"]))
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            return cls(
                value_pct=float(data["value_pct"]),
                as_of=date.fromisoformat(str(data["as_of"])),
                source_url=str(data.get("source_url") or CBR_KEY_RATE_URL),
                fetched_at=fetched_at,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None


def parse_key_rate(html: str, source_url: str = CBR_KEY_RATE_URL) -> KeyRateSnapshot | None:
    """Parse the latest key rate from the CBR KeyRate HTML table."""
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    candidates: list[tuple[date, float]] = []

    for table in soup.find_all("table"):
        headers = [
            cell.get_text(" ", strip=True).lower()
            for cell in table.find_all(["th", "td"])[:2]
        ]
        if not any("дата" in header for header in headers):
            continue
        if not any("ставка" in header for header in headers):
            continue
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            row_date = _parse_date(cells[0].get_text(" ", strip=True))
            row_rate = _parse_float(cells[1].get_text(" ", strip=True))
            if row_date is None or row_rate is None:
                continue
            if 0.0 < row_rate <= 100.0:
                candidates.append((row_date, row_rate))

    if not candidates:
        return None

    latest_date, latest_rate = max(candidates, key=lambda item: item[0])
    return KeyRateSnapshot(value_pct=latest_rate, as_of=latest_date, source_url=source_url)


class CbrKeyRateClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "CbrKeyRateClient":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.settings.key_rate_timeout),
            headers={
                "User-Agent": self.settings.user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._session is not None:
            await self._session.close()

    async def fetch(self) -> KeyRateSnapshot:
        if self._session is None:
            raise RuntimeError("client is not started")
        async with self._session.get(self.settings.key_rate_url) as response:
            if response.status >= 400:
                raise RuntimeError(f"CBR HTTP {response.status}")
            html = await response.text()
        snapshot = parse_key_rate(html, self.settings.key_rate_url)
        if snapshot is None:
            raise ValueError("CBR key rate table not found")
        log.info("CBR key rate: %.2f%% as of %s", snapshot.value_pct, snapshot.as_of)
        return snapshot


class KeyRateService:
    """Fetch the CBR key rate with a SQLite-backed TTL cache."""

    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db

    def cached(self) -> KeyRateSnapshot | None:
        raw = self.db.kv_get(CACHE_KEY)
        return KeyRateSnapshot.from_json(raw) if raw else None

    def _is_fresh(self, snapshot: KeyRateSnapshot) -> bool:
        ttl = timedelta(hours=max(0, self.settings.key_rate_ttl_hours))
        if ttl <= timedelta(0):
            return False
        return utcnow() - snapshot.fetched_at < ttl

    def _save(self, snapshot: KeyRateSnapshot) -> None:
        self.db.kv_set(CACHE_KEY, snapshot.to_json())

    async def get(self) -> KeyRateSnapshot:
        cached = self.cached()
        if cached is not None and self._is_fresh(cached):
            return cached

        try:
            async with CbrKeyRateClient(self.settings) as client:
                fresh = await client.fetch()
        except Exception as exc:
            log.warning("CBR key rate unavailable: %s", exc)
            if cached is not None:
                return replace(cached, stale=True)
            raise

        self._save(fresh)
        return fresh
