from __future__ import annotations

import logging
from datetime import datetime

from bondbot.analytics.bonds import required_daily_volume_mn, screen_bonds
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
from bondbot.services.news import build_news_digest
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
/screen — подбор по текущему профилю
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
/position add ISIN кол-во цена | remove ISIN | list
/ask вопрос — ИИ-аналитик
/status — состояние данных
/connect — подключить беседу (админ)
/help — эта справка

Данные: smart-lab.ru. Это аналитика, не индивидуальная инвестиционная рекомендация."""


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def _num(value: float | None, suffix: str = "", digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}{suffix}"


def _short(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


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
) -> str:
    cap = max_yield or MaxYield(value_pct=settings.max_yield_pct, source="fixed")
    filters = ScreenFilters(
        min_yield_pct=settings.min_yield_pct,
        max_yield_pct=cap.value_pct,
        max_duration_years=settings.max_duration_years,
        min_rating=settings.min_rating,
        min_price_pct=settings.min_price_pct,
        max_price_pct=settings.max_price_pct,
        position_size_rub=settings.position_size_rub,
    )
    required = required_daily_volume_mn(
        settings.position_size_rub, settings.max_pct_daily_volume
    )
    results = screen_bonds(db.list_bonds(), filters, required_volume_mn=required)
    if not results:
        return (
            f"Под текущий профиль ничего не найдено.\n"
            f"Лимит доходности: {cap.describe()}\n"
            f"Обнови данные на сервере."
        )
    lines = [
        f"🔎 Кандидаты: доходность {settings.min_yield_pct}–{cap.value_pct:.2f}%, "
        f"дюрация ≤ {settings.max_duration_years} лет, рейтинг ≥ {settings.min_rating}",
        f"Лимит: {cap.describe()}",
        f"Позиция {_money(settings.position_size_rub)} ≤ {settings.max_pct_daily_volume:.0%} "
        f"дневного объёма (≥ {required:.0f} млн ₽)",
        "",
    ]
    for item in results[:limit]:
        bond = item.bond
        lines.append(
            f"• {bond.name} ({bond.isin})\n"
            f"  YTM {_num(bond.ytm_pct, '%')} · дюр. {_num(bond.duration_years)} · "
            f"{bond.rating or '—'} · оборот {_num(bond.volume_mn_rub, ' млн ₽')}"
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

        command, _, argument = text.partition(" ")
        command = command.lower().split("@")[0]
        is_admin = bool(self.settings.vk_admin_user_id) and from_id == self.settings.vk_admin_user_id
        is_chat = VkClient.is_chat_peer(peer_id)

        if not is_admin:
            log.warning("ignored message from non-owner %s", from_id)
            return

        if command == "/start":
            if not is_chat:
                self.db.kv_set("owner_peer_id", str(peer_id))
            if is_chat:
                await self._reply(peer_id, HELP_TEXT)
            else:
                await self._reply(peer_id, "Привет. Я аналитик по облигациям.\n\n" + HELP_TEXT)
        elif command == "/connect":
            await self._connect(peer_id, is_admin, is_chat)
        elif command == "/portfolio":
            await self._reply(peer_id, format_portfolio(self.settings, self.db))
        elif command == "/screen":
            cap = await resolve_max_yield(self.settings, self.db)
            await self._reply(peer_id, format_screen(self.settings, self.db, max_yield=cap))
        elif command in {"/safe", "/stable"}:
            await self._safe(peer_id)
        elif command == "/exit":
            await self._exit(peer_id)
        elif command == "/alloc":
            await self._alloc(peer_id)
        elif command == "/bond":
            await self._bond(peer_id, argument)
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
        elif command == "/position":
            await self._position(peer_id, argument)
        elif command == "/ask":
            await self._ask(peer_id, argument)
        elif command == "/watch":
            await self._watch(peer_id, from_id, is_admin, argument)
        elif command == "/status":
            cap = await resolve_max_yield(self.settings, self.db)
            await self._reply(peer_id, format_status(self.settings, self.db, max_yield=cap))
        elif command in {"/help", "/commands"}:
            await self._reply(peer_id, HELP_TEXT)
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

    async def _ask(self, peer_id: int, argument: str) -> None:
        if not argument.strip():
            await self._reply(peer_id, "Напиши вопрос: /ask что интересного в коридоре ставки?")
            return
        answer = await Assistant(self.settings, self.db).answer(argument)
        await self._reply(peer_id, answer)

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

    async def _reply(self, peer_id: int, text: str) -> None:
        try:
            await self.vk.send_message(peer_id, _short(text, 3900))
        except VkApiError as exc:
            log.warning("reply to %s failed: %s", peer_id, exc)

    async def _key_rate_snapshot(self):
        from bondbot.data.cbr import KeyRateService

        return await KeyRateService(self.settings, self.db).get()

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
