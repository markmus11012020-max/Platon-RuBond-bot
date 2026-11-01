from __future__ import annotations

from datetime import date

DEMO_AS_OF = "2026-11-01T09:15:00+03:00"

DEMO_POSITIONS: list[dict] = [
    {
        "isin": "RU000A10AS02",
        "name": "ТГК-14 1Р5",
        "qty": 1500,
        "value_rub": 1_575_000.0,
        "ytm_pct": 24.2,
        "duration_years": 1.71,
        "rating": "BBB-",
        "current_price_pct": 105.0,
        "buy_price_pct": 105.48,
        "pnl_rub": -7_200.0,
        "annual_coupon_rub": 376_238.0,
        "next_coupon_date": "2026-11-21",
        "maturity_date": "2029-01-09",
        "offer_date": None,
        "color": "#f6c453",
    },
    {
        "isin": "RU000A10FWZ8",
        "name": "АЛМ01Р2",
        "qty": 1000,
        "value_rub": 998_800.0,
        "ytm_pct": 19.7,
        "duration_years": 1.52,
        "rating": "A-",
        "current_price_pct": 99.88,
        "buy_price_pct": 99.88,
        "pnl_rub": 0.0,
        "annual_coupon_rub": 177_480.0,
        "next_coupon_date": "2026-11-15",
        "maturity_date": "2028-08-10",
        "offer_date": None,
        "color": "#7dd3fc",
    },
    {
        "isin": "RU000A10AS28",
        "name": "БинФарм1P4",
        "qty": 1000,
        "value_rub": 1_015_700.0,
        "ytm_pct": 19.1,
        "duration_years": 1.10,
        "rating": "A-",
        "current_price_pct": 101.57,
        "buy_price_pct": 101.57,
        "pnl_rub": 0.0,
        "annual_coupon_rub": 187_440.0,
        "next_coupon_date": "2026-11-20",
        "maturity_date": "2028-01-22",
        "offer_date": None,
        "color": "#a7f3d0",
    },
    {
        "isin": "RU000A10DSY4",
        "name": "СовкоКап01",
        "qty": 950,
        "value_rub": 968_810.0,
        "ytm_pct": 18.5,
        "duration_years": 1.70,
        "rating": "A+",
        "current_price_pct": 101.98,
        "buy_price_pct": 101.60,
        "pnl_rub": 3_610.0,
        "annual_coupon_rub": 180_595.0,
        "next_coupon_date": "2026-11-10",
        "maturity_date": "2029-11-24",
        "offer_date": "2026-12-10",
        "color": "#c4b5fd",
    },
    {
        "isin": "RU000A10ES32",
        "name": "ОДК1Р01",
        "qty": 600,
        "value_rub": 603_900.0,
        "ytm_pct": 18.0,
        "duration_years": 1.95,
        "rating": "A+",
        "current_price_pct": 100.65,
        "buy_price_pct": 100.19,
        "pnl_rub": 2_760.0,
        "annual_coupon_rub": 102_000.0,
        "next_coupon_date": "2026-11-03",
        "maturity_date": "2029-03-22",
        "offer_date": None,
        "color": "#fda4af",
    },
    {
        "isin": "RU000A10DNX7",
        "name": "Сплит ПВ-2",
        "qty": 600,
        "value_rub": 606_600.0,
        "ytm_pct": 16.6,
        "duration_years": 0.60,
        "rating": "AAA",
        "current_price_pct": 101.10,
        "buy_price_pct": 100.82,
        "pnl_rub": 1_680.0,
        "annual_coupon_rub": 103_740.0,
        "next_coupon_date": "2026-11-30",
        "maturity_date": "2030-01-30",
        "offer_date": None,
        "color": "#93c5fd",
    },
]

