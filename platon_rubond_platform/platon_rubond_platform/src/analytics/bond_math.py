"""
Класс BondAnalyzer — финансовая математика облигаций РФ.

Улучшения:
  1. Точная YTM через Newton-Raphson (IRR)
  2. Поддержка амортизируемых выпусков
  3. НКД (accrued interest) — dirty / clean price
  4. Кредитный спред и упрощённый Z-spread
  5. Налоговая корректировка (net yield)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.analytics.bond")

RATING_ORDER: List[str] = [
    "AAA", "AA+", "AA", "AA-", "A+", "A", "A-",
    "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
    "B+", "B", "B-", "CCC", "CC", "C", "D", "NR",
]

# Параметры Newton-Raphson
_NR_MAX_ITER = 100
_NR_TOL = 1e-8
_NR_INITIAL_GUESS = 0.10


class BondAnalyzer:
    """
    Аналитика параметров доходности облигаций РФ.

    Публичные методы
    ----------------
    calculate_ytm              — точная YTM (Newton-Raphson) + fallback на простую
    calculate_simple_ytm       — линейная аппроксимация
    estimate_floater_yield     — оценка доходности флоатера
    calculate_current_yield    — текущая купонная доходность
    calculate_z_spread         — упрощённый Z-spread к безрисковой ставке
    calculate_credit_spread    — спред над ключевой ставкой / RUONIA
    apply_tax                  — net-доходность после НДФЛ
    filter_by_risk / filter_by_rating
    build_cashflows            — построение графика денежных потоков
    """

    # ------------------------------------------------------------------
    # 1. Точная YTM (Newton-Raphson)
    # ------------------------------------------------------------------

    def calculate_ytm(
        self,
        bond_data: Dict[str, Any],
        *,
        use_dirty_price: bool = True,
        tax_rate: float = 0.0,
    ) -> Optional[float]:
        """
        Точная доходность к погашению/оферте методом Newton-Raphson.

        Решает уравнение NPV(r) = 0, где
            NPV(r) = Σ CF_t / (1+r)^(t/365)  −  dirty_price

        При неудаче итераций возвращает простую (линейную) оценку.

        Параметры
        ----------
        bond_data : dict
            current_price, face_value, nearest_coupon_value, coupon_period,
            maturity_date | offer_date, accrued_interest (опционально),
            amortization_schedule (опционально) — list[{date, amount}]
        use_dirty_price : bool
            Если True и есть НКД — цена += accrued_interest
        tax_rate : float
            Ставка налога на купонный доход (0.13 для физлиц РФ).
            Применяется только к купонной части cash-flow.

        Returns
        -------
        float | None
            YTM в долях, округлённая до 4 знаков.
        """
        try:
            price_rub = self._price_to_rub(bond_data)
            if price_rub is None or price_rub <= 0:
                return None

            accrued = self._safe_float(bond_data.get("accrued_interest"), default=0.0) or 0.0
            dirty = price_rub + accrued if use_dirty_price else price_rub

            cashflows = self.build_cashflows(bond_data, tax_rate=tax_rate)
            if not cashflows:
                logger.warning("calculate_ytm: пустой график cash-flow — fallback")
                return self.calculate_simple_ytm(bond_data)

            ytm = self._newton_raphson_ytm(dirty, cashflows)
            if ytm is None:
                return self.calculate_simple_ytm(bond_data)
            return round(ytm, 4)

        except Exception as exc:
            logger.exception("calculate_ytm: ошибка — %s", exc)
            return self.calculate_simple_ytm(bond_data)

    def calculate_simple_ytm(self, bond_data: Dict[str, Any]) -> Optional[float]:
        """
        Линейная аппроксимация YTM (быстрый fallback).

        YTM ≈ (Σ купонов + (номинал − цена)) / цена / годы
        """
        try:
            price_rub = self._price_to_rub(bond_data)
            face = self._safe_float(bond_data.get("face_value"), default=1000.0) or 1000.0
            coupon = self._safe_float(bond_data.get("nearest_coupon_value"), default=0.0) or 0.0
            period = self._safe_int(bond_data.get("coupon_period"), default=182)

            if price_rub is None or price_rub <= 0:
                logger.warning("calculate_simple_ytm: некорректная цена")
                return None

            target = self._parse_date(
                bond_data.get("offer_date") or bond_data.get("maturity_date")
            )
            if target is None:
                return None

            days = (target - date.today()).days
            if days <= 0:
                return None

            remaining = bond_data.get("remaining_coupons")
            if remaining is None:
                remaining = max(1, round(days / period)) if period > 0 else 1
            remaining = max(1, int(remaining))

            # Остаточный номинал с учётом амортизации
            residual_face = self._residual_face(bond_data, face)

            total_coupons = coupon * remaining
            capital_gain = residual_face - price_rub
            years = days / 365.0
            if years <= 0:
                return None

            return round((total_coupons + capital_gain) / price_rub / years, 4)

        except Exception as exc:
            logger.exception("calculate_simple_ytm: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 2. Построение cash-flow (в т.ч. амортизация)
    # ------------------------------------------------------------------

    def build_cashflows(
        self,
        bond_data: Dict[str, Any],
        *,
        tax_rate: float = 0.0,
    ) -> List[Tuple[float, float]]:
        """
        Строит список (days_from_today, cash_flow_rub).

        Поддерживает:
          - регулярные купоны
          - амортизацию номинала (amortization_schedule)
          - налог на купонную часть (tax_rate)

        Returns
        -------
        list[tuple[float, float]]
            [(days, cf), ...] отсортированный по days > 0
        """
        face = self._safe_float(bond_data.get("face_value"), default=1000.0) or 1000.0
        coupon = self._safe_float(bond_data.get("nearest_coupon_value"), default=0.0) or 0.0
        period = self._safe_int(bond_data.get("coupon_period"), default=182)
        if period <= 0:
            period = 182

        target = self._parse_date(
            bond_data.get("offer_date") or bond_data.get("maturity_date")
        )
        if target is None:
            return []

        today = date.today()
        total_days = (target - today).days
        if total_days <= 0:
            return []

        # График амортизации: {date → amount}
        amort_map: Dict[date, float] = {}
        schedule = bond_data.get("amortization_schedule") or []
        for item in schedule:
            d = self._parse_date(item.get("date"))
            amt = self._safe_float(item.get("amount"), default=0.0) or 0.0
            if d and amt > 0:
                amort_map[d] = amt

        net_coupon = coupon * (1.0 - tax_rate)
        flows: List[Tuple[float, float]] = []

        # Купонные даты
        n_coupons = max(1, round(total_days / period))
        for i in range(1, n_coupons + 1):
            days_i = min(i * period, total_days)
            cf_date = today + timedelta(days=int(days_i))
            cf = net_coupon
            # Амортизация в эту дату
            if cf_date in amort_map:
                cf += amort_map.pop(cf_date)
            elif i == n_coupons:
                # Финальное погашение остатка
                residual = self._residual_face(bond_data, face)
                # Вычитаем уже учтённую амортизацию
                already = sum(amort_map.values())  # оставшиеся (не попавшие)
                cf += max(0.0, residual - already)
            flows.append((float(days_i), cf))

        # Оставшиеся амортизации, не совпавшие с купонными датами
        for d, amt in sorted(amort_map.items()):
            days_a = (d - today).days
            if days_a > 0:
                flows.append((float(days_a), amt))

        flows.sort(key=lambda x: x[0])
        return flows

    # ------------------------------------------------------------------
    # 3. НКД / dirty-clean helpers
    # ------------------------------------------------------------------

    def dirty_price(self, bond_data: Dict[str, Any]) -> Optional[float]:
        """Грязная цена = чистая цена (в рублях) + НКД."""
        clean = self._price_to_rub(bond_data)
        if clean is None:
            return None
        accrued = self._safe_float(bond_data.get("accrued_interest"), default=0.0) or 0.0
        return round(clean + accrued, 4)

    def clean_price(self, bond_data: Dict[str, Any]) -> Optional[float]:
        """Чистая цена в рублях (без НКД)."""
        return self._price_to_rub(bond_data)

    # ------------------------------------------------------------------
    # 4. Z-spread и кредитный спред
    # ------------------------------------------------------------------

    def calculate_z_spread(
        self,
        bond_data: Dict[str, Any],
        risk_free_rate: float,
    ) -> Optional[float]:
        """
        Упрощённый Z-spread: постоянный спред z над плоской безрисковой кривой,
        при котором NPV dirty-price = 0.

            dirty = Σ CF_t / (1 + r_f + z)^(t/365)

        Решается Newton-Raphson по z.

        Параметры
        ----------
        risk_free_rate : float
            Безрисковая ставка в долях (например, YTM ОФЗ той же дюрации
            или текущая ключевая ставка / RUONIA).

        Returns
        -------
        float | None
            Z-spread в долях.
        """
        try:
            if risk_free_rate is None or risk_free_rate < 0:
                return None

            dirty = self.dirty_price(bond_data)
            if dirty is None or dirty <= 0:
                return None

            cashflows = self.build_cashflows(bond_data)
            if not cashflows:
                return None

            def npv(z: float) -> float:
                total = 0.0
                for days, cf in cashflows:
                    total += cf / ((1.0 + risk_free_rate + z) ** (days / 365.0))
                return total - dirty

            def d_npv(z: float) -> float:
                total = 0.0
                for days, cf in cashflows:
                    t = days / 365.0
                    total += -t * cf / ((1.0 + risk_free_rate + z) ** (t + 1.0))
                return total

            z = 0.01
            for _ in range(_NR_MAX_ITER):
                f = npv(z)
                df = d_npv(z)
                if abs(df) < 1e-14:
                    break
                z_new = z - f / df
                if abs(z_new - z) < _NR_TOL:
                    return round(z_new, 4)
                z = z_new

            return round(z, 4) if abs(npv(z)) < 1e-4 else None

        except Exception as exc:
            logger.exception("calculate_z_spread: %s", exc)
            return None

    def calculate_credit_spread(
        self,
        bond_data: Dict[str, Any],
        benchmark_rate: float,
    ) -> Optional[float]:
        """
        Простой кредитный спред = YTM облигации − benchmark_rate.

        benchmark_rate — ключевая ставка ЦБ, RUONIA или YTM ОФЗ.
        """
        ytm = self.calculate_ytm(bond_data)
        if ytm is None or benchmark_rate is None:
            return None
        return round(ytm - benchmark_rate, 4)

    # ------------------------------------------------------------------
    # 5. Налоги
    # ------------------------------------------------------------------

    def apply_tax(self, yield_value: Optional[float], tax_rate: float = 0.13) -> Optional[float]:
        """
        Net-доходность после налога на купонный доход.

        Упрощённо: yield_net = yield_gross * (1 − tax_rate).
        Для более точного учёта используйте calculate_ytm(..., tax_rate=...).
        """
        if yield_value is None:
            return None
        if tax_rate < 0 or tax_rate >= 1:
            logger.warning("apply_tax: некорректная tax_rate %s", tax_rate)
            return yield_value
        return round(yield_value * (1.0 - tax_rate), 4)

    # ------------------------------------------------------------------
    # Флоатеры / текущая доходность / фильтры (без изменений логики)
    # ------------------------------------------------------------------

    def estimate_floater_yield(
        self,
        bond_data: Dict[str, Any],
        current_key_rate: float,
    ) -> Optional[float]:
        """
        Оценка текущей доходности флоатера.
        1) key_rate + spread  2) годовой купон / face  3) key_rate
        """
        try:
            if current_key_rate is None or current_key_rate < 0:
                logger.warning("estimate_floater_yield: некорректная key_rate")
                return None

            spread = self._safe_float(
                bond_data.get("spread") or bond_data.get("margin")
            )
            if spread is not None:
                return round(current_key_rate + spread, 4)

            coupon = self._safe_float(bond_data.get("nearest_coupon_value"))
            period = self._safe_int(bond_data.get("coupon_period"), default=0)
            face = self._safe_float(bond_data.get("face_value"), default=1000.0)

            if coupon is not None and period > 0 and face and face > 0:
                annual = coupon * (365.0 / period)
                return round(annual / face, 4)

            return round(float(current_key_rate), 4)

        except Exception as exc:
            logger.exception("estimate_floater_yield: %s", exc)
            return None

    def calculate_current_yield(self, bond_data: Dict[str, Any]) -> Optional[float]:
        """Текущая купонная доходность = годовой купон / цена в рублях."""
        try:
            price_rub = self._price_to_rub(bond_data)
            coupon = self._safe_float(bond_data.get("nearest_coupon_value"), default=0.0) or 0.0
            period = self._safe_int(bond_data.get("coupon_period"), default=365)
            if price_rub is None or price_rub <= 0:
                return None
            if period <= 0:
                period = 365
            annual = coupon * (365.0 / period)
            return round(annual / price_rub, 4)
        except Exception as exc:
            logger.exception("calculate_current_yield: %s", exc)
            return None

    def filter_by_risk(
        self,
        bond_list: List[Dict[str, Any]],
        max_risk_level: str = "BBB-",
    ) -> List[Dict[str, Any]]:
        """Отсекает ВДО и бумаги с рейтингом ниже max_risk_level."""
        if not bond_list:
            return []
        max_idx = self._rating_index(max_risk_level)
        if max_idx is None:
            return list(bond_list)

        result: List[Dict[str, Any]] = []
        for bond in bond_list:
            if bond.get("is_vdo") is True:
                continue
            rating = (
                bond.get("rating")
                or bond.get("credit_rating")
                or bond.get("rating_acra")
                or bond.get("rating_raex")
                or "NR"
            )
            idx = self._rating_index(str(rating))
            if idx is None or idx > max_idx:
                continue
            result.append(bond)
        logger.info(
            "filter_by_risk: %d → %d (max_risk=%s)",
            len(bond_list), len(result), max_risk_level,
        )
        return result

    def filter_by_rating(
        self, bonds: List[Dict[str, Any]], min_rating: str = "BBB-"
    ) -> List[Dict[str, Any]]:
        return self.filter_by_risk(bonds, max_risk_level=min_rating)

    # ------------------------------------------------------------------
    # Newton-Raphson core
    # ------------------------------------------------------------------

    def _newton_raphson_ytm(
        self,
        dirty_price: float,
        cashflows: Sequence[Tuple[float, float]],
    ) -> Optional[float]:
        """Итеративный поиск r: NPV(r) = 0."""

        def npv(r: float) -> float:
            total = 0.0
            for days, cf in cashflows:
                total += cf / ((1.0 + r) ** (days / 365.0))
            return total - dirty_price

        def d_npv(r: float) -> float:
            total = 0.0
            for days, cf in cashflows:
                t = days / 365.0
                total += -t * cf / ((1.0 + r) ** (t + 1.0))
            return total

        r = _NR_INITIAL_GUESS
        for _ in range(_NR_MAX_ITER):
            f = npv(r)
            df = d_npv(r)
            if abs(df) < 1e-14:
                break
            r_new = r - f / df
            # Ограничиваем разумный диапазон
            r_new = max(-0.5, min(r_new, 5.0))
            if abs(r_new - r) < _NR_TOL:
                return r_new
            r = r_new

        return r if abs(npv(r)) < 1e-4 else None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _price_to_rub(self, bond_data: Dict[str, Any]) -> Optional[float]:
        """Перевод цены Мосбиржи (% от номинала) в рубли."""
        price = self._safe_float(bond_data.get("current_price"))
        face = self._safe_float(bond_data.get("face_value"), default=1000.0) or 1000.0
        if price is None or price <= 0:
            return None
        if price <= 200:
            return price / 100.0 * face
        return price

    def _residual_face(self, bond_data: Dict[str, Any], original_face: float) -> float:
        """Остаточный номинал с учётом уже прошедшей амортизации."""
        residual = self._safe_float(bond_data.get("residual_face_value"))
        if residual is not None and residual > 0:
            return residual
        schedule = bond_data.get("amortization_schedule") or []
        paid = sum(
            self._safe_float(item.get("amount"), default=0.0) or 0.0
            for item in schedule
            if self._parse_date(item.get("date"))
            and self._parse_date(item.get("date")) <= date.today()  # type: ignore[operator]
        )
        return max(0.0, original_face - paid)

    @staticmethod
    def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        if value is None or value == "":
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if value is None or value in ("", "0000-00-00"):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _rating_index(rating: str) -> Optional[int]:
        if not rating:
            return RATING_ORDER.index("NR")
        r = rating.strip().upper().replace(" ", "")
        aliases = {
            "ААА": "AAA", "АА+": "AA+", "АА": "AA", "АА-": "AA-",
            "А+": "A+", "А": "A", "А-": "A-",
            "ВВВ+": "BBB+", "ВВВ": "BBB", "ВВВ-": "BBB-",
            "ВВ+": "BB+", "ВВ": "BB", "ВВ-": "BB-",
            "В+": "B+", "В": "B", "В-": "B-",
            "NO RATING": "NR", "UNRATED": "NR", "N/R": "NR",
        }
        r = aliases.get(r, r)
        try:
            return RATING_ORDER.index(r)
        except ValueError:
            return None
