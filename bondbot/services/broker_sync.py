from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from bondbot.brokers.base import BrokerAccount, BrokerPosition, BrokerUnsupportedError
from bondbot.brokers.tinvest import TInvestClient
from bondbot.config import Settings
from bondbot.data.smartlab import SmartLabClient
from bondbot.db import Database
from bondbot.models import Bond, Coupon, PortfolioPosition, utcnow
from bondbot.services.review import save_portfolio_snapshot

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BrokerSyncResult:
    broker: str
    account_id: str
    account_name: str
    positions: int
    warnings: tuple[str, ...] = ()


def _price_pct(price_rub: float | None, face_value: float | None) -> float | None:
    if price_rub is None or not face_value:
        return None
    return round(price_rub / face_value * 100.0, 4)


def _select_account(
    accounts: list[BrokerAccount],
    preferred: str = "",
) -> BrokerAccount | None:
    if not accounts:
        return None
    if preferred:
        for account in accounts:
            if account.id == preferred:
                return account
        return None
    for account in accounts:
        if "OPEN" in account.status.upper():
            return account
    return accounts[0]


def _position_from_broker(
    broker: BrokerPosition,
    bond: Bond,
    source: str,
) -> PortfolioPosition:
    price_pct = _price_pct(broker.current_price_rub, broker.face_value or bond.face_value)
    buy_pct = _price_pct(broker.average_price_rub, broker.face_value or bond.face_value)
    current_value = broker.current_value_rub
    if current_value is None and broker.current_price_rub is not None:
        current_value = broker.quantity * broker.current_price_rub
    annual_coupon = (
        bond.coupon_rub * bond.coupon_freq * broker.quantity
        if bond.coupon_rub is not None and bond.coupon_freq is not None
        else None
    )
    return PortfolioPosition(
        isin=bond.isin,
        name=bond.name or broker.name,
        qty=broker.quantity,
        buy_price_pct=buy_pct,
        current_price_pct=price_pct,
        ytm_pct=bond.ytm_pct,
        maturity_date=bond.maturity_date,
        rating=bond.rating,
        g_spread_bp=bond.g_spread_bp,
        coupon_rub=bond.coupon_rub,
        coupon_freq=bond.coupon_freq,
        annual_coupon_rub=annual_coupon,
        current_value_rub=current_value,
        next_coupon_date=bond.next_coupon_date,
        source_url=f"broker:{source}",
    )


