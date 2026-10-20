"""Fill-gated hedge-first execution for TRADE defined-risk spreads."""

from __future__ import annotations

from typing import Any, Callable


def execute_hedge_first(
    preview: dict[str, Any], broker: Any, *, final_validator: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    if not preview.get("hedged_order_acknowledged"):
        raise PermissionError("Explicit defined-risk spread acknowledgement is required.")
    if str(preview.get("strategy_type")) != "BULL_PUT_SPREAD" or not preview.get("hedge_symbol"):
        raise PermissionError("A verified protective spread is required.")
    final_validator(preview)
    quantity = int(preview.get("quantity") or 0)
    buy_payload = dict((preview.get("order_payloads") or [{}, {}])[0])
    sell_payload = dict((preview.get("order_payloads") or [{}, {}])[1])
    if quantity <= 0 or buy_payload.get("transaction_type") != "BUY" or sell_payload.get("transaction_type") != "SELL":
        raise ValueError("Invalid protected spread payload.")
    buy_result = broker.place_order(buy_payload)
    if getattr(broker, "paper_trading", False):
        filled = quantity
        hedge_status = "HEDGE_FILLED"
    else:
        trades = broker.get_order_trades(str(buy_result.get("order_id") or ""))
        filled = sum(int(row.get("quantity") or 0) for row in trades)
        hedge_status = "HEDGE_FILLED" if filled >= quantity else "PARTIAL_HEDGE" if filled > 0 else "HEDGE_SUBMITTED"
    if filled <= 0:
        return {"state": hedge_status, "hedge_order_id": buy_result.get("order_id"), "sell_order_id": None, "filled_hedge_qty": 0}
    covered_qty = min(quantity, filled)
    sell_payload["quantity"] = covered_qty
    final_validator({**preview, "quantity": covered_qty})
    sell_result = broker.place_order(sell_payload)
    return {"state": "BOTH_FILLED" if getattr(broker, "paper_trading", False) else "SELL_SUBMITTED",
            "hedge_order_id": buy_result.get("order_id"), "sell_order_id": sell_result.get("order_id"),
            "filled_hedge_qty": filled, "submitted_short_qty": covered_qty}
