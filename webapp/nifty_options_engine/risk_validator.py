from __future__ import annotations

from typing import Any


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def validate_nifty_strategy(
    strategy: dict[str, Any],
    account_state: dict[str, Any] | None = None,
    risk_state: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    account_state = account_state or {}
    risk_state = risk_state or {}
    warnings: list[str] = []
    blocks: list[str] = []

    legs = list(strategy.get("legs") or [])
    short_legs = [leg for leg in legs if str(leg.get("transaction_type") or "").upper() == "SELL"]
    hedge_legs = [leg for leg in legs if str(leg.get("transaction_type") or "").upper() == "BUY"]
    if config.get("disallow_naked_short_options", True) and short_legs and len(hedge_legs) < len(short_legs):
        blocks.append("NAKED_SHORT_OPTION_BLOCKED")

    width = _float(strategy.get("spread_width_points"))
    credit = _float(strategy.get("net_credit_points"))
    credit_pct = credit / width * 100 if width > 0 else 0.0
    min_credit = _float(config.get("min_credit_pct_of_spread_width"), 8.0)
    if width <= 0 or credit_pct < min_credit:
        blocks.append("CREDIT_BELOW_MINIMUM")

    vix = _float(risk_state.get("india_vix") or strategy.get("india_vix"))
    if 0 < vix < 11:
        warnings.append("LOW_VIX_POOR_PREMIUM")
    if vix > 24:
        blocks.append("HIGH_VIX_NO_TRADE")

    if risk_state.get("breakout_day"):
        blocks.append("BREAKOUT_DAY_NO_TRADE")
    if risk_state.get("panic_fall"):
        blocks.append("PANIC_FALL_NO_TRADE")
    if risk_state.get("major_event_within_3_days"):
        blocks.append("MAJOR_EVENT_RISK")
    if _float(account_state.get("nifty_margin_heat_pct")) > _float(config.get("max_nifty_margin_heat_pct"), 20.0):
        blocks.append("NIFTY_MARGIN_HEAT_LIMIT")
    if _float(account_state.get("total_margin_heat_pct")) > _float(config.get("max_total_margin_heat_pct"), 40.0):
        blocks.append("TOTAL_MARGIN_HEAT_LIMIT")

    return {
        "allowed": not blocks,
        "risk_status": "ALLOWED" if not blocks else "BLOCKED",
        "warnings": warnings,
        "skip_reason": ", ".join(blocks),
        "credit_pct_of_spread_width": credit_pct,
    }
