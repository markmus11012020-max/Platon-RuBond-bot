from __future__ import annotations

import logging
from datetime import date

from bondbot.models import Bond, Coupon
from bondbot.strategy.types import BondValuation

log = logging.getLogger(__name__)

DEFAULT_TAX_RATE = 0.13

_DAILY = 365.0


def after_tax_ytm(ytm_pct: float | None, tax_rate: float = DEFAULT_TAX_RATE) -> float | None:
    """ytm_after_tax = ytm × (1 − tax_rate)"""
    if ytm_pct is None:
        return None
    return ytm_pct * (1.0 - tax_rate)


def modified_duration(duration_years: float | None, ytm_pct: float | None) -> float | None:
    """modified_duration = duration / (1 + ytm/100)"""
    if duration_years is None or ytm_pct is None:
        return None
    base = 1.0 + ytm_pct / 100.0
    if base <= 0:
        return None
    return duration_years / base


def carry_yield(bond: Bond, key_rate_pct: float | None) -> float | None:
    """carry = доходность купона (или YTM) − ключевая ставка.

    Положительный carry значит каждую дату выплаты купонно-безрисковой части
    инвестор зарабатывает ставку ЦБ плюс спред."""
    if key_rate_pct is None:
        return None
    base = bond.current_coupon_yield_pct or bond.annual_coupon_yield_pct or bond.ytm_pct
    if base is None:
        return None
    return base - key_rate_pct


def g_spread_bp(bond: Bond, key_rate_pct: float | None) -> tuple[float | None, bool]:
    """Возвращает (G-спред, б.п., использован ли fallback)."""
    if bond.g_spread_bp is not None:
        return bond.g_spread_bp, False
    if bond.ytm_pct is not None and key_rate_pct is not None:
        return (bond.ytm_pct - key_rate_pct) * 100.0, True
    return None, False


DEFAULT_FACE_VALUE = 1000.0


def _cashflows(coupons: list[Coupon], bond: Bond, today: date, face_value: float) -> list[tuple[float, float]] | None:
    """Собирает денежный поток (сумма, лет) из купонов и погашения номинала."""
    if bond.maturity_date is None:
        return None
    flows: list[tuple[float, float]] = []
    for coupon in sorted(coupons, key=lambda item: item.coupon_date):
        if coupon.coupon_date <= today:
            continue
        if coupon.coupon_date > bond.maturity_date:
            break
        years = max((coupon.coupon_date - today).days / _DAILY, 1.0 / _DAILY)
        flows.append((coupon.value_rub or 0.0, years))
    redemption_years = max((bond.maturity_date - today).days / _DAILY, 1.0 / _DAILY)
    if bond.amortized:
        # доля номинала, погашенная с купонами, неизвестна — считаем, что вся
        # амортизация уже отражена в цене и не строим поток погашения.
        log.debug("z_spread %s: амортизация без календаря погашений", bond.isin)
        return None
    flows.append((face_value, redemption_years))
    return flows


def z_spread_bp(
    bond: Bond,
    coupons: list[Coupon] | None,
    key_rate_pct: float | None,
    *,
    today: date | None = None,
) -> float | None:
    """Z-спред к плоской кривой (ключевая ставка) в б.п.

    Цена решается по НКД (dirty price = clean + НКД).
    Если данных недостаточно — возвращает None и причина фиксируется в warnings."""
    if key_rate_pct is None:
        return None
    if bond.price_pct is None:
        return None
    face_value = bond.face_value or DEFAULT_FACE_VALUE
    flows = _cashflows(list(coupons or []), bond, today or date.today(), face_value)
    if not flows:
        return None

    dirty_price = bond.price_pct / 100.0 * face_value + (bond.nkd_rub or 0.0)
    low = -50.0  # bp per 1.0
    high = 10000.0  # bp per 1.0

    def npv(z_bp: float) -> float:
        rate = (key_rate_pct + z_bp / 100.0) / 100.0
        base = 1.0 + rate
        if base <= 0:
            return float("inf")
        return sum(amount / pow(base, years) for amount, years in flows) - dirty_price

    if npv(low) < 0 and npv(high) < 0:
        return None
    if npv(low) > 0 and npv(high) > 0:
        return None

    for _ in range(200):
        mid = (low + high) / 2.0
        value = npv(mid)
        if value == 0:
            return round(mid, 4)
        if value > 0:
            low = mid
        else:
            high = mid
        if high - low < 0.01:
            break
    return round((low + high) / 2.0, 4)


