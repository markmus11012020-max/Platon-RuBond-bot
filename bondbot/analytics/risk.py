from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from bondbot.analytics.bonds import is_ofz, rating_rank
from bondbot.models import Bond, PortfolioPosition, utcnow
from bondbot.strategy.stability import _RATING_MAX
from bondbot.strategy.valuation import modified_duration

MAX_DURATION_YEARS = 5.0
REQUIRED_VOLUME_MN = 20.0
MAX_POSITION_SHARE = 0.25


@dataclass(frozen=True, slots=True)
class RiskFactor:
    name: str
    score: float
    weight: float
    note: str


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    isin: str
    name: str
    score: float
    level: str
    factors: tuple[RiskFactor, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class StressResult:
    delta_bp: float
    current_value_rub: float
    impact_rub: float
    new_value_rub: float
    annual_income_rub: float
    notes: tuple[str, ...] = ()


def _credit_factor(bond: Bond) -> RiskFactor:
    if is_ofz(bond):
        return RiskFactor("credit", 0.0, 0.35, "ОФЗ, суверенный кредит")
    rank = rating_rank(bond.rating)
    if rank < 0:
        score = 75.0
        note = "нет рейтинга"
    else:
        score = max(0.0, (1.0 - rank / max(1, _RATING_MAX)) * 100.0)
        note = f"рейтинг {bond.rating}"
    return RiskFactor("credit", score, 0.35, note)


def _duration_factor(bond: Bond) -> RiskFactor:
    if bond.duration_years is None:
        return RiskFactor("duration", 60.0, 0.20, "нет дюрации")
    score = min(100.0, max(0.0, bond.duration_years / MAX_DURATION_YEARS * 100.0))
    return RiskFactor("duration", score, 0.20, f"дюрация {bond.duration_years:.2f} г")


def _liquidity_factor(bond: Bond) -> RiskFactor:
    volume = bond.volume_mn_rub
    if volume is None or volume <= 0:
        return RiskFactor("liquidity", 90.0, 0.15, "нет данных об обороте")
    if volume < REQUIRED_VOLUME_MN:
        score = 90.0
    elif volume < REQUIRED_VOLUME_MN * 2:
        score = 60.0
    elif volume < REQUIRED_VOLUME_MN * 5:
        score = 30.0
    else:
        score = 0.0
    return RiskFactor("liquidity", score, 0.15, f"оборот {volume:.1f} млн ₽")


def _event_factor(bond: Bond, today: date) -> RiskFactor:
    score = 0.0
    notes: list[str] = []
    if bond.offer_date is not None and 0 <= (bond.offer_date - today).days <= 60:
        score = max(score, 80.0)
        notes.append(f"оферта через {(bond.offer_date - today).days} дн.")
    if bond.maturity_date is not None and 0 <= (bond.maturity_date - today).days <= 30:
        score = max(score, 70.0)
        notes.append(f"погашение через {(bond.maturity_date - today).days} дн.")
    if bond.amortized:
        score = max(score, 30.0)
        notes.append("амортизация")
    return RiskFactor("event", score, 0.10, ", ".join(notes) or "событий нет")


def _yield_factor(bond: Bond, key_rate_pct: float | None) -> RiskFactor:
    if bond.ytm_pct is None:
        return RiskFactor("yield", 50.0, 0.10, "нет YTM")
    if key_rate_pct is None:
        return RiskFactor("yield", 0.0, 0.10, f"YTM {bond.ytm_pct:.2f}%")
    premium = bond.ytm_pct - key_rate_pct
    if premium > 12:
        score = 90.0
    elif premium > 8:
        score = 60.0
    elif premium > 5:
        score = 30.0
    else:
        score = 0.0
    return RiskFactor("yield", score, 0.10, f"YTM {bond.ytm_pct:.2f}% (ЦБ + {premium:.1f} п.п.)")


def _data_factor(bond: Bond, now: datetime) -> RiskFactor:
    fields = (
        bond.ytm_pct,
        bond.duration_years,
        bond.rating,
        bond.price_pct,
        bond.volume_mn_rub,
    )
    missing = sum(
        1
        for value in fields
        if value is None and not (value is bond.rating and is_ofz(bond))
    )
    score = min(100.0, missing / len(fields) * 100.0)
    fetched = bond.fetched_at
    if fetched is None:
        score = max(score, 70.0)
    else:
        age_days = (now - fetched).total_seconds() / 86400.0
        if age_days > 30:
            score = max(score, 80.0)
        elif age_days > 7:
            score = max(score, 50.0)
    return RiskFactor("data", score, 0.10, "данные устарели" if score >= 50 else "данные свежие")


def _level(score: float) -> str:
    if score < 25:
        return "LOW"
    if score < 50:
        return "MEDIUM"
    if score < 75:
        return "HIGH"
    return "CRITICAL"


def assess_bond_risk(
    bond: Bond,
    key_rate_pct: float | None = None,
    *,
    now: datetime | None = None,
) -> RiskAssessment:
    current = now or utcnow()
    factors = (
        _credit_factor(bond),
        _duration_factor(bond),
        _liquidity_factor(bond),
        _event_factor(bond, current.date()),
        _yield_factor(bond, key_rate_pct),
        _data_factor(bond, current),
    )
    score = round(sum(factor.score * factor.weight for factor in factors), 1)
    warnings = [
        f"{factor.name}: {factor.note}"
        for factor in factors
        if factor.score >= 60
    ]
    if bond.ytm_pct is not None and bond.ytm_pct > 25:
        warnings.append(f"YTM {bond.ytm_pct:.2f}% — зона высокого кредитного риска")
    if bond.price_pct is not None and bond.price_pct < 90:
        warnings.append(f"цена {bond.price_pct:.2f}% — ниже 90%")
    return RiskAssessment(
        isin=bond.isin,
        name=bond.name,
        score=score,
        level=_level(score),
        factors=factors,
        warnings=tuple(warnings),
    )


def assess_portfolio_risk(
    positions: list[PortfolioPosition],
    bonds: dict[str, Bond],
    key_rate_pct: float | None = None,
    *,
    now: datetime | None = None,
) -> RiskAssessment:
    current = now or utcnow()
    total = sum(position.current_value_rub or 0.0 for position in positions)
    weighted = 0.0
    warnings: list[str] = []
    for position in positions:
        value = position.current_value_rub or 0.0
        bond = bonds.get(position.isin)
        if bond is None:
            warnings.append(f"{position.isin}: нет карточки бумаги")
            weighted += value * 75.0
            continue
        assessment = assess_bond_risk(bond, key_rate_pct, now=current)
        weighted += value * assessment.score
        warnings.extend(f"{bond.name}: {warning}" for warning in assessment.warnings[:2])
        if total > 0 and value / total > MAX_POSITION_SHARE:
            warnings.append(
                f"{bond.name}: {value / total:.1%} портфеля — выше лимита {MAX_POSITION_SHARE:.0%}"
            )
    score = round(weighted / total, 1) if total > 0 else 0.0
    return RiskAssessment(
        isin="PORTFOLIO",
        name="Портфель",
        score=score,
        level=_level(score),
        factors=(),
        warnings=tuple(warnings),
    )


def stress_portfolio(
    positions: list[PortfolioPosition],
    bonds: dict[str, Bond],
    delta_bp: float = 100.0,
) -> StressResult:
    current_value = 0.0
    impact = 0.0
    income = 0.0
    notes: list[str] = []
    for position in positions:
        value = position.current_value_rub or 0.0
        current_value += value
        income += position.annual_coupon_rub or 0.0
        bond = bonds.get(position.isin)
        if bond is None:
            notes.append(f"{position.isin}: нет карточки, стресс не рассчитан")
            continue
        mod_duration = modified_duration(bond.duration_years, bond.ytm_pct)
        if mod_duration is None:
            notes.append(f"{bond.name}: нет дюрации, стресс не рассчитан")
            continue
        impact += -value * mod_duration * delta_bp / 10_000.0
    return StressResult(
        delta_bp=delta_bp,
        current_value_rub=current_value,
        impact_rub=impact,
        new_value_rub=current_value + impact,
        annual_income_rub=income,
        notes=tuple(notes),
    )


__all__ = [
    "RiskAssessment",
    "RiskFactor",
    "StressResult",
    "assess_bond_risk",
    "assess_portfolio_risk",
    "stress_portfolio",
]
