from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime

from bondbot.analytics.bonds import meets_min_rating, rating_rank
from bondbot.config import Settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import Bond
from bondbot.strategy.stability import WEIGHTS, stability_score
from bondbot.strategy.types import AuditRecord, SafeBond, SafeListResult, YieldRange

log = logging.getLogger(__name__)


def safe_range(
    snapshot: KeyRateSnapshot,
    *,
    margin_low_pct: float = 5.0,
    margin_high_pct: float = 10.0,
) -> YieldRange:
    """Диапазон YTM: ключевая ставка + маржа (по умолчанию 5–10 п.п.)."""
    low = round(snapshot.value_pct + margin_low_pct, 2)
    high = round(snapshot.value_pct + margin_high_pct, 2)
    return YieldRange(
        low_pct=low,
        high_pct=high,
        key_rate_pct=snapshot.value_pct,
        margin_low_pct=margin_low_pct,
        margin_high_pct=margin_high_pct,
        as_of=snapshot.as_of,
        stale=snapshot.stale,
    )


def _eligible(
    bond: Bond,
    range: YieldRange,
    settings: Settings,
    required_volume_mn: float,
) -> bool:
    if bond.qual_only:
        return False
    if bond.ytm_pct is None or bond.duration_years is None:
        return False
    if bond.ytm_pct < range.low_pct or bond.ytm_pct > range.high_pct:
        return False
    if bond.duration_years > settings.max_duration_years:
        return False
    if not meets_min_rating(bond.rating, settings.min_rating):
        return False
    if bond.price_pct is None:
        return False
    if bond.price_pct < settings.min_price_pct or bond.price_pct > settings.max_price_pct:
        return False
    if bond.volume_mn_rub is None or bond.volume_mn_rub < required_volume_mn:
        return False
    return True


def build_safe_list(
    settings: Settings,
    db: Database,
    snapshot: KeyRateSnapshot,
    *,
    limit: int = 8,
    margin_low_pct: float = 5.0,
    margin_high_pct: float = 10.0,
    save_audit: bool = True,
    now: datetime | None = None,
) -> SafeListResult:
    """Список «самых стабильных» бумаг внутри ключевого диапазона.

    Диапазон считается сутью стратегии: ЦБ + 5..10 п.п. (по умолчанию).
    Оценка стабильности — чистая математика, без LLM."""
    range = safe_range(
        snapshot,
        margin_low_pct=margin_low_pct,
        margin_high_pct=margin_high_pct,
    )
    required_volume_mn = required_daily_volume_mn_from(settings)

    bonds = db.list_bonds()
    universe_size = len(bonds)
    items: list[SafeBond] = []
    for bond in bonds:
        if not _eligible(bond, range, settings, required_volume_mn):
            continue
        score = stability_score(
            bond,
            low_pct=range.low_pct,
            high_pct=range.high_pct,
            max_duration_years=settings.max_duration_years,
            required_volume_mn=required_volume_mn,
            now=now,
        )
        items.append(SafeBond(bond=bond, score=score))

    items.sort(
        key=lambda item: (
            item.score.score,
            rating_rank(item.bond.rating),
            item.bond.volume_mn_rub or 0.0,
        ),
        reverse=True,
    )
    selected = tuple(items[: max(1, limit)])
    eligible_size = len(items)

    audit_id: int | None = None
    if save_audit:
        result_payload = {
            "count": len(selected),
            "eligible": eligible_size,
            "universe": universe_size,
            "selected": [asdict(item) for item in selected],
        }
        audit_id = db.save_audit(
            kind="safe_list",
            inputs={
                "key_rate_pct": snapshot.value_pct,
                "key_rate_as_of": str(snapshot.as_of),
                "key_rate_stale": snapshot.stale,
                "range_low_pct": range.low_pct,
                "range_high_pct": range.high_pct,
                "max_duration_years": settings.max_duration_years,
                "min_rating": settings.min_rating,
                "min_price_pct": settings.min_price_pct,
                "max_price_pct": settings.max_price_pct,
                "required_volume_mn": required_volume_mn,
                "position_size_rub": settings.position_size_rub,
            },
            formulas=(
                f"range = ЦБ {snapshot.value_pct:.2f}% + {margin_low_pct:.0f}–{margin_high_pct:.0f} п.п. "
                f"= {range.low_pct:.2f}–{range.high_pct:.2f}%",
                "score = 0.30×rating + 0.20×liquidity + 0.15×duration + 0.10×issue_size "
                "+ 0.10×price + 0.10×yield_position + 0.05×data_quality − penalties",
                "liquidity_filter = позиция ≤ дневной объём × 5%",
            ),
            result=result_payload,
            created_at=now,
        )

    return SafeListResult(
        range=range,
        items=selected,
        universe_size=universe_size,
        eligible_size=eligible_size,
        audit_id=audit_id,
        generated_at=now or datetime.now().astimezone(),
    )


def required_daily_volume_mn_from(settings: Settings) -> float:
    from bondbot.analytics.bonds import required_daily_volume_mn

    return required_daily_volume_mn(settings.position_size_rub, settings.max_pct_daily_volume)


__all__ = ["WEIGHTS", "build_safe_list", "required_daily_volume_mn_from", "safe_range"]
