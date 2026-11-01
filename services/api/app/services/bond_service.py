from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.demo import (
    DEMO_AS_OF,
    DEMO_EXCLUDED,
    DEMO_INSIGHTS,
    demo_events,
    demo_positions,
)
from app.schemas import (
    ActionCard,
    AllocationSlice,
    BondOverview,
    ChatResponse,
    ConfirmResponse,
    EventCard,
    ExcludedCandidate,
    PortfolioSummary,
    PositionCard,
)
from app.services.llm_service import LLMAnswerer

COLORS = ["#f6c453", "#7dd3fc", "#a7f3d0", "#c4b5fd", "#fda4af", "#93c5fd"]

_ACTIONS: dict[str, ActionCard] = {}


def _summary(positions: list[dict]) -> PortfolioSummary:
    total = sum(item["value_rub"] for item in positions)
    profit = sum(item.get("pnl_rub") or 0 for item in positions)
    coupon = sum(item.get("annual_coupon_rub") or 0 for item in positions)
    ytm = sum((item.get("ytm_pct") or 0) * item["value_rub"] for item in positions) / total
    duration = (
        sum((item.get("duration_years") or 0) * item["value_rub"] for item in positions)
        / total
    )
    return PortfolioSummary(
        total_value_rub=round(total, 2),
        profit_rub=round(profit, 2),
        annual_coupon_rub=round(coupon, 2),
        weighted_ytm_pct=round(ytm, 2),
        weighted_duration_years=round(duration, 2),
        risk_level="MEDIUM",
        risk_score=42,
        positions_count=len(positions),
    )


def _allocation(positions: list[dict]) -> list[AllocationSlice]:
    total = sum(item["value_rub"] for item in positions)
    return [
        AllocationSlice(
            name=item["name"],
            value_rub=round(item["value_rub"], 2),
            share_pct=round(item["value_rub"] / total * 100, 1) if total else 0.0,
            color=COLORS[index % len(COLORS)],
        )
        for index, item in enumerate(positions)
    ]


def _rating_mix(positions: list[dict]) -> dict[str, float]:
    total = sum(item["value_rub"] for item in positions)
    mix: dict[str, float] = {}
    for item in positions:
        rating = item.get("rating") or "—"
        mix[rating] = mix.get(rating, 0.0) + item["value_rub"]
    return {
        rating: round(value / total * 100, 1) if total else 0.0
        for rating, value in sorted(mix.items(), key=lambda pair: -pair[1])
    }


def build_overview() -> BondOverview:
    positions = demo_positions()
    return BondOverview(
        as_of=DEMO_AS_OF,
        summary=_summary(positions),
        positions=[
            PositionCard(
                isin=item["isin"],
                name=item["name"],
                qty=item["qty"],
                value_rub=item["value_rub"],
                weight_pct=item["weight_pct"],
                ytm_pct=item.get("ytm_pct"),
                duration_years=item.get("duration_years"),
                rating=item.get("rating"),
                current_price_pct=item.get("current_price_pct"),
                buy_price_pct=item.get("buy_price_pct"),
                pnl_rub=item.get("pnl_rub"),
                annual_coupon_rub=item.get("annual_coupon_rub"),
                next_coupon_date=item.get("next_coupon_date"),
                maturity_date=item.get("maturity_date"),
                offer_date=item.get("offer_date"),
            )
            for item in positions
        ],
        allocation=_allocation(positions),
        rating_mix=_rating_mix(positions),
        events=[
            EventCard(
                date=item["date"],
                kind=item["kind"],
                title=item["title"],
                isin=item["isin"],
                days=item["days"],
            )
            for item in demo_events()
        ],
        candidates=[],
        excluded=[
            ExcludedCandidate(
                isin=item["isin"],
                name=item["name"],
                reason=item["reason"],
                severity=item["severity"],
            )
            for item in DEMO_EXCLUDED
        ],
        insights=DEMO_INSIGHTS,
    )


def _review_action() -> ActionCard:
    action = ActionCard(
        id="review-tgk-concentration",
        title="Проверить концентрацию ТГК-14 1Р5",
        description=(
            "Автоматическую замену не предлагаю. Кандидаты не прошли проверку "
            "кредитных событий и ликвидности. Сначала проверьте первоисточники, "
            "кредитные события, цену, объём и доступность бумаги."
        ),
        kind="review",
        expected_effect={
            "concentration_pct": 27.3,
            "limit_pct": 25.0,
        },
        legs=[],
        risk_notes=[
            "МГКЛ 2Р9 исключён: по данным мониторинга зафиксирован технический дефолт.",
            "БалтЛизП12 исключён: аномальная распродажа, цена и объём вне нормы.",
            "Аэрофьюэл 2Р4 исключён: недостаточно проверенных данных.",
            "Сделка не выставляется. Это чек-лист проверки, а не рекомендация.",
        ],
    )
    _ACTIONS[action.id] = action
    return action