DEMO_EVENTS: list[dict] = [
    {
        "date": "2026-11-03",
        "kind": "coupon",
        "title": "Купон ОДК1Р01",
        "isin": "RU000A10ES32",
    },
    {
        "date": "2026-11-10",
        "kind": "coupon",
        "title": "Купон СовкоКап01",
        "isin": "RU000A10DSY4",
    },
    {
        "date": "2026-11-15",
        "kind": "coupon",
        "title": "Купон АЛМ01Р2",
        "isin": "RU000A10FWZ8",
    },
    {
        "date": "2026-11-21",
        "kind": "coupon",
        "title": "Купон ТГК-14 1Р5",
        "isin": "RU000A10AS02",
    },
    {
        "date": "2026-11-30",
        "kind": "coupon",
        "title": "Купон Сплит ПВ-2",
        "isin": "RU000A10DNX7",
    },
    {
        "date": "2026-12-10",
        "kind": "offer",
        "title": "Оферта СовкоКап01",
        "isin": "RU000A10DSY4",
    },
    {
        "date": "2028-01-22",
        "kind": "maturity",
        "title": "Погашение БинФарм1P4",
        "isin": "RU000A10AS28",
    },
]

DEMO_EXCLUDED: list[dict] = [
    {
        "isin": "RU000A10G1Q1",
        "name": "МГКЛ 2Р9",
        "reason": (
            "По данным мониторинга зафиксирован технический дефолт. "
            "Бумага исключена из кандидатов до проверки первоисточника и условий."
        ),
        "severity": "blocked",
    },
    {
        "isin": "RU000A10FWC7",
        "name": "БалтЛизП12",
        "reason": (
            "Аномальная распродажа: цена и объём вне обычного профиля. "
            "Исключена до проверки кредитного события и ликвидности."
        ),
        "severity": "blocked",
    },
    {
        "isin": "RU000A10G1T5",
        "name": "Аэрофьюэл 2Р4",
        "reason": (
            "Недостаточно проверенных данных по кредитному качеству, "
            "ликвидности и свежести котировок."
        ),
        "severity": "review",
    },
]

DEMO_FREELANCE_ORDERS: list[dict] = [
    {
        "id": 101,
        "title": "AI-агент для анализа заявок в Telegram",
        "source": "fl.ru",
        "budget_text": "80 000 ₽",
        "score": 68,
        "url": "https://www.fl.ru/",
        "published_at": "2026-11-01T06:40:00+00:00",
        "category": "AI / боты",
        "matched_keywords": ["python", "ai агент", "telegram"],
        "red_flags": [],
    },
    {
        "id": 102,
        "title": "Автоматизация отчётов и выгрузок в Excel",
        "source": "kwork.ru",
        "budget_text": "25 000 ₽",
        "score": 54,
        "url": "https://kwork.ru/",
        "published_at": "2026-11-01T05:10:00+00:00",
        "category": "Автоматизация",
        "matched_keywords": ["python", "excel"],
        "red_flags": [],
    },
    {
        "id": 103,
        "title": "Парсер маркетплейса с ежедневной выгрузкой",
        "source": "freelance.ru",
        "budget_text": "40 000 ₽",
        "score": 61,
        "url": "https://freelance.ru/",
        "published_at": "2026-10-31T18:20:00+00:00",
        "category": "Парсинг",
        "matched_keywords": ["python", "парсинг"],
        "red_flags": ["нужна проверка ToS источника"],
    },
]

DEMO_INSIGHTS = [
    "ТГК-14 1Р5 занимает 27% портфеля — выше комфортного лимита 25%.",
    "Автоматические идеи отключены: кандидаты не проходят проверку кредитных событий и ликвидности.",
    "Ближайшая оферта — СовкоКап01 10 декабря. Есть время на проверку альтернатив.",
    "Купонный поток 1,13 млн ₽ в год покрывает около 19,5% стоимости портфеля.",
]


def demo_events() -> list[dict]:
    today = date.today()
    result = []
    for item in DEMO_EVENTS:
        try:
            days = (date.fromisoformat(item["date"]) - today).days
        except ValueError:
            days = 0
        if days < 0:
            continue
        result.append({**item, "days": days})
    return sorted(result, key=lambda item: item["days"])


def demo_positions() -> list[dict]:
    total = sum(item["value_rub"] for item in DEMO_POSITIONS)
    return [
        {
            **item,
            "weight_pct": round(item["value_rub"] / total * 100, 1) if total else 0.0,
        }
        for item in DEMO_POSITIONS
    ]


__all__ = [
    "DEMO_AS_OF",
    "DEMO_EXCLUDED",
    "DEMO_FREELANCE_ORDERS",
    "DEMO_INSIGHTS",
    "DEMO_POSITIONS",
    "demo_events",
    "demo_positions",
]
