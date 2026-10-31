from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bondbot.data.quality import sanitize_bond, sanitize_position
from bondbot.models import Bond, Coupon, PortfolioPosition

SCHEMA_VERSION = 3

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

CREATE TABLE IF NOT EXISTS strategy_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    formulas_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    version TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_audit_kind
    ON strategy_audit(kind, id);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_job_runs_started
    ON job_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    isin TEXT,
    dedupe_key TEXT NOT NULL UNIQUE,
    message TEXT NOT NULL,
    sent_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_sent
    ON alerts(sent_at, id);

CREATE TABLE IF NOT EXISTS new_issues (
    isin TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL,
    name TEXT,
    is_initial INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_new_issues_seen
    ON new_issues(first_seen DESC);
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


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _row_to_bond(row: sqlite3.Row) -> Bond:
    data = dict(row)
    for key in ("next_coupon_date", "placement_date", "maturity_date", "offer_date"):
        data[key] = _parse_date(data.get(key))
    if data.get("qual_only") is not None:
        data["qual_only"] = bool(data["qual_only"])
    if data.get("amortized") is not None:
        data["amortized"] = bool(data["amortized"])
    parsed_fetched = _parse_datetime(data.get("fetched_at"))
    if parsed_fetched is not None:
        data["fetched_at"] = parsed_fetched
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
        version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"БД новее кода: user_version={version}, ожидается {SCHEMA_VERSION}"
            )

        if version < 1:
            columns = {
                row[1]
                for row in self.conn.execute("PRAGMA table_info(positions)").fetchall()
            }
            if columns and "annual_coupon_rub" not in columns:
                self.conn.execute("ALTER TABLE positions ADD COLUMN annual_coupon_rub REAL")
            version = 1

        if version < 2:
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_strategy_audit_kind "
                "ON strategy_audit(kind, id)"
            )
            version = 2

        if version < 3:
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_runs_started "
                "ON job_runs(started_at DESC)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerts_sent ON alerts(sent_at, id)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_new_issues_seen "
                "ON new_issues(first_seen DESC)"
            )
            version = 3

        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

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
        for bond in (sanitize_bond(item) for item in bonds):
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
        for position in (sanitize_position(item) for item in positions):
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

    def save_audit(
        self,
        kind: str,
        inputs: dict[str, Any],
        formulas: tuple[str, ...] | list[str],
        result: dict[str, Any],
        version: str = "strategy-1.0",
        created_at: datetime | None = None,
    ) -> int:
        payload = (created_at or datetime.now(timezone.utc)).isoformat()
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO strategy_audit "
                "(created_at, kind, inputs_json, formulas_json, result_json, version) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    payload,
                    kind,
                    json.dumps(inputs, ensure_ascii=False, default=str),
                    json.dumps(list(formulas), ensure_ascii=False, default=str),
                    json.dumps(result, ensure_ascii=False, default=str),
                    version,
                ),
            )
        return int(cursor.lastrowid or 0)

    def audits(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, created_at, kind, inputs_json, formulas_json, result_json, version "
            "FROM strategy_audit ORDER BY id DESC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        audits: list[dict[str, Any]] = []
        for row in rows:
            audits.append(
                {
                    "id": int(row["id"]),
                    "created_at": row["created_at"],
                    "kind": row["kind"],
                    "inputs": json.loads(row["inputs_json"]),
                    "formulas": json.loads(row["formulas_json"]),
                    "result": json.loads(row["result_json"]),
                    "version": row["version"],
                }
            )
        return audits

    def count_bonds(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM bonds").fetchone()
        return int(row["count"]) if row else 0

    def start_job(self, name: str, started_at: datetime | None = None) -> int:
        payload = (started_at or datetime.now(timezone.utc)).isoformat()
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO job_runs (name, started_at, status) VALUES (?, ?, 'running')",
                (name, payload),
            )
        return int(cursor.lastrowid or 0)

    def finish_job(
        self,
        job_id: int,
        status: str,
        details: dict[str, Any] | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        payload = (finished_at or datetime.now(timezone.utc)).isoformat()
        with self.conn:
            self.conn.execute(
                "UPDATE job_runs SET finished_at = ?, status = ?, details_json = ? "
                "WHERE id = ?",
                (
                    payload,
                    status,
                    json.dumps(details or {}, ensure_ascii=False, default=str),
                    job_id,
                ),
            )

    def last_jobs(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, name, started_at, finished_at, status, details_json "
            "FROM job_runs ORDER BY id DESC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                details = json.loads(row["details_json"])
            except json.JSONDecodeError:
                details = {}
            result.append(
                {
                    "id": int(row["id"]),
                    "name": row["name"],
                    "started_at": row["started_at"],
                    "finished_at": row["finished_at"],
                    "status": row["status"],
                    "details": details,
                }
            )
        return result

    def save_alert(
        self,
        kind: str,
        severity: str,
        message: str,
        dedupe_key: str,
        isin: str | None = None,
        created_at: datetime | None = None,
    ) -> int:
        payload = (created_at or datetime.now(timezone.utc)).isoformat()
        with self.conn:
            cursor = self.conn.execute(
                "INSERT OR IGNORE INTO alerts "
                "(created_at, kind, severity, isin, dedupe_key, message) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (payload, kind, severity, isin, dedupe_key, message),
            )
        if cursor.rowcount == 0:
            return 0
        return int(cursor.lastrowid or 0)

    def unsent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, created_at, kind, severity, isin, message "
            "FROM alerts WHERE sent_at IS NULL ORDER BY id LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_alert_sent(self, alert_id: int, sent_at: datetime | None = None) -> None:
        payload = (sent_at or datetime.now(timezone.utc)).isoformat()
        with self.conn:
            self.conn.execute(
                "UPDATE alerts SET sent_at = ? WHERE id = ? AND sent_at IS NULL",
                (payload, alert_id),
            )

    def alerts_sent_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) AS count FROM alerts WHERE sent_at LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return int(row["count"]) if row else 0

    def record_new_issues(self, bonds: list[Bond]) -> list[str]:
        """Запоминает новые ISIN. При первой загрузке помечает их как initial."""
        known_issues = self.conn.execute(
            "SELECT COUNT(*) AS count FROM new_issues"
        ).fetchone()
        initial = 1 if self.count_bonds() == 0 or not known_issues or known_issues["count"] == 0 else 0
        now = datetime.now(timezone.utc).isoformat()
        new_isins: list[str] = []
        with self.conn:
            for bond in bonds:
                cursor = self.conn.execute(
                    "INSERT OR IGNORE INTO new_issues (isin, first_seen, name, is_initial) "
                    "VALUES (?, ?, ?, ?)",
                    (bond.isin, now, bond.name, initial),
                )
                if cursor.rowcount:
                    new_isins.append(bond.isin)
        return new_isins

    def recent_new_issues(self, days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat()
        rows = self.conn.execute(
            "SELECT n.isin, n.first_seen, b.name, b.ytm_pct, b.rating, "
            "b.duration_years, b.price_pct, b.volume_mn_rub "
            "FROM new_issues n LEFT JOIN bonds b ON b.isin = n.isin "
            "WHERE n.is_initial = 0 AND n.first_seen >= ? "
            "ORDER BY n.first_seen DESC LIMIT ?",
            (cutoff, max(1, limit)),
        ).fetchall()
        return [dict(row) for row in rows]
