from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

from bondbot.analytics.bonds import meets_min_rating
from bondbot.config import Settings
from bondbot.data.cbr import KeyRateSnapshot
from bondbot.db import Database
from bondbot.models import Bond, PortfolioPosition, to_msk, utcnow
from bondbot.strategy.liquidity import liquidity_plan
from bondbot.strategy.safe import safe_range

log = logging.getLogger(__name__)

MAX_POSITION_SHARE = 0.25
OFFER_WARN_DAYS = 60
MATURITY_WARN_DAYS = 30


@dataclass(frozen=True, slots=True)
class Alert:
    kind: str
    severity: str
    isin: str | None
    message: str
    dedupe_key: str


def _position_value(position: PortfolioPosition) -> float:
    if position.current_value_rub is not None:
        return position.current_value_rub
    if position.buy_price_pct is not None and position.qty is not None:
        return position.qty * position.buy_price_pct / 100 * 1000
    return 0.0


def _days_until(value: date | None, today: date) -> int | None:
    if value is None:
        return None
    return (value - today).days


def _bond_line(bond: Bond) -> str:
    return (
        f"{bond.name} ({bond.isin}): YTM "
        f"{bond.ytm_pct:.2f}%" if bond.ytm_pct is not None else f"{bond.name} ({bond.isin})"
    )


def build_alerts(
    settings: Settings,
    db: Database,
    snapshot: KeyRateSnapshot | None = None,
    *,
    now: datetime | None = None,
) -> list[Alert]:
    current = now or utcnow()
    today = current.date()
    day_key = today.isoformat()
    range_ = safe_range(snapshot) if snapshot is not None else None
    bonds = {bond.isin: bond for bond in db.list_bonds()}
    positions = db.positions()
    alerts: list[Alert] = []

    def add(kind: str, severity: str, isin: str | None, message: str, key: str) -> None:
        alerts.append(Alert(kind, severity, isin, message, key))

    total_value = sum(_position_value(position) for position in positions)

    for position in positions:
        bond = bonds.get(position.isin)
        if bond is None:
            add(
                "data",
                "warning",
                position.isin,
                f"{position.name} ({position.isin}): нет карточки бумаги — обнови данные",
                f"data:{position.isin}:{day_key}",
            )
            continue

        plan = liquidity_plan(
            bond,
            _position_value(position),
            max_pct_daily_volume=settings.max_pct_daily_volume,
            horizon_days=settings.exit_horizon_days,
        )
        if plan.warnings:
            add(
                "liquidity",
                "warning",
                bond.isin,
                _bond_line(bond) + "\n" + "\n".join(plan.warnings),
                f"liquidity:{bond.isin}:{day_key}",
            )

        offer_days = _days_until(bond.offer_date, today)
        if offer_days is not None and 0 <= offer_days <= OFFER_WARN_DAYS:
            add(
                "offer",
                "warning",
                bond.isin,
                f"{_bond_line(bond)} — оферта через {offer_days} дн. ({bond.offer_date:%d.%m.%Y})",
                f"offer:{bond.isin}:{bond.offer_date.isoformat()}",
            )

        maturity_days = _days_until(bond.maturity_date, today)
        if maturity_days is not None and 0 <= maturity_days <= MATURITY_WARN_DAYS:
            add(
                "maturity",
                "warning",
                bond.isin,
                f"{_bond_line(bond)} — погашение через {maturity_days} дн.",
                f"maturity:{bond.isin}:{bond.maturity_date.isoformat()}",
            )

        if not meets_min_rating(bond.rating, settings.min_rating):
            add(
                "rating",
                "critical",
                bond.isin,
                f"{_bond_line(bond)} — рейтинг {bond.rating or '—'} ниже минимума {settings.min_rating}",
                f"rating:{bond.isin}:{bond.rating or 'none'}",
            )

        if range_ is not None and bond.ytm_pct is not None:
            if bond.ytm_pct > range_.high_pct:
                add(
                    "yield_high",
                    "warning",
                    bond.isin,
                    f"{_bond_line(bond)} — выше коридора {range_.high_pct:.2f}%: риск ВДО",
                    f"yield_high:{bond.isin}:{range_.high_pct:.2f}:{day_key}",
                )
            elif bond.ytm_pct < range_.low_pct:
                add(
                    "yield_low",
                    "info",
                    bond.isin,
                    f"{_bond_line(bond)} — ниже коридора {range_.low_pct:.2f}%",
                    f"yield_low:{bond.isin}:{range_.low_pct:.2f}:{day_key}",
                )

        if total_value > 0:
            share = _position_value(position) / total_value
            if share > MAX_POSITION_SHARE:
                add(
                    "concentration",
                    "warning",
                    bond.isin,
                    f"{_bond_line(bond)} — {share:.1%} портфеля (лимит {MAX_POSITION_SHARE:.0%})",
                    f"concentration:{bond.isin}:{day_key}",
                )

    watch_rows = db.watchlist()
    for row in watch_rows:
        isin = str(row["isin"])
        bond = bonds.get(isin)
        if bond is None:
            continue
        if range_ is not None and bond.ytm_pct is not None:
            if bond.ytm_pct > range_.high_pct:
                add(
                    "watch_yield_high",
                    "info",
                    isin,
                    f"Наблюдение: {_bond_line(bond)} — выше коридора {range_.high_pct:.2f}%",
                    f"watch_yield_high:{isin}:{range_.high_pct:.2f}:{day_key}",
                )
            elif bond.ytm_pct < range_.low_pct:
                add(
                    "watch_yield_low",
                    "info",
                    isin,
                    f"Наблюдение: {_bond_line(bond)} — ниже коридора {range_.low_pct:.2f}%",
                    f"watch_yield_low:{isin}:{range_.low_pct:.2f}:{day_key}",
                )
        offer_days = _days_until(bond.offer_date, today)
        if offer_days is not None and 0 <= offer_days <= OFFER_WARN_DAYS:
            add(
                "watch_offer",
                "info",
                isin,
                f"Наблюдение: {_bond_line(bond)} — оферта через {offer_days} дн.",
                f"watch_offer:{isin}:{bond.offer_date.isoformat()}",
            )

    if range_ is not None:
        for row in db.recent_new_issues(days=7, limit=20):
            isin = str(row["isin"])
            ytm = row.get("ytm_pct")
            rating = row.get("rating")
            if ytm is None or not (range_.low_pct <= float(ytm) <= range_.high_pct):
                continue
            if not meets_min_rating(rating, settings.min_rating):
                continue
            add(
                "new_issue",
                "info",
                isin,
                f"Новый выпуск {row.get('name') or isin} ({isin}): YTM {float(ytm):.2f}%, "
                f"рейтинг {rating or '—'}",
                f"new_issue:{isin}",
            )

    return alerts