async def sync_broker(
    settings: Settings,
    db: Database,
    broker_name: str = "tinvest",
    *,
    account_id: str | None = None,
) -> BrokerSyncResult:
    name = (broker_name or "tinvest").lower()
    if name == "sber":
        raise BrokerUnsupportedError(
            "У СберИнвестиций нет публичного API для брокерских счетов физлиц. "
            "Нужен отчёт брокера или партнёрский доступ Sber API. "
            "T-Invest API поддерживается полностью."
        )
    if name != "tinvest":
        raise BrokerUnsupportedError(f"Неизвестный брокер: {broker_name}")

    client = TInvestClient(settings)
    try:
        accounts = await client.accounts()
        preferred_account = account_id or settings.tinvest_account_id
        selected = _select_account(accounts, preferred_account)
        if selected is None:
            if preferred_account:
                raise RuntimeError(
                    f"Счёт {preferred_account} не найден среди счетов T-Invest"
                )
            raise RuntimeError("У брокера нет доступных счетов")
        portfolio = await client.portfolio(selected.id)
    finally:
        await client.close()

    if not portfolio.positions:
        return BrokerSyncResult(
            broker=name,
            account_id=selected.id,
            account_name=selected.name,
            positions=0,
            warnings=("брокер вернул пустой портфель; текущие позиции не изменены",),
        )

    warnings: list[str] = []
    known = {bond.isin: bond for bond in db.list_bonds()}
    positions: list[PortfolioPosition] = []
    bonds_to_upsert: list[Bond] = []
    coupons_to_upsert: list[Coupon] = []
    unresolved: list[str] = []
    detail_client: SmartLabClient | None = None
    try:
        for item in portfolio.positions:
            if not item.isin:
                label = item.name or item.figi
                warnings.append(f"{label}: нет ISIN, пропущено")
                unresolved.append(label)
                continue
            bond = known.get(item.isin)
            if bond is None:
                # Пытаемся обогатить новую бумагу карточкой smart-lab.
                try:
                    if detail_client is None:
                        detail_client = SmartLabClient(settings)
                        await detail_client.__aenter__()
                    fetched, coupons = await detail_client.fetch_detail(item.isin)
                    if fetched is not None:
                        bond = fetched
                        known[item.isin] = bond
                        if coupons:
                            coupons_to_upsert.extend(coupons)
                except Exception as exc:
                    log.warning("broker bond detail %s failed: %s", item.isin, exc)
                if bond is None:
                    bond = Bond(
                        isin=item.isin,
                        name=item.name,
                        face_value=item.face_value,
                        coupon_freq=item.coupon_freq,
                        coupon_type=item.coupon_type,
                        amortized=item.amortized,
                        maturity_date=item.maturity_date,
                    )
                    known[item.isin] = bond

            price_pct = _price_pct(item.current_price_rub, item.face_value or bond.face_value)
            updated = replace(
                bond,
                name=bond.name or item.name,
                price_pct=price_pct if price_pct is not None else bond.price_pct,
                nkd_rub=item.current_nkd_rub if item.current_nkd_rub is not None else bond.nkd_rub,
                face_value=item.face_value or bond.face_value,
                coupon_freq=item.coupon_freq or bond.coupon_freq,
                coupon_type=item.coupon_type or bond.coupon_type,
                amortized=item.amortized if item.amortized is not None else bond.amortized,
                maturity_date=item.maturity_date or bond.maturity_date,
                source_url=f"broker:{name}",
                fetched_at=utcnow(),
            )
            bonds_to_upsert.append(updated)
            known[item.isin] = updated
            positions.append(_position_from_broker(item, updated, name))
    finally:
        if detail_client is not None:
            await detail_client.__aexit__(None, None, None)

    if unresolved:
        return BrokerSyncResult(
            broker=name,
            account_id=selected.id,
            account_name=selected.name,
            positions=0,
            warnings=tuple(
                warnings
                + [
                    "состав портфеля не изменён: у части бумаг не удалось "
                    "определить ISIN"
                ]
            ),
        )

    if not positions:
        return BrokerSyncResult(
            broker=name,
            account_id=selected.id,
            account_name=selected.name,
            positions=0,
            warnings=tuple(warnings + ["не удалось получить облигационные позиции"]),
        )

    db.upsert_bonds(bonds_to_upsert)
    if coupons_to_upsert:
        db.upsert_coupons(coupons_to_upsert)
    db.replace_positions(positions)
    for position in positions:
        db.add_watch(position.isin, f"broker:{name}")
    save_portfolio_snapshot(settings, db, now=utcnow())
    log.info(
        "broker %s synced account=%s positions=%s warnings=%s",
        name,
        selected.id,
        len(positions),
        len(warnings),
    )
    return BrokerSyncResult(
        broker=name,
        account_id=selected.id,
        account_name=selected.name,
        positions=len(positions),
        warnings=tuple(warnings),
    )


def format_broker_sync(result: BrokerSyncResult) -> str:
    lines = [
        f"🏦 {result.broker}: портфель синхронизирован",
        f"Счёт: {result.account_name} ({result.account_id})",
        f"Позиций: {result.positions}",
    ]
    if result.warnings:
        lines.append("")
        lines.append("Предупреждения:")
        lines.extend(f"• {warning}" for warning in result.warnings[:10])
    lines.append("")
    lines.append("Это аналитика по данным брокера, не инвестиционная рекомендация.")
    return "\n".join(lines)


__all__ = ["BrokerSyncResult", "format_broker_sync", "sync_broker"]
