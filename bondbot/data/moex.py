from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import aiohttp

from bondbot.config import Settings
from bondbot.data.quality import sanitize_bond
from bondbot.models import Bond, utcnow

log = logging.getLogger(__name__)

BOND_BOARDS = {"TQCB", "TQOB", "TQIR", "TQOD", "TQOY"}
RUBLE_UNITS = {"SUR", "RUB"}


def _rows(block: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not block:
        return []
    columns = block.get("columns") or []
    return [dict(zip(columns, row)) for row in block.get("data") or []]


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text or text.startswith("0000-00-00"):
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", "-"):
            return value
    return None


def _first_positive(*values: Any) -> float | None:
    for value in values:
        number = _number(value)
        if number is not None and number > 0:
            return number
    return None


def _normalize_coupon_freq(value: float | None) -> float | None:
    if value is None:
        return None
    for common in (1, 2, 4, 6, 12):
        if abs(value - common) <= 0.5:
            return float(common)
    return value


def _coupon_type(row: dict[str, Any]) -> str | None:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("COUPON_DETAILS", "BONDTYPE", "BONDSUBTYPE")
    ).lower()
    if "структур" in text:
        return "structured"
    if "фиксирован" in text or "постоян" in text:
        return "fixed"
    if any(
        marker in text
        for marker in ("плава", "перемен", "ключев", "ruonia", "ипц", "индекс")
    ):
        return "floating"
    return None


def _parse_row(
    row: dict[str, Any],
    market: dict[str, Any],
) -> Bond | None:
    isin = str(_first(row.get("ISIN"), row.get("SECID")) or "").strip().upper()
    if not isin:
        return None
    if str(row.get("BOARDID") or "") not in BOND_BOARDS:
        return None
    face_unit = str(row.get("FACEUNIT") or "").upper()
    if face_unit and face_unit not in RUBLE_UNITS:
        return None

    face_value = _number(row.get("FACEVALUE"))
    if face_value is not None and face_value > 1_000_000:
        return None
    issue_size = _number(row.get("ISSUESIZE"))
    coupon_period = _number(row.get("COUPONPERIOD"))
    coupon_freq = (
        _normalize_coupon_freq(round(365.0 / coupon_period, 4))
        if coupon_period and coupon_period > 0
        else None
    )
    coupon_rub = _number(row.get("COUPONVALUE"))
    price = _first_positive(
        market.get("LAST"),
        market.get("WAPRICE"),
        market.get("MARKETPRICE"),
        row.get("PREVPRICE"),
        row.get("PREVWAPRICE"),
    )
    ytm = _first_positive(
        market.get("YIELD"),
        market.get("CLOSEYIELD"),
        row.get("YIELDATPREVWAPRICE"),
    )
    duration_days = _number(market.get("DURATION"))
    duration_years = round(duration_days / 365.0, 4) if duration_days and duration_days > 0 else None
    volume_rub = _number(market.get("VALTODAY"))
    volume_mn_rub = round(volume_rub / 1_000_000.0, 4) if volume_rub and volume_rub > 0 else None

    current_coupon_yield = None
    if coupon_rub is not None and coupon_freq and price and face_value:
        current_coupon_yield = round(coupon_rub * coupon_freq / (price / 100.0 * face_value) * 100.0, 4)

    maturity = _parse_date(row.get("MATDATE"))
    next_coupon = _parse_date(row.get("NEXTCOUPON"))
    offer = _parse_date(row.get("OFFERDATE"))
    today = date.today()
    years_to_maturity = round((maturity - today).days / 365.0, 4) if maturity and maturity > today else None
    amortized_text = " ".join(
        str(row.get(key) or "")
        for key in ("BONDTYPE", "BONDSUBTYPE", "COUPON_DETAILS")
    ).lower()
    amortized = True if "амортиз" in amortized_text else None

    return sanitize_bond(
        Bond(
            isin=isin,
            name=str(_first(row.get("SHORTNAME"), row.get("SECNAME"), isin)),
            price_pct=price,
            ytm_pct=ytm,
            current_coupon_yield_pct=current_coupon_yield,
            annual_coupon_yield_pct=_number(row.get("COUPONPERCENT")),
            volume_mn_rub=volume_mn_rub,
            coupon_rub=coupon_rub,
            coupon_freq=coupon_freq,
            coupon_type=_coupon_type(row),
            nkd_rub=_number(row.get("ACCRUEDINT")),
            duration_years=duration_years,
            next_coupon_date=next_coupon,
            maturity_date=maturity,
            offer_date=offer,
            years_to_maturity=years_to_maturity,
            face_value=face_value,
            issue_size_rub=(issue_size * face_value) if issue_size and face_value else None,
            amortized=amortized,
            source_url=f"https://www.moex.com/ru/issue.aspx?code={isin}",
            fetched_at=utcnow(),
        )
    )


def _completeness(bond: Bond) -> int:
    fields = (
        bond.ytm_pct,
        bond.duration_years,
        bond.price_pct,
        bond.volume_mn_rub,
        bond.coupon_rub,
        bond.maturity_date,
    )
    return sum(1 for value in fields if value is not None)


def parse_moex_bonds(payload: dict[str, Any]) -> list[Bond]:
    """Преобразует ответ MOEX ISS securities+marketdata в список Bond."""
    securities = _rows(payload.get("securities"))
    market_rows = _rows(payload.get("marketdata"))
    market = {
        (str(row.get("SECID") or ""), str(row.get("BOARDID") or "")): row
        for row in market_rows
    }

    best: dict[str, Bond] = {}
    for row in securities:
        key = (str(row.get("SECID") or ""), str(row.get("BOARDID") or ""))
        bond = _parse_row(row, market.get(key, {}))
        if bond is None:
            continue
        current = best.get(bond.isin)
        if current is None or _completeness(bond) > _completeness(current):
            best[bond.isin] = bond
    return list(best.values())


class MoexClient:
    """Официальный источник рыночных данных Московской Биржи."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "MoexClient":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.settings.request_timeout),
            headers={
                "User-Agent": self.settings.user_agent,
                "Accept": "application/json",
            },
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._session is not None:
            await self._session.close()

    async def fetch_bonds(self) -> list[Bond]:
        if self._session is None:
            raise RuntimeError("client is not started")
        url = f"{self.settings.moex_base}/iss/engines/stock/markets/bonds/securities.json"
        params = {
            "iss.meta": "off",
            "iss.only": "securities,marketdata",
            "limit": "10000",
        }
        last_error: Exception | None = None
        payload: dict[str, Any] | None = None
        for attempt in range(1, 4):
            try:
                async with self._session.get(url, params=params) as response:
                    if response.status >= 500:
                        raise aiohttp.ClientResponseError(
                            response.request_info,
                            response.history,
                            status=response.status,
                            message=f"MOEX HTTP {response.status}",
                        )
                    if response.status >= 400:
                        raise RuntimeError(f"MOEX HTTP {response.status}")
                    payload = await response.json(content_type=None)
                break
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt >= 3:
                    raise
                log.warning("MOEX attempt %s failed: %s", attempt, exc)
                await asyncio.sleep(1.5 * attempt)
        if payload is None:
            raise RuntimeError(f"MOEX unavailable: {last_error}")
        bonds = parse_moex_bonds(payload)
        log.info("MOEX: %s bonds", len(bonds))
        return bonds


__all__ = ["MoexClient", "parse_moex_bonds"]
