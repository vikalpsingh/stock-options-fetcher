"""ATR-first strike selection for covered calls."""

from __future__ import annotations

from .config import COVERED_CALL_CONFIG, CoveredCallConfig


def estimate_lightweight_atr(
    *,
    spot_price: float,
    today_change_pct: float | None = None,
    week_change_pct: float | None = None,
) -> float:
    """Estimate an ATR-like buffer when full historical candles are unavailable."""

    if spot_price <= 0:
        return 0.0
    daily_move = abs(today_change_pct or 0.0) / 100.0 * spot_price
    weekly_daily_equivalent = abs(week_change_pct or 0.0) / 100.0 * spot_price / 5.0
    return max(spot_price * 0.025, daily_move * 1.5, weekly_daily_equivalent * 1.5)


def select_atr_guarded_call_strike(
    *,
    spot_price: float,
    available_strikes: list[float],
    category: str = "NORMAL",
    today_change_pct: float | None = None,
    week_change_pct: float | None = None,
    config: CoveredCallConfig = COVERED_CALL_CONFIG,
) -> tuple[float | None, dict[str, float | str]]:
    """Pick a strike using ATR buffer, then enforce OTM guardrails."""

    strikes = sorted({float(strike) for strike in available_strikes if float(strike or 0) > spot_price})
    if spot_price <= 0 or not strikes:
        return None, {"method": "NO_VALID_STRIKE"}

    rule = config.category_rules.get(category, config.category_rules["NORMAL"])
    atr = estimate_lightweight_atr(
        spot_price=spot_price,
        today_change_pct=today_change_pct,
        week_change_pct=week_change_pct,
    )
    atr_target = spot_price + atr * rule.atr_multiplier
    min_target = spot_price * (1.0 + rule.min_otm_pct / 100.0)
    max_target = spot_price * (1.0 + rule.max_otm_pct / 100.0)
    target = min(max(atr_target, min_target), max_target)

    selected = min(strikes, key=lambda strike: abs(strike - target))
    if selected < min_target:
        higher = [strike for strike in strikes if strike >= min_target]
        selected = higher[0] if higher else selected
    if selected > max_target:
        lower = [strike for strike in strikes if strike <= max_target]
        selected = lower[-1] if lower else selected

    return selected, {
        "method": "ATR_GUARDRAIL",
        "atr": round(atr, 2),
        "atr_target": round(atr_target, 2),
        "min_otm_pct": rule.min_otm_pct,
        "max_otm_pct": rule.max_otm_pct,
        "target": round(target, 2),
    }

