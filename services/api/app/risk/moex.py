from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx

log = logging.getLogger(__name__)

MOEX_BASE = "https://iss.moex.com"


def _rows(block: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not block:
        return []
    columns = block.get("columns") or []
    return [dict(zip(columns, row)) for row in block.get("data") or []]


def _number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class MarketSnapshot:
    isin: str
    last_price_pct: float | None = None
    last_value_rub: float | None = None
    drawdown_7d_pct: float | None = None
    drawdown_30d_pct: float | None = None
    volume_ratio_30d: float | None = None
    bid_pct: float | None = None
    offer_pct: float | None = None
    spread_pct: float | None = None
    available_buy_rub: float | None = None
    available_sell_rub: float | None = None
    data_date: str | None = None
    quote_time: str | None = None
    error: str = ""
    history_points: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


async def fetch_snapshot(isin: str, days: int = 45) -> MarketSnapshot:
    isin = isin.strip().upper()
    today = date.today()
    start = today - timedelta(days=max(10, days))
    history_url = (
        f"{MOEX_BASE}/iss/history/engines/stock/markets/bonds/"
        f"securities/{isin}.json"
    )
    quote_url = (
        f"{MOEX_BASE}/iss/engines/stock/markets/bonds/"
        f"securities/{isin}.json"
    )
    params_history = {
        "from": start.isoformat(),
        "till": today.isoformat(),
        "iss.meta": "off",
        "iss.only": "history",
    }
    params_quote = {
        "iss.meta": "off",
        "iss.only": "securities,marketdata",
    }
    try:
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "PlatonRisk/0.1"},
        ) as client:
            history_response, quote_response = await client.get(
                history_url, params=params_history
            ), await client.get(quote_url, params=params_quote)
        history_payload = history_response.json()
        quote_payload = quote_response.json()
    except Exception as exc:
        log.warning("MOEX snapshot %s failed: %s", isin, exc)
        return MarketSnapshot(isin=isin, error=str(exc))

    history = _rows(history_payload.get("history"))
    securities = _rows(quote_payload.get("securities"))
    marketdata = _rows(quote_payload.get("marketdata"))
    security = securities[0] if securities else {}
    quote = marketdata[0] if marketdata else {}

    points: list[tuple[date, float, float | None]] = []
    for row in history:
        traded = str(row.get("TRADEDATE") or "")
        close = _number(row.get("LEGALCLOSEPRICE")) or _number(row.get("CLOSE"))
        if not traded or close is None:
            continue
        try:
            traded_date = date.fromisoformat(traded[:10])
        except ValueError:
            continue
        value = _number(row.get("VALUE"))
        points.append((traded_date, close, value))
    points.sort(key=lambda item: item[0])

    snapshot = MarketSnapshot(
        isin=isin,
        history_points=len(points),
        data_date=points[-1][0].isoformat() if points else None,
    )
    if points:
        last_close = points[-1][1]
        snapshot.last_price_pct = last_close
        snapshot.last_value_rub = points[-1][2]
        by_date = {item[0]: item[1] for item in points}
        for label, delta_days in (("7d", 7), ("30d", 30)):
            target = today - timedelta(days=delta_days)
            older = [item for item in points if item[0] <= target]
            base = older[-1][1] if older else points[0][1]
            if base:
                drawdown = (last_close - base) / base * 100
                if label == "7d":
                    snapshot.drawdown_7d_pct = round(drawdown, 2)
                else:
                    snapshot.drawdown_30d_pct = round(drawdown, 2)
        values = [
            value
            for traded_date, _, value in points
            if value is not None and traded_date >= today - timedelta(days=30)
        ]
        if values and points[-1][2] is not None:
            median_value = statistics.median(values)
            if median_value > 0:
                snapshot.volume_ratio_30d = round(points[-1][2] / median_value, 2)

    bid = _number(quote.get("BID"))
    offer = _number(quote.get("OFFER"))
    snapshot.bid_pct = bid
    snapshot.offer_pct = offer
    if bid and offer and bid > 0:
        snapshot.spread_pct = round((offer - bid) / bid * 100, 2)

    lotsize = _number(security.get("LOTSIZE")) or 1.0
    facevalue = _number(security.get("FACEVALUE")) or 1000.0
    bid_depth = _number(quote.get("BIDDEPTHT")) or _number(quote.get("BIDDEPTH")) or 0.0
    offer_depth = _number(quote.get("OFFERDEPTHT")) or _number(quote.get("OFFERDEPTH")) or 0.0
    if bid:
        snapshot.available_sell_rub = round(bid_depth * lotsize * facevalue * bid / 100, 2)
    if offer:
        snapshot.available_buy_rub = round(offer_depth * lotsize * facevalue * offer / 100, 2)
    snapshot.quote_time = str(quote.get("UPDATETIME") or "") or None
    snapshot.raw = {
        "bid_depth": bid_depth,
        "offer_depth": offer_depth,
        "lotsize": lotsize,
        "facevalue": facevalue,
        "board": security.get("BOARDID"),
    }
    return snapshot


__all__ = ["MarketSnapshot", "fetch_snapshot"]
