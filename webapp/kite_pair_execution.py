"""Kite paired spread execution with hedge-first safety default."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from kite_spread_repository import KiteSpreadRepository


def round_limit_price_to_tick(price: float, tick_size: float = 0.05) -> float:
    """Round an NFO LIMIT price to the broker-accepted tick size."""

    value = Decimal(str(float(price or 0)))
    tick = Decimal(str(tick_size))
    if value <= 0 or tick <= 0:
        return 0.0
    ticks = (value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float((ticks * tick).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_kite_order_payload(tradingsymbol: str, transaction_type: str, quantity: int, price: float, tag: str = "") -> dict[str, Any]:
    return {
        "variety": "regular",
        "exchange": "NFO",
        "tradingsymbol": tradingsymbol,
        "transaction_type": transaction_type,
        "quantity": int(quantity),
        "product": "NRML",
        "order_type": "LIMIT",
        "price": round_limit_price_to_tick(float(price)),
        "validity": "DAY",
        "tag": tag[:20],
    }


def dhan_initial_sell_limit_price(option_cmp: float) -> float:
    """Park the short leg 10% above evaluated option CMP until hedge is filled."""

    return round_limit_price_to_tick(float(option_cmp or 0) * 1.10)


def submit_kite_pair(preview: dict[str, Any], repository: KiteSpreadRepository, broker: Any, user_confirmed: bool, mode: str = "PAPER", execution_mode: str = "HEDGE_FIRST") -> dict[str, Any]:
    if not user_confirmed:
        raise ValueError("Explicit confirmation is required before placing a Kite spread pair.")
    if str(mode or "").upper() != "PAPER" and (
        str(preview.get("pair_liquidity_condition") or "").upper() == "RED"
        or preview.get("liquidity_order_allowed") is False
    ):
        repository.log("", "LIQUIDITY_RED_ORDER_BLOCKED", str(preview.get("liquidity_reason") or "RED liquidity blocked order"))
        raise ValueError("LIQUIDITY_RED_ORDER_BLOCKED: Place Order disabled because liquidity condition is RED.")
    if str(preview.get("risk_decision") or "").upper() != "APPROVED":
        raise ValueError(f"Spread is blocked: {preview.get('risk_reason') or preview.get('reason')}")
    pair_id = repository.create_pair(preview, mode=mode, user_confirmed=True, execution_mode=execution_mode)
    tag = pair_id[-20:]
    buy_payload = build_kite_order_payload(preview["buy_leg_tradingsymbol"], "BUY", preview["quantity"], preview["buy_limit_price"], tag)
    sell_cmp_limit_price = round_limit_price_to_tick(float(preview["sell_limit_price"]))
    sell_entry_limit_price = dhan_initial_sell_limit_price(sell_cmp_limit_price) if execution_mode == "HEDGE_FIRST" else sell_cmp_limit_price
    sell_payload = build_kite_order_payload(preview["sell_leg_tradingsymbol"], "SELL", preview["quantity"], sell_entry_limit_price, tag)
    if execution_mode == "HEDGE_FIRST":
        buy_result = broker.place_order(buy_payload)
        sell_result = broker.place_order(sell_payload)
        payload_json = json.dumps(
            {
                **preview,
                "sell_order_payload": sell_payload,
                "buy_order_payload": buy_payload,
                "sell_cmp_limit_price": sell_cmp_limit_price,
                "sell_initial_limit_price": sell_entry_limit_price,
                "sell_reprice_after_hedge": True,
            },
            default=str,
        )
        repository.update_pair(
            pair_id,
            buy_leg_order_id=buy_result["order_id"],
            sell_leg_order_id=sell_result["order_id"],
            buy_leg_status=buy_result.get("status", "OPEN"),
            sell_leg_status=sell_result.get("status", "OPEN"),
            sell_leg_placed=1,
            pair_status="SUBMITTED_WAITING_HEDGE",
            payload_json=payload_json,
        )
        repository.log(pair_id, "BUY_HEDGE_SUBMITTED", buy_result["order_id"])
        repository.log(pair_id, "SELL_PARKED_ABOVE_CMP", f"{sell_result['order_id']} @ {sell_entry_limit_price}; reprice to {sell_cmp_limit_price} after hedge fill")
        return {"pair_id": pair_id, "buy_leg_order_id": buy_result["order_id"], "sell_leg_order_id": sell_result["order_id"], "mode": mode}
    buy_result = broker.place_order(buy_payload)
    sell_result = broker.place_order(sell_payload)
    repository.update_pair(pair_id, buy_leg_order_id=buy_result["order_id"], sell_leg_order_id=sell_result["order_id"], buy_leg_status=buy_result.get("status", "OPEN"), sell_leg_status=sell_result.get("status", "OPEN"), sell_leg_placed=1, pair_status="SUBMITTED", payload_json=json.dumps({**preview, "sell_order_payload": sell_payload, "buy_order_payload": buy_payload}, default=str))
    repository.log(pair_id, "SIMULTANEOUS_SUBMITTED", f"{buy_result['order_id']} {sell_result['order_id']}")
    return {"pair_id": pair_id, "buy_leg_order_id": buy_result["order_id"], "sell_leg_order_id": sell_result["order_id"], "mode": mode}
