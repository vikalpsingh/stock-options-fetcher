"""Build the advisory-only TRADE payload sent to GPT.

The builder is deliberately pure: it performs no network or broker calls and
never substitutes invented market values for unavailable fields.
"""

from __future__ import annotations

from typing import Any


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_trade_gpt_payload(
    *,
    instruction: str,
    preview: dict[str, Any],
    market: dict[str, Any],
    checks: list[dict[str, Any]],
    earnings: dict[str, Any] | None = None,
    monthly_risk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    earnings = earnings or {}
    monthly_risk = monthly_risk or {}
    technical = market.get("technical_checklist") if isinstance(market.get("technical_checklist"), dict) else {}
    intelligence = market.get("intelligence") if isinstance(market.get("intelligence"), dict) else {}
    direction_engine = market.get("direction_engine") if isinstance(market.get("direction_engine"), dict) else {}
    bid = _number(preview.get("bid"))
    ask = _number(preview.get("ask"))
    volume = _number(preview.get("volume"))
    oi = _number(preview.get("oi"))
    iv = _number(preview.get("iv_percent"))
    quote_session = str(preview.get("market_session") or "UNKNOWN").upper()
    bid_ask_available = bool(bid and ask and bid > 0 and ask >= bid)
    earnings_date = earnings.get("next_result_date") or None
    earnings_source = earnings.get("result_date_source") or None
    data_issues: list[str] = []
    if quote_session != "LIVE":
        data_issues.append(f"Selected quote is {quote_session}, not a fresh LIVE market quote.")
    if volume is None:
        data_issues.append("Option volume is unavailable.")
    elif volume == 0:
        data_issues.append("Option volume is reported as zero; treat liquidity as weak.")
    if oi is None:
        data_issues.append("Option open interest is unavailable.")
    if not bid_ask_available:
        data_issues.append("Usable positive bid/ask depth is unavailable or crossed.")
    if iv is None:
        data_issues.append("Implied volatility and model Greeks could not be calculated reliably.")
    if not (earnings_date and earnings_source):
        data_issues.append("A verified upcoming earnings date/source is unavailable; event risk is UNKNOWN.")
    for check in checks:
        if str(check.get("status") or "").upper() in {"WARNING", "BLOCK"}:
            data_issues.append(f"{check.get('name')}: {check.get('reason')}")

    availability = {
        "live_option_chain_available": quote_session == "LIVE" and bool(preview.get("quote_fresh")),
        "volume_available": volume is not None,
        "iv_available": iv is not None,
        "oi_available": oi is not None,
        "bid_ask_available": bid_ask_available and bool(preview.get("quote_fresh")),
        "earnings_date_available": bool(earnings_date and earnings_source),
    }
    data_quality = "LIVE" if all(
        availability[key]
        for key in ("live_option_chain_available", "volume_available", "oi_available", "bid_ask_available", "iv_available")
    ) else "STALE" if quote_session == "AFTER_HOURS" else "PARTIAL"
    return {
        "instruction": instruction,
        "selection": {
            "symbol": preview.get("symbol"),
            "expiry": preview.get("expiry"),
            "strike": _number(preview.get("strike")),
            "option_type": preview.get("option_type"),
            "transaction_type": preview.get("side"),
            "lots": preview.get("lots"),
            "quantity": preview.get("quantity"),
            "product": preview.get("product"),
        },
        "market": {
            "spot_price": _number(preview.get("stock_cmp")),
            "previous_close": _number((market.get("ohlc") or {}).get("close")),
            "day_change_pct": _number(preview.get("day_change_pct")),
            "dma_20": _number(market.get("dma_20")),
            "dma_50": _number(market.get("dma_50")),
            "dma_200": _number(market.get("dma_200")),
            "rsi_14": _number(technical.get("rsi_14")),
            "rsi_direction": technical.get("rsi_direction"),
            "support": _number(technical.get("support")),
            "resistance": _number(technical.get("resistance")),
            "breakout": technical.get("breakout"),
            "breakdown": technical.get("breakdown"),
            "sector_alignment": technical.get("sector_alignment") or "UNKNOWN",
            "supported_structure": technical.get("supports"),
            "opposing_technical_evidence": list(technical.get("opposing_evidence") or []),
            "technical_thesis_invalidation": technical.get("thesis_invalidation"),
            "technical_source": technical.get("source"),
            "five_pct_direction_choices": list(intelligence.get("five_pct_direction_choices") or []),
            "trend_score": _number(preview.get("trend_score")),
            "trend_label": preview.get("trend_label"),
            "trend_reasons": list(preview.get("trend_reasons") or []),
            "sector_change_pct": None,
            "nifty_trend": None,
            "india_vix": None,
            "global_cues": None,
            "as_of_ist": preview.get("quote_at"),
            "market_session": quote_session,
            "technical_direction_engine": {
                "all_strategy_scores": direction_engine.get("scores") or {},
                "technical_direction": direction_engine.get("technical_direction"),
                "strategy_candidate": direction_engine.get("strategy_candidate"),
                "technical_score": _number(direction_engine.get("technical_score")),
                "data_quality_status": direction_engine.get("data_quality_status"),
                "hourly_confirmation": direction_engine.get("hourly_confirmation") or {},
                "execution_readiness": direction_engine.get("execution_readiness"),
                "final_decision": direction_engine.get("final_decision"),
                "contradictory_evidence": (direction_engine.get("scores") or {}).get(
                    str(direction_engine.get("strategy_candidate") or "").replace(" ", "_"), {}
                ).get("contradictory_evidence", []),
            },
        },
        "option": {
            "tradingsymbol": preview.get("tradingsymbol"),
            "premium": _number(preview.get("ltp")),
            "limit_price": _number(preview.get("limit_price")),
            "bid": bid,
            "ask": ask,
            "spread_rupees": _number(preview.get("spread_rupees")),
            "spread_pct": _number(preview.get("spread_pct")),
            "top_five_bids": list(preview.get("top_five_bids") or []),
            "top_five_asks": list(preview.get("top_five_asks") or []),
            "volume": volume,
            "oi": oi,
            "iv_pct": iv,
            "delta": _number(preview.get("delta")),
            "gamma": _number(preview.get("gamma")),
            "theta": _number(preview.get("theta")),
            "vega": _number(preview.get("vega")),
            "greeks_provenance": "MODEL_ESTIMATED" if iv is not None else None,
            "pop_model_estimate_pct": _number(preview.get("pop")),
            "intrinsic_value": _number(preview.get("intrinsic_value")),
            "time_value": _number(preview.get("time_value")),
            "moneyness": preview.get("moneyness"),
            "dte": preview.get("dte"),
            "lot_size": preview.get("lot_size"),
            "quote_timestamp": preview.get("quote_at"),
        },
        "availability": availability,
        "risk": {
            "earnings_date": earnings_date,
            "earnings_source": earnings_source,
            "earnings_verified_at": earnings.get("verified_at"),
            "days_to_earnings": earnings.get("days_to_result"),
            "event_risk": "BLOCK" if earnings.get("result_date_near") else "CLEAR" if earnings_date else "UNKNOWN",
            "market_regime": preview.get("trend_label") or "UNKNOWN",
            "existing_exposure": list(market.get("positions") or []),
            "monthly_loss_budget_remaining": _number(monthly_risk.get("remaining_loss_budget")),
            "monthly_risk_state": monthly_risk.get("risk_state") or "UNKNOWN",
            "margin_required": _number(preview.get("margin_required")),
            "available_funds": _number(preview.get("available_funds")),
            "maximum_loss": _number(preview.get("maximum_loss")),
            "risk_engine_decision": preview.get("decision"),
            "risk_engine_score": _number(preview.get("decision_score")),
            "data_quality": data_quality,
        },
        "option_chain": list(preview.get("nearby_strikes") or []),
        "risk_checks": list(checks),
        "data_issues": list(dict.fromkeys(data_issues)),
        "metadata": {
            "underlying_source": "ZERODHA_KITE_QUOTE",
            "contract_source": "ZERODHA_KITE_NFO_INSTRUMENT_MASTER",
            "option_quote_source": "ZERODHA_KITE_FULL_QUOTE",
            "greeks_method": "BLACK_SCHOLES_MODEL_ESTIMATE",
            "risk_free_rate": 0.065,
            "advisory_only": True,
            "gpt_cannot_override_risk_engine": True,
        },
        "required_json_fields": [
            "decision", "summary", "market_outlook", "recommended_action", "recommended_strike",
            "recommended_expiry", "entry_price", "profit_target", "risk_limit", "maximum_loss",
            "supporting_evidence", "opposing_evidence", "confidence_rationale", "thesis_invalidation",
            "earnings_caution", "alternatives", "final_decision",
        ],
    }
