"""Covered-call recommendation service."""

from __future__ import annotations

from datetime import date

from .capacity import calculate_covered_call_capacity
from .config import COVERED_CALL_CONFIG, CoveredCallConfig
from .models import CoveredCallInput, CoveredCallRecommendation
from .regime import classify_stock_regime


def _days_to_expiry(expiry: date | None, as_of: date | None = None) -> int | None:
    if not expiry:
        return None
    today = as_of or date.today()
    return (expiry - today).days


def build_covered_call_recommendation(
    request: CoveredCallInput,
    *,
    as_of: date | None = None,
    config: CoveredCallConfig = COVERED_CALL_CONFIG,
) -> CoveredCallRecommendation:
    """Return a transparent covered-call decision for one stock."""

    capacity = calculate_covered_call_capacity(
        symbol=request.symbol,
        holding_qty=request.holding_qty,
        lot_size=request.lot_size,
        spot_price=request.spot_price,
        existing_short_ce_qty=request.existing_short_ce_qty,
        user_max_lots=request.user_max_lots,
        category=request.category,
        config=config,
    )

    reason_codes = list(capacity.reason_codes)
    risk_flags: list[str] = []
    dte = _days_to_expiry(request.expiry, as_of=as_of)
    premium = request.premium or 0.0
    strike = request.strike
    premium_yield_pct = 0.0
    if request.spot_price > 0 and request.lot_size > 0 and premium > 0:
        premium_yield_pct = premium / request.spot_price * 100.0
    otm_pct = ((strike - request.spot_price) / request.spot_price * 100.0) if strike and request.spot_price else None

    regime, regime_reasons = classify_stock_regime(
        today_change_pct=request.today_change_pct,
        week_change_pct=request.week_change_pct,
        month_change_pct=request.month_change_pct,
    )
    reason_codes.extend(regime_reasons)
    if regime == "BREAKOUT_RISK":
        risk_flags.append("BREAKOUT_RISK")

    decision = "SELL_NOW"
    if capacity.capacity_lots <= 0:
        decision = "NEED_MORE_SHARES"
    elif capacity.recommended_lots <= 0:
        decision = "NO_TRADE_EXCESSIVE_COVERAGE"
    elif dte is not None and dte < config.min_opening_dte:
        decision = "NO_TRADE_EXPIRY_TOO_CLOSE"
        reason_codes.append("EXPIRY_TOO_CLOSE")
    elif premium <= 0 or premium_yield_pct < config.min_premium_yield_pct:
        decision = "NO_TRADE_LOW_PREMIUM"
        reason_codes.append("LOW_PREMIUM_YIELD")
    elif regime in {"BREAKOUT_RISK", "STRONG_UP_MOVE"}:
        decision = "WAIT_FOR_BOUNCE"

    score = 100
    score -= 30 if capacity.recommended_lots <= 0 else 0
    score -= 20 if premium_yield_pct < config.min_premium_yield_pct else 0
    score -= 20 if "EXPIRY_TOO_CLOSE" in reason_codes else 0
    score -= 15 if risk_flags else 0
    score = max(0, min(100, score))

    if decision == "SELL_NOW":
        explanation = (
            f"SELL {capacity.recommended_lots} covered lot(s): shares are available, "
            f"expiry risk is acceptable, and premium yield is {premium_yield_pct:.2f}%."
        )
    elif decision == "WAIT_FOR_BOUNCE":
        explanation = "Wait for the stock to cool down; current momentum raises call-away risk."
    elif decision == "NO_TRADE_EXCESSIVE_COVERAGE":
        explanation = "Mechanical capacity exists, but portfolio coverage guardrails block fresh covered CALLs."
    elif decision == "NEED_MORE_SHARES":
        explanation = "Holding is below one full F&O lot, so no covered CALL can be sold."
    elif decision == "NO_TRADE_LOW_PREMIUM":
        explanation = "Premium is too low for the upside being capped."
    else:
        explanation = "New covered CALL entry is blocked by expiry or risk guardrails."

    max_profit = capacity.recommended_quantity * premium if premium > 0 else 0.0
    return CoveredCallRecommendation(
        symbol=request.symbol,
        decision=decision,
        score=score,
        capacity=capacity,
        recommended_lots=capacity.recommended_lots,
        recommended_quantity=capacity.recommended_quantity,
        strike=strike,
        expiry=request.expiry,
        dte=dte,
        premium=premium,
        max_profit=max_profit,
        premium_yield_pct=premium_yield_pct,
        otm_pct=otm_pct,
        reason_codes=sorted(set(reason_codes)),
        explanation=explanation,
        category=request.category,
        risk_flags=risk_flags,
        metadata={"regime": regime},
    )

