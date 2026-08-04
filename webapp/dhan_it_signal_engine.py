"""Simple IT-sector trader signal engine for DHAN-IT spreads."""

from __future__ import annotations

from typing import Any


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
    cmp_value = _num(market.get("cmp") or market.get("spot"))
    ema20 = _num(technical.get("ema20") or cmp_value)
    ema50 = _num(technical.get("ema50") or cmp_value)
    rsi = _num(technical.get("rsi") or 50)
    high_20 = _num(technical.get("high_20d") or technical.get("twenty_day_high"))
    high_52 = _num(technical.get("high_52w") or technical.get("yearly_high"))
    event_risk = "YES" if event.get("event_risk") or event.get("event_risk_flag") else "NO"
    near_high = bool(cmp_value and ((high_20 and cmp_value >= high_20 * 0.97) or (high_52 and cmp_value >= high_52 * 0.97)))
    below_ema50 = bool(cmp_value and ema50 and cmp_value < ema50)
    above_trend = bool(cmp_value and ema20 and ema50 and cmp_value >= ema20 >= ema50)
    weak = bool(cmp_value and ema20 and cmp_value < ema20)

    if event_risk == "YES":
        view, strategy, confidence, reason = "AVOID", "NONE", 20, "Event/result risk exists within the configured risk window."
    elif near_high and rsi > 60:
        view, strategy, confidence, reason = "CE_SELL_CANDIDATE", "BEAR_CALL_SPREAD", 62, "Near resistance/highs with elevated RSI; prefer defined-risk CE spread only."
    elif below_ema50:
        view, strategy, confidence, reason = "CE_SELL_CANDIDATE", "BEAR_CALL_SPREAD", 68, "Below EMA50 / weak structure; PE selling avoided."
    elif above_trend and rsi < 62:
        view, strategy, confidence, reason = "PE_SELL_CANDIDATE", "BULL_PUT_SPREAD", 70, "Above EMA20/EMA50 with stable momentum; PE spread candidate."
    elif weak:
        view, strategy, confidence, reason = "CE_SELL_CANDIDATE", "BEAR_CALL_SPREAD", 60, "Struggling near/below EMA20; CE spread candidate."
    else:
        view, strategy, confidence, reason = "BOTH", "BOTH", 55, "Sideways/neutral IT setup; evaluate both defined-risk spreads."

    return {
        "symbol": str(symbol or "").upper(),
        "cmp": cmp_value,
        "trader_view": view,
        "recommended_strategy": strategy,
        "confidence": confidence,
        "reason": reason,
        "event_risk": event_risk,
        "liquidity_view": liquidity_view,
        "rsi": rsi,
        "ema20": ema20,
        "ema50": ema50,
        "trend_view": "WEAK" if below_ema50 or weak else "STABLE" if above_trend else "SIDEWAYS",
        "result_date": str(event.get("result_date") or ""),
    }
