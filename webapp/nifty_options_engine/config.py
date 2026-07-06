from __future__ import annotations

from typing import Any


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
