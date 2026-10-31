from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from bondbot.config import Settings
from bondbot.data.quality import sanitize_bond
from bondbot.models import Bond, Coupon

log = logging.getLogger(__name__)

HEADER_TO_FIELD = {
    "имя": "name",
    "лет до погаш.": "years_to_maturity",
    "доходн": "ytm_pct",
    "год.куп. дох.": "annual_coupon_yield_pct",
    "куп.дох. посл.": "current_coupon_yield_pct",
    "рейтинг": "rating",
    "g-спред": "g_spread_bp",
    "объем млн руб": "volume_mn_rub",
    "купон, руб": "coupon_rub",
    "частота, раз в год": "coupon_freq",
    "нкд, руб": "nkd_rub",
    "дюр-я, лет": "duration_years",
    "цена": "price_pct",
    "дата купона": "next_coupon_date",
    "размещение": "placement_date",
    "погашение": "maturity_date",
    "оферта": "offer_date",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip().lower()


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = (value.replace("\xa0", " ").replace("%", "").replace(" ", "").replace(",", "."))
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    number = _parse_float(value)
    return int(number) if number is not None else None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d.%m.%y", "%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _norm_rating(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().upper()
    if value in {"-", "—", "НЕТ", "N/A"}:
        return None
    return value


def _norm_coupon_freq(value: float | None) -> float | None:
    if value is None:
        return None
    for common in (1, 2, 4, 6, 12):
        if abs(value - common) <= 0.5:
            return float(common)
    return value


def _norm_coupon_type(value: str | None) -> str | None:
    if not value:
        return None
    text = value.lower()
    if "структур" in text:
        return "structured"
    if "фиксирован" in text or "постоян" in text:
        return "fixed"
    if "плава" in text or "перемен" in text:
        return "floating"
    return None


def _parse_screener_row(row: Any, field_index: dict[str, int], source_url: str) -> Bond | None:
    cells = row.find_all("td")
    if len(cells) < 19:
        return None

    def cell(field: str) -> str:
        index = field_index.get(field)
        if index is None or index >= len(cells):
            return ""
        return cells[index].get_text(" ", strip=True)

    name_cell = cells[1] if len(cells) > 1 else None
    link = name_cell.find("a", href=True) if name_cell else None
    href = link.get("href") if link else ""
    isin_match = re.search(r"/q/bonds/([A-Z0-9]+)/", href or "")
    if not isin_match:
        return None
    isin = isin_match.group(1)
    name = (link.get_text(" ", strip=True) if link else cell("name")).strip()
    if not name:
        return None

    return Bond(
        isin=isin,
        name=name,
        price_pct=_parse_float(cell("price_pct")),
        ytm_pct=_parse_float(cell("ytm_pct")),
        current_coupon_yield_pct=_parse_float(cell("current_coupon_yield_pct")),
        annual_coupon_yield_pct=_parse_float(cell("annual_coupon_yield_pct")),
        rating=_norm_rating(cell("rating")),
        g_spread_bp=_parse_float(cell("g_spread_bp")),
        volume_mn_rub=_parse_float(cell("volume_mn_rub")),
        coupon_rub=_parse_float(cell("coupon_rub")),
        coupon_freq=_norm_coupon_freq(_parse_float(cell("coupon_freq"))),
        nkd_rub=_parse_float(cell("nkd_rub")),
        duration_years=_parse_float(cell("duration_years")),
        next_coupon_date=_parse_date(cell("next_coupon_date")),
        placement_date=_parse_date(cell("placement_date")),
        maturity_date=_parse_date(cell("maturity_date")),
        offer_date=_parse_date(cell("offer_date")),
        years_to_maturity=_parse_float(cell("years_to_maturity")),
        amortized="амортизац" in name.lower(),
        source_url=source_url,
        fetched_at=datetime.now(timezone.utc),
    )


def parse_screener(html: str, source_url: str = "") -> list[Bond]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        return []
    rows = table.find_all("tr")
    if not rows:
        return []

    header_cells = rows[0].find_all(["th", "td"])
    field_index: dict[str, int] = {}
    for index, header in enumerate(header_cells):
        field = HEADER_TO_FIELD.get(_norm(header.get_text(" ", strip=True)))
        if field:
            field_index[field] = index

    bonds: list[Bond] = []
    for row in rows[1:]:
        bond = _parse_screener_row(row, field_index, source_url)
        if bond is not None:
            bonds.append(bond)
    return bonds


def _extract_first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


def parse_detail(html: str, isin: str = "") -> tuple[Bond | None, list[Coupon]]:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = soup.get_text(" ", strip=True)

    name = None
    if isin:
        name = _extract_first(rf"Облигация\s+(.+?)\s*\({re.escape(isin)}\)", title)
    if not name:
        name = _extract_first(r"Облигация\s+(.+?)\s*\(", title) or title[:120]
    name = re.sub(r"\s+", " ", name or "").strip()

    price_pct = _parse_float(_extract_first(r"Котировка облигации,\s*%\s*([\d.,]+)", text))
    ytm = _parse_float(
        _extract_first(r"Доходность\*?\s*облигации к погашению составляет\s*([\d.,]+)%", text)
    )
    years = _parse_float(_extract_first(r"Лет до погашения\s*([\d.,]+)", text))
    duration_days = _parse_float(_extract_first(r"Дюрация,\s*дней\s*(\d+)", text))
    coupon = _parse_float(_extract_first(r"Купон,\s*руб.*?([\d]+[.,][\d]+)", text))
    coupon_freq = _parse_float(_extract_first(r"Частота купона,\s*раз в год\s*([\d.,]+)", text))
    coupon_type = _norm_coupon_type(
        _extract_first(r"(?:Тип купона|Тип ставки)\s*[:\-]?\s*([А-Яа-яA-Za-z]+)", text)
    )
    nkd = _parse_float(_extract_first(r"НКД.*?([\d]+[.,][\d]+)", text))
    current_yield = _parse_float(
        _extract_first(r"Текущ\.\s*дох\.\s*купона\s*([\d.,]+)%", text)
    )
    g_spread = _parse_float(_extract_first(r"G-спред.*?(-?\d+)", text))
    face = _parse_float(_extract_first(r"Номинал\s*([\d\s]+)", text))
    issue_mn = _parse_float(_extract_first(r"Объем выпуска,\s*млн руб\s*([\d\s]+)", text))
    volume_day = _parse_float(
        _extract_first(r"Объем день,\s*млн\.?\s*руб\s*([\d.,]+)", text)
    )
    rating = _norm_rating(_extract_first(r"Кредитный рейтинг\s*([A-ZА-Я+\-]+)", text))
    qual_raw = _extract_first(r"Только для квалов\?\s*(Да|Нет)", text)
    qual_only = qual_raw.lower() == "да" if qual_raw else None

    maturity = _parse_date(_extract_first(r"Дата погашения\s*(\d{2}-\d{2}-\d{4})", text))
    placement = _parse_date(_extract_first(r"Дата размещения\s*(\d{2}-\d{2}-\d{4})", text))
    next_coupon = _parse_date(_extract_first(r"Дата след\.\s*выплаты\s*(\d{2}-\d{2}-\d{4})", text))
    offer = None
    if "Оферты отсутствуют" not in text:
        offer = _parse_date(_extract_first(r"Дата оферты.*?(\d{2}-\d{2}-\d{4})", text))

    bond = Bond(
        isin=isin,
        name=name,
        issuer=None,
        price_pct=price_pct,
        ytm_pct=ytm,
        current_coupon_yield_pct=current_yield,
        rating=rating,
        g_spread_bp=g_spread,
        coupon_rub=coupon,
        coupon_freq=_norm_coupon_freq(coupon_freq),
        coupon_type=coupon_type,
        nkd_rub=nkd,
        volume_mn_rub=volume_day,
        duration_years=round(duration_days / 365, 4) if duration_days else None,
        next_coupon_date=next_coupon,
        placement_date=placement,
        maturity_date=maturity,
        offer_date=offer,
        years_to_maturity=years,
        face_value=face,
        issue_size_rub=issue_mn * 1_000_000 if issue_mn else None,
        qual_only=qual_only,
        amortized="Амортизируемая облигация" in text or "амортизац" in name.lower(),
        source_url=f"https://smart-lab.ru/q/bonds/{isin}/" if isin else "",
        fetched_at=datetime.now(timezone.utc),
    )

    coupons: list[Coupon] = []
    for table in soup.find_all("table"):
        header_text = table.get_text(" ", strip=True)[:120].lower()
        if "дата купона" not in header_text or "купон" not in header_text:
            continue
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            coupon_date = _parse_date(cells[1].get_text(" ", strip=True))
            if coupon_date is None:
                continue
            coupons.append(
                Coupon(
                    isin=isin,
                    coupon_date=coupon_date,
                    value_rub=_parse_float(cells[2].get_text(" ", strip=True)),
                    yield_pct=_parse_float(cells[3].get_text(" ", strip=True)) if len(cells) > 3 else None,
                )
            )
        break

    return bond, coupons


class SmartLabClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "SmartLabClient":
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.settings.request_timeout),
            headers={
                "User-Agent": self.settings.user_agent,
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._session is not None:
            await self._session.close()

    def page_url(self, page: int) -> str:
        base = self.settings.smartlab_base
        if page <= 1:
            return f"{base}/q/bonds/order_by_val_to_day/desc/"
        return f"{base}/q/bonds/order_by_val_to_day/desc/page{page}/"

    def detail_url(self, isin: str) -> str:
        return f"{self.settings.smartlab_base}/q/bonds/{isin.upper()}/"

    async def _fetch(self, url: str) -> str:
        if self._session is None:
            raise RuntimeError("client is not started")
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                async with self._session.get(url) as response:
                    if response.status >= 500:
                        raise aiohttp.ClientResponseError(
                            response.request_info,
                            response.history,
                            status=response.status,
                            message=f"smart-lab HTTP {response.status}",
                        )
                    if response.status >= 400:
                        raise RuntimeError(f"smart-lab HTTP {response.status}: {url}")
                    return await response.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt >= 3:
                    raise
                log.warning("smart-lab attempt %s failed for %s: %s", attempt, url, exc)
                await asyncio.sleep(1.0 * attempt)
        raise RuntimeError(f"smart-lab unavailable: {last_error}")

    async def fetch_screener(self, pages: int | None = None) -> list[Bond]:
        pages = pages or self.settings.smartlab_pages
        bonds: list[Bond] = []
        seen: set[str] = set()
        for page in range(1, max(1, pages) + 1):
            url = self.page_url(page)
            html = await self._fetch(url)
            parsed = [sanitize_bond(bond) for bond in parse_screener(html, source_url=url)]
            for bond in parsed:
                if bond.isin not in seen:
                    seen.add(bond.isin)
                    bonds.append(bond)
            log.info("smart-lab page %s: %s bonds", page, len(parsed))
            if page < pages:
                await asyncio.sleep(1.0)
        return bonds

    async def fetch_detail(self, isin: str) -> tuple[Bond | None, list[Coupon]]:
        html = await self._fetch(self.detail_url(isin))
        bond, coupons = parse_detail(html, isin.upper())
        return (sanitize_bond(bond) if bond is not None else None), coupons
