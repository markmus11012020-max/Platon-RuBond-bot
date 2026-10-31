from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime

from bondbot.analytics.bonds import (
    COUPON_TYPE_ALIASES,
    coupon_type_label,
    required_daily_volume_mn,
    screen_bonds,
)
from bondbot.analytics.portfolio import analyze_portfolio
from bondbot.analytics.rates import MaxYield, resolve_max_yield
from bondbot.analytics.risk import assess_bond_risk, assess_portfolio_risk, stress_portfolio
from bondbot.config import Settings
from bondbot.data.smartlab import SmartLabClient
from bondbot.db import Database
from bondbot.models import Bond, PortfolioPosition, ScreenFilters, now_msk, to_msk
from bondbot.services.assistant import Assistant
from bondbot.services.ideas import (
    build_ideas,
    build_strategy_note,
    render_ideas,
    render_journal,
    save_ideas,
)
from bondbot.services.issuer import (
    enrich_issuer_payload,
    issuer_payload,
    render_issuer,
)
from bondbot.services.news import build_news_digest
from bondbot.services.relative import build_relative_value
from bondbot.services.review import build_portfolio_review, build_what_changed
from bondbot.strategy.allocation import build_allocation
from bondbot.strategy.exit import build_exit_plan
from bondbot.strategy.render import (
    render_allocation,
    render_exit_plan,
    render_risk,
    render_safe_list,
    render_stress,
    render_valuation,
)
from bondbot.strategy.safe import build_safe_list
from bondbot.strategy.valuation import value_bond
from bondbot.vk.client import VkClient, VkApiError

log = logging.getLogger(__name__)

HELP_TEXT = """Platon Bond Bot — аналитика облигаций РФ.

/portfolio — бумажный портфель и риски
/watch add ISIN — добавить бумагу в наблюдение
/watch remove ISIN — убрать
/watch — список наблюдения
/bond ISIN — карточка бумаги
/issuer НАЗВАНИЕ — обзор эмитента без ISIN
/screen [постоянный|плавающий] [2 4 12] — подбор с фильтром купона
/safe — стабильные бумаги ЦБ+5–10 п.п.
/exit — ликвидность и план выхода
/alloc — целевая аллокация
/value ISIN — доходность после налога, спреды, дюрация
/risk [ISIN] — риск бумаги или портфеля
/stress [б.п.] — стресс-тест по ставке
/news [ISIN] — новости по портфелю или бумаге
/new — новые выпуски
/idea — идеи в коридоре
/journal — журнал идей
/strategy — стратегия на неделю
/relative [ISIN] — сравнение доходности с peers
/calendar [дней] — оферты, погашения, купоны
/doctor — здоровье портфеля
/whatsnew — что изменилось
/position add ISIN кол-во цена | remove ISIN | list
/ask вопрос — ИИ-аналитик (или просто напиши вопрос текстом)
/clear — очистить историю диалога
/keyboard — показать кнопки
/status — состояние данных
/connect — подключить беседу (админ)
/help — эта справка

Данные: smart-lab.ru и MOEX ISS. Это аналитика, не индивидуальная инвестиционная рекомендация."""

MAIN_KEYBOARD = {
    "one_time": False,
    "buttons": [
        [
            {"action": {"type": "text", "label": "/portfolio"}},
            {"action": {"type": "text", "label": "/safe"}},
            {"action": {"type": "text", "label": "/idea"}},
        ],
        [
            {"action": {"type": "text", "label": "/risk"}},
            {"action": {"type": "text", "label": "/stress"}},
            {"action": {"type": "text", "label": "/news"}},
        ],
        [
            {"action": {"type": "text", "label": "/strategy"}},
            {"action": {"type": "text", "label": "/journal"}},
            {"action": {"type": "text", "label": "/help"}},
        ],
    ],
}


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def _num(value: float | None, suffix: str = "", digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}{suffix}"


def _short(text: str, limit: int) -> str:
    # Длинные сообщения разбиваются в _reply, а не обрезаются.
    return (text or "").strip()


