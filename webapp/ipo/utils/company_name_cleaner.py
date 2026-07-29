from __future__ import annotations

import html
import re
from typing import Any


NOISE_PATTERNS = (
    r"\bIPO\s+Detail\b.*$",
    r"\bStock\s+Quotes\b.*$",
    r"\bSymbol\s+pending\b.*$",
    r"\bListed\s*:\s*\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2}\b.*$",
    r"\bListed\s*:.*$",
    r"\bListed\s+On\b.*$",
)


def _remove_duplicate_short_prefix(text: str) -> str:
    parts = text.split()
    if len(parts) < 2:
        return text
    first = re.sub(r"[^A-Za-z0-9]", "", parts[0])
    second = re.sub(r"[^A-Za-z0-9]", "", parts[1])
    if first and len(first) <= 3 and second.upper().startswith(first.upper()):
        return " ".join(parts[1:])
    return text


def clean_ipo_company_name(raw_name: Any) -> str:
    """Return a production-safe company name from noisy IPO tracker text.

    IPO trackers often join hidden detail links, stock-quote labels, listing
    dates, and a duplicated two-letter prefix into the company column. This
    keeps the actual company name for display, Screener search, and symbol
    resolution without inventing a tradingsymbol.
    """

    text = html.unescape(str(raw_name or ""))
    text = text.replace("\ufeff", " ").replace("\u200b", " ").replace("\xa0", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    for pattern in NOISE_PATTERNS:
        text = re.sub(r"\s*" + pattern, "", text, flags=re.I).strip()
    text = re.sub(r"\s+", " ", text).strip(" -|:\t\r\n")
    text = _remove_duplicate_short_prefix(text)
    return re.sub(r"\s+", " ", text).strip(" -|:\t\r\n")