def value_bond(
    bond: Bond,
    *,
    key_rate_pct: float | None,
    tax_rate: float = DEFAULT_TAX_RATE,
    coupons: list[Coupon] | None = None,
    now: date | None = None,
) -> BondValuation:
    """Чистая математическая оценка бумаги, без LLM."""
    ytm = bond.ytm_pct
    warnings: list[str] = []
    formulas: list[str] = []

    if ytm is None:
        warnings.append(f"{bond.isin}: нет YTM")

    duration = bond.duration_years
    if duration is None:
        warnings.append(f"{bond.isin}: нет дюрации")

    after_tax = after_tax_ytm(ytm, tax_rate)
    if after_tax is not None:
        formulas.append(f"ytm_after_tax = {ytm:.2f}% × (1 − {tax_rate:.0%}) = {after_tax:.2f}%")

    mod_duration = modified_duration(duration, ytm)
    if mod_duration is not None and ytm is not None and duration is not None:
        formulas.append(
            f"modified_duration = {duration:.2f} / (1 + {ytm:.2f}%/100) = {mod_duration:.2f} лет"
        )

    g_spread, fallback = g_spread_bp(bond, key_rate_pct)
    if fallback and g_spread is not None and ytm is not None:
        formulas.append(f"g_spread = (YTM {ytm:.2f}% − ЦБ {key_rate_pct:.2f}%) × 100 = {g_spread:.0f} б.п.")
        warnings.append(f"{bond.isin}: G-спред от ЦБ — приблизительный")
    elif g_spread is not None:
        formulas.append(f"g_spread = {g_spread:.0f} б.п.")

    z_spread = z_spread_bp(bond, coupons, key_rate_pct, today=now)
    if z_spread is None:
        warnings.append(f"{bond.isin}: Z-спред не рассчитан — нет календаря купонов или НКД")
    else:
        formulas.append(f"z_spread = {z_spread:.2f} б.п. к плоской кривой (ключевая ставка)")

    carry = carry_yield(bond, key_rate_pct)
    if carry is None:
        warnings.append(f"{bond.isin}: carry не рассчитан — нет ставки ЦБ")
    else:
        base = bond.current_coupon_yield_pct or bond.annual_coupon_yield_pct or ytm
        base_txt = f"{base:.2f}%" if base is not None else "—"
        formulas.append(f"carry = {base_txt} − ЦБ {key_rate_pct:.2f}% = {carry:.2f} п.п.")
        if carry <= 0:
            warnings.append(f"{bond.isin}: купон ниже ключевой ставки (carry {carry:.2f} п.п.)")

    if bond.amortized:
        warnings.append(f"{bond.isin}: амортизация может менять YTM/дюрацию")
    if bond.offer_date is not None:
        ref = now or date.today()
        delta = (bond.offer_date - ref).days
        if 0 <= delta <= 365:
            warnings.append(f"{bond.isin}: оферта через {delta} дн. — риск вероятностного отказа")
    horizon = max(1, (bond.maturity_date - (now or date.today())).days) if bond.maturity_date else None
    if horizon is not None and horizon <= 90:
        warnings.append(f"{bond.isin}: погашение через {horizon} дн. — инструмент короткий")

    return BondValuation(
        isin=bond.isin,
        name=bond.name,
        ytm_pct=ytm,
        after_tax_ytm_pct=after_tax,
        duration_years=duration,
        modified_duration=mod_duration,
        g_spread_bp=g_spread,
        z_spread_bp=z_spread,
        carry_pct=carry,
        tax_rate=tax_rate,
        amortized=bool(bond.amortized),
        warnings=tuple(warnings),
        formulas=tuple(formulas),
    )
