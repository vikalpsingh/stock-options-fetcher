from __future__ import annotations

from typing import Any


def place_nifty_orders(order_intents: list[Any], execution_mode: str = "SUGGESTION_ONLY", *, live_order_enabled: bool = False, manual_confirmation: bool = False) -> dict[str, Any]:
    mode = str(execution_mode or "SUGGESTION_ONLY").upper()
    if mode == "SUGGESTION_ONLY":
        return {"placed": False, "status": "SUGGESTION_ONLY", "orders": order_intents}
    if mode == "DRY_RUN":
        return {"placed": False, "status": "DRY_RUN", "orders": order_intents}
    if mode == "LIVE_CONFIRMED" and (not live_order_enabled or not manual_confirmation):
        return {"placed": False, "status": "BLOCKED_CONFIRMATION_REQUIRED", "orders": []}
    return {"placed": False, "status": "EXECUTOR_REQUIRES_APP_KITE_CONTEXT", "orders": []}
