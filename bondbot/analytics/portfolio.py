from __future__ import annotations

from dataclasses import dataclass, field

from bondbot.analytics.bonds import normalize_rating, rating_rank
from bondbot.models import Bond, PortfolioPosition


@dataclass(slots=True)
class PortfolioMetrics:
    total_value_rub: float = 0.0
    total_cost_rub: float = 0.0
    profit_rub: float = 0.0
    annual_coupon_rub: float = 0.0
    weighted_ytm_pct: float | None = None
    weighted_duration_years: float | None = None
    rating_mix: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _weighted(values: list[tuple[float | None, float]], total: float) -> float | None:
    if total <= 0:
        return None
    known = [(value, weight) for value, weight in values if value is not None and weight > 0]
    if not known:
        return None
    return sum(value * weight for value, weight in known) / sum(weight for _, weight in known)


def analyze_portfolio(
    positions: list[PortfolioPosition],
    bonds: dict[str, Bond],
    *,
    max_pct_daily_volume: float = 0.05,
    max_position_share: float = 0.25,
) -> PortfolioMetrics:
    metrics = PortfolioMetrics()
    rows: list[tuple[PortfolioPosition, Bond | None, float, str, float | None, float | None]] = []
    ytm_values: list[tuple[float | None, float]] = []
    duration_values: list[tuple[float | None, float]] = []
    rating_values: dict[str, float] = {}

    for position in positions:
        bond = bonds.get(position.isin)
        value = position.current_value_rub
        if value is None and position.current_price_pct is not None:
            value = position.qty * position.current_price_pct / 100 * 1000
        value = value or 0.0
        metrics.total_value_rub += value
        if position.buy_value_rub is not None:
            metrics.total_cost_rub += position.buy_value_rub
        if position.annual_coupon_rub is not None:
            metrics.annual_coupon_rub += position.annual_coupon_rub

        ytm = position.ytm_pct if position.ytm_pct is not None else (bond.ytm_pct if bond else None)
        duration = bond.duration_years if bond else None
        rating = normalize_rating(position.rating or (bond.rating if bond else None)) or "Без рейтинга"
        rows.append((position, bond, value, rating, ytm, duration))
        ytm_values.append((ytm, value))
        duration_values.append((duration, value))
        rating_values[rating] = rating_values.get(rating, 0.0) + value

    metrics.profit_rub = metrics.total_value_rub - metrics.total_cost_rub
    metrics.weighted_ytm_pct = _weighted(ytm_values, metrics.total_value_rub)
    metrics.weighted_duration_years = _weighted(duration_values, metrics.total_value_rub)
    if metrics.total_value_rub > 0:
        metrics.rating_mix = {
            rating: value / metrics.total_value_rub for rating, value in rating_values.items()
        }

    for position, bond, value, rating, _, _ in rows:
        if value <= 0 or metrics.total_value_rub <= 0:
            continue
        share = value / metrics.total_value_rub
        if share > max_position_share:
            metrics.warnings.append(
                f"{position.isin} ({position.name}): {share:.1%} портфеля — выше лимита {max_position_share:.0%}"
            )

        if bond and bond.volume_mn_rub and bond.volume_mn_rub > 0:
            volume_share = value / (bond.volume_mn_rub * 1_000_000)
            if volume_share > max_pct_daily_volume:
                metrics.warnings.append(
                    f"{position.isin} ({position.name}): позиция {volume_share:.1%} дневного объёма "
                    f"(лимит {max_pct_daily_volume:.0%})"
                )
        elif bond:
            metrics.warnings.append(f"{position.isin} ({position.name}): нет данных об объёме торгов")

        if rating_rank(rating) >= 0 and rating_rank(rating) < rating_rank("BBB-"):
            metrics.warnings.append(
                f"{position.isin} ({position.name}): рейтинг {rating} ниже BBB- — высокий кредитный риск"
            )

    if metrics.weighted_ytm_pct is not None and metrics.weighted_ytm_pct > 22:
        metrics.warnings.append(
            f"Средняя доходность {metrics.weighted_ytm_pct:.1f}% — высокая, вероятен повышенный кредитный риск"
        )
    return metrics
