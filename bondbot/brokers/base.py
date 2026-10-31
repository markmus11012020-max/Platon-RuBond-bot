from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


class BrokerError(RuntimeError):
    pass


class BrokerUnsupportedError(BrokerError):
    pass


@dataclass(frozen=True, slots=True)
class BrokerAccount:
    id: str
    name: str
    type: str
    status: str
    opened_date: date | None = None


@dataclass(frozen=True, slots=True)
class BrokerPosition:
    figi: str
    isin: str | None
    name: str
    instrument_type: str
    quantity: float
    average_price_rub: float | None = None
    current_price_rub: float | None = None
    current_nkd_rub: float | None = None
    current_value_rub: float | None = None
    currency: str = "rub"
    face_value: float | None = None
    coupon_freq: float | None = None
    coupon_type: str | None = None
    amortized: bool | None = None
    maturity_date: date | None = None


@dataclass(frozen=True, slots=True)
class BrokerPortfolio:
    account: BrokerAccount
    positions: tuple[BrokerPosition, ...]
    total_value_rub: float | None = None
    currency: str = "rub"


class BrokerClient(Protocol):
    name: str

    async def accounts(self) -> list[BrokerAccount]: ...

    async def portfolio(self, account_id: str) -> BrokerPortfolio: ...

    async def close(self) -> None: ...


__all__ = [
    "BrokerAccount",
    "BrokerClient",
    "BrokerError",
    "BrokerPortfolio",
    "BrokerPosition",
    "BrokerUnsupportedError",
]
