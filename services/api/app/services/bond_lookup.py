from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import httpx

from bondbot.data.smartlab import parse_detail

from app.risk.moex import fetch_snapshot

log = logging.getLogger(__name__)

SMARTLAB_URL = "https://smart-lab.ru/q/bonds/{isin}/"
CACHE_TTL_SECONDS = 600
_CACHE: dict[str, tuple[float, "BondLookup | None"]] = {}


@dataclass(slots=True)
class BondLookup:
    isin: str
    name: str
    rating: str | None = None
    price_pct: float | None = None
    ytm_pct: float | None = None
    duration_years: float | None = None
    coupon_rub: float | None = None
    coupon_freq: float | None = None
    next_coupon_date: date | None = None
    maturity_date: date | None = None
    offer_date: date | None = None
    volume_mn_rub: float | None = None
    bid_pct: float | None = None
    offer_pct: float | None = None
    spread_pct: float | None = None
    available_buy_rub: float | None = None
    available_sell_rub: float | None = None
    data_date: str | None = None
    source_url: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("next_coupon_date", "maturity_date", "offer_date"):
            value = payload.get(key)
            payload[key] = value.isoformat() if value else None
        return payload

    def as_text(self) -> str:
        lines = [
            f"{self.name} ({self.isin})",
            f"Рейтинг: {self.rating or '—'} · цена: {self.price_pct:.2f}% · YTM: {self.ytm_pct:.2f}%"
            if self.price_pct is not None and self.ytm_pct is not None
            else f"Рейтинг: {self.rating or '—'}",
            f"Дюрация: {self.duration_years:.2f} г. · купон: {self.coupon_rub:.2f} ₽ × {self.coupon_freq:g}"
            if self.duration_years is not None
            and self.coupon_rub is not None
            and self.coupon_freq is not None
            else "Дюрация и купон: —",
            f"Погашение: {self.maturity_date or '—'} · оферта: {self.offer_date or '—'}",
        ]
        if self.bid_pct is not None and self.offer_pct is not None:
            lines.append(
                f"Bid/ask: {self.bid_pct:.2f}% / {self.offer_pct:.2f}% · "
                f"спред {self.spread_pct:.2f}%"
                if self.spread_pct is not None
                else f"Bid/ask: {self.bid_pct:.2f}% / {self.offer_pct:.2f}%"
            )
        if self.available_buy_rub is not None:
            lines.append(f"Доступно на покупку: {self.available_buy_rub:,.0f} ₽".replace(",", " "))
        if self.data_date:
            lines.append(f"Данные MOEX: {self.data_date}")
        return "\n".join(lines)


async def lookup_bond(isin: str) -> BondLookup | None:
    isin = isin.strip().upper()
    cached = _CACHE.get(isin)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    bond = None
    try:
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "PlatonBondLookup/0.1"},
        ) as client:
            response = await client.get(SMARTLAB_URL.format(isin=isin))
            response.raise_for_status()
        bond, _ = parse_detail(response.text, isin)
    except Exception as exc:
        log.warning("bond lookup %s failed: %s", isin, exc)

    snapshot = await fetch_snapshot(isin)
    if bond is None and snapshot.history_points == 0:
        _CACHE[isin] = (time.monotonic(), None)
        return None

    result = BondLookup(
        isin=isin,
        name=bond.name if bond else isin,
        rating=bond.rating if bond else None,
        price_pct=snapshot.last_price_pct or (bond.price_pct if bond else None),
        ytm_pct=bond.ytm_pct if bond else None,
        duration_years=bond.duration_years if bond else None,
        coupon_rub=bond.coupon_rub if bond else None,
        coupon_freq=bond.coupon_freq if bond else None,
        next_coupon_date=bond.next_coupon_date if bond else None,
        maturity_date=bond.maturity_date if bond else None,
        offer_date=bond.offer_date if bond else None,
        volume_mn_rub=(
            round(snapshot.last_value_rub / 1_000_000, 2)
            if snapshot.last_value_rub
            else (bond.volume_mn_rub if bond else None)
        ),
        bid_pct=snapshot.bid_pct,
        offer_pct=snapshot.offer_pct,
        spread_pct=snapshot.spread_pct,
        available_buy_rub=snapshot.available_buy_rub,
        available_sell_rub=snapshot.available_sell_rub,
        data_date=snapshot.data_date,
        source_url=(
            bond.source_url
            if bond
            else f"https://www.moex.com/ru/issue.aspx?code={isin}"
        ),
    )
    _CACHE[isin] = (time.monotonic(), result)
    return result


def clear_cache() -> None:
    _CACHE.clear()


__all__ = ["BondLookup", "clear_cache", "lookup_bond"]
