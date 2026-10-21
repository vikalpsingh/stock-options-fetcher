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
    lot_size = int(preview.get("lot_size") or 0)
    buy_payload = dict((preview.get("order_payloads") or [{}, {}])[0])
    sell_payload = dict((preview.get("order_payloads") or [{}, {}])[1])
    if (
        quantity <= 0 or lot_size <= 0 or quantity % lot_size
        or buy_payload.get("transaction_type") != "BUY"
        or sell_payload.get("transaction_type") != "SELL"
        or buy_payload.get("tradingsymbol") != preview.get("hedge_symbol")
        or sell_payload.get("tradingsymbol") != preview.get("short_symbol")
        or buy_payload.get("quantity") != quantity or sell_payload.get("quantity") != quantity
    ):
        raise ValueError("Invalid protected spread payload.")
    buy_result = broker.place_order(buy_payload)
    result = {"state": "HEDGE_FILL_UNVERIFIED", "hedge_order_id": buy_result.get("order_id"),
              "sell_order_id": None, "filled_hedge_qty": 0, "submitted_short_qty": 0}
    if not result["hedge_order_id"]:
        return result
    if getattr(broker, "paper_trading", False):
        filled = quantity
    else:
        try:
            trades = broker.get_order_trades(str(result["hedge_order_id"]))
            filled, seen = 0, set()
            for row in trades:
                trade_id = str(row.get("trade_id") or "")
                qty = int(row.get("quantity") or 0)
                if (
                    not trade_id or trade_id in seen or qty <= 0 or qty != row.get("quantity")
                    or str(row.get("order_id") or "") != str(result["hedge_order_id"])
                    or any(row.get(key) != buy_payload.get(key)
                           for key in ("tradingsymbol", "exchange", "product", "transaction_type"))
                ):
                    return result
                seen.add(trade_id)
                filled += qty
        except Exception:
            # Retain the hedge ID for reconciliation without exposing broker errors.
            return result
    if filled > quantity:
        return result
    result["filled_hedge_qty"] = filled
    if filled < quantity:
        # Partial fills never authorize a short, including fractional lots.
        result["state"] = "PARTIAL_HEDGE" if filled else "HEDGE_SUBMITTED"
        return result
    try:
        final_validator(preview)
    except Exception:
        result["state"] = "HEDGE_FILLED_SHORT_BLOCKED"
        return result
    try:
        sell_result = broker.place_order(sell_payload)
    except Exception:
        # Submission may have reached the broker. Never automatically retry it.
        result["state"] = "SHORT_SUBMISSION_UNKNOWN"
        return result
    if not sell_result.get("order_id"):
        result["state"] = "SHORT_SUBMISSION_UNKNOWN"
        return result
    return {"state": "BOTH_FILLED" if getattr(broker, "paper_trading", False) else "SELL_SUBMITTED",
            "hedge_order_id": buy_result.get("order_id"), "sell_order_id": sell_result.get("order_id"),
            "filled_hedge_qty": filled, "submitted_short_qty": quantity}
