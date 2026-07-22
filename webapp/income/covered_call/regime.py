"""Simple stock-regime labels for covered-call decisions."""

from __future__ import annotations


def classify_stock_regime(
    *,
    today_change_pct: float | None = None,
    week_change_pct: float | None = None,
    month_change_pct: float | None = None,
) -> tuple[str, list[str]]:
    """Classify a stock using lightweight momentum inputs already in the app."""

    warnings: list[str] = []
    today = today_change_pct or 0.0
    week = week_change_pct or 0.0
    month = month_change_pct or 0.0

    if today >= 3.0 or week >= 7.0:
        return "BREAKOUT_RISK", ["STOCK_NEAR_BREAKOUT_AVOID_CE"]
    if today >= 1.5 or week >= 4.0:
        return "STRONG_UP_MOVE", ["WAIT_FOR_BOUNCE"]
    if today <= -3.0 or week <= -8.0 or month <= -15.0:
        return "WEAK_OR_PANIC", ["CHECK_SUPPORT_BEFORE_CE"]
    if abs(today) <= 1.25 and abs(week) <= 4.0:
        return "SIDEWAYS", warnings
    return "MIXED", warnings

