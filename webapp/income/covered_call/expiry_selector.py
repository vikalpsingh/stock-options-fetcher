"""Expiry selection helpers for monthly covered calls."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .config import COVERED_CALL_CONFIG, CoveredCallConfig
from .models import ExpiryChoice


def _as_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d %b %Y", "%d-%b-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def select_monthly_expiry(
    instruments: list[dict[str, Any]],
    *,
    as_of: date,
    config: CoveredCallConfig = COVERED_CALL_CONFIG,
) -> ExpiryChoice:
    """Prefer the next monthly expiry in the 28-42 DTE window.

    The app already receives validated Kite instrument rows; this helper only
    chooses among those dates and never constructs symbols manually.
    """

    expiries: list[date] = []
    for row in instruments:
        expiry = _as_date(row.get("expiry") or row.get("_expiry_day"))
        if expiry and expiry >= as_of:
            expiries.append(expiry)

    unique = sorted(set(expiries))
    if not unique:
        return ExpiryChoice(None, None, "NO_EXPIRY", "No valid future expiry found in Kite instruments.")

    preferred = [
        expiry
        for expiry in unique
        if config.target_expiry_min_dte <= (expiry - as_of).days <= config.target_expiry_max_dte
    ]
    if preferred:
        expiry = preferred[0]
        return ExpiryChoice(
            expiry,
            (expiry - as_of).days,
            "PREFERRED_MONTHLY",
            f"Selected expiry in {config.target_expiry_min_dte}-{config.target_expiry_max_dte} DTE window.",
        )

    acceptable = [expiry for expiry in unique if (expiry - as_of).days >= config.min_opening_dte]
    if acceptable:
        expiry = acceptable[0]
        return ExpiryChoice(
            expiry,
            (expiry - as_of).days,
            "ACCEPTABLE_FALLBACK",
            "No preferred monthly expiry found; selected nearest expiry above minimum opening DTE.",
        )

    expiry = unique[0]
    return ExpiryChoice(
        expiry,
        (expiry - as_of).days,
        "EXPIRY_TOO_CLOSE",
        f"Nearest expiry has fewer than {config.min_opening_dte} days to expiry.",
    )

