"""Canonical IT-sector sell-on-rise signal engine for DHAN-IT spreads."""

from __future__ import annotations

from typing import Any

from dhan_it_call_watch import build_dhan_it_call_spread_signal


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def evaluate_it_signal(
    symbol: str,
    market_data: dict[str, Any] | None = None,
    technical_data: dict[str, Any] | None = None,
    event_data: dict[str, Any] | None = None,
    liquidity_view: str = "UNKNOWN",
) -> dict[str, Any]:
    market = market_data or {}
    technical = technical_data or {}
    event = event_data or {}
    signal = build_dhan_it_call_spread_signal(
        str(symbol or "").upper(),
        market_data=market,
        technical_data=technical,
        sector_regime=str(technical.get("nifty_it_regime") or event.get("nifty_it_regime") or "DATA_UNAVAILABLE"),
        event_data=event,
        liquidity_condition=liquidity_view,
    )
    signal_dict = signal.to_dict()

    return {
        "symbol": str(symbol or "").upper(),
        "cmp": _num(market.get("cmp") or market.get("spot")),
        "trader_view": signal.signal_status,
        "recommended_strategy": signal.strategy_type,
        "confidence": signal.confidence,
        "reason": signal.decision_reason,
        "event_risk": signal.event_risk,
        "liquidity_view": liquidity_view,
        "rsi": signal.rsi,
        "ema20": signal.ema20,
        "ema50": signal.ema50,
        "trend_view": signal.stock_regime,
        "result_date": str(event.get("result_date") or ""),
        "dhan_it_signal": signal_dict,
        "signal_status": signal.signal_status,
        "stock_regime": signal.stock_regime,
        "nifty_it_regime": signal.nifty_it_regime,
        "decision": signal.decision,
        "decision_reason": signal.decision_reason,
    }
