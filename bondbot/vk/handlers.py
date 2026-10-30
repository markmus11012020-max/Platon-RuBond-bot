from __future__ import annotations

import logging
from datetime import datetime

from bondbot.analytics.bonds import required_daily_volume_mn, screen_bonds
from bondbot.analytics.portfolio import analyze_portfolio
from bondbot.analytics.rates import MaxYield, resolve_max_yield
from bondbot.config import Settings
from bondbot.data.smartlab import SmartLabClient
from bondbot.db import Database
from bondbot.models import Bond, ScreenFilters
from bondbot.vk.client import VkClient, VkApiError

log = logging.getLogger(__name__)

HELP_TEXT = """Platon Bond Bot — аналитика облигаций РФ.

/portfolio — бумажный портфель и риски
/watch add ISIN — добавить бумагу в наблюдение
/watch remove ISIN — убрать
/watch — список наблюдения
/bond ISIN — карточка бумаги
/screen — подбор по текущему профилю
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
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


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
    lines.append(f"Данные: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
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
    last = max((b.fetched_at for b in bonds), default=None)
    cap = max_yield or MaxYield(value_pct=settings.max_yield_pct, source="fixed")
    return (
        f"Бумаг в базе: {len(bonds)}\n"
        f"Позиций: {len(positions)}\n"
        f"Купонов в календаре: {coupons}\n"
        f"Последнее обновление: {last.strftime('%d.%m.%Y %H:%M') if last else '—'}\n"
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

        if command == "/start":
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
        elif command == "/bond":
            await self._bond(peer_id, argument)
        elif command == "/watch":
            await self._watch(peer_id, from_id, is_admin, argument)
        elif command == "/status":
            cap = await resolve_max_yield(self.settings, self.db)
            await self._reply(peer_id, format_status(self.settings, self.db, max_yield=cap))
        elif command in {"/help", "/commands"}:
            await self._reply(peer_id, HELP_TEXT)
        elif command == "/ask":
            await self._reply(peer_id, "Диалог с ИИ подключу на следующем этапе. Пока доступны команды из /help.")
        elif command == "/news":
            await self._reply(peer_id, "Новостной монитор подключу на следующем этапе.")
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

    async def _bond(self, peer_id: int, argument: str) -> None:
        isin = argument.strip().upper()
        if not isin:
            await self._reply(peer_id, "Укажи ISIN: /bond RU000A10G1T5")
            return
        bond = self.db.get_bond(isin)
        if bond is None or bond.duration_years is None:
            try:
                async with SmartLabClient(self.settings) as client:
                    bond, coupons = await client.fetch_detail(isin)
                if bond is not None:
                    self.db.upsert_bonds([bond])
                    if coupons:
                        self.db.upsert_coupons(coupons)
            except Exception as exc:
                log.warning("bond %s fetch failed: %s", isin, exc)
                await self._reply(peer_id, f"Не удалось получить данные по {isin}.")
                return
        if bond is None:
            await self._reply(peer_id, f"Не удалось разобрать карточку {isin}.")
            return
        await self._reply(peer_id, format_bond(bond))

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
