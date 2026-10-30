from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime

from bondbot.analytics.bonds import required_daily_volume_mn, screen_bonds
from bondbot.config import load_settings
from bondbot.data.smartlab import SmartLabClient
from bondbot.db import Database
from bondbot.models import Bond, ScreenFilters

log = logging.getLogger("bondbot")


def _fmt(value: float | None, suffix: str = "", digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}{suffix}"


def _print_bond(bond: Bond) -> None:
    print(
        f"{bond.isin}  {bond.name}\n"
        f"  доходность: {_fmt(bond.ytm_pct, '%')}  дюрация: {_fmt(bond.duration_years, ' лет')}  "
        f"рейтинг: {bond.rating or '—'}  цена: {_fmt(bond.price_pct, '%')}\n"
        f"  объём: {_fmt(bond.volume_mn_rub, ' млн ₽')}  купон: {_fmt(bond.coupon_rub, ' ₽')}  "
        f"частота: {_fmt(bond.coupon_freq, '')}\n"
        f"  погашение: {bond.maturity_date or '—'}  оферта: {bond.offer_date or '—'}\n"
        f"  {bond.source_url}"
    )


async def cmd_update(args: argparse.Namespace, db: Database) -> None:
    settings = load_settings()
    async with SmartLabClient(settings) as client:
        bonds = await client.fetch_screener(pages=args.pages)
    count = db.upsert_bonds(bonds)
    print(f"Загружено/обновлено: {count} бумаг")
    for bond in sorted(bonds, key=lambda item: item.ytm_pct or 0, reverse=True)[:5]:
        _print_bond(bond)


async def cmd_bond(args: argparse.Namespace, db: Database) -> None:
    settings = load_settings()
    async with SmartLabClient(settings) as client:
        bond, coupons = await client.fetch_detail(args.isin)
    if bond is None:
        print(f"Не удалось разобрать карточку {args.isin}")
        return
    db.upsert_bonds([bond])
    if coupons:
        db.upsert_coupons(coupons)
    _print_bond(bond)
    if coupons:
        print(f"  купонов в календаре: {len(coupons)}")
        for coupon in coupons[:3]:
            print(f"    {coupon.coupon_date}: {_fmt(coupon.value_rub, ' ₽')}")


async def cmd_screen(args: argparse.Namespace, db: Database) -> None:
    settings = load_settings()
    position = args.position or settings.position_size_rub
    filters = ScreenFilters(
        min_yield_pct=args.yield_min if args.yield_min is not None else settings.min_yield_pct,
        max_yield_pct=args.yield_max if args.yield_max is not None else settings.max_yield_pct,
        max_duration_years=args.duration_max if args.duration_max is not None else settings.max_duration_years,
        min_rating=args.rating or settings.min_rating,
        min_volume_mn_rub=args.volume_min,
        min_price_pct=args.price_min if args.price_min is not None else settings.min_price_pct,
        max_price_pct=args.price_max if args.price_max is not None else settings.max_price_pct,
        exclude_qual_only=not args.allow_qual,
        position_size_rub=position,
    )
    required = required_daily_volume_mn(position, settings.max_pct_daily_volume)
    results = screen_bonds(db.list_bonds(), filters, required_volume_mn=required)
    print(
        f"Фильтр: доходность {filters.min_yield_pct}–{filters.max_yield_pct}%, "
        f"дюрация <= {filters.max_duration_years} лет, рейтинг >= {filters.min_rating}, "
        f"цена {filters.min_price_pct}–{filters.max_price_pct}%, объём >= {required:.1f} млн ₽ "
        f"(позиция {position:,.0f} ₽, доля объёма <= {settings.max_pct_daily_volume:.0%})"
    )
    if not results:
        print("Ничего не найдено. Обнови базу: python -m bondbot.cli update")
        return
    print(f"{'ISIN':14} {'Доходн':>7} {'Дюр':>5} {'Рейт':>5} {'Объём':>8} {'Цена':>7}  Имя")
    for item in results[: args.limit]:
        bond = item.bond
        print(
            f"{bond.isin:14} {_fmt(bond.ytm_pct, '%'):>7} {_fmt(bond.duration_years):>5} "
            f"{(bond.rating or '—'):>5} {_fmt(bond.volume_mn_rub):>8} {_fmt(bond.price_pct):>7}  "
            f"{bond.name[:45]}"
        )
        if item.liquidity_share is not None:
            print(f"    позиция = {item.liquidity_share:.1%} дневного объёма")


async def cmd_watch(args: argparse.Namespace, db: Database) -> None:
    if args.action == "add":
        if db.get_bond(args.isin) is None:
            await cmd_bond(argparse.Namespace(isin=args.isin), db)
        db.add_watch(args.isin, args.note or "")
        print(f"{args.isin.upper()} добавлен в watchlist")
    elif args.action == "remove":
        db.remove_watch(args.isin)
        print(f"{args.isin.upper()} удалён из watchlist")
    else:
        rows = db.watchlist()
        if not rows:
            print("watchlist пуст")
            return
        for row in rows:
            if row.get("name"):
                print(
                    f"{row['isin']}  {row['name']}  доходность={_fmt(row.get('ytm_pct'), '%')}  "
                    f"дюрация={_fmt(row.get('duration_years'))}  рейтинг={row.get('rating') or '—'}"
                )
            else:
                print(f"{row['isin']}  нет данных — сделай bond {row['isin']}")


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}".replace(",", " ") + " ₽"


