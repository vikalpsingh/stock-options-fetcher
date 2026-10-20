"""Volatility-aware comparison of bullish option strategies.

This module is advisory.  It does not authorize or place broker orders.
"""

from __future__ import annotations

import math
import statistics
from typing import Any


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def realised_volatility(closes: list[float], window: int) -> float | None:
    values = [float(value) for value in closes if _num(value) and float(value) > 0]
    if len(values) <= window:
        return None
    returns = [math.log(values[index] / values[index - 1]) for index in range(len(values) - window, len(values))]
    return statistics.stdev(returns) * math.sqrt(252) * 100 if len(returns) > 1 else None


def compare_bullish_strategies(
    *, spot: float, dte: int, iv_pct: float | None, closes: list[float],
    ce_buy: dict[str, Any], pe_spread: dict[str, Any], technical_scores: dict[str, Any],
    event_status: str = "UNKNOWN", sector_status: str = "UNKNOWN",
) -> dict[str, Any]:
    """Compare long CE with a defined-risk bull-put spread, failing closed."""
    iv = _num(iv_pct)
    hv20, hv60 = realised_volatility(closes, 20), realised_volatility(closes, 60)
    expected_move = float(spot) * (iv / 100) * math.sqrt(max(int(dte), 0) / 365) if spot > 0 and iv and dte > 0 else None
    iv_hv = iv / hv20 if iv and hv20 and hv20 > 0 else None
    ce_score = float((technical_scores.get("CE_BUY") or {}).get("score") or 0)
    pe_score = float((technical_scores.get("PE_SELL") or {}).get("score") or 0)
    hard_event = str(event_status).upper() == "BLOCK"
    ce_liquid = str(ce_buy.get("liquidity") or "UNKNOWN").upper() == "PASS"
    spread_ok = bool(pe_spread.get("eligible")) and str(pe_spread.get("liquidity") or "UNKNOWN").upper() == "PASS"
    ce_cost = float(ce_buy.get("cost") or 0)
    spread_credit = float(pe_spread.get("net_credit") or 0)
    spread_loss = float(pe_spread.get("max_loss") or 0)
    ce_points = ce_score * 0.55 + (15 if ce_liquid else 0) + (15 if iv_hv is not None and iv_hv <= 1.25 else 6) + (15 if 7 <= dte <= 60 else 3)
    pe_points = pe_score * 0.55 + (15 if spread_ok else 0) + (15 if iv_hv is not None and iv_hv >= 1 else 6) + (15 if 21 <= dte <= 35 else 8 if 14 <= dte <= 45 else 0)
    reasons: list[str] = []
    if hard_event:
        outcome = "NO TRADE"
        reasons.append("Verified earnings/event blackout blocks both strategies.")
    elif not iv or expected_move is None or hv20 is None:
        outcome = "WAIT"
        reasons.append("Reliable IV, expected movement and 20-session realised volatility are required.")
    elif ce_points >= 70 and ce_points >= pe_points + 5 and ce_liquid and ce_cost > 0:
        outcome = "PREFER CE BUY"
        reasons.append("Directional score and bounded premium risk outweigh the protected income alternative.")
    elif pe_points >= 70 and pe_points > ce_points and spread_ok and spread_credit > 0 and spread_loss > 0:
        outcome = "PREFER HEDGED PE SELL"
        reasons.append("Supportive technical evidence and executable defined-risk credit are stronger.")
    else:
        outcome = "WAIT"
        reasons.append("Neither strategy has sufficient combined technical, volatility and execution evidence.")
    if str(sector_status).upper() not in {"PASS", "BULLISH"}:
        reasons.append("Sector confirmation is unavailable or not bullish.")
    return {
        "outcome": outcome,
        "ce_buy_score": round(min(100, ce_points), 1),
        "hedged_pe_sell_score": round(min(100, pe_points), 1),
        "iv_pct": iv,
        "realised_volatility_20_pct": round(hv20, 2) if hv20 is not None else None,
        "realised_volatility_60_pct": round(hv60, 2) if hv60 is not None else None,
        "iv_hv_ratio": round(iv_hv, 2) if iv_hv is not None else None,
        "iv_rank": None,
        "iv_percentile": None,
        "expected_move": round(expected_move, 2) if expected_move is not None else None,
        "dte": int(dte),
        "reasons": reasons,
        "model_note": "Expected move uses spot × IV × sqrt(DTE/365); it is not a guaranteed range or stop-loss.",
    }