async def answer(question: str, history: list[dict[str, str]] | None = None) -> ChatResponse:
    text = (question or "").strip().lower()
    overview = build_overview()
    summary = overview.summary

    if any(word in text for word in ("привет", "что ты", "кто ты", "помощь")):
        return ChatResponse(
            message=(
                "Я Bond Copilot — агент по облигационному портфелю. "
                "Могу показать состав, риски, купоны и оферты, подобрать замену "
                "и подготовить сделку в sandbox."
            ),
            suggestions=[
                "Покажи портфель",
                "Где риск?",
                "Что с купонами?",
                "Предложи замену",
            ],
        )

    is_swap = any(
        word in text
        for word in ("замен", "swap", "доходн", "улучш", "продать", "купить")
    )
    if not is_swap:
        llm_text = await LLMAnswerer(get_settings()).answer(
            question, overview, history
        )
        if llm_text:
            return ChatResponse(
                message=llm_text,
                suggestions=["Покажи портфель", "Где риск?", "Предложи замену"],
            )

    if any(word in text for word in ("брифинг", "утр", "план на день", "premarket")):
        events = "\n".join(
            f"• {item.date}: {item.title} — через {item.days} дн."
            for item in overview.events[:4]
        )
        return ChatResponse(
            message=(
                "Утренний брифинг по портфелю:\n"
                f"• Стоимость: {summary.total_value_rub:,.0f} ₽, "
                f"YTM {summary.weighted_ytm_pct:.2f}%, "
                f"дюрация {summary.weighted_duration_years:.2f} года.\n"
                f"• Купонный поток: {summary.annual_coupon_rub:,.0f} ₽ в год.\n"
                f"• Ближайшие события:\n{events}\n\n"
                "Фокус: доля ТГК-14 выше лимита, есть кандидаты на замену. "
                "Сделки — только после подтверждения."
            ).replace(",", " "),
            suggestions=["Предложи замену", "Где риск?", "Покажи портфель"],
        )

    if any(word in text for word in ("риск", "стресс", "концентрац")):
        return ChatResponse(
            message=(
                "Главные риски сейчас:\n"
                "• ТГК-14 1Р5 — 27% портфеля, выше лимита 25%.\n"
                "• Рейтинг BBB- — самый низкий в портфеле.\n"
                "• Средняя дюрация 1,48 года, процентный риск умеренный.\n"
                "• Ликвидность МГКЛ 2Р9 ниже, чем у ОФЗ, учитывай при объёме."
            ),
            suggestions=["Предложи замену", "Покажи купоны", "Открой портфель"],
        )

    if any(word in text for word in ("купон", "оферт", "календар", "погаш")):
        events = "\n".join(
            f"• {item.date}: {item.title} — через {item.days} дн."
            for item in overview.events[:5]
        )
        return ChatResponse(
            message=(
                "Ближайшие события по портфелю:\n"
                f"{events}\n\n"
                "Оферта СовкоКап01 10 декабря — хороший повод заранее сравнить "
                "доходность с альтернативами."
            ),
            suggestions=["Предложи замену", "Где риск?", "Покажи портфель"],
        )

    if is_swap:
        action = _review_action()
        return ChatResponse(
            message=(
                "Автоматическую замену не предлагаю: сначала нужна проверка "
                "кредитных событий и ликвидности.\n\n"
                "Что уже исключено:\n"
                "• МГКЛ 2Р9 — технический дефолт по данным мониторинга.\n"
                "• БалтЛизП12 — аномальная распродажа, цена и объём вне нормы.\n"
                "• Аэрофьюэл 2Р4 — недостаточно проверенных данных.\n\n"
                "Могу зафиксировать риск-проверку и показать чек-лист. "
                "Сделка не выставляется."
            ),
            suggestions=["Зафиксировать проверку", "Где риск?", "Покажи портфель"],
            action=action,
        )

    if any(word in text for word in ("портфель", "состав", "стоимость", "сколько")):
        positions = "\n".join(
            f"• {item.name}: {item.value_rub:,.0f} ₽, YTM {item.ytm_pct:.1f}%, "
            f"{item.rating}"
            for item in overview.positions
        ).replace(",", " ")
        return ChatResponse(
            message=(
                f"Портфель: {summary.total_value_rub:,.0f} ₽, "
                f"P&L {summary.profit_rub:,.0f} ₽, "
                f"годовой купон {summary.annual_coupon_rub:,.0f} ₽.\n"
                f"Средняя YTM {summary.weighted_ytm_pct:.2f}%, "
                f"дюрация {summary.weighted_duration_years:.2f} года.\n\n"
                f"{positions}".replace(",", " ")
            ),
            suggestions=["Где риск?", "Предложи замену", "Что с купонами?"],
        )

    return ChatResponse(
        message=(
            f"По портфелю: {summary.total_value_rub:,.0f} ₽, "
            f"средняя YTM {summary.weighted_ytm_pct:.2f}%, "
            f"дюрация {summary.weighted_duration_years:.2f} года.\n\n"
            "Могу разобрать риски, купоны и оферты или подготовить swap. "
            "Сформулируй задачу: «снизить риск», «повысить доходность», "
            "«что с офертой»."
        ).replace(",", " "),
        suggestions=["Покажи портфель", "Где риск?", "Предложи замену"],
    )


def confirm_action(action_id: str) -> ConfirmResponse | None:
    action = _ACTIONS.get(action_id)
    if action is None:
        return None
    action.status = "confirmed"
    now = datetime.now(timezone.utc)
    review = action.kind == "review"
    return ConfirmResponse(
        action_id=action.id,
        status="confirmed",
        message=(
            "Риск-проверка зафиксирована. Сделка не выставлялась. "
            "Перед любым решением нужны первоисточники, проверка кредитных "
            "событий и ликвидности."
            if review
            else (
                "Сделка подтверждена в sandbox. В production-режиме здесь будет "
                "вызов MCP order-tool после повторной проверки лимитов."
            )
        ),
        audit_id=f"PRE-{now.strftime('%Y%m%d-%H%M%S')}",
        executed_at=now.isoformat(),
    )


__all__ = ["answer", "build_overview", "confirm_action"]
