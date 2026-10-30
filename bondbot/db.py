from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from bondbot.models import Bond, Coupon, PortfolioPosition

SCHEMA = """
CREATE TABLE IF NOT EXISTS bonds (
    isin TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    issuer TEXT,
    price_pct REAL,
    ytm_pct REAL,
    current_coupon_yield_pct REAL,
    annual_coupon_yield_pct REAL,
    rating TEXT,
    g_spread_bp REAL,
    volume_mn_rub REAL,
    coupon_rub REAL,
    coupon_freq REAL,
    nkd_rub REAL,
    duration_years REAL,
    next_coupon_date TEXT,
    placement_date TEXT,
    maturity_date TEXT,
    offer_date TEXT,
    years_to_maturity REAL,
    face_value REAL,
    issue_size_rub REAL,
    qual_only INTEGER,
    amortized INTEGER,
    source_url TEXT,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS coupons (
    isin TEXT NOT NULL,
    coupon_date TEXT NOT NULL,
    value_rub REAL,
    yield_pct REAL,
    PRIMARY KEY (isin, coupon_date)
);

CREATE TABLE IF NOT EXISTS watchlist (
    isin TEXT PRIMARY KEY,
    note TEXT NOT NULL DEFAULT '',
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    isin TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    qty REAL NOT NULL,
    buy_price_pct REAL,
    current_price_pct REAL,
    ytm_pct REAL,
    rating TEXT,
    g_spread_bp REAL,
    coupon_rub REAL,
    coupon_freq REAL,
    annual_coupon_rub REAL,
    current_value_rub REAL,
    next_coupon_date TEXT,
    source_url TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _date_iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _row_to_bond(row: sqlite3.Row) -> Bond:
    data = dict(row)
    for key in ("next_coupon_date", "placement_date", "maturity_date", "offer_date"):
        data[key] = _parse_date(data.get(key))
    if data.get("qual_only") is not None:
        data["qual_only"] = bool(data["qual_only"])
    if data.get("amortized") is not None:
        data["amortized"] = bool(data["amortized"])
    fetched = data.get("fetched_at")
    if fetched:
        try:
            data["fetched_at"] = datetime.fromisoformat(fetched)
        except ValueError:
            pass
    return Bond(**{key: value for key, value in data.items() if key in Bond.__dataclass_fields__})


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        columns = {
            row[1]
            for row in self.conn.execute("PRAGMA table_info(positions)").fetchall()
        }
        if columns and "annual_coupon_rub" not in columns:
            self.conn.execute("ALTER TABLE positions ADD COLUMN annual_coupon_rub REAL")

    def close(self) -> None:
        self.conn.close()

    def upsert_bonds(self, bonds: list[Bond]) -> int:
        query = """
        INSERT INTO bonds (
            isin, name, issuer, price_pct, ytm_pct, current_coupon_yield_pct,
            annual_coupon_yield_pct, rating, g_spread_bp, volume_mn_rub,
            coupon_rub, coupon_freq, nkd_rub, duration_years, next_coupon_date,
            placement_date, maturity_date, offer_date, years_to_maturity,
            face_value, issue_size_rub, qual_only, amortized, source_url, fetched_at
        ) VALUES (
            :isin, :name, :issuer, :price_pct, :ytm_pct, :current_coupon_yield_pct,
            :annual_coupon_yield_pct, :rating, :g_spread_bp, :volume_mn_rub,
            :coupon_rub, :coupon_freq, :nkd_rub, :duration_years, :next_coupon_date,
            :placement_date, :maturity_date, :offer_date, :years_to_maturity,
            :face_value, :issue_size_rub, :qual_only, :amortized, :source_url, :fetched_at
        )
        ON CONFLICT(isin) DO UPDATE SET
            name = excluded.name,
            issuer = COALESCE(excluded.issuer, bonds.issuer),
            price_pct = COALESCE(excluded.price_pct, bonds.price_pct),
            ytm_pct = COALESCE(excluded.ytm_pct, bonds.ytm_pct),
            current_coupon_yield_pct = COALESCE(excluded.current_coupon_yield_pct, bonds.current_coupon_yield_pct),
            annual_coupon_yield_pct = COALESCE(excluded.annual_coupon_yield_pct, bonds.annual_coupon_yield_pct),
            rating = COALESCE(excluded.rating, bonds.rating),
            g_spread_bp = COALESCE(excluded.g_spread_bp, bonds.g_spread_bp),
            volume_mn_rub = COALESCE(excluded.volume_mn_rub, bonds.volume_mn_rub),
            coupon_rub = COALESCE(excluded.coupon_rub, bonds.coupon_rub),
            coupon_freq = COALESCE(excluded.coupon_freq, bonds.coupon_freq),
            nkd_rub = COALESCE(excluded.nkd_rub, bonds.nkd_rub),
            duration_years = COALESCE(excluded.duration_years, bonds.duration_years),
            next_coupon_date = COALESCE(excluded.next_coupon_date, bonds.next_coupon_date),
            placement_date = COALESCE(excluded.placement_date, bonds.placement_date),
            maturity_date = COALESCE(excluded.maturity_date, bonds.maturity_date),
            offer_date = COALESCE(excluded.offer_date, bonds.offer_date),
            years_to_maturity = COALESCE(excluded.years_to_maturity, bonds.years_to_maturity),
            face_value = COALESCE(excluded.face_value, bonds.face_value),
            issue_size_rub = COALESCE(excluded.issue_size_rub, bonds.issue_size_rub),
            qual_only = COALESCE(excluded.qual_only, bonds.qual_only),
            amortized = COALESCE(excluded.amortized, bonds.amortized),
            source_url = excluded.source_url,
            fetched_at = excluded.fetched_at
        """
        rows = []
        for bond in bonds:
            rows.append(
                {
                    "isin": bond.isin,
                    "name": bond.name,
                    "issuer": bond.issuer,
                    "price_pct": bond.price_pct,
                    "ytm_pct": bond.ytm_pct,
                    "current_coupon_yield_pct": bond.current_coupon_yield_pct,
                    "annual_coupon_yield_pct": bond.annual_coupon_yield_pct,
                    "rating": bond.rating,
                    "g_spread_bp": bond.g_spread_bp,
                    "volume_mn_rub": bond.volume_mn_rub,
                    "coupon_rub": bond.coupon_rub,
                    "coupon_freq": bond.coupon_freq,
                    "nkd_rub": bond.nkd_rub,
                    "duration_years": bond.duration_years,
                    "next_coupon_date": _date_iso(bond.next_coupon_date),
                    "placement_date": _date_iso(bond.placement_date),
                    "maturity_date": _date_iso(bond.maturity_date),
                    "offer_date": _date_iso(bond.offer_date),
                    "years_to_maturity": bond.years_to_maturity,
                    "face_value": bond.face_value,
                    "issue_size_rub": bond.issue_size_rub,
                    "qual_only": int(bond.qual_only) if bond.qual_only is not None else None,
                    "amortized": int(bond.amortized) if bond.amortized is not None else None,
                    "source_url": bond.source_url,
                    "fetched_at": bond.fetched_at.isoformat(),
                }
            )
        with self.conn:
            self.conn.executemany(query, rows)
        return len(rows)

    def get_bond(self, isin: str) -> Bond | None:
        row = self.conn.execute("SELECT * FROM bonds WHERE isin = ?", (isin,)).fetchone()
        return _row_to_bond(row) if row else None

    def list_bonds(self) -> list[Bond]:
        rows = self.conn.execute("SELECT * FROM bonds").fetchall()
        return [_row_to_bond(row) for row in rows]

    def upsert_coupons(self, coupons: list[Coupon]) -> int:
        query = """
        INSERT INTO coupons (isin, coupon_date, value_rub, yield_pct)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(isin, coupon_date) DO UPDATE SET
            value_rub = COALESCE(excluded.value_rub, coupons.value_rub),
            yield_pct = COALESCE(excluded.yield_pct, coupons.yield_pct)
        """
        rows = [
            (coupon.isin, coupon.coupon_date.isoformat(), coupon.value_rub, coupon.yield_pct)
            for coupon in coupons
        ]
        with self.conn:
            self.conn.executemany(query, rows)
        return len(rows)

    def coupons(self, isin: str) -> list[Coupon]:
        rows = self.conn.execute(
            "SELECT * FROM coupons WHERE isin = ? ORDER BY coupon_date", (isin,)
        ).fetchall()
        return [
            Coupon(
                isin=row["isin"],
                coupon_date=date.fromisoformat(row["coupon_date"]),
                value_rub=row["value_rub"],
                yield_pct=row["yield_pct"],
            )
            for row in rows
        ]

    def add_watch(self, isin: str, note: str = "") -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO watchlist (isin, note, added_at) VALUES (?, ?, ?) "
                "ON CONFLICT(isin) DO UPDATE SET note = excluded.note",
                (isin.upper(), note, datetime.now(timezone.utc).isoformat()),
            )

    def remove_watch(self, isin: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM watchlist WHERE isin = ?", (isin.upper(),))

    def watchlist(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT w.isin, w.note, w.added_at, b.* FROM watchlist w "
            "LEFT JOIN bonds b ON b.isin = w.isin ORDER BY w.added_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def upsert_positions(self, positions: list[PortfolioPosition]) -> int:
        query = """
        INSERT INTO positions (
            isin, name, qty, buy_price_pct, current_price_pct, ytm_pct, rating,
            g_spread_bp, coupon_rub, coupon_freq, annual_coupon_rub, current_value_rub,
            next_coupon_date, source_url, updated_at
        ) VALUES (
            :isin, :name, :qty, :buy_price_pct, :current_price_pct, :ytm_pct, :rating,
            :g_spread_bp, :coupon_rub, :coupon_freq, :annual_coupon_rub, :current_value_rub,
            :next_coupon_date, :source_url, :updated_at
        )
        ON CONFLICT(isin) DO UPDATE SET
            name = excluded.name,
            qty = excluded.qty,
            buy_price_pct = COALESCE(excluded.buy_price_pct, positions.buy_price_pct),
            current_price_pct = COALESCE(excluded.current_price_pct, positions.current_price_pct),
            ytm_pct = COALESCE(excluded.ytm_pct, positions.ytm_pct),
            rating = COALESCE(excluded.rating, positions.rating),
            g_spread_bp = COALESCE(excluded.g_spread_bp, positions.g_spread_bp),
            coupon_rub = COALESCE(excluded.coupon_rub, positions.coupon_rub),
            coupon_freq = COALESCE(excluded.coupon_freq, positions.coupon_freq),
            annual_coupon_rub = COALESCE(excluded.annual_coupon_rub, positions.annual_coupon_rub),
            current_value_rub = COALESCE(excluded.current_value_rub, positions.current_value_rub),
            next_coupon_date = COALESCE(excluded.next_coupon_date, positions.next_coupon_date),
            source_url = excluded.source_url,
            updated_at = excluded.updated_at
        """
        rows = []
        now = datetime.now(timezone.utc).isoformat()
        for position in positions:
            rows.append(
                {
                    "isin": position.isin,
                    "name": position.name,
                    "qty": position.qty,
                    "buy_price_pct": position.buy_price_pct,
                    "current_price_pct": position.current_price_pct,
                    "ytm_pct": position.ytm_pct,
                    "rating": position.rating,
                    "g_spread_bp": position.g_spread_bp,
                    "coupon_rub": position.coupon_rub,
                    "coupon_freq": position.coupon_freq,
                    "annual_coupon_rub": position.annual_coupon_rub,
                    "current_value_rub": position.current_value_rub,
                    "next_coupon_date": _date_iso(position.next_coupon_date),
                    "source_url": position.source_url,
                    "updated_at": now,
                }
            )
        with self.conn:
            self.conn.executemany(query, rows)
        return len(rows)

    def positions(self) -> list[PortfolioPosition]:
        rows = self.conn.execute("SELECT * FROM positions ORDER BY updated_at").fetchall()
        result: list[PortfolioPosition] = []
        for row in rows:
            data = dict(row)
            data["maturity_date"] = None
            data["next_coupon_date"] = _parse_date(data.get("next_coupon_date"))
            data.pop("updated_at", None)
            result.append(
                PortfolioPosition(
                    **{key: value for key, value in data.items() if key in PortfolioPosition.__dataclass_fields__}
                )
            )
        return result

    def remove_position(self, isin: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM positions WHERE isin = ?", (isin.upper(),))

    def portfolio_totals(self) -> dict[str, float]:
        rows = self.conn.execute(
            "SELECT qty, buy_price_pct, current_value_rub, coupon_rub, coupon_freq, annual_coupon_rub FROM positions"
        ).fetchall()
        total_value = 0.0
        total_cost = 0.0
        annual_coupon = 0.0
        for row in rows:
            qty = row["qty"] or 0
            current = row["current_value_rub"]
            if current is None and row["buy_price_pct"] is not None:
                current = qty * row["buy_price_pct"] / 100 * 1000
            total_value += current or 0
            if row["buy_price_pct"] is not None:
                total_cost += qty * row["buy_price_pct"] / 100 * 1000
            if row["annual_coupon_rub"] is not None:
                annual_coupon += row["annual_coupon_rub"]
            elif row["coupon_rub"] is not None and row["coupon_freq"] is not None:
                annual_coupon += row["coupon_rub"] * row["coupon_freq"] * qty
        return {
            "total_value_rub": total_value,
            "total_cost_rub": total_cost,
            "profit_rub": total_value - total_cost,
            "annual_coupon_rub": annual_coupon,
        }

    def kv_get(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def kv_set(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