def _split_message(text: str, limit: int = 3500) -> list[str]:
    text = (text or "").strip()
    if not text:
        return [""]
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines():
        while len(line) > limit:
            if current:
                chunks.append("\n".join(current).strip())
                current = []
                size = 0
            chunks.append(line[:limit])
            line = line[limit:]
        add = len(line) + (1 if current else 0)
        if size + add > limit:
            chunks.append("\n".join(current).strip())
            current = [line]
            size = len(line)
        else:
            current.append(line)
            size += add
    if current:
        chunks.append("\n".join(current).strip())
    return [chunk for chunk in chunks if chunk] or [text[:limit]]


def format_portfolio(settings: Settings, db: Database) -> str:
    positions = db.positions()
    if not positions:
        return "Портфель пуст. Пришли portfolio.html или добавь бумаги через /watch add ISIN."
    bonds = {bond.isin: bond for bond in db.list_bonds()}
    metrics = analyze_portfolio(
        positions,
        bonds,
        max_pct_daily_volume=settings.max_pct_daily_volume,
    )
    lines = [
        "📊 Бумажный портфель",
        f"Стоимость: {_money(metrics.total_value_rub)}",
        f"P&L: {_money(metrics.profit_rub)}",
        f"Годовой купон: {_money(metrics.annual_coupon_rub)}",
        f"Средняя доходность: {_num(metrics.weighted_ytm_pct, '%')}",
        f"Средняя дюрация: {_num(metrics.weighted_duration_years)} лет",
    ]
    if metrics.rating_mix:
        ratings = " · ".join(
            f"{rating} {share:.0%}" for rating, share in sorted(metrics.rating_mix.items())
        )
        lines.append(f"Рейтинги: {ratings}")
    lines.append("")
    for position in positions:
        bond = bonds.get(position.isin)
        duration = bond.duration_years if bond else None
        lines.append(
            f"• {position.name} ({position.isin})\n"
            f"  {_money(position.current_value_rub)} · P&L {_money(position.profit_rub)} · "
            f"YTM {_num(position.ytm_pct, '%')} · дюр. {_num(duration)} · "
            f"{position.rating or '—'}"
        )
    if metrics.warnings:
        lines.append("")
        lines.append("⚠️ Риски:")
        for warning in metrics.warnings[:8]:
            lines.append(f"• {_short(warning, 180)}")
    lines.append("")
    lines.append(f"Данные: {now_msk().strftime('%d.%m.%Y %H:%M')}")
    return _short("\n".join(lines), 3900)


def format_bond(bond: Bond) -> str:
    lines = [
        f"📌 {bond.name} ({bond.isin})",
        f"Цена: {_num(bond.price_pct, '%')} · YTM: {_num(bond.ytm_pct, '%')} · "
        f"дюрация: {_num(bond.duration_years)} лет",
        f"Рейтинг: {bond.rating or '—'} · G-спред: {_num(bond.g_spread_bp, ' б.п.', 0)}",
        f"Купон: {_num(bond.coupon_rub, ' ₽')} × {_num(bond.coupon_freq, '', 0)} · "
        f"тип: {coupon_type_label(bond.coupon_type)} · "
        f"НКД: {_num(bond.nkd_rub, ' ₽')}",
        f"Погашение: {bond.maturity_date or '—'} · оферта: {bond.offer_date or '—'}",
        f"Дневной оборот: {_num(bond.volume_mn_rub, ' млн ₽')}",
    ]
    if bond.issue_size_rub:
        lines.append(f"Объём выпуска: {_num(bond.issue_size_rub / 1_000_000, ' млн ₽', 0)}")
    if bond.qual_only:
        lines.append("⚠️ Только для квалифицированных инвесторов")
    if bond.amortized:
        lines.append("Амортизируемая облигация")
    if bond.source_url:
        lines.append(bond.source_url)
    lines.append("Аналитика, не индивидуальная инвестиционная рекомендация.")
    return _short("\n".join(lines), 3900)


