from __future__ import annotations

from statistics import mean, median, pstdev

from bondbot.analytics.bonds import normalize_rating
from bondbot.config import Settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import Bond
from bondbot.strategy.safe import safe_range


def _universe(settings: Settings, db: Database) -> list[Bond]:
    required = 20.0
    return [
        bond
        for bond in db.list_bonds()
        if bond.ytm_pct is not None
        and bond.duration_years is not None
        and bond.rating
        and bond.price_pct is not None
        and (bond.volume_mn_rub or 0.0) >= required
        and bond.duration_years <= 5.0
    ]


def _peers(target: Bond, bonds: list[Bond]) -> list[Bond]:
    rating = normalize_rating(target.rating)
    peers = [
        bond
        for bond in bonds
        if bond.isin != target.isin
        and normalize_rating(bond.rating) == rating
        and abs((bond.duration_years or 0.0) - (target.duration_years or 0.0)) <= 1.5
    ]
    if len(peers) >= 2:
        return peers
    return [
        bond
        for bond in bonds
        if bond.isin != target.isin and normalize_rating(bond.rating) == rating
    ]


def _premium(target: Bond, peers: list[Bond]) -> tuple[float | None, float | None, float | None]:
    values = [peer.ytm_pct for peer in peers if peer.ytm_pct is not None]
    if not values or target.ytm_pct is None:
        return None, None, None
    med = median(values)
    premium = target.ytm_pct - med
    z_score = None
    if len(values) >= 3:
        deviation = pstdev(values)
        if deviation > 0:
            z_score = (target.ytm_pct - mean(values)) / deviation
    return premium, med, z_score


def build_relative_value(
    settings: Settings,
    db: Database,
    snapshot: KeyRateSnapshot,
    *,
    isin: str | None = None,
) -> str:
    bonds = _universe(settings, db)
    range_ = safe_range(snapshot)
    if not bonds:
        return "Недостаточно данных для relative value: нужны рейтинг, дюрация и ликвидность."
    if isin:
        target = next((bond for bond in bonds if bond.isin == isin.upper()), None)
        if target is None:
            return f"Нет подходящей бумаги {isin.upper()} для relative value."
        peers = _peers(target, bonds)
        premium, med, z_score = _premium(target, peers)
        lines = [
            f"⚖️ Relative value: {target.name} ({target.isin})",
            f"YTM {target.ytm_pct:.2f}% · дюр. {target.duration_years:.2f} г · "
            f"{target.rating} · цена {target.price_pct:.2f}%",
            f"Коридор: {range_.low_pct:.2f}–{range_.high_pct:.2f}%",
        ]
        if premium is None:
            lines.append("Недостаточно peers для сравнения.")
        else:
            lines.append(
                f"Peers: {len(peers)} · медиана YTM {med:.2f}% · "
                f"премия {premium:+.2f} п.п."
            )
            if z_score is not None:
                lines.append(f"Z-score к peers: {z_score:+.2f}")
            lines.append(
                "Дорого/дёшево относительно peers — это не оценка кредитного качества."
            )
        lines.append("Не индивидуальная инвестиционная рекомендация.")
        return "\n".join(lines)

    ranked: list[tuple[float, Bond, int, float | None, float | None]] = []
    for bond in bonds:
        peers = _peers(bond, bonds)
        premium, med, z_score = _premium(bond, peers)
        if premium is not None:
            ranked.append((premium, bond, len(peers), med, z_score))
    if not ranked:
        return "Недостаточно данных для relative value."
    ranked.sort(key=lambda item: item[0], reverse=True)
    lines = [
        "⚖️ Relative value: где доходность выше peers",
        f"Коридор: {range_.low_pct:.2f}–{range_.high_pct:.2f}%",
        "",
        "Дешевле peers (премия к медиане):",
    ]
    for premium, bond, peers_count, med, z_score in ranked[:5]:
        lines.append(
            f"• {bond.name} ({bond.isin}) — YTM {bond.ytm_pct:.2f}%, "
            f"премия {premium:+.2f} п.п. к {med:.2f}% ({peers_count} peers)"
        )
    lines.append("")
    lines.append("Дороже peers:")
    for premium, bond, peers_count, med, z_score in ranked[-3:]:
        lines.append(
            f"• {bond.name} ({bond.isin}) — YTM {bond.ytm_pct:.2f}%, "
            f"премия {premium:+.2f} п.п. к {med:.2f}%"
        )
    lines.append("")
    lines.append("Сравнение по доходности, не по кредитному риску. Проверяй рейтинг и новости.")
    return "\n".join(lines)


__all__ = ["build_relative_value"]
