"""
Класс PortfolioManager — управление портфелем облигаций.

Улучшения:
  5. Персистентность позиций в SQLite
  6. Налоговая корректировка метрик (tax_rate)
  7. Интеграция с макро-ставкой для флоатеров (через active_bonds_data)
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.analytics.portfolio")

DEFAULT_MAX_POSITION_WEIGHT = 0.20
DEFAULT_DB_PATH = "portfolio.db"


class PortfolioManager:
    """
    Моделирование, контроль и персистентное хранение портфеля
    рублёвых облигаций.
    """

    def __init__(
        self,
        max_position_weight: float = DEFAULT_MAX_POSITION_WEIGHT,
        db_path: Optional[str] = None,
        tax_rate: float = 0.0,
        auto_load: bool = True,
    ) -> None:
        """
        Параметры
        ----------
        max_position_weight : float
            Порог концентрации одной позиции / эмитента
        db_path : str | None
            Путь к SQLite-файлу. None → только in-memory
        tax_rate : float
            Ставка НДФЛ на купонный доход (0.13 для физлиц)
        auto_load : bool
            Загружать позиции из БД при инициализации
        """
        self.positions: List[Dict[str, Any]] = []
        self.max_position_weight = max_position_weight
        self.tax_rate = tax_rate
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

        if db_path:
            self._init_db()
            if auto_load:
                self.load_from_db()

    # ------------------------------------------------------------------
    # 5. SQLite persistence
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        if not self.db_path:
            return
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio_positions (
                isin          TEXT PRIMARY KEY,
                secid         TEXT,
                shortname     TEXT,
                quantity      REAL NOT NULL,
                purchase_price REAL NOT NULL,
                issuer        TEXT DEFAULT 'unknown',
                sector        TEXT DEFAULT 'unknown',
                updated_at    TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
        logger.info("PortfolioManager: SQLite инициализирован (%s)", self.db_path)

    def _persist_position(self, pos: Dict[str, Any]) -> None:
        if not self._conn:
            return
        self._conn.execute(
            """
            INSERT INTO portfolio_positions
                (isin, secid, shortname, quantity, purchase_price, issuer, sector, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(isin) DO UPDATE SET
                secid=excluded.secid,
                shortname=excluded.shortname,
                quantity=excluded.quantity,
                purchase_price=excluded.purchase_price,
                issuer=excluded.issuer,
                sector=excluded.sector,
                updated_at=excluded.updated_at
            """,
            (
                pos["isin"],
                pos.get("secid"),
                pos.get("shortname"),
                pos["quantity"],
                pos["purchase_price"],
                pos.get("issuer", "unknown"),
                pos.get("sector", "unknown"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def _delete_position_db(self, isin: str) -> None:
        if not self._conn:
            return
        self._conn.execute(
            "DELETE FROM portfolio_positions WHERE isin = ?", (isin,)
        )
        self._conn.commit()

    def load_from_db(self) -> int:
        """Загружает позиции из SQLite. Возвращает количество."""
        if not self._conn:
            return 0
        rows = self._conn.execute(
            "SELECT * FROM portfolio_positions"
        ).fetchall()
        self.positions = [
            {
                "isin": r["isin"],
                "secid": r["secid"] or r["isin"],
                "shortname": r["shortname"] or r["isin"],
                "quantity": r["quantity"],
                "purchase_price": r["purchase_price"],
                "issuer": r["issuer"] or "unknown",
                "sector": r["sector"] or "unknown",
            }
            for r in rows
        ]
        logger.info("PortfolioManager: загружено %d позиций из БД", len(self.positions))
        return len(self.positions)

    def save_to_db(self) -> None:
        """Принудительно сохраняет все текущие позиции."""
        if not self._conn:
            return
        for pos in self.positions:
            self._persist_position(pos)
        logger.info("PortfolioManager: сохранено %d позиций", len(self.positions))

    # ------------------------------------------------------------------
    # Управление позициями
    # ------------------------------------------------------------------

    def add_to_portfolio(
        self,
        isin: str,
        quantity: float,
        purchase_price: float,
        *,
        secid: Optional[str] = None,
        shortname: Optional[str] = None,
        issuer: Optional[str] = None,
        sector: Optional[str] = None,
    ) -> bool:
        """Добавляет или увеличивает позицию (с персистентностью)."""
        if not isin or not isinstance(isin, str):
            logger.warning("add_to_portfolio: пустой ISIN")
            return False
        try:
            qty = float(quantity)
            price = float(purchase_price)
        except (TypeError, ValueError):
            logger.warning("add_to_portfolio: некорректные quantity/price")
            return False
        if qty <= 0 or price <= 0:
            logger.warning(
                "add_to_portfolio: qty и price должны быть > 0 (qty=%s, price=%s)",
                qty, price,
            )
            return False

        isin = isin.strip().upper()

        for pos in self.positions:
            if pos["isin"] == isin:
                old_qty = pos["quantity"]
                old_cost = old_qty * pos["purchase_price"]
                new_cost = qty * price
                pos["quantity"] = old_qty + qty
                pos["purchase_price"] = round(
                    (old_cost + new_cost) / pos["quantity"], 4
                )
                if shortname:
                    pos["shortname"] = shortname
                if issuer:
                    pos["issuer"] = issuer
                if sector:
                    pos["sector"] = sector
                self._persist_position(pos)
                logger.info(
                    "add_to_portfolio: увеличена %s → qty=%.2f", isin, pos["quantity"]
                )
                return True

        new_pos = {
            "isin": isin,
            "secid": secid or isin,
            "shortname": shortname or isin,
            "quantity": qty,
            "purchase_price": price,
            "issuer": issuer or "unknown",
            "sector": sector or "unknown",
        }
        self.positions.append(new_pos)
        self._persist_position(new_pos)
        logger.info("add_to_portfolio: новая позиция %s qty=%.2f", isin, qty)
        return True

    def remove_from_portfolio(self, isin: str, quantity: Optional[float] = None) -> bool:
        """Удаляет позицию целиком или уменьшает quantity."""
        isin = isin.strip().upper()
        for i, pos in enumerate(self.positions):
            if pos["isin"] != isin:
                continue
            if quantity is None or quantity >= pos["quantity"]:
                self.positions.pop(i)
                self._delete_position_db(isin)
                logger.info("remove_from_portfolio: удалена %s", isin)
                return True
            pos["quantity"] -= quantity
            self._persist_position(pos)
            logger.info(
                "remove_from_portfolio: %s qty → %.2f", isin, pos["quantity"]
            )
            return True
        logger.warning("remove_from_portfolio: %s не найдена", isin)
        return False

    def add_position(self, bond: Dict[str, Any], weight: float = 0.0) -> bool:
        """Обёртка для обратной совместимости."""
        isin = bond.get("isin") or bond.get("secid")
        qty = bond.get("quantity") or bond.get("qty") or 1.0
        price = bond.get("purchase_price") or bond.get("current_price") or 100.0
        return self.add_to_portfolio(
            isin=str(isin),
            quantity=float(qty),
            purchase_price=float(price),
            secid=bond.get("secid"),
            shortname=bond.get("shortname"),
            issuer=bond.get("issuer"),
            sector=bond.get("sector"),
        )

    # ------------------------------------------------------------------
    # Метрики (с налогом)
    # ------------------------------------------------------------------

    def calculate_portfolio_metrics(
        self,
        active_bonds_data: List[Dict[str, Any]],
        *,
        tax_rate: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Ключевые метрики портфеля.

        tax_rate перекрывает self.tax_rate для расчёта net weighted YTM
        и net купонного календаря.
        """
        effective_tax = tax_rate if tax_rate is not None else self.tax_rate

        empty: Dict[str, Any] = {
            "total_market_value": 0.0,
            "total_cost": 0.0,
            "pnl": 0.0,
            "weighted_ytm": None,
            "weighted_ytm_net": None,
            "positions_count": 0,
            "weights": {},
            "issuer_weights": {},
            "sector_weights": {},
            "diversification_ok": True,
            "concentration_warnings": [],
            "coupon_calendar": {},
            "coupon_calendar_net": {},
            "tax_rate": effective_tax,
        }

        if not self.positions:
            return empty

        market_map: Dict[str, Dict[str, Any]] = {}
        for b in active_bonds_data or []:
            key = (b.get("isin") or b.get("secid") or "").upper()
            if key:
                market_map[key] = b

        total_mv = 0.0
        total_cost = 0.0
        w_yield_sum = 0.0
        w_yield_sum_net = 0.0
        yield_w = 0.0
        position_values: Dict[str, float] = {}
        issuer_values: Dict[str, float] = defaultdict(float)
        sector_values: Dict[str, float] = defaultdict(float)
        coupon_cal: Dict[str, float] = defaultdict(float)
        coupon_cal_net: Dict[str, float] = defaultdict(float)

        for pos in self.positions:
            isin = pos["isin"]
            qty = pos["quantity"]
            cost_price = pos["purchase_price"]
            mkt = market_map.get(isin, {})

            cur_price = self._safe_float(mkt.get("current_price"), default=cost_price)
            face = self._safe_float(mkt.get("face_value"), default=1000.0) or 1000.0

            position_mv = self._position_value(qty, cur_price, face)
            position_cost = self._position_value(qty, cost_price, face)

            total_mv += position_mv
            total_cost += position_cost
            position_values[isin] = position_mv
            issuer_values[pos.get("issuer", "unknown")] += position_mv
            sector_values[pos.get("sector", "unknown")] += position_mv

            ytm = self._safe_float(
                mkt.get("ytm")
                or mkt.get("estimated_yield")
                or mkt.get("current_yield")
            )
            if ytm is not None and position_mv > 0:
                w_yield_sum += ytm * position_mv
                # Net: упрощённо ytm * (1 - tax)
                w_yield_sum_net += ytm * (1.0 - effective_tax) * position_mv
                yield_w += position_mv

            coupon_val = self._safe_float(mkt.get("nearest_coupon_value"), default=0.0) or 0.0
            period = self._safe_int(mkt.get("coupon_period"), default=182)
            next_d = mkt.get("next_coupon_date") or mkt.get("offer_date")
            self._accumulate_coupons(
                coupon_cal, qty, coupon_val, period, next_d, tax=0.0
            )
            self._accumulate_coupons(
                coupon_cal_net, qty, coupon_val, period, next_d, tax=effective_tax
            )

        if total_mv <= 0:
            return empty

        weights = {i: round(v / total_mv, 4) for i, v in position_values.items()}
        issuer_w = {i: round(v / total_mv, 4) for i, v in issuer_values.items()}
        sector_w = {s: round(v / total_mv, 4) for s, v in sector_values.items()}

        warnings: List[str] = []
        for isin, w in weights.items():
            if w > self.max_position_weight:
                warnings.append(
                    f"Концентрация {isin}: {w:.1%} > {self.max_position_weight:.0%}"
                )
        for iss, w in issuer_w.items():
            if w > self.max_position_weight and iss != "unknown":
                warnings.append(
                    f"Эмитент {iss}: {w:.1%} > {self.max_position_weight:.0%}"
                )

        weighted_ytm = (
            round(w_yield_sum / yield_w, 4) if yield_w > 0 else None
        )
        weighted_ytm_net = (
            round(w_yield_sum_net / yield_w, 4) if yield_w > 0 else None
        )

        return {
            "total_market_value": round(total_mv, 2),
            "total_cost": round(total_cost, 2),
            "pnl": round(total_mv - total_cost, 2),
            "weighted_ytm": weighted_ytm,
            "weighted_ytm_net": weighted_ytm_net,
            "positions_count": len(self.positions),
            "weights": weights,
            "issuer_weights": issuer_w,
            "sector_weights": sector_w,
            "diversification_ok": len(warnings) == 0,
            "concentration_warnings": warnings,
            "coupon_calendar": {
                k: round(v, 2) for k, v in sorted(coupon_cal.items())
            },
            "coupon_calendar_net": {
                k: round(v, 2) for k, v in sorted(coupon_cal_net.items())
            },
            "tax_rate": effective_tax,
        }

    def calculate_monthly_coupon_flow(self) -> float:
        """Заглушка обратной совместимости."""
        return 0.0

    def check_diversification(self) -> Dict[str, Any]:
        if not self.positions:
            return {
                "diversification_ok": True,
                "concentration_warnings": [],
                "weights": {},
            }
        total = sum(p["quantity"] * p["purchase_price"] for p in self.positions)
        if total <= 0:
            return {
                "diversification_ok": True,
                "concentration_warnings": [],
                "weights": {},
            }
        weights = {
            p["isin"]: round(p["quantity"] * p["purchase_price"] / total, 4)
            for p in self.positions
        }
        warnings = [
            f"Концентрация {isin}: {w:.1%} > {self.max_position_weight:.0%}"
            for isin, w in weights.items()
            if w > self.max_position_weight
        ]
        return {
            "diversification_ok": len(warnings) == 0,
            "concentration_warnings": warnings,
            "weights": weights,
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        return [dict(p) for p in self.positions]

    def clear(self) -> None:
        isins = [p["isin"] for p in self.positions]
        self.positions.clear()
        for isin in isins:
            self._delete_position_db(isin)
        logger.info("PortfolioManager: портфель очищен")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _position_value(qty: float, price: float, face: float) -> float:
        if price is None:
            return 0.0
        if price > 200:
            return qty * price
        return qty * (price / 100.0) * face

    def _accumulate_coupons(
        self,
        calendar: Dict[str, float],
        qty: float,
        coupon_value: float,
        period: int,
        next_date: Any,
        tax: float = 0.0,
    ) -> None:
        if coupon_value is None or coupon_value <= 0 or period <= 0:
            return
        payment = qty * coupon_value * (1.0 - tax)
        start = self._parse_date(next_date) or date.today()
        horizon = date.today() + timedelta(days=365)
        current = start
        while current < date.today():
            current += timedelta(days=period)
        while current <= horizon:
            key = current.strftime("%Y-%m")
            calendar[key] += payment
            current += timedelta(days=period)

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
