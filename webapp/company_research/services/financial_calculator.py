from __future__ import annotations

from typing import Any


def number(value: Any) -> float | None:
    try:
        if value in {None, "", "N/A", "NA", "-", "—"}:
            return None
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def pct_change(current: float | None, previous: float | None) -> float | None:
    value = safe_divide(None if current is None or previous is None else current - previous, previous)
    return round(value * 100, 2) if value is not None else None


def opm(operating_profit: float | None, sales: float | None) -> float | None:
    value = safe_divide(operating_profit, sales)
    return round(value * 100, 2) if value is not None else None


def calculated_pe(market_cap: float | None, ttm_pat: float | None, quarterly_count: int) -> tuple[float | str | None, list[str]]:
    warnings: list[str] = []
    if quarterly_count < 4:
        warnings.append("INSUFFICIENT_TTM_PERIODS")
        return None, warnings
    if ttm_pat is None or ttm_pat <= 0:
        return "NM", warnings
    pe_value = safe_divide(market_cap, ttm_pat)
    return (round(pe_value, 2) if pe_value is not None else None), warnings

