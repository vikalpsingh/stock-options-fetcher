from __future__ import annotations

from typing import Any


def dashboard_summary(strategy: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
    return {
        "engine_mode": "REGIME_BASED_TACTICAL_SPREAD",
        "selected_strategy": strategy.get("selected_strategy"),
        "net_credit_points": strategy.get("net_credit_points"),
        "spread_width_points": strategy.get("spread_width_points"),
        "credit_pct_of_spread_width": strategy.get("credit_pct_of_spread_width"),
        "max_gain": strategy.get("max_gain"),
        "max_loss": strategy.get("max_loss"),
        "risk_status": risk.get("risk_status"),
        "skip_reason": risk.get("skip_reason"),
    }