def format_screen(
    settings: Settings,
    db: Database,
    limit: int = 8,
    max_yield: MaxYield | None = None,
    filters: ScreenFilters | None = None,
) -> str:
    cap = max_yield or MaxYield(value_pct=settings.max_yield_pct, source="fixed")
    filters = filters or ScreenFilters(
        min_yield_pct=settings.min_yield_pct,
        max_yield_pct=cap.value_pct,
        max_duration_years=settings.max_duration_years,
        min_rating=settings.min_rating,
        min_price_pct=settings.min_price_pct,
        max_price_pct=settings.max_price_pct,
        position_size_rub=settings.position_size_rub,
    )
    required = required_daily_volume_mn(
        filters.position_size_rub or settings.position_size_rub,
        settings.max_pct_daily_volume,
    )
    results = screen_bonds(db.list_bonds(), filters, required_volume_mn=required)
    coupon_text = coupon_type_label(filters.coupon_type) if filters.coupon_type else "любой"
    freq_text = (
        ", ".join(f"{freq:g}" for freq in filters.coupon_freqs)
        if filters.coupon_freqs
        else "любая"
    )
    if not results:
        return (
            f"Под текущий профиль ничего не найдено.\n"
            f"Купон: {coupon_text} · выплат в год: {freq_text}\n"
            f"Лимит доходности: {cap.describe()}\n"
            f"Обнови данные на сервере."
        )
    lines = [
        f"🔎 Кандидаты: доходность {filters.min_yield_pct}–{cap.value_pct:.2f}%, "
        f"дюрация ≤ {filters.max_duration_years} лет, рейтинг ≥ {filters.min_rating}",
        f"Купон: {coupon_text} · выплат в год: {freq_text}",
        f"Лимит: {cap.describe()}",
        f"Позиция {_money(filters.position_size_rub or settings.position_size_rub)} ≤ "
        f"{settings.max_pct_daily_volume:.0%} дневного объёма (≥ {required:.0f} млн ₽)",
        "",
    ]
    for item in results[:limit]:
        bond = item.bond
        lines.append(
            f"• {bond.name} ({bond.isin})\n"
            f"  YTM {_num(bond.ytm_pct, '%')} · дюр. {_num(bond.duration_years)} · "
            f"{bond.rating or '—'} · оборот {_num(bond.volume_mn_rub, ' млн ₽')} · "
            f"купон {coupon_type_label(bond.coupon_type)} {_num(bond.coupon_freq, '/год', 0)}"
        )
    lines.append("")
    lines.append("Не рекомендация к покупке. Проверяй оферту, амортизацию и кредитные новости.")
    return _short("\n".join(lines), 3900)


def format_status(
    settings: Settings,
    db: Database,
    max_yield: MaxYield | None = None,
) -> str:
    bonds = db.list_bonds()
    positions = db.positions()
    coupons = sum(len(db.coupons(p.isin)) for p in positions)
    last = to_msk(max((b.fetched_at for b in bonds), default=None))
    cap = max_yield or MaxYield(value_pct=settings.max_yield_pct, source="fixed")
    market_raw = db.kv_get("last_market_refresh")
    news_raw = db.kv_get("last_news_refresh")
    def stamp(raw: str) -> str:
        if not raw:
            return "—"
        try:
            return to_msk(datetime.fromisoformat(raw)).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            return raw
    return (
        f"Бумаг в базе: {len(bonds)}\n"
        f"Позиций: {len(positions)}\n"
        f"Купонов в календаре: {coupons}\n"
        f"Новостей: {db.news_count()} · идей: {len(db.ideas(limit=100))}\n"
        f"Последнее обновление карточек: {last.strftime('%d.%m.%Y %H:%M') if last else '—'}\n"
        f"Рынок обновлён: {stamp(market_raw)}\n"
        f"Новости обновлены: {stamp(news_raw)}\n"
        f"Лимит доходности: {cap.describe()}\n"
        f"LLM: {'on' if settings.llm_configured else 'off'} ({settings.openai_model})\n"
        f"VK: {'configured' if settings.vk_configured else 'not configured'}"
    )


