from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS credit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    isin TEXT NOT NULL,
    issuer TEXT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    event_date TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(isin, event_type, event_date, source)
);

CREATE INDEX IF NOT EXISTS idx_credit_events_isin
    ON credit_events(isin, event_date DESC);

CREATE TABLE IF NOT EXISTS blocklist (
    isin TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    severity TEXT NOT NULL DEFAULT 'blocked',
    added_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS credit_checks (
    isin TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    checked_at TEXT NOT NULL,
    expires_at TEXT,
    note TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RiskRepository:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def seed_demo(self) -> None:
        with self._connect() as connection:
            if connection.execute("SELECT COUNT(*) FROM credit_events").fetchone()[0] == 0:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO credit_events
                    (isin, issuer, event_type, severity, event_date, source,
                     source_url, summary, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "RU000A10G1Q1",
                        "МГКЛ",
                        "technical_default",
                        "critical",
                        "2026-10-30",
                        "manual/demo",
                        "",
                        "Технический дефолт по данным мониторинга. Требуется проверка первоисточника.",
                        _now(),
                    ),
                )
            if connection.execute("SELECT COUNT(*) FROM blocklist").fetchone()[0] == 0:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO blocklist
                    (isin, reason, source, source_url, severity, added_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        "RU000A10FWC7",
                        "Аномальная распродажа: цена и объём вне обычного профиля.",
                        "manual/demo",
                        "",
                        "blocked",
                        _now(),
                    ),
                )

    def active_blocklist(self) -> list[dict[str, Any]]:
        now = _now()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM blocklist
                WHERE expires_at IS NULL OR expires_at > ?
                ORDER BY added_at DESC
                """,
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def blocklist_hit(self, isin: str) -> dict[str, Any] | None:
        now = _now()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM blocklist
                WHERE isin = ? AND (expires_at IS NULL OR expires_at > ?)
                """,
                (isin, now),
            ).fetchone()
        return dict(row) if row else None

    def add_blocklist(
        self,
        isin: str,
        reason: str,
        source: str,
        source_url: str = "",
        severity: str = "blocked",
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        isin = isin.strip().upper()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO blocklist
                (isin, reason, source, source_url, severity, added_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(isin) DO UPDATE SET
                    reason = excluded.reason,
                    source = excluded.source,
                    source_url = excluded.source_url,
                    severity = excluded.severity,
                    added_at = excluded.added_at,
                    expires_at = excluded.expires_at
                """,
                (isin, reason, source, source_url, severity, _now(), expires_at),
            )
        return {
            "isin": isin,
            "reason": reason,
            "source": source,
            "source_url": source_url,
            "severity": severity,
            "added_at": _now(),
            "expires_at": expires_at,
        }

    def remove_blocklist(self, isin: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM blocklist WHERE isin = ?",
                (isin.strip().upper(),),
            )
        return cursor.rowcount > 0

    def events_for(self, isin: str, days: int = 365) -> list[dict[str, Any]]:
        cutoff = (date.today() - timedelta(days=max(1, days))).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM credit_events
                WHERE isin = ? AND event_date >= ?
                ORDER BY event_date DESC
                """,
                (isin, cutoff),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_events(self, days: int = 90) -> list[dict[str, Any]]:
        cutoff = (date.today() - timedelta(days=max(1, days))).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM credit_events
                WHERE event_date >= ?
                ORDER BY event_date DESC, id DESC
                """,
                (cutoff,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_event(
        self,
        isin: str,
        event_type: str,
        severity: str,
        event_date: str,
        source: str,
        summary: str,
        issuer: str = "",
        source_url: str = "",
    ) -> dict[str, Any]:
        payload = (
            isin.strip().upper(),
            issuer,
            event_type,
            severity,
            event_date,
            source,
            source_url,
            summary,
            _now(),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO credit_events
                (isin, issuer, event_type, severity, event_date, source,
                 source_url, summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
        return {
            "isin": payload[0],
            "issuer": issuer,
            "event_type": event_type,
            "severity": severity,
            "event_date": event_date,
            "source": source,
            "source_url": source_url,
            "summary": summary,
        }

    def credit_check(self, isin: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM credit_checks WHERE isin = ?",
                (isin.strip().upper(),),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        if result.get("expires_at") and result["expires_at"] <= _now():
            return None
        return result

    def set_credit_check(
        self,
        isin: str,
        status: str,
        source: str,
        note: str = "",
        source_url: str = "",
        valid_days: int = 90,
    ) -> dict[str, Any]:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=max(1, valid_days))).isoformat()
        payload = (isin.strip().upper(), status, source, source_url, _now(), expires_at, note)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO credit_checks
                (isin, status, source, source_url, checked_at, expires_at, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(isin) DO UPDATE SET
                    status = excluded.status,
                    source = excluded.source,
                    source_url = excluded.source_url,
                    checked_at = excluded.checked_at,
                    expires_at = excluded.expires_at,
                    note = excluded.note
                """,
                payload,
            )
        return {
            "isin": payload[0],
            "status": status,
            "source": source,
            "source_url": source_url,
            "checked_at": payload[4],
            "expires_at": expires_at,
            "note": note,
        }

    def summary(self) -> dict[str, Any]:
        with self._connect() as connection:
            events = connection.execute(
                "SELECT COUNT(*) FROM credit_events"
            ).fetchone()[0]
            blocked = connection.execute(
                "SELECT COUNT(*) FROM blocklist"
            ).fetchone()[0]
            checks = connection.execute(
                "SELECT COUNT(*) FROM credit_checks"
            ).fetchone()[0]
        return {
            "credit_events": int(events),
            "blocklist": int(blocked),
            "credit_checks": int(checks),
            "risk_db": str(self.path),
        }


def dump_evidence(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False, default=str)


__all__ = ["RiskRepository", "dump_evidence"]
