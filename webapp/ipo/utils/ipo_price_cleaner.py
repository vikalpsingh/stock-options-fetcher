"""Shared IPO price normalization helpers.

IPO tracker pages vary heavily: some use rupee symbols, commas, percent signs,
blank dashes, or literal zeroes for unavailable prices. Treating those zeroes as
real prices creates false rankings and division-by-zero bugs, so production IPO
analysis should normalize them before scoring.
"""

from __future__ import annotations

import html
import re
from typing import Any


IPO_PRICE_MISSING = "IPO_PRICE_MISSING"
LISTING_PRICE_MISSING = "LISTING_PRICE_MISSING"
CURRENT_PRICE_MISSING = "CURRENT_PRICE_MISSING"

_EMPTY_PRICE_VALUES = {
    "",
    "-",
    "--",
    "NA",
    "N/A",
    "NONE",
    "NULL",
    "NIL",
    "SYMBOL PENDING",
}


def clean_price(value: Any, *, zero_is_missing: bool = False) -> float | None:
    """Return a float from common IPO tracker price text, or None when unusable."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return None if zero_is_missing and parsed == 0 else parsed

    text = html.unescape(str(value or ""))
    text = (
        text.replace("\ufeff", " ")
        .replace("\u200b", " ")
        .replace("\xa0", " ")
        .replace("₹", " ")
        .replace("â‚¹", " ")
        .replace("Rs.", " ")
        .replace("Rs", " ")
        .replace("INR", " ")
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text.upper() in _EMPTY_PRICE_VALUES:
        return None

    match = re.search(r"-?\d+(?:,\d{2,3})*(?:\.\d+)?|-?\d+(?:\.\d+)?", text.replace("%", " "))
    if not match:
        return None
    try:
        parsed = float(match.group(0).replace(",", ""))
    except ValueError:
        return None
    if zero_is_missing and parsed == 0:
        return None
    return parsed


def missing_price_flag(field_name: str) -> str:
    """Return the standard data-quality flag for a missing IPO price field."""

    key = re.sub(r"[^a-z0-9]+", "_", str(field_name or "").strip().lower())
    if key in {"ipo_price", "issue_price", "issue_price_rs"}:
        return IPO_PRICE_MISSING
    if key in {"listing_price", "listing_day_close", "listing_day_price"}:
        return LISTING_PRICE_MISSING
    if key in {"current_price", "ltp", "cmp"}:
        return CURRENT_PRICE_MISSING
    return f"{key.upper()}_MISSING" if key else "PRICE_MISSING"
