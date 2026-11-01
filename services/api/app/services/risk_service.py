from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from app.config import Settings
from app.demo import DEMO_RISK_CANDIDATES
from app.risk.moex import MarketSnapshot, fetch_snapshot
from app.risk.news import NewsFlag, scan_news
from app.risk.repository import RiskRepository
from app.schemas import CandidateCard, ExcludedCandidate


@dataclass(slots=True)
class RiskCheck:
    name: str
    status: str
    message: str
    source: str = ""


@dataclass(slots=True)
class RiskAssessment:
    isin: str
    name: str
    issuer: str
    status: str
    reason: str
    checks: list[RiskCheck] = field(default_factory=list)
    market: dict[str, Any] = field(default_factory=dict)
    news: list[dict[str, Any]] = field(default_factory=list)
    checked_at: str = ""


def _stale_days(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return None
    return (date.today() - parsed).days


def _assessment_status(checks: list[RiskCheck]) -> str:
    if any(item.status == "fail" for item in checks):
        return "blocked"
    if any(item.status in {"warn", "unknown"} for item in checks):
        return "review"
    return "ok"


def _reason(checks: list[RiskCheck]) -> str:
    failed = [item for item in checks if item.status in {"fail", "warn", "unknown"}]
    if not failed:
        return "Проверки пройдены. Это не инвестиционная рекомендация."
    return " ".join(
        f"{item.message}" + (f" ({item.source})" if item.source else "")
        for item in failed[:3]
    )


async def evaluate_candidate(
    settings: Settings,
    repository: RiskRepository,
    candidate: dict[str, Any],
) -> RiskAssessment:
    isin = str(candidate["isin"]).upper()
    name = str(candidate["name"])
    issuer = str(candidate.get("issuer") or "")
    checks: list[RiskCheck] = []

    blocked = repository.blocklist_hit(isin)
    if blocked:
        checks.append(
            RiskCheck(
                "blocklist",
                "fail",
                f"Ручной блоклист: {blocked['reason']}",
                str(blocked.get("source") or ""),
            )
        )
    else:
        checks.append(RiskCheck("blocklist", "ok", "В ручном блоклисте нет"))

    events = repository.events_for(isin)
    if events:
        critical = [item for item in events if item.get("severity") == "critical"]
        if critical:
            event = critical[0]
            checks.append(
                RiskCheck(
                    "credit_events",
                    "fail",
                    f"Кредитное событие: {event['summary']}",
                    f"{event.get('source')} · {event.get('event_date')}",
                )
            )
        else:
            event = events[0]
            checks.append(
                RiskCheck(
                    "credit_events",
                    "warn",
                    f"Кредитное событие требует проверки: {event['summary']}",
                    f"{event.get('source')} · {event.get('event_date')}",
                )
            )
    else:
        checks.append(RiskCheck("credit_events", "ok", "Кредитных событий в базе нет"))

    news_flags, news_error = scan_news(
        settings.bond_db_path, isin, name, issuer
    )
    if news_error:
        checks.append(
            RiskCheck(
                "news",
                "unknown",
                "Новостной источник недоступен, негативные события не проверены",
                news_error,
            )
        )
    elif any(item.severity == "critical" for item in news_flags):
        flag = next(item for item in news_flags if item.severity == "critical")
        checks.append(
            RiskCheck(
                "news",
                "fail",
                f"Негативная новость: {flag.title}",
                f"{flag.source} · {flag.published_at[:10]}",
            )
        )
    elif news_flags:
        flag = news_flags[0]
        checks.append(
            RiskCheck(
                "news",
                "warn",
                f"Новость требует проверки: {flag.title}",
                f"{flag.source} · {flag.published_at[:10]}",
            )
        )
    else:
        checks.append(RiskCheck("news", "ok", "Негативных новостей не найдено"))

    credit_check = repository.credit_check(isin)
    if credit_check and credit_check.get("status") == "passed":
        checks.append(
            RiskCheck(
                "credit_check",
                "ok",
                "Кредитная проверка подтверждена",
                f"{credit_check.get('source')} · {str(credit_check.get('checked_at'))[:10]}",
            )
        )
    else:
        checks.append(
            RiskCheck(
                "credit_check",
                "warn",
                "Нет подтверждённой кредитной проверки",
                "manual",
            )
        )

    snapshot = await fetch_snapshot(isin)
    market = {
        "last_price_pct": snapshot.last_price_pct,
        "drawdown_7d_pct": snapshot.drawdown_7d_pct,
        "drawdown_30d_pct": snapshot.drawdown_30d_pct,
        "volume_ratio_30d": snapshot.volume_ratio_30d,
        "bid_pct": snapshot.bid_pct,
        "offer_pct": snapshot.offer_pct,
        "spread_pct": snapshot.spread_pct,
        "available_buy_rub": snapshot.available_buy_rub,
        "available_sell_rub": snapshot.available_sell_rub,
        "data_date": snapshot.data_date,
        "quote_time": snapshot.quote_time,
        "history_points": snapshot.history_points,
        "error": snapshot.error,
    }
    if snapshot.error or snapshot.history_points == 0:
        checks.append(
            RiskCheck(
                "market_data",
                "unknown",
                "Нет проверенных рыночных данных MOEX",
                snapshot.error or "history empty",
            )
        )
    else:
        stale = _stale_days(snapshot.data_date)
        if stale is not None and stale > settings.risk_data_stale_days:
            checks.append(
                RiskCheck(
                    "market_data",
                    "warn",
                    f"Котировки устарели на {stale} дн.",
                    f"MOEX · {snapshot.data_date}",
                )
            )
        else:
            checks.append(
                RiskCheck(
                    "market_data",
                    "ok",
                    "Рыночные данные MOEX актуальны",
                    f"MOEX · {snapshot.data_date}",
                )
            )

        if snapshot.drawdown_7d_pct is not None:
            if snapshot.drawdown_7d_pct <= settings.risk_max_drawdown_7d:
                checks.append(
                    RiskCheck(
                        "drawdown_7d",
                        "fail",
                        f"Просадка за 7 дней {snapshot.drawdown_7d_pct:.1f}%",
                        f"MOEX · {snapshot.data_date}",
                    )
                )
            elif snapshot.drawdown_7d_pct <= settings.risk_max_drawdown_7d / 2:
                checks.append(
                    RiskCheck(
                        "drawdown_7d",
                        "warn",
                        f"Просадка за 7 дней {snapshot.drawdown_7d_pct:.1f}%",
                        f"MOEX · {snapshot.data_date}",
                    )
                )
        if snapshot.drawdown_30d_pct is not None:
            if snapshot.drawdown_30d_pct <= settings.risk_max_drawdown_30d:
                checks.append(
                    RiskCheck(
                        "drawdown_30d",
                        "fail",
                        f"Просадка за 30 дней {snapshot.drawdown_30d_pct:.1f}%",
                        f"MOEX · {snapshot.data_date}",
                    )
                )
            elif snapshot.drawdown_30d_pct <= settings.risk_max_drawdown_30d / 2:
                checks.append(
                    RiskCheck(
                        "drawdown_30d",
                        "warn",
                        f"Просадка за 30 дней {snapshot.drawdown_30d_pct:.1f}%",
                        f"MOEX · {snapshot.data_date}",
                    )
                )
        if snapshot.volume_ratio_30d is not None:
            if snapshot.volume_ratio_30d < settings.risk_min_volume_ratio:
                checks.append(
                    RiskCheck(
                        "volume",
                        "warn",
                        f"Объём торгов {snapshot.volume_ratio_30d:.0%} от медианы 30 дней",
                        f"MOEX · {snapshot.data_date}",
                    )
                )
        if snapshot.spread_pct is not None:
            if snapshot.spread_pct > settings.risk_max_spread_pct:
                checks.append(
                    RiskCheck(
                        "spread",
                        "warn",
                        f"Спред bid/ask {snapshot.spread_pct:.1f}%",
                        "MOEX marketdata",
                    )
                )
        else:
            checks.append(
                RiskCheck(
                    "spread",
                    "unknown",
                    "Нет bid/ask в стакане",
                    "MOEX marketdata",
                )
            )
        if (
            snapshot.available_buy_rub is not None
            and snapshot.available_buy_rub < settings.risk_position_size_rub
        ):
            checks.append(
                RiskCheck(
                    "depth",
                    "warn",
                    f"Доступный объём на покупку {snapshot.available_buy_rub:,.0f} ₽",
                    "MOEX marketdata",
                )
            )

    status = _assessment_status(checks)
    return RiskAssessment(
        isin=isin,
        name=name,
        issuer=issuer,
        status=status,
        reason=_reason(checks),
        checks=[
            {
                "name": item.name,
                "status": item.status,
                "message": item.message,
                "source": item.source,
            }
            for item in checks
        ],
        market=market,
        news=[
            {
                "severity": item.severity,
                "term": item.term,
                "title": item.title,
                "source": item.source,
                "url": item.url,
                "published_at": item.published_at,
            }
            for item in news_flags
        ],
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


async def evaluate_candidates(
    settings: Settings,
    repository: RiskRepository,
    candidates: list[dict[str, Any]] | None = None,
) -> list[RiskAssessment]:
    source = candidates or DEMO_RISK_CANDIDATES
    semaphore = asyncio.Semaphore(4)

    async def run(item: dict[str, Any]) -> RiskAssessment:
        async with semaphore:
            return await evaluate_candidate(settings, repository, item)

    return list(await asyncio.gather(*(run(item) for item in source)))


def to_excluded(assessment: RiskAssessment) -> ExcludedCandidate:
    severity = "blocked" if assessment.status == "blocked" else "review"
    return ExcludedCandidate(
        isin=assessment.isin,
        name=assessment.name,
        reason=assessment.reason,
        severity=severity,
    )


def to_candidate(
    assessment: RiskAssessment,
    candidate: dict[str, Any],
) -> CandidateCard:
    return CandidateCard(
        isin=assessment.isin,
        name=assessment.name,
        ytm_pct=float(candidate.get("ytm_pct") or 0),
        duration_years=float(candidate.get("duration_years") or 0),
        rating=str(candidate.get("rating") or "—"),
        price_pct=float(assessment.market.get("last_price_pct") or 0),
        volume_mn_rub=round(float(assessment.market.get("last_value_rub") or 0) / 1_000_000, 2),
        reason="Проверки пройдены. Это не инвестиционная рекомендация.",
        risk_flags=[],
    )


def build_risk_summary(assessments: list[RiskAssessment]) -> dict[str, Any]:
    return {
        "total": len(assessments),
        "passed": sum(1 for item in assessments if item.status == "ok"),
        "blocked": sum(1 for item in assessments if item.status == "blocked"),
        "review": sum(1 for item in assessments if item.status == "review"),
        "checked_at": max((item.checked_at for item in assessments), default=""),
    }


__all__ = [
    "RiskAssessment",
    "build_risk_summary",
    "evaluate_candidate",
    "evaluate_candidates",
    "to_candidate",
    "to_excluded",
]
