"""DHAN-IT spread builder using the shared Kite expiry-comparison evaluator."""

from __future__ import annotations

from datetime import date
from typing import Any

from kite_option_resolver import KiteOptionResolver
from kite_spread_evaluator import evaluate_spread_with_expiry_comparison


def build_dhan_it_spread(
    symbol: str,
    strategy_type: str,
    spot: float | None,
    lots: int,
    option_chain_data: list[dict[str, Any]],
    kite_adapter: Any = None,
    risk_engine: Any = None,
    market_data: dict[str, Any] | None = None,
    technical_data: dict[str, Any] | None = None,
    event_data: dict[str, Any] | None = None,
    current_month_expiry: str = "",
    next_month_expiry: str = "",
) -> dict[str, Any]:
    resolver = KiteOptionResolver(instruments=option_chain_data, today=(market_data or {}).get("today") or date.today())
    current = current_month_expiry or (resolver.selected_expiry(symbol) or "")
    later = ""
    if current:
        current_date = resolver.selected_expiry(symbol, current)
        later_expiries = [item for item in resolver.monthly_expiries(symbol) if current_date and item > current_date]
        later = later_expiries[0].isoformat() if later_expiries else ""
    comparison = evaluate_spread_with_expiry_comparison(
        symbol=symbol,
        strategy_type=strategy_type,
        spot=spot,
        selected_lots=lots,
        current_month_expiry=current,
        next_month_expiry=next_month_expiry or later,
        option_chain_data=option_chain_data,
        kite_adapter=kite_adapter,
        risk_engine=risk_engine,
        market_data=market_data or {},
        technical_data=technical_data or {},
        event_data=event_data or {},
    )
    preview = dict(comparison["recommended_preview"])
    preview["screen_name"] = "DHAN-IT"
    return preview
