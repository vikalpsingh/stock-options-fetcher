from __future__ import annotations

from typing import Any


NIFTY_INCOME_V2_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "timezone": "Asia/Kolkata",
    "max_total_nifty_defined_loss_inr": 60000,
    "default_lots": 2,
    "maximum_lots_per_new_trade": 4,
    "allowed_lots": [1, 2, 3, 4],
    "default_hedge_width_points": 300,
    "use_live_instrument_lot_size": True,
    "preferred_entry_dte_min": 21,
    "preferred_entry_dte_max": 35,
    "alternate_entry_dte_min": 18,
    "alternate_entry_dte_max": 24,
    "allowed_strategies": ["BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "IRON_CONDOR"],
    "entry_mode": "SUGGESTION_ONLY",
    "live_enabled": False,
    "manual_confirmation_required": True,
    "countdown_seconds": 10,
    "no_naked_nifty_sell": True,
    "hedge_first_execution": True,
    "hedge_must_be_filled_before_short_sell": True,
    "credit_capture_target_pct": 55,
    "quick_short_premium_capture_pct": 20,
    "spread_stop_loss_credit_multiple": 1.5,
    "emergency_short_premium_multiple": 2.0,
    "force_exit_dte": 7,
    "estimated_execution_costs_inr": 500,
    "max_quote_age_seconds": 120,
    "max_bid_ask_spread_pct": 8,
    "monthly_loss_kill_switch_enabled": True,
    "entry_order_type": "LIMIT",
    "product": "NRML",
}


def income_v2_config(overrides=None):
    """Normalize saved v2 settings without allowing safety switches to be removed."""
    import copy
    import math

    result = copy.deepcopy(NIFTY_INCOME_V2_DEFAULTS)
    result.update({key: value for key, value in (overrides or {}).items() if key in result})
    for key, default in NIFTY_INCOME_V2_DEFAULTS.items():
        if isinstance(default, (int, float)) and not isinstance(default, bool):
            try:
                value = float(result[key])
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(key)
                if isinstance(default, int) and not value.is_integer():
                    raise ValueError(key)
                result[key] = int(value) if isinstance(default, int) else value
            except (ValueError, TypeError):
                raise ValueError(f"Invalid NIFTY setting: {key}") from None
    if result["max_total_nifty_defined_loss_inr"] > 60000:
        raise ValueError("NIFTY portfolio loss cap cannot exceed ₹60,000.")
    if (not isinstance(result["allowed_lots"], list) or not result["allowed_lots"]
            or any(type(n) is not int or n not in (1, 2, 3, 4) for n in result["allowed_lots"])
            or result["maximum_lots_per_new_trade"] > 4
            or result["default_lots"] not in result["allowed_lots"]):
        raise ValueError("NIFTY lots must be selected from 1, 2, 3 and 4.")
    if result["default_lots"] > result["maximum_lots_per_new_trade"]:
        raise ValueError("Default lots exceed the configured maximum.")
    for prefix in ("preferred", "alternate"):
        if result[f"{prefix}_entry_dte_min"] > result[f"{prefix}_entry_dte_max"]:
            raise ValueError("Minimum entry DTE exceeds maximum.")
    if result["entry_mode"] not in {"SUGGESTION_ONLY", "PAPER", "LIVE_CONFIRMED"}:
        raise ValueError("Invalid NIFTY entry mode.")
    if (not isinstance(result["allowed_strategies"], list) or not result["allowed_strategies"]
            or any(strategy not in NIFTY_INCOME_V2_DEFAULTS["allowed_strategies"]
                   for strategy in result["allowed_strategies"])):
        raise ValueError("Only protected PE/CE spreads and iron condors are supported.")
    if any(result[key] > 100 for key in ("credit_capture_target_pct", "quick_short_premium_capture_pct")):
        raise ValueError("Profit capture percentages cannot exceed 100.")
    for key in ("manual_confirmation_required", "no_naked_nifty_sell", "hedge_first_execution",
                "hedge_must_be_filled_before_short_sell", "use_live_instrument_lot_size",
                "monthly_loss_kill_switch_enabled"):
        result[key] = True
    for key in ("enabled", "live_enabled"):
        if not isinstance(result[key], bool):
            raise ValueError(f"NIFTY setting {key} must be true or false.")
    result["countdown_seconds"] = max(10, result["countdown_seconds"])
    result["entry_order_type"], result["product"] = "LIMIT", "NRML"
    return result


NIFTY_OPTIONS_ENGINE_CONFIG: dict[str, Any] = {
    "enabled": True,
    "mode": "REGIME_BASED_TACTICAL_SPREAD",
    "entry_execution_mode": "SUGGESTION_ONLY",
    "live_order_enabled": False,
    "require_manual_confirmation": True,
    "allowed_live_structures": ["BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "IRON_CONDOR"],
    "disallow_naked_short_options": True,
    "entry_day": "FRIDAY",
    "entry_time": "15:16",
    "timezone": "Asia/Kolkata",
    "dte_min": 21,
    "dte_max": 35,
    "sell_delta_min": 0.12,
    "sell_delta_max": 0.18,
    "hedge_delta_min": 0.03,
    "hedge_delta_max": 0.06,
    "default_spread_width_points": 500,
    "min_credit_pct_of_spread_width": 8.0,
    "base_min_premium_yield_on_margin_pct": 0.80,
    "low_vix_exception_min_yield_pct": 0.65,
    "low_vix_exception_vix_below": 12.0,
    "profit_booking_credit_decay_pct": 55.0,
    "stop_loss_credit_multiple": 1.75,
    "low_vix_exception_max_stop_loss_credit_multiple": 1.5,
    "max_nifty_margin_heat_pct": 20.0,
    "max_total_margin_heat_pct": 40.0,
    "max_lots_per_trade": 1,
    "max_active_nifty_strategies": 3,
    "product": "NRML",
    "order_type": "LIMIT",
    "validity": "DAY",
    "sell_limit_markup_pct": 10.0,
    "buy_limit_discount_pct": 5.0,
    "max_bid_ask_spread_pct": 8.0,
    "dry_run_default": True,
}


def engine_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = dict(NIFTY_OPTIONS_ENGINE_CONFIG)
    if overrides:
        for key, value in overrides.items():
            if key in config:
                config[key] = value
    return config