class BotHandlers:
    def __init__(self, settings: Settings, db: Database, vk: VkClient) -> None:
        self.settings = settings
        self.db = db
        self.vk = vk

    async def handle_update(self, update: dict) -> None:
        if update.get("type") != "message_new":
            return
        message = (update.get("object") or {}).get("message") or {}
        text = (message.get("text") or "").strip()
        peer_id = int(message.get("peer_id") or 0)
        from_id = int(message.get("from_id") or 0)
        if not text or from_id <= 0 or not peer_id:
            return

        is_admin = bool(self.settings.vk_admin_user_id) and from_id == self.settings.vk_admin_user_id
        if not is_admin:
            log.warning("ignored message from non-owner %s", from_id)
            return

        # VK добавляет mention сообщества к кнопкам в беседе:
        # "[club123|@club123] /help" или "@club123 /help".
        match = re.search(r"(?<!\S)/[A-Za-zА-Яа-я0-9_]+", text)
        if match is None:
            # Любой обычный текст — это диалог с ИИ, а не команда.
            await self._ask(peer_id, text)
            return
        command = match.group(0).lower().split("@")[0]
        argument = text[match.end():].strip()
        is_chat = VkClient.is_chat_peer(peer_id)

        if command == "/start":
            if not is_chat:
                self.db.kv_set("owner_peer_id", str(peer_id))
            if is_chat:
                await self._reply(peer_id, HELP_TEXT, keyboard=MAIN_KEYBOARD)
            else:
                await self._reply(
                    peer_id,
                    "Привет. Я аналитик по облигациям.\n\n" + HELP_TEXT,
                    keyboard=MAIN_KEYBOARD,
                )
        elif command == "/connect":
            await self._connect(peer_id, is_admin, is_chat)
        elif command == "/portfolio":
            await self._reply(peer_id, format_portfolio(self.settings, self.db))
        elif command == "/screen":
            await self._screen(peer_id, argument)
        elif command in {"/safe", "/stable"}:
            await self._safe(peer_id)
        elif command == "/exit":
            await self._exit(peer_id)
        elif command == "/alloc":
            await self._alloc(peer_id)
        elif command == "/bond":
            await self._bond(peer_id, argument)
        elif command == "/issuer":
            await self._issuer(peer_id, argument)
        elif command == "/value":
            await self._value(peer_id, argument)
        elif command == "/risk":
            await self._risk(peer_id, argument)
        elif command == "/stress":
            await self._stress(peer_id, argument)
        elif command == "/news":
            await self._news(peer_id, argument)
        elif command == "/new":
            await self._new_issues(peer_id)
        elif command == "/idea":
            await self._ideas(peer_id)
        elif command == "/journal":
            await self._reply(peer_id, render_journal(self.db))
        elif command == "/strategy":
            await self._strategy(peer_id)
        elif command == "/relative":
            await self._relative(peer_id, argument)
        elif command == "/calendar":
            await self._calendar(peer_id, argument)
        elif command == "/doctor":
            await self._doctor(peer_id)
        elif command == "/whatsnew":
            await self._reply(peer_id, build_what_changed(self.settings, self.db))
        elif command in {"/keyboard", "/buttons"}:
            await self._reply(peer_id, "Кнопки включены. /help — команды.", keyboard=MAIN_KEYBOARD)
        elif command == "/position":
            await self._position(peer_id, argument)
        elif command == "/ask":
            await self._ask(peer_id, argument)
        elif command in {"/clear", "/reset"}:
            await self._clear_dialog(peer_id)
        elif command == "/watch":
            await self._watch(peer_id, from_id, is_admin, argument)
        elif command == "/status":
            cap = await resolve_max_yield(self.settings, self.db)
            await self._reply(peer_id, format_status(self.settings, self.db, max_yield=cap))
        elif command in {"/help", "/commands"}:
            await self._reply(peer_id, HELP_TEXT, keyboard=MAIN_KEYBOARD)
        else:
            await self._reply(peer_id, "Неизвестная команда. /help — список команд.")

    async def _connect(self, peer_id: int, is_admin: bool, is_chat: bool) -> None:
        if not is_admin:
            await self._reply(peer_id, "Подключить беседу может только админ.")
            return
        if not is_chat:
            await self._reply(peer_id, "Эту команду нужно отправить в беседе.")
            return
        self.db.kv_set("chat_peer_id", str(peer_id))
        await self._reply(peer_id, "Беседа подключена. Сюда буду присылать портфель и алерты.")

    async def _resolve_bond(self, isin: str) -> Bond | None:
        isin = isin.upper()
        bond = self.db.get_bond(isin)
        if bond is not None and bond.duration_years is not None:
            return bond
        try:
            async with SmartLabClient(self.settings) as client:
                fetched, coupons = await client.fetch_detail(isin)
            if fetched is not None:
                self.db.upsert_bonds([fetched])
                if coupons:
                    self.db.upsert_coupons(coupons)
                return fetched
        except Exception as exc:
            log.warning("bond %s fetch failed: %s", isin, exc)
        return bond

    async def _bond(self, peer_id: int, argument: str) -> None:
        isin = argument.strip().upper()
        if not isin:
            await self._reply(peer_id, "Укажи ISIN: /bond RU000A10G1T5")
            return
        bond = await self._resolve_bond(isin)
        if bond is None:
            await self._reply(peer_id, f"Не удалось получить данные по {isin}.")
            return
        await self._reply(peer_id, format_bond(bond))

    async def _issuer(self, peer_id: int, argument: str) -> None:
        name = argument.strip()
        if not name:
            await self._reply(peer_id, "Укажи название: /issuer Балтийский лизинг")
            return
        snapshot = None
        try:
            snapshot = await self._key_rate_snapshot()
        except Exception as exc:
            log.warning("key rate for issuer failed: %s", exc)
        try:
            payload = issuer_payload(
                self.db,
                name,
                key_rate_pct=snapshot.value_pct if snapshot else None,
            )
            payload = await enrich_issuer_payload(self.settings, self.db, payload, name)
        except Exception as exc:
            log.warning("issuer overview failed: %s", exc)
            await self._reply(peer_id, f"Не удалось собрать обзор эмитента: {exc}")
            return
        await self._reply(peer_id, render_issuer(payload))

    async def _value(self, peer_id: int, argument: str) -> None:
        isin = argument.strip().upper()
        if not isin:
            await self._reply(peer_id, "Укажи ISIN: /value RU000A10G1T5")
            return
        bond = await self._resolve_bond(isin)
        if bond is None:
            await self._reply(peer_id, f"Нет данных по {isin}.")
            return
        snapshot = None
        try:
            snapshot = await self._key_rate_snapshot()
        except Exception as exc:
            log.warning("key rate for valuation failed: %s", exc)
        valuation = value_bond(
            bond,
            key_rate_pct=snapshot.value_pct if snapshot else None,
            coupons=self.db.coupons(isin),
        )
        await self._reply(peer_id, render_valuation(valuation))

    async def _risk(self, peer_id: int, argument: str) -> None:
        isin = argument.strip().upper()
        snapshot = None
        try:
            snapshot = await self._key_rate_snapshot()
        except Exception as exc:
            log.warning("key rate for risk failed: %s", exc)
        if isin:
            bond = await self._resolve_bond(isin)
            if bond is None:
                await self._reply(peer_id, f"Нет данных по {isin}.")
                return
            assessment = assess_bond_risk(
                bond, snapshot.value_pct if snapshot else None
            )
            await self._reply(peer_id, render_risk(assessment))
            return
        positions = self.db.positions()
        bonds = {bond.isin: bond for bond in self.db.list_bonds()}
        assessment = assess_portfolio_risk(
            positions, bonds, snapshot.value_pct if snapshot else None
        )
        await self._reply(peer_id, render_risk(assessment))

    async def _stress(self, peer_id: int, argument: str) -> None:
        try:
            delta = float((argument or "100").replace(",", "."))
        except ValueError:
            await self._reply(peer_id, "Укажи изменение ставки в б.п.: /stress 100")
            return
        delta = max(-500.0, min(500.0, delta))
        positions = self.db.positions()
        bonds = {bond.isin: bond for bond in self.db.list_bonds()}
        result = stress_portfolio(positions, bonds, delta)
        await self._reply(peer_id, render_stress(result))

    async def _news(self, peer_id: int, argument: str) -> None:
        isin = argument.strip().upper() or None
        await self._reply(peer_id, build_news_digest(self.settings, self.db, isin=isin))

    async def _new_issues(self, peer_id: int) -> None:
        rows = self.db.recent_new_issues(days=30, limit=10)
        if not rows:
            await self._reply(peer_id, "Новых выпусков с рейтингом за 30 дней пока нет.")
            return
        lines = ["🆕 Новые выпуски", ""]
        for row in rows:
            lines.append(
                f"• {row.get('name') or row['isin']} ({row['isin']}) — "
                f"YTM {_num(row.get('ytm_pct'), '%')}, "
                f"дюр. {_num(row.get('duration_years'))}, "
                f"{row.get('rating') or '—'}"
            )
        await self._reply(peer_id, "\n".join(lines))

    async def _ideas(self, peer_id: int) -> None:
        try:
            snapshot = await self._key_rate_snapshot()
            ideas = build_ideas(self.settings, self.db, snapshot, limit=3)
        except Exception as exc:
            log.warning("ideas failed: %s", exc)
            await self._reply(peer_id, f"Не удалось построить идеи: {exc}")
            return
        saved = save_ideas(self.db, ideas)
        text = render_ideas(ideas, snapshot)
        if saved:
            text += f"\n\nВ журнал добавлено идей: {saved}."
        await self._reply(peer_id, text)

    async def _strategy(self, peer_id: int) -> None:
        try:
            snapshot = await self._key_rate_snapshot()
            text = build_strategy_note(self.settings, self.db, snapshot)
        except Exception as exc:
            log.warning("strategy failed: %s", exc)
            await self._reply(peer_id, f"Не удалось построить стратегию: {exc}")
            return
        await self._reply(peer_id, text)

    async def _position(self, peer_id: int, argument: str) -> None:
        parts = argument.split()
        action = parts[0].lower() if parts else "list"
        if action == "list" or not parts:
            await self._reply(peer_id, format_portfolio(self.settings, self.db))
            return
        if action == "remove":
            if len(parts) < 2:
                await self._reply(peer_id, "Укажи ISIN: /position remove RU000A10G1T5")
                return
            isin = parts[1].upper()
            self.db.remove_position(isin)
            await self._reply(peer_id, f"Позиция {isin} удалена.")
            return
        if action != "add":
            await self._reply(
                peer_id,
                "Команды: /position add ISIN кол-во цена_в_% | "
                "/position remove ISIN | /position list",
            )
            return
        if len(parts) < 4:
            await self._reply(
                peer_id,
                "Формат: /position add RU000A10G1T5 100 99.5 — "
                "количество и цена в % от номинала.",
            )
            return
        isin = parts[1].upper()
        try:
            qty = float(parts[2].replace(",", "."))
            buy_price = float(parts[3].replace(",", "."))
        except ValueError:
            await self._reply(peer_id, "Количество и цена должны быть числами.")
            return
        if qty <= 0 or buy_price <= 0:
            await self._reply(peer_id, "Количество и цена должны быть больше нуля.")
            return
        bond = await self._resolve_bond(isin)
        if bond is None:
            await self._reply(peer_id, f"Нет данных по {isin}.")
            return
        current_price = bond.price_pct or buy_price
        annual_coupon = (
            bond.coupon_rub * bond.coupon_freq * qty
            if bond.coupon_rub is not None and bond.coupon_freq is not None
            else None
        )
        self.db.upsert_positions(
            [
                PortfolioPosition(
                    isin=isin,
                    name=bond.name,
                    qty=qty,
                    buy_price_pct=buy_price,
                    current_price_pct=bond.price_pct,
                    ytm_pct=bond.ytm_pct,
                    rating=bond.rating,
                    g_spread_bp=bond.g_spread_bp,
                    coupon_rub=bond.coupon_rub,
                    coupon_freq=bond.coupon_freq,
                    annual_coupon_rub=annual_coupon,
                    current_value_rub=qty * current_price / 100 * 1000,
                    next_coupon_date=bond.next_coupon_date,
                    source_url=bond.source_url,
                )
            ]
        )
        await self._reply(
            peer_id,
            f"Позиция добавлена: {bond.name} ({isin}) · {qty:g} шт. · "
            f"покупка {buy_price:.2f}% · сейчас {current_price:.2f}%.",
        )

    def _dialog_key(self, peer_id: int) -> str:
        return f"dialog:{peer_id}"

    def _load_dialog(self, peer_id: int) -> list[dict[str, str]]:
        raw = self.db.kv_get(self._dialog_key(peer_id))
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [
            {"role": str(item.get("role")), "content": str(item.get("content"))}
            for item in data
            if isinstance(item, dict)
        ][-12:]

    def _save_dialog(self, peer_id: int, question: str, answer: str) -> None:
        history = self._load_dialog(peer_id)
        history.append({"role": "user", "content": question[:1500]})
        history.append({"role": "assistant", "content": answer[:2000]})
        self.db.kv_set(
            self._dialog_key(peer_id),
            json.dumps(history[-12:], ensure_ascii=False),
        )

    async def _ask(self, peer_id: int, argument: str) -> None:
        question = argument.strip()
        if not question:
            await self._reply(peer_id, "Напиши вопрос: /ask что интересного в коридоре ставки?")
            return
        history = self._load_dialog(peer_id)
        answer = await Assistant(self.settings, self.db).answer(question, history=history)
        if not answer.startswith(("Не удалось", "LLM не настроен")):
            self._save_dialog(peer_id, question, answer)
        await self._reply(peer_id, answer)

    async def _clear_dialog(self, peer_id: int) -> None:
        self.db.kv_set(self._dialog_key(peer_id), "[]")
        await self._reply(peer_id, "История диалога очищена.")

    async def _relative(self, peer_id: int, argument: str) -> None:
        try:
            snapshot = await self._key_rate_snapshot()
            text = build_relative_value(
                self.settings,
                self.db,
                snapshot,
                isin=argument.strip().upper() or None,
            )
        except Exception as exc:
            log.warning("relative value failed: %s", exc)
            await self._reply(peer_id, f"Не удалось посчитать relative value: {exc}")
            return
        await self._reply(peer_id, text)

    async def _calendar(self, peer_id: int, argument: str) -> None:
        try:
            days = max(1, min(365, int((argument or "90").strip())))
        except ValueError:
            days = 90
        today = date.today()
        bonds = {bond.isin: bond for bond in self.db.list_bonds()}
        positions = self.db.positions()
        isins = {position.isin for position in positions} | {
            str(row["isin"]) for row in self.db.watchlist()
        }
        events: list[tuple[int, str, str, str]] = []
        for isin in isins:
            bond = bonds.get(isin)
            if bond is None:
                continue
            for kind, value in (
                ("оферта", bond.offer_date),
                ("погашение", bond.maturity_date),
                ("купон", bond.next_coupon_date),
            ):
                if value is None:
                    continue
                delta = (value - today).days
                if 0 <= delta <= days:
                    events.append((delta, bond.name, kind, value.isoformat()))
        for position in positions:
            for coupon in self.db.coupons(position.isin):
                delta = (coupon.coupon_date - today).days
                if 0 <= delta <= days:
                    events.append(
                        (delta, position.name, "купон", coupon.coupon_date.isoformat())
                    )
        if not events:
            await self._reply(peer_id, f"Событий на {days} дней нет.")
            return
        seen: set[tuple[str, str, str]] = set()
        lines = [f"📅 Календарь на {days} дней", ""]
        for delta, name, kind, value in sorted(events)[:25]:
            key = (name, kind, value)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"• через {delta} дн. ({value}) — {name}: {kind}")
        await self._reply(peer_id, "\n".join(lines))

    async def _doctor(self, peer_id: int) -> None:
        try:
            snapshot = await self._key_rate_snapshot()
            text = build_portfolio_review(self.settings, self.db, snapshot)
        except Exception as exc:
            log.warning("portfolio review failed: %s", exc)
            await self._reply(peer_id, f"Не удалось проверить портфель: {exc}")
            return
        await self._reply(peer_id, text)

    async def _watch(self, peer_id: int, from_id: int, is_admin: bool, argument: str) -> None:
        parts = argument.split()
        action = parts[0].lower() if parts else "list"
        if action == "list" or not parts:
            rows = self.db.watchlist()
            if not rows:
                await self._reply(peer_id, "Список наблюдения пуст.")
                return
            lines = ["👀 Наблюдение:"]
            for row in rows:
                lines.append(
                    f"• {row.get('name') or row['isin']} ({row['isin']}) · "
                    f"YTM {_num(row.get('ytm_pct'), '%')} · {row.get('rating') or '—'}"
                )
            await self._reply(peer_id, _short("\n".join(lines), 3900))
            return
        if not is_admin:
            await self._reply(peer_id, "Менять список наблюдения может только админ.")
            return
        if len(parts) < 2:
            await self._reply(peer_id, "Укажи ISIN: /watch add RU000A10G1T5")
            return
        isin = parts[1].upper()
        if action == "add":
            if self.db.get_bond(isin) is None:
                await self._bond(peer_id, isin)
            self.db.add_watch(isin)
            await self._reply(peer_id, f"{isin} добавлен в наблюдение.")
        elif action == "remove":
            self.db.remove_watch(isin)
            await self._reply(peer_id, f"{isin} удалён из наблюдения.")
        else:
            await self._reply(peer_id, "Команды: /watch add ISIN, /watch remove ISIN, /watch")

    async def _reply(
        self,
        peer_id: int,
        text: str,
        *,
        keyboard: dict | None = None,
    ) -> None:
        chunks = _split_message(_short(text, 3900), limit=3500)
        try:
            for index, chunk in enumerate(chunks):
                await self.vk.send_message(
                    peer_id,
                    chunk,
                    keyboard=keyboard if index == len(chunks) - 1 else None,
                )
        except VkApiError as exc:
            log.warning("reply to %s failed: %s", peer_id, exc)

    async def _key_rate_snapshot(self):
        from bondbot.data.cbr import KeyRateService

        return await KeyRateService(self.settings, self.db).get()

    async def _screen(self, peer_id: int, argument: str) -> None:
        cap = await resolve_max_yield(self.settings, self.db)
        tokens = [token for token in re.split(r"[\s,;]+", argument.lower()) if token]
        coupon_type = None
        freqs: list[float] = []
        for token in tokens:
            if token in COUPON_TYPE_ALIASES:
                coupon_type = COUPON_TYPE_ALIASES[token]
            elif re.fullmatch(r"\d{1,2}", token):
                value = int(token)
                if 1 <= value <= 12:
                    freqs.append(float(value))
        filters = ScreenFilters(
            min_yield_pct=self.settings.min_yield_pct,
            max_yield_pct=cap.value_pct,
            max_duration_years=self.settings.max_duration_years,
            min_rating=self.settings.min_rating,
            min_price_pct=self.settings.min_price_pct,
            max_price_pct=self.settings.max_price_pct,
            coupon_type=coupon_type,
            coupon_freqs=tuple(freqs) if freqs else None,
            position_size_rub=self.settings.position_size_rub,
        )
        await self._reply(
            peer_id,
            format_screen(
                self.settings,
                self.db,
                max_yield=cap,
                filters=filters,
            ),
        )

    async def _safe(self, peer_id: int) -> None:
        try:
            snapshot = await self._key_rate_snapshot()
        except Exception as exc:
            await self._reply(
                peer_id,
                "Не удалось получить ключевую ставку ЦБ — не посчитаю диапазон. "
                f"Попробуй позже.\n{exc}",
            )
            return
        try:
            result = build_safe_list(self.settings, self.db, snapshot, limit=8)
        except Exception as exc:
            log.exception("safe list failed")
            await self._reply(peer_id, f"Не удалось построить список стабильных бумаг: {exc}")
            return
        await self._reply(peer_id, render_safe_list(result))

    async def _exit(self, peer_id: int) -> None:
        try:
            result = build_exit_plan(self.settings, self.db)
        except Exception as exc:
            log.exception("exit plan failed")
            await self._reply(peer_id, f"Не удалось построить план выхода: {exc}")
            return
        await self._reply(peer_id, render_exit_plan(result))

    async def _alloc(self, peer_id: int) -> None:
        try:
            snapshot = await self._key_rate_snapshot()
        except Exception as exc:
            await self._reply(
                peer_id,
                "Не удалось получить ключевую ставку ЦБ — не посчитаю аллокацию. "
                f"Попробуй позже.\n{exc}",
            )
            return
        try:
            result = build_allocation(self.settings, self.db, snapshot)
        except Exception as exc:
            log.exception("allocation failed")
            await self._reply(peer_id, f"Не удалось построить аллокацию: {exc}")
            return
        await self._reply(peer_id, render_allocation(result))
