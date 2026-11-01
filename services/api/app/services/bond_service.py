from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.demo import (
    DEMO_AS_OF,
    DEMO_CANDIDATES,
    DEMO_INSIGHTS,
    DEMO_POSITIONS,
    demo_events,
    demo_positions,
)
from app.schemas import (
    ActionCard,
    ActionLeg,
    AllocationSlice,
    BondOverview,
    CandidateCard,
    ChatResponse,
    ConfirmResponse,
    EventCard,
    PortfolioSummary,
    PositionCard,
)

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
        candidates=[
            CandidateCard(
                isin=item["isin"],
                name=item["name"],
                ytm_pct=item["ytm_pct"],
                duration_years=item["duration_years"],
                rating=item["rating"],
                price_pct=item["price_pct"],
                volume_mn_rub=item["volume_mn_rub"],
                reason=item["reason"],
            )
            for item in DEMO_CANDIDATES
        ],
        insights=DEMO_INSIGHTS,
    )


def _swap_action() -> ActionCard:
    action = ActionCard(
        id="swap-tgk-mgkl",
        title="Снизить долю ТГК-14 и добавить МГКЛ 2Р9",
        description=(
            "Продать 200 шт. ТГК-14 1Р5 и купить 200 шт. МГКЛ 2Р9. "
            "Доля ТГК-14 снизится примерно до 24%, портфель станет доходнее "
            "при сопоставимой дюрации."
        ),
        kind="rebalance",
        expected_effect={
            "yield_delta_pct": 0.1,
            "duration_delta_years": -0.02,
            "free_cash_rub": 11_000,
            "rating_change": "BBB- → A- по новой позиции",
        },
        legs=[
            ActionLeg(
                side="sell",
                isin="RU000A10AS02",
                name="ТГК-14 1Р5",
                quantity=200,
                price_pct=105.0,
                amount_rub=210_000,
            ),
            ActionLeg(
                side="buy",
                isin="RU000A10G1Q1",
                name="МГКЛ 2Р9",
                quantity=200,
                price_pct=99.5,
                amount_rub=199_000,
            ),
        ],
        risk_notes=[
            "МГКЛ 2Р9 — эмитент с рейтингом A-, проверь кредитный риск.",
            "Сделка в sandbox: реальные заявки не выставляются.",
            "Перед подтверждением проверь цену и доступный объём.",
        ],
    )
    _ACTIONS[action.id] = action
    return action


def answer(question: str, history: list[dict[str, str]] | None = None) -> ChatResponse:
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

    if any(word in text for word in ("замен", "swap", "доходн", "улучш", "продать", "купить")):
        action = _swap_action()
        return ChatResponse(
            message=(
                "Вижу понятный swap-сценарий:\n"
                "• Продать 200 шт. ТГК-14 1Р5 по 105,0% — около 210 000 ₽.\n"
                "• Купить 200 шт. МГКЛ 2Р9 по 99,5% — около 199 000 ₽.\n"
                "• Доходность портфеля +0,1 п.п., дюрация почти не меняется.\n"
                "• Доля ТГК-14 снижается с 27% до 24%.\n\n"
                "Это не рекомендация. Проверь карточку сделки и подтверди в sandbox."
            ),
            suggestions=["Подтвердить сделку", "Покажи риски", "Другой вариант"],
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
    return ConfirmResponse(
        action_id=action.id,
        status="confirmed",
        message=(
            "Сделка подтверждена в sandbox. В production-режиме здесь будет "
            "вызов MCP order-tool после повторной проверки лимитов."
        ),
        audit_id=f"PRE-{now.strftime('%Y%m%d-%H%M%S')}",
        executed_at=now.isoformat(),
    )


__all__ = ["answer", "build_overview", "confirm_action"]
