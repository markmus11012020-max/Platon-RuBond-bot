from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from bondbot.config import Settings
from bondbot.data.cbr import KeyRateService
from bondbot.db import Database

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MaxYield:
    value_pct: float
    source: str = "fixed"  # key_rate | fixed | fallback
    key_rate_pct: float | None = None
    margin_pct: float = 0.0
    as_of: date | None = None
    stale: bool = False

    def describe(self) -> str:
        if self.source == "key_rate" and self.key_rate_pct is not None:
            suffix = " (кэш, ЦБ недоступен)" if self.stale else ""
            date_suffix = f" на {self.as_of:%d.%m.%Y}" if self.as_of else ""
            return (
                f"ставка ЦБ {self.key_rate_pct:.2f}% + {self.margin_pct:.1f} п.п. "
                f"= {self.value_pct:.2f}%{date_suffix}{suffix}"
            )
        if self.source == "fallback":
            return f"фиксированный лимит {self.value_pct:.2f}% (ставка ЦБ недоступна)"
        return f"фиксированный лимит {self.value_pct:.2f}%"


async def resolve_max_yield(settings: Settings, db: Database) -> MaxYield:
    """Return CBR key rate + margin, or the configured fallback cap."""
    if not settings.dynamic_max_yield:
        return MaxYield(value_pct=settings.max_yield_pct, source="fixed")

    try:
        snapshot = await KeyRateService(settings, db).get()
    except Exception as exc:
        log.warning("using fixed max yield %.2f%%: %s", settings.max_yield_pct, exc)
        return MaxYield(value_pct=settings.max_yield_pct, source="fallback")

    value = round(snapshot.value_pct + settings.key_rate_margin_pct, 2)
    return MaxYield(
        value_pct=value,
        source="key_rate",
        key_rate_pct=snapshot.value_pct,
        margin_pct=settings.key_rate_margin_pct,
        as_of=snapshot.as_of,
        stale=snapshot.stale,
    )
