from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime

from bondbot.config import Settings
from bondbot.data.cbr import KeyRateService, KeyRateSnapshot
from bondbot.data.moex import MoexClient
from bondbot.data.smartlab import SmartLabClient
from bondbot.db import Database
from bondbot.models import Bond, utcnow

log = logging.getLogger(__name__)

# Поля, где официальные данные MOEX приоритетнее smart-lab.
OFFICIAL_FIELDS = (
    "price_pct",
    "ytm_pct",
    "current_coupon_yield_pct",
    "annual_coupon_yield_pct",
    "volume_mn_rub",
    "coupon_rub",
    "coupon_freq",
    "nkd_rub",
    "duration_years",
    "next_coupon_date",
    "maturity_date",
    "offer_date",
    "years_to_maturity",
    "face_value",
    "issue_size_rub",
    "source_url",
    "fetched_at",
)


@dataclass(frozen=True, slots=True)
class RefreshResult:
    source: str
    seen: int
    upserted: int
    new_isins: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


def merge_bond(base: Bond, official: Bond) -> Bond:
    updates = {
        field: getattr(official, field)
        for field in OFFICIAL_FIELDS
        if getattr(official, field) is not None
    }
    return replace(base, **updates) if updates else base


def merge_bonds(primary: list[Bond], official: list[Bond]) -> list[Bond]:
    merged: dict[str, Bond] = {bond.isin: bond for bond in primary}
    for bond in official:
        existing = merged.get(bond.isin)
        merged[bond.isin] = merge_bond(existing, bond) if existing else bond
    return list(merged.values())


async def refresh_market(settings: Settings, db: Database) -> RefreshResult:
    errors: list[str] = []
    smartlab: list[Bond] = []
    official: list[Bond] = []

    try:
        async with SmartLabClient(settings) as client:
            smartlab = await client.fetch_screener()
    except Exception as exc:
        log.warning("smart-lab refresh failed: %s", exc)
        errors.append(f"smart-lab: {exc}")

    if settings.moex_enabled:
        try:
            async with MoexClient(settings) as client:
                official = await client.fetch_bonds()
        except Exception as exc:
            log.warning("MOEX refresh failed: %s", exc)
            errors.append(f"MOEX: {exc}")

    bonds = merge_bonds(smartlab, official)
    if not bonds:
        message = "; ".join(errors) or "источники вернули пустой список"
        raise RuntimeError(f"нет данных для обновления: {message}")

    # Новинками считаем только бумаги с рейтингом: без него нельзя оценить риск.
    new_isins = db.record_new_issues([bond for bond in bonds if bond.rating])
    upserted = db.upsert_bonds(bonds)
    repaired = db.repair_bond_data()
    db.kv_set("last_market_refresh", utcnow().isoformat())
    source = "+".join(
        name for name, count in (("smart-lab", len(smartlab)), ("moex", len(official))) if count
    )
    log.info(
        "market refreshed: source=%s seen=%s upserted=%s new=%s repaired=%s",
        source,
        len(bonds),
        upserted,
        len(new_isins),
        repaired,
    )
    return RefreshResult(
        source=source,
        seen=len(bonds),
        upserted=upserted,
        new_isins=tuple(new_isins),
        errors=tuple(errors),
    )


async def refresh_details(settings: Settings, db: Database) -> tuple[int, list[str]]:
    isins = sorted(
        {
            position.isin
            for position in db.positions()
        }
        | {
            str(row["isin"])
            for row in db.watchlist()
        }
    )
    if not isins:
        return 0, []

    updated = 0
    errors: list[str] = []
    async with SmartLabClient(settings) as client:
        for isin in isins:
            try:
                bond, coupons = await client.fetch_detail(isin)
                if bond is not None:
                    db.upsert_bonds([bond])
                    updated += 1
                if coupons:
                    db.upsert_coupons(coupons)
            except Exception as exc:
                log.warning("detail refresh %s failed: %s", isin, exc)
                errors.append(f"{isin}: {exc}")
            await asyncio.sleep(1.0)
    db.repair_bond_data()
    db.kv_set("last_detail_refresh", utcnow().isoformat())
    return updated, errors


async def refresh_key_rate(settings: Settings, db: Database) -> KeyRateSnapshot:
    snapshot = await KeyRateService(settings, db).get()
    db.kv_set("last_key_rate_refresh", utcnow().isoformat())
    return snapshot


def last_refresh_at(db: Database, key: str = "last_market_refresh") -> datetime | None:
    raw = db.kv_get(key)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed


__all__ = [
    "RefreshResult",
    "last_refresh_at",
    "merge_bond",
    "merge_bonds",
    "refresh_details",
    "refresh_key_rate",
    "refresh_market",
]
