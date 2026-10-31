from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, datetime

from bondbot.analytics.bonds import COUPON_TYPE_ALIASES
from bondbot.analytics.presets import PRESET_LABELS, preset_filters
from bondbot.analytics.rates import MaxYield
from bondbot.config import Settings
from bondbot.models import ScreenFilters

_DATE = r"(\d{2}[.\-]\d{2}[.\-]\d{4}|\d{4}-\d{2}-\d{2})"

SORT_ALIASES = {
    "доходность": "yield",
    "доходности": "yield",
    "доход": "yield",
    "дюрация": "duration",
    "дюрации": "duration",
    "дюрацию": "duration",
    "погашение": "maturity",
    "погашения": "maturity",
    "оферта": "offer",
    "оферты": "offer",
    "частота": "coupon_freq",
    "частоту": "coupon_freq",
    "купон": "coupon_type",
    "тип": "coupon_type",
    "рейтинг": "rating",
    "цена": "price",
    "объём": "volume",
    "объем": "volume",
    "выпуск": "issue_size",
    "скор": "score",
}


def _number(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _date(value: str) -> date | None:
    for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _range(text: str, label: str) -> tuple[float | None, float | None]:
    pattern = rf"{label}[^\d]{{0,12}}(?:от\s+)?([\d.,]+)\s*(?:-|–|—|\.\.|до)\s*([\d.,]+)"
    match = re.search(pattern, text)
    if match:
        return _number(match.group(1)), _number(match.group(2))
    match = re.search(rf"{label}[^\d]{{0,12}}(?:до|≤)\s*([\d.,]+)", text)
    if match:
        return None, _number(match.group(1))
    match = re.search(rf"{label}[^\d]{{0,12}}(?:от|≥)\s*([\d.,]+)", text)
    if match:
        return _number(match.group(1)), None
    return None, None


def _date_range(text: str, label: str) -> tuple[date | None, date | None]:
    match = re.search(rf"{label}[^\d]{{0,12}}{_DATE}\s*(?:-|–|—|\.\.|до)\s*{_DATE}", text)
    if match:
        return _date(match.group(1)), _date(match.group(2))
    match = re.search(rf"{label}[^\d]{{0,12}}(?:до|к)\s*{_DATE}", text)
    if match:
        return None, _date(match.group(1))
    match = re.search(rf"{label}[^\d]{{0,12}}(?:от|после)\s*{_DATE}", text)
    if match:
        return _date(match.group(1)), None
    return None, None


def parse_screen_query(
    settings: Settings,
    argument: str,
    max_yield: MaxYield,
) -> ScreenFilters:
    text = " ".join((argument or "").lower().replace("ё", "е").split())
    preset = None
    for key, label in PRESET_LABELS.items():
        if key in text or label in text:
            preset = key
            break
    filters = (
        preset_filters(settings, preset, max_yield)
        if preset
        else ScreenFilters(
            min_yield_pct=settings.min_yield_pct,
            max_yield_pct=max_yield.value_pct,
            max_duration_years=settings.max_duration_years,
            min_rating=settings.min_rating,
            min_price_pct=settings.min_price_pct,
            max_price_pct=settings.max_price_pct,
            position_size_rub=settings.position_size_rub,
        )
    )

    y_min, y_max = _range(text, r"доходност\w*")
    if y_min is not None:
        filters = replace(filters, min_yield_pct=y_min)
    if y_max is not None:
        filters = replace(filters, max_yield_pct=y_max)

    d_min, d_max = _range(text, r"дюрац\w*")
    if d_min is not None:
        filters = replace(filters, min_duration_years=d_min)
    if d_max is not None:
        filters = replace(filters, max_duration_years=d_max)

    m_from, m_to = _date_range(text, r"погашени\w*")
    if m_from is not None:
        filters = replace(filters, maturity_from=m_from)
    if m_to is not None:
        filters = replace(filters, maturity_to=m_to)

    o_from, o_to = _date_range(text, r"оферт\w*")
    if o_from is not None:
        filters = replace(filters, offer_from=o_from)
    if o_to is not None:
        filters = replace(filters, offer_to=o_to)

    for alias, normalized in COUPON_TYPE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}", text):
            filters = replace(filters, coupon_type=normalized)
            break

    if re.search(r"(частот|выплат|раз в год)", text) or filters.coupon_type:
        freq_text = re.split(
            r"погашени|оферт|цена|рейтинг|сортиров|эмитент",
            text,
            maxsplit=1,
        )[0]
        values = list(
            dict.fromkeys(
                float(value)
                for value in re.findall(r"\b(1|2|4|6|12)\b", freq_text)
            )
        )
        if values:
            filters = replace(filters, coupon_freqs=tuple(values))

    rating = re.search(r"рейтинг[^\w]{0,12}([A-D][A-D+-]{0,4})", text.upper())
    if rating:
        filters = replace(filters, min_rating=rating.group(1))

    p_min, p_max = _range(text, r"цен\w*")
    if p_min is not None:
        filters = replace(filters, min_price_pct=p_min)
    if p_max is not None:
        filters = replace(filters, max_price_pct=p_max)

    volume = re.search(r"(оборот|объем|объём)[^\d]{0,12}(?:от|≥)\s*([\d.,]+)", text)
    if volume:
        value = _number(volume.group(2))
        if value is not None:
            filters = replace(filters, min_volume_mn_rub=value)

    issue = re.search(r"выпуск[^\d]{0,12}(?:от|≥)\s*([\d.,]+)", text)
    if issue:
        value = _number(issue.group(1))
        if value is not None:
            filters = replace(filters, min_issue_size_rub=value * 1_000_000)

    if "без амортизации" in text:
        filters = replace(filters, exclude_amortized=True)
    if "полные данные" in text:
        filters = replace(filters, only_complete_data=True)

    sort = re.search(r"сортиров\w*[^\w]{0,8}(?:по\s+)?([а-яa-z]+)", text)
    if sort:
        field = SORT_ALIASES.get(sort.group(1))
        if field:
            filters = replace(filters, sort_by=field)
    if re.search(r"(по возрастанию|возрастани)", text):
        filters = replace(filters, sort_order="asc")
    elif re.search(r"(по убыванию|убывани)", text):
        filters = replace(filters, sort_order="desc")

    issuer = re.search(r"эмитент[^\w]{0,8}([^,;]+)", text)
    if issuer:
        filters = replace(filters, issuer=issuer.group(1).strip())

    page = re.search(r"страниц\w*[^\d]{0,5}(\d+)", text)
    if page:
        offset = max(0, int(page.group(1)) - 1) * 8
        filters = replace(filters, offset=offset, limit=8)
    return filters


__all__ = ["parse_screen_query"]
