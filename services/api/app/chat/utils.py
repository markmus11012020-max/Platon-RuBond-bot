from __future__ import annotations

import re

ISIN_RE = re.compile(r"\bRU[A-Z0-9]{10}\b")


def extract_isin(text: str | None) -> str | None:
    match = ISIN_RE.search((text or "").upper())
    return match.group(0) if match else None


__all__ = ["ISIN_RE", "extract_isin"]
