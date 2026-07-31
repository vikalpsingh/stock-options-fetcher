from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from .ratio_calculator import percentage_change


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text[:11] if fmt == "%d-%b-%Y" else text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _subtract_months(anchor: date, months: int) -> date:
    month_index = anchor.month - 1 - months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor.day, monthrange(year, month)[1])
    return date(year, month, day)


def _subtract_year(anchor: date) -> date:
    try:
        return anchor.replace(year=anchor.year - 1)
    except ValueError:
        return anchor.replace(year=anchor.year - 1, day=28)


def normalise_daily_candles(candles: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for row in candles:
        if not isinstance(row, dict):
            continue
        trade_date = _as_date(row.get("date") or row.get("trade_date"))
        close = _as_float(row.get("close"))
        if trade_date is None or close is None:
            continue
        clean.append(
            {
                **row,
                "date": trade_date,
                "close": close,
                "high": _as_float(row.get("high")) or close,
                "low": _as_float(row.get("low")) or close,
                "volume": float(row.get("volume") or 0),
            }
        )
    deduped = {row["date"]: row for row in clean}
    return [deduped[key] for key in sorted(deduped)]


def get_close_on_or_before(candles: list[dict[str, Any]], target_date: date) -> float | None:
    for row in reversed(candles):
        if row["date"] <= target_date:
            return _as_float(row.get("close"))
    return None


def calculate_period_returns(
    candles: list[dict[str, Any]],
    *,
    current_price: float | None = None,
    ipo_price: float | None = None,
) -> tuple[dict[str, float | None], list[str]]:
    if not candles:
        return {}, ["INSUFFICIENT_TRADING_HISTORY"]
    latest = candles[-1]
    latest_date = latest["date"]
    price = current_price or _as_float(latest.get("close"))
    if price is None:
        return {}, ["CURRENT_PRICE_MISSING"]

    references = {
        "day_return_pct": latest_date - timedelta(days=1),
        "one_week_return_pct": latest_date - timedelta(days=7),
        "one_month_return_pct": _subtract_months(latest_date, 1),
        "three_month_return_pct": _subtract_months(latest_date, 3),
        "six_month_return_pct": _subtract_months(latest_date, 6),
        "one_year_return_pct": _subtract_year(latest_date),
    }
    status_names = {
        "day_return_pct": "INSUFFICIENT_1D_HISTORY",
        "one_week_return_pct": "INSUFFICIENT_1W_HISTORY",
        "one_month_return_pct": "INSUFFICIENT_1M_HISTORY",
        "three_month_return_pct": "INSUFFICIENT_3M_HISTORY",
        "six_month_return_pct": "INSUFFICIENT_6M_HISTORY",
        "one_year_return_pct": "INSUFFICIENT_1Y_HISTORY",
    }
    output: dict[str, float | None] = {}
    warnings: list[str] = []
    first_date = candles[0]["date"]
    for field, target in references.items():
        if first_date > target:
            output[field] = None
            warnings.append(status_names[field])
            continue
        output[field] = percentage_change(price, get_close_on_or_before(candles, target))
    output["return_since_listing_pct"] = percentage_change(price, _as_float(candles[0].get("close")))
    output["gain_from_ipo_price_pct"] = percentage_change(price, ipo_price)
    return output, warnings
