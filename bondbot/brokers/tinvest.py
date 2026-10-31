from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import aiohttp

from bondbot.brokers.base import (
    BrokerAccount,
    BrokerError,
    BrokerPortfolio,
    BrokerPosition,
)
from bondbot.config import Settings

log = logging.getLogger(__name__)

SERVICE = "tinkoff.public.invest.api.contract.v1"


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def quotation(value: Any) -> float | None:
    if not isinstance(value, dict):
        return _number(value)
    units = _number(value.get("units")) or 0.0
    nano = _number(value.get("nano")) or 0.0
    return units + nano / 1_000_000_000.0


def money(value: Any) -> float | None:
    return quotation(value)


def parse_accounts(payload: dict[str, Any]) -> list[BrokerAccount]:
    result: list[BrokerAccount] = []
    for item in payload.get("accounts") or []:
        account_id = str(item.get("id") or "")
        if not account_id:
            continue
        opened = item.get("openedDate")
        opened_date = None
        if opened:
            try:
                opened_date = date.fromisoformat(str(opened)[:10])
            except ValueError:
                pass
        result.append(
            BrokerAccount(
                id=account_id,
                name=str(item.get("name") or account_id),
                type=str(item.get("type") or ""),
                status=str(item.get("status") or ""),
                opened_date=opened_date,
            )
        )
    return result


def parse_portfolio(
    payload: dict[str, Any],
    bond_infos: dict[str, dict[str, Any]],
    *,
    account: BrokerAccount | None = None,
) -> BrokerPortfolio:
    positions: list[BrokerPosition] = []
    for item in payload.get("positions") or []:
        instrument_type = str(item.get("instrumentType") or "").lower()
        if instrument_type != "bond":
            continue
        quantity = quotation(item.get("quantity")) or 0.0
        if quantity <= 0:
            continue
        figi = str(item.get("figi") or "")
        uid = str(item.get("instrumentUid") or "")
        info = bond_infos.get(uid) or bond_infos.get(figi) or {}
        isin = str(info.get("isin") or "").upper() or None
        if not isin:
            log.warning("T-Invest bond position %s has no ISIN", figi or uid)
        name = str(info.get("name") or item.get("ticker") or figi or isin or "bond")
        average = money(item.get("averagePositionPrice"))
        price = money(item.get("currentPrice"))
        nkd = money(item.get("currentNkd")) or 0.0
        face = money(info.get("nominal")) or 1000.0
        current_value = (price + nkd) * quantity if price is not None else None
        coupon_type = None
        if info.get("floating") is True:
            coupon_type = "floating"
        elif info:
            coupon_type = "fixed"
        maturity = info.get("maturity_date")
        maturity_date = None
        if maturity:
            try:
                maturity_date = date.fromisoformat(str(maturity)[:10])
            except ValueError:
                pass
        positions.append(
            BrokerPosition(
                figi=figi,
                isin=isin,
                name=name,
                instrument_type=instrument_type,
                quantity=quantity,
                average_price_rub=average,
                current_price_rub=price,
                current_nkd_rub=nkd,
                current_value_rub=current_value,
                currency=str((item.get("currentPrice") or {}).get("currency") or "rub"),
                face_value=face,
                coupon_freq=float(info["coupon_freq"]) if info.get("coupon_freq") else None,
                coupon_type=coupon_type,
                amortized=bool(info.get("amortized")) if "amortized" in info else None,
                maturity_date=maturity_date,
            )
        )
    total = money(payload.get("totalAmountBonds")) or money(payload.get("totalAmountPortfolio"))
    return BrokerPortfolio(
        account=account or BrokerAccount(id=str(payload.get("accountId") or ""), name="", type="", status=""),
        positions=tuple(positions),
        total_value_rub=total,
        currency="rub",
    )


class TInvestClient:
    name = "tinvest"

    def __init__(self, settings: Settings, session: aiohttp.ClientSession | None = None) -> None:
        self.settings = settings
        self._session = session
        self._own_session = session is None
        self._bond_cache: dict[str, dict[str, Any]] = {}

    async def __aenter__(self) -> "TInvestClient":
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.settings.broker_timeout),
            )
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None

    def _url(self, method: str) -> str:
        return (
            f"{self.settings.tinvest_base_url.rstrip('/')}/rest/"
            f"{SERVICE}.{method}"
        )

    async def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.tinvest_token:
            raise BrokerError("BONDBOT_TINVEST_TOKEN не задан")
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.settings.broker_timeout),
            )
            self._own_session = True
        headers = {
            "Authorization": f"Bearer {self.settings.tinvest_token}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                async with self._session.post(self._url(method), json=payload, headers=headers) as response:
                    text = await response.text()
                    if response.status in {429, 500, 502, 503, 504} and attempt < 3:
                        await asyncio.sleep(1.0 * attempt)
                        continue
                    if response.status >= 400:
                        raise BrokerError(
                            f"T-Invest {method}: HTTP {response.status}: {text[:300]}"
                        )
                    return await response.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt >= 3:
                    raise BrokerError(f"T-Invest {method}: {exc}") from exc
                await asyncio.sleep(1.0 * attempt)
        raise BrokerError(f"T-Invest {method}: {last_error}")

    async def accounts(self) -> list[BrokerAccount]:
        payload = await self._post("UsersService/GetAccounts", {})
        return parse_accounts(payload)

    async def _bond_info(self, figi: str, uid: str) -> dict[str, Any]:
        key = uid or figi
        if key in self._bond_cache:
            return self._bond_cache[key]
        if uid:
            request = {"idType": "INSTRUMENT_ID_TYPE_UID", "id": uid}
        elif figi:
            request = {"idType": "INSTRUMENT_ID_TYPE_FIGI", "id": figi}
        else:
            return {}
        try:
            payload = await self._post("InstrumentsService/BondBy", request)
            instrument = payload.get("instrument") or {}
            bond = {
                "isin": str(instrument.get("isin") or "").upper(),
                "name": str(instrument.get("name") or ""),
                "nominal": money(instrument.get("nominal")),
                "coupon_freq": instrument.get("couponQuantityPerYear"),
                "floating": bool(instrument.get("floatingCouponFlag")),
                "amortized": bool(instrument.get("amortizationFlag")),
                "maturity_date": instrument.get("maturityDate"),
            }
        except Exception as exc:
            log.warning("T-Invest BondBy %s failed: %s", key, exc)
            bond = {}
        self._bond_cache[key] = bond
        return bond

    async def portfolio(self, account_id: str) -> BrokerPortfolio:
        payload = await self._post(
            "OperationsService/GetPortfolio",
            {"accountId": account_id, "currency": "RUB"},
        )
        infos: dict[str, dict[str, Any]] = {}
        for item in payload.get("positions") or []:
            if str(item.get("instrumentType") or "").lower() != "bond":
                continue
            figi = str(item.get("figi") or "")
            uid = str(item.get("instrumentUid") or "")
            info = await self._bond_info(figi, uid)
            if uid:
                infos[uid] = info
            if figi:
                infos[figi] = info
        account = BrokerAccount(
            id=account_id,
            name=self.settings.tinvest_account_id or account_id,
            type="",
            status="ACCOUNT_STATUS_OPEN",
        )
        return parse_portfolio(payload, infos, account=account)


__all__ = ["TInvestClient", "money", "parse_accounts", "parse_portfolio", "quotation"]
