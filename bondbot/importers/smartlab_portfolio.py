from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from bondbot.data.smartlab import _norm, _parse_date, _parse_float
from bondbot.db import Database
from bondbot.models import Bond, PortfolioPosition


def parse_portfolio_html(html: str, source_url: str = "") -> list[PortfolioPosition]:
    soup = BeautifulSoup(html, "lxml")
    table = None
    for candidate in soup.find_all("table"):
        header_text = _norm(candidate.get_text(" ", strip=True)[:300])
        if "кол-во" in header_text and "цена покупки" in header_text:
            table = candidate
            break
    if table is None:
        raise ValueError("portfolio table not found (save the page while logged in)")

    rows = table.find_all("tr")
    headers = [_norm(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
    index = {name: i for i, name in enumerate(headers)}

    def idx(*prefixes: str) -> int | None:
        for prefix in prefixes:
            for name, position in index.items():
                if name.startswith(prefix):
                    return position
        return None

    i_price = idx("текущ. цена")
    i_ytm = idx("рын. дох")
    i_maturity = idx("погашение")
    i_rating = idx("рейтинг")
    i_gspread = idx("g-спред")
    i_coupon = idx("купон,")
    i_qty = idx("кол-во")
    i_buy = idx("цена покупки")
    i_value = idx("тек. стоим")

    positions: list[PortfolioPosition] = []
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 12:
            continue
        link = None
        for anchor in row.find_all("a", href=True):
            if re.search(r"/q/bonds/[A-Z0-9]+/", anchor.get("href") or ""):
                link = anchor
                break
        if link is None:
            continue
        isin_match = re.search(r"/q/bonds/([A-Z0-9]+)/", link.get("href") or "")
        if not isin_match:
            continue
        isin = isin_match.group(1)
        name = link.get_text(" ", strip=True) or (cells[1].get_text(" ", strip=True) if len(cells) > 1 else isin)

        def cell(position: int | None) -> str:
            return cells[position].get_text(" ", strip=True) if position is not None and position < len(cells) else ""

        qty = _parse_float(cell(i_qty)) or 0.0
        if qty <= 0:
            continue

        annual_coupon = _parse_float(cell(16)) if len(cells) > 16 else None
        coupon_freq = _parse_float(cell(17)) if len(cells) > 17 else None
        next_coupon = _parse_date(cell(19)) if len(cells) > 19 else None

        positions.append(
            PortfolioPosition(
                isin=isin,
                name=name,
                qty=qty,
                buy_price_pct=_parse_float(cell(i_buy)),
                current_price_pct=_parse_float(cell(i_price)),
                ytm_pct=_parse_float(cell(i_ytm)),
                maturity_date=_parse_date(cell(i_maturity)),
                rating=cell(i_rating) or None,
                g_spread_bp=_parse_float(cell(i_gspread)),
                coupon_rub=_parse_float(cell(i_coupon)),
                coupon_freq=coupon_freq,
                annual_coupon_rub=annual_coupon,
                current_value_rub=_parse_float(cell(i_value)),
                next_coupon_date=next_coupon,
                source_url=source_url,
            )
        )
    return positions


def import_portfolio_html(
    db: Database,
    html: str,
    source_url: str = "",
) -> list[PortfolioPosition]:
    positions = parse_portfolio_html(html, source_url=source_url)
    if not positions:
        raise ValueError("no positions parsed from portfolio")

    now = datetime.now(timezone.utc)
    bonds = [
        Bond(
            isin=position.isin,
            name=position.name,
            price_pct=position.current_price_pct,
            ytm_pct=position.ytm_pct,
            rating=position.rating,
            g_spread_bp=position.g_spread_bp,
            coupon_rub=position.coupon_rub,
            coupon_freq=position.coupon_freq,
            next_coupon_date=position.next_coupon_date,
            maturity_date=position.maturity_date,
            source_url=position.source_url,
            fetched_at=now,
        )
        for position in positions
    ]
    db.upsert_bonds(bonds)
    # Портфель на Smart-Lab — источник истины: старые позиции удаляем.
    db.clear_positions()
    db.upsert_positions(positions)
    for position in positions:
        db.add_watch(position.isin, "paper portfolio")
    return positions


def import_portfolio_file(db: Database, path: str | Path) -> list[PortfolioPosition]:
    path = Path(path)
    return import_portfolio_html(
        db,
        path.read_text(encoding="utf-8", errors="replace"),
        source_url=str(path),
    )