async def cmd_import_portfolio(args: argparse.Namespace, db: Database) -> None:
    from bondbot.data.smartlab import SmartLabClient
    from bondbot.importers.smartlab_portfolio import import_portfolio_file

    positions = import_portfolio_file(db, args.file)
    settings = load_settings()
    async with SmartLabClient(settings) as client:
        for position in positions:
            try:
                bond, coupons = await client.fetch_detail(position.isin)
                if bond is not None:
                    db.upsert_bonds([bond])
                if coupons:
                    db.upsert_coupons(coupons)
            except Exception as exc:
                log.warning("detail %s failed: %s", position.isin, exc)
            await asyncio.sleep(1.0)
    totals = db.portfolio_totals()
    print(f"Импортировано позиций: {len(positions)}")
    print(f"Стоимость: {_fmt_money(totals['total_value_rub'])}")
    print(f"Прибыль: {_fmt_money(totals['profit_rub'])}")
    print(f"Годовой купон: {_fmt_money(totals['annual_coupon_rub'])}")
    await cmd_portfolio(args, db)


async def cmd_portfolio(args: argparse.Namespace, db: Database) -> None:
    from bondbot.analytics.portfolio import analyze_portfolio

    positions = db.positions()
    if positions:
        bonds = {bond.isin: bond for bond in db.list_bonds()}
        metrics = analyze_portfolio(positions, bonds)
        print(
            f"{'ISIN':14} {'Кол-во':>8} {'Покупка':>8} {'Цена':>7} {'Стоимость':>12} "
            f"{'P&L':>10} {'Доходн':>7} {'Дюр':>5} {'Рейт':>5}  Имя"
        )
        for position in positions:
            bond = bonds.get(position.isin)
            duration = bond.duration_years if bond else None
            print(
                f"{position.isin:14} {position.qty:>8.0f} {_fmt(position.buy_price_pct):>8} "
                f"{_fmt(position.current_price_pct):>7} {_fmt_money(position.current_value_rub):>12} "
                f"{_fmt_money(position.profit_rub):>10} {_fmt(position.ytm_pct, '%'):>7} "
                f"{_fmt(duration):>5} {(position.rating or '—'):>5}  {position.name[:40]}"
            )
        print(
            f"\nИтого: {_fmt_money(metrics.total_value_rub)} · "
            f"P&L {_fmt_money(metrics.profit_rub)} · "
            f"годовой купон {_fmt_money(metrics.annual_coupon_rub)}"
        )
        print(
            f"Средняя доходность: {_fmt(metrics.weighted_ytm_pct, '%')} · "
            f"средняя дюрация: {_fmt(metrics.weighted_duration_years)} лет"
        )
        if metrics.rating_mix:
            print(
                "Рейтинги: "
                + " · ".join(
                    f"{rating} {share:.0%}" for rating, share in sorted(metrics.rating_mix.items())
                )
            )
        if metrics.warnings:
            print("Предупреждения:")
            for warning in metrics.warnings:
                print(f"  - {warning}")
        print(f"Данные портфеля: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        return

    rows = db.watchlist()
    if not rows:
        print("Портфель пуст: импортируй portfolio.html или добавь бумаги через watch add <ISIN>")
        return
    print(f"{'ISIN':14} {'Доходн':>7} {'Дюр':>5} {'Рейт':>5} {'Цена':>7} {'Купон':>7}  Имя")
    for row in rows:
        print(
            f"{row['isin']:14} {_fmt(row.get('ytm_pct'), '%'):>7} {_fmt(row.get('duration_years')):>5} "
            f"{(row.get('rating') or '—'):>5} {_fmt(row.get('price_pct')):>7} "
            f"{_fmt(row.get('coupon_rub')):>7}  {(row.get('name') or 'нет данных')[:45]}"
        )
    print(f"\nОбновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}")


async def async_main(args: argparse.Namespace) -> None:
    db = Database(args.db)
    try:
        if args.command == "update":
            await cmd_update(args, db)
        elif args.command == "bond":
            await cmd_bond(args, db)
        elif args.command == "screen":
            await cmd_screen(args, db)
        elif args.command == "watch":
            await cmd_watch(args, db)
        elif args.command == "portfolio":
            await cmd_portfolio(args, db)
        elif args.command == "import-portfolio":
            await cmd_import_portfolio(args, db)
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Platon bond bot CLI")
    parser.add_argument("--db", default=None, help="path to SQLite (default from BONDBOT_DB_PATH)")
    sub = parser.add_subparsers(dest="command", required=True)

    update = sub.add_parser("update", help="fetch smart-lab screener")
    update.add_argument("--pages", type=int, default=None)

    bond = sub.add_parser("bond", help="fetch bond detail")
    bond.add_argument("isin")

    screen = sub.add_parser("screen", help="screen bonds from local DB")
    screen.add_argument("--yield-min", type=float, default=None)
    screen.add_argument("--yield-max", type=float, default=None)
    screen.add_argument("--duration-max", type=float, default=None)
    screen.add_argument("--rating", default=None)
    screen.add_argument("--volume-min", type=float, default=None)
    screen.add_argument("--price-min", type=float, default=None)
    screen.add_argument("--price-max", type=float, default=None)
    screen.add_argument("--position", type=float, default=None)
    screen.add_argument("--limit", type=int, default=15)
    screen.add_argument("--allow-qual", action="store_true")

    watch = sub.add_parser("watch", help="manage watchlist")
    watch.add_argument("action", choices=["add", "remove", "list"])
    watch.add_argument("isin", nargs="?")
    watch.add_argument("note", nargs="?")

    sub.add_parser("portfolio", help="show watchlist with current metrics")
    import_portfolio = sub.add_parser("import-portfolio", help="import smart-lab portfolio HTML")
    import_portfolio.add_argument("--file", required=True, help="saved portfolio.html")
    return parser


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args()
    if not args.db:
        args.db = load_settings().db_path
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
