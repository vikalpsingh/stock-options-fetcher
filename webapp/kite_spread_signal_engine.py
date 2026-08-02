"""Simple trader-view signal classification for Kite spread candidates."""

from __future__ import annotations

from typing import Any


def evaluate_signal(row: dict[str, Any], market_regime: str = "", technical: dict[str, Any] | None = None) -> dict[str, Any]:
    tech = technical or {}
    gpt_view = str(row.get("gpt_view") or "UNKNOWN").upper()
    event = bool(row.get("event_risk_flag"))
    if event or gpt_view == "AVOID":
        return {"candidate_type": "AVOID", "preferred_strategy": "NONE", "confidence": 0, "reason": "Event risk or GPT avoid."}
    rsi = float(tech.get("rsi") or 50)
    close = float(row.get("cmp") or tech.get("close") or 0)
    ema20 = float(tech.get("ema20") or 0)
    ema50 = float(tech.get("ema50") or 0)
    regime = str(market_regime or "").upper()
    if gpt_view == "CE_SELL" or regime in {"SELL_ON_RISE", "HIGH_VIX_SIDEWAYS"} or rsi > 65:
        return {"candidate_type": "CE_SELL", "preferred_strategy": "BEAR_CALL_SPREAD", "confidence": 70, "reason": "Sell-on-rise/overextended setup."}
    if gpt_view == "PE_SELL" or (close > ema20 > ema50 > 0) or regime == "BUY_ON_DIPS":
        return {"candidate_type": "PE_SELL", "preferred_strategy": "BULL_PUT_SPREAD", "confidence": 70, "reason": "Buy-on-dips/supportive trend setup."}
    if gpt_view == "BOTH":
        return {"candidate_type": "BOTH", "preferred_strategy": "BEAR_CALL_SPREAD", "confidence": 60, "reason": "Both sides possible; choose by premium and risk."}
    return {"candidate_type": "AVOID", "preferred_strategy": "NONE", "confidence": 30, "reason": "No clear trader edge."}