def save_alerts(db: Database, alerts: list[Alert], *, now: datetime | None = None) -> int:
    saved = 0
    for alert in alerts:
        saved += 1 if db.save_alert(
            kind=alert.kind,
            severity=alert.severity,
            message=alert.message,
            dedupe_key=alert.dedupe_key,
            isin=alert.isin,
            created_at=now,
        ) else 0
    return saved


def _quiet_hour(settings: Settings, current: datetime) -> bool:
    hour = to_msk(current).hour if current.tzinfo else current.hour
    start = settings.alert_quiet_start % 24
    end = settings.alert_quiet_end % 24
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def owner_peer(settings: Settings, db: Database) -> int:
    if settings.owner_peer_id:
        return settings.owner_peer_id
    for key in ("owner_peer_id", "chat_peer_id"):
        raw = db.kv_get(key)
        if raw:
            try:
                return int(raw)
            except ValueError:
                continue
    return 0


def format_alert(alert: dict) -> str:
    icons = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
    return f"{icons.get(str(alert.get('severity')), '•')} {alert.get('message', '')}"


async def send_pending_alerts(
    settings: Settings,
    db: Database,
    vk,
    *,
    now: datetime | None = None,
) -> int:
    if not settings.alerts_enabled:
        return 0
    peer_id = owner_peer(settings, db)
    if not peer_id:
        log.info("alerts skipped: owner peer is not configured")
        return 0

    current = now or utcnow()
    db.expire_alerts(hours=48)
    quiet = _quiet_hour(settings, current)
    remaining = max(0, settings.alert_max_per_day - db.alerts_sent_today())
    if remaining <= 0:
        return 0

    sent = 0
    for alert in db.unsent_alerts(limit=50):
        if sent >= remaining:
            break
        if quiet and alert.get("severity") != "critical":
            continue
        try:
            await vk.send_message(peer_id, format_alert(alert))
        except Exception as exc:
            log.warning("alert %s send failed: %s", alert.get("id"), exc)
            break
        db.mark_alert_sent(int(alert["id"]), sent_at=current)
        sent += 1
    return sent


async def build_and_send(
    settings: Settings,
    db: Database,
    vk,
    snapshot: KeyRateSnapshot | None = None,
    *,
    now: datetime | None = None,
) -> int:
    current = now or utcnow()
    alerts = build_alerts(settings, db, snapshot, now=current)
    save_alerts(db, alerts, now=current)
    return await send_pending_alerts(settings, db, vk, now=current)


__all__ = [
    "Alert",
    "build_alerts",
    "build_and_send",
    "format_alert",
    "owner_peer",
    "save_alerts",
    "send_pending_alerts",
]
