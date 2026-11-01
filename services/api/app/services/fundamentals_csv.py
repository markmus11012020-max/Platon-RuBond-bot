from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ParsedFundamentalsRow:
    data: dict[str, Any]
    error: str = ""


@dataclass(slots=True)
class ParsedFundamentals:
    rows: list[ParsedFundamentalsRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


HEADER_ALIASES = {
    "isin": "isin",
    "issuer": "issuer",
    "эмитент": "issuer",
    "period": "period",
    "период": "period",
    "revenue_rub": "revenue_rub",
    "выручка": "revenue_rub",
    "net_profit_rub": "net_profit_rub",
    "чистая_прибыль": "net_profit_rub",
    "ebitda_rub": "ebitda_rub",
    "ebitda": "ebitda_rub",
    "net_debt_rub": "net_debt_rub",
    "чистый_долг": "net_debt_rub",
    "equity_rub": "equity_rub",
    "капитал": "equity_rub",
    "current_ratio": "current_ratio",
    "source": "source",
    "источник": "source",
    "source_url": "source_url",
    "ссылка": "source_url",
    "notes": "notes",
    "комментарий": "notes",
}

NUMERIC_FIELDS = (
    "revenue_rub",
    "net_profit_rub",
    "ebitda_rub",
    "net_debt_rub",
    "equity_rub",
    "current_ratio",
)


def decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("\xa0", "").replace(" ", "")
    if not text or text in {"-", "—", "n/a", "нет"}:
        return None
    text = text.replace("₽", "").replace("руб.", "").replace("руб", "")
    text = text.replace("RUB", "").replace("RUR", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"не число: {value!r}") from None


def _normalize_header(value: str) -> str:
    key = value.strip().lower().replace(" ", "_")
    return HEADER_ALIASES.get(key, key)


def parse_fundamentals_csv(raw: bytes, *, max_rows: int = 2000) -> ParsedFundamentals:
    text = decode_csv(raw)
    if not text.strip():
        return ParsedFundamentals(errors=["пустой файл"])

    first_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        return ParsedFundamentals(errors=["нет заголовка CSV"])

    headers = [_normalize_header(name or "") for name in reader.fieldnames]
    result = ParsedFundamentals()
    for index, raw_row in enumerate(reader, start=2):
        if index - 1 > max_rows:
            result.errors.append(f"строк больше лимита {max_rows}, импорт остановлен")
            break
        row: dict[str, Any] = {}
        for original, header in zip(reader.fieldnames, headers):
            if header:
                row[header] = (raw_row.get(original) or "").strip()
        if not any(row.values()):
            continue

        isin = str(row.get("isin") or "").strip().upper()
        issuer = str(row.get("issuer") or "").strip()
        period = str(row.get("period") or "").strip()
        source = str(row.get("source") or "").strip()
        if not isin and not issuer:
            result.rows.append(
                ParsedFundamentalsRow(data=row, error=f"строка {index}: нужен ISIN или эмитент")
            )
            continue
        if not period or not source:
            result.rows.append(
                ParsedFundamentalsRow(data=row, error=f"строка {index}: нужны period и source")
            )
            continue

        try:
            for field_name in NUMERIC_FIELDS:
                row[field_name] = _number(row.get(field_name))
        except ValueError as exc:
            result.rows.append(
                ParsedFundamentalsRow(data=row, error=f"строка {index}: {exc}")
            )
            continue

        row["isin"] = isin
        row["issuer"] = issuer
        row["period"] = period
        row["source"] = source
        row["source_url"] = str(row.get("source_url") or "").strip()
        row["notes"] = str(row.get("notes") or "").strip()
        result.rows.append(ParsedFundamentalsRow(data=row))
    return result


def template_csv() -> str:
    headers = [
        "isin",
        "issuer",
        "period",
        "revenue_rub",
        "net_profit_rub",
        "ebitda_rub",
        "net_debt_rub",
        "equity_rub",
        "current_ratio",
        "source",
        "source_url",
        "notes",
    ]
    example = [
        "RU000A10E4Y1",
        "Аэрофьюэлз",
        "2025FY",
        "12500000000",
        "1200000000",
        "2100000000",
        "3400000000",
        "5000000000",
        "1.4",
        "e-disclosure / МСФО 2025",
        "https://www.e-disclosure.ru/",
        "Суммы в рублях",
    ]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    writer.writerow(example)
    return output.getvalue()


__all__ = [
    "ParsedFundamentals",
    "ParsedFundamentalsRow",
    "decode_csv",
    "parse_fundamentals_csv",
    "template_csv",
]
