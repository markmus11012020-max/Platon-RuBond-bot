from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from bondbot.analytics.risk import assess_bond_risk
from bondbot.db import Database
from bondbot.models import Bond, to_msk
from bondbot.strategy.valuation import value_bond


def issuer_payload(
    db: Database,
    query: str,
    *,
    key_rate_pct: float | None = None,
    limit: int = 6,
) -> dict[str, Any]:
    bonds = db.search_bonds_by_name(query, limit=limit)
    news: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    queries = [query]
    for bond in bonds[:3]:
        short_name = re.sub(r"[А-ЯA-Z]?\d.*$", "", bond.name).strip() or bond.name[:8]
        if short_name and short_name not in queries:
            queries.append(short_name)
    for news_query in queries:
        for item in db.search_news(news_query, limit=4):
            url = str(item.get("url") or item.get("title"))
            if url in seen_urls:
                continue
            seen_urls.add(url)
            news.append(item)
    news.sort(key=lambda item: item.get("published_at") or "", reverse=True)

    bond_rows: list[dict[str, Any]] = []
    for bond in bonds:
        valuation = value_bond(
            bond,
            key_rate_pct=key_rate_pct,
            coupons=db.coupons(bond.isin),
        )
        risk = assess_bond_risk(bond, key_rate_pct)
        bond_rows.append(
            {
                "isin": bond.isin,
                "name": bond.name,
                "ytm_pct": bond.ytm_pct,
                "price_pct": bond.price_pct,
                "duration_years": bond.duration_years,
                "rating": bond.rating,
                "volume_mn_rub": bond.volume_mn_rub,
                "maturity_date": bond.maturity_date.isoformat() if bond.maturity_date else None,
                "offer_date": bond.offer_date.isoformat() if bond.offer_date else None,
                "risk_score": risk.score,
                "risk_level": risk.level,
                "risk_warnings": list(risk.warnings[:4]),
                "after_tax_ytm_pct": valuation.after_tax_ytm_pct,
                "g_spread_bp": valuation.g_spread_bp,
                "z_spread_bp": valuation.z_spread_bp,
                "carry_pct": valuation.carry_pct,
                "valuation_warnings": list(valuation.warnings[:4]),
            }
        )
    return {"query": query, "bonds": bond_rows, "news": news[:8]}


def _pct(value: float | None) -> str:
    return f"{value:.2f}%" if value is not None else "—"


def _num(value: float | None, suffix: str = "", digits: int = 2) -> str:
    return f"{value:.{digits}f}{suffix}" if value is not None else "—"


def render_issuer(payload: dict[str, Any]) -> str:
    query = payload.get("query") or ""
    bonds = payload.get("bonds") or []
    news = payload.get("news") or []
    lines = [f"🏢 {query}: обзор эмитента"]
    if bonds:
        lines.append(f"Найдено выпусков: {len(bonds)}")
        lines.append("")
        for bond in bonds:
            lines.append(
                f"• {bond['name']} ({bond['isin']}) — YTM {_pct(bond['ytm_pct'])}, "
                f"цена {_pct(bond['price_pct'])}, дюр. {_num(bond['duration_years'])} г, "
                f"{bond['rating'] or 'рейтинг н/д'}"
            )
            lines.append(
                f"   риск {bond['risk_score']:.0f}/100 ({bond['risk_level']}) · "
                f"после налога {_pct(bond['after_tax_ytm_pct'])} · "
                f"G-спред {_num(bond['g_spread_bp'], ' б.п.', 0)}"
            )
            if bond.get("offer_date") or bond.get("maturity_date"):
                lines.append(
                    f"   оферта {bond.get('offer_date') or '—'} · "
                    f"погашение {bond.get('maturity_date') or '—'}"
                )
    else:
        lines.append("В базе не нашёл выпусков по этому названию.")
        lines.append("Проверил новости и доступные источники — ниже то, что есть.")

    if news:
        lines.append("")
        lines.append("Новости и контекст:")
        for item in news[:6]:
            published = item.get("published_at")
            try:
                stamp = to_msk(datetime.fromisoformat(published)) if published else None
            except ValueError:
                stamp = None
            when = f" · {stamp:%d.%m %H:%M}" if stamp else ""
            lines.append(f"• {item.get('title')} — {item.get('source')}{when}")
            if item.get("url"):
                lines.append(f"   {item['url']}")
    else:
        lines.append("")
        lines.append("Свежих новостей по эмитенту не найдено.")
    lines.append("")
    lines.append("Обзор по данным базы и новостей. Не индивидуальная инвестиционная рекомендация.")
    return "\n".join(lines).strip()


__all__ = ["issuer_payload", "render_issuer"]
