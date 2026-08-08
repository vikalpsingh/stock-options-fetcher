"""DHAN-IT pair-order monitor and hedge-first SELL scheduler."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from dhan_it_pair_execution import DhanItPairRepository
from kite_option_liquidity import analyze_option_liquidity
from kite_pair_execution import build_kite_order_payload

COMPLETE = {"COMPLETE"}
FAILED = {"REJECTED", "CANCELLED"}


def _orders_by_id(orders: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("order_id") or row.get("orderId") or ""): row for row in orders if row.get("order_id") or row.get("orderId")}


def _status(row: dict[str, Any] | None, fallback: str) -> str:
    return str((row or {}).get("status") or fallback).upper()


def _fresh_quote_for_symbol(broker: Any, tradingsymbol: str) -> dict[str, Any] | None:
    if hasattr(broker, "quote"):
        quotes = broker.quote([f"NFO:{tradingsymbol}"])
        return (quotes or {}).get(f"NFO:{tradingsymbol}") or (quotes or {}).get(tradingsymbol)
    if hasattr(broker, "get_quote"):
        quotes = broker.get_quote([f"NFO:{tradingsymbol}"])
        return (quotes or {}).get(f"NFO:{tradingsymbol}") or (quotes or {}).get(tradingsymbol)
    if hasattr(broker, "quotes") and isinstance(getattr(broker, "quotes"), dict):
        return broker.quotes.get(tradingsymbol) or broker.quotes.get(f"NFO:{tradingsymbol}")
    return None


def run_dhan_it_pair_monitor_once(repository: DhanItPairRepository, broker: Any, now: datetime | None = None) -> dict[str, int]:
    current = now or datetime.now(timezone.utc)
    by_id = _orders_by_id(broker.get_orders())
    checked = placed = failed = exit_required = both = 0
    for pair in repository.list_pairs(include_closed=False):
        checked += 1
        pair_id = pair["pair_id"]
        buy_id = str(pair.get("buy_leg_order_id") or "")
        sell_id = str(pair.get("sell_leg_order_id") or "")
        buy_status = _status(by_id.get(buy_id), pair.get("buy_leg_status") or "OPEN")
        sell_status = _status(by_id.get(sell_id), pair.get("sell_leg_status") or "PENDING")
        payload = json.loads(pair.get("payload_json") or "{}")
        if buy_status in FAILED or sell_status in FAILED:
            repository.update_pair(pair_id, buy_leg_status=buy_status, sell_leg_status=sell_status, pair_status="FAILED", last_checked_at=current.isoformat(timespec="seconds"))
            failed += 1
            continue
        if buy_status in COMPLETE and not int(pair.get("sell_leg_placed") or 0):
            sell_quote = _fresh_quote_for_symbol(broker, pair["sell_leg_tradingsymbol"])
            sell_liquidity = analyze_option_liquidity(pair["sell_leg_tradingsymbol"], sell_quote)
            if str(sell_liquidity.get("liquidity_condition") or "").upper() == "RED":
                repository.update_pair(
                    pair_id,
                    buy_leg_status=buy_status,
                    sell_leg_status="BLOCKED_LIQUIDITY",
                    pair_status="HEDGE_FILLED_SELL_BLOCKED_LIQUIDITY",
                    last_checked_at=current.isoformat(timespec="seconds"),
                    payload_json=json.dumps({**payload, "sell_leg_liquidity_recheck": sell_liquidity}, default=str),
                )
                repository.log(pair_id, "SELL_BLOCKED_LIQUIDITY_AFTER_HEDGE", sell_liquidity.get("liquidity_reason", "RED liquidity"))
                failed += 1
                continue
            sell_payload = payload.get("sell_order_payload") or build_kite_order_payload(pair["sell_leg_tradingsymbol"], "SELL", int(pair["quantity"]), float(payload.get("sell_limit_price") or 0), pair_id[-20:])
            result = broker.place_order(sell_payload)
            repository.update_pair(pair_id, sell_leg_order_id=result["order_id"], sell_leg_status=result.get("status", "OPEN"), sell_leg_placed=1, pair_status="HEDGE_FILLED_WAITING_SELL", last_checked_at=current.isoformat(timespec="seconds"))
            repository.log(pair_id, "SELL_SUBMITTED_AFTER_HEDGE", result["order_id"])
            placed += 1
            continue
        if buy_status in COMPLETE and sell_status in COMPLETE:
            repository.update_pair(pair_id, buy_leg_status=buy_status, sell_leg_status=sell_status, pair_status="BOTH_FILLED", last_checked_at=current.isoformat(timespec="seconds"))
            both += 1
            continue
        if sell_status in COMPLETE and buy_status not in COMPLETE:
            repository.update_pair(pair_id, pair_status="EXIT_REQUIRED", last_checked_at=current.isoformat(timespec="seconds"))
            exit_required += 1
    repository.export_outputs()
    return {"checked": checked, "placed": placed, "failed": failed, "exit_required": exit_required, "both_filled": both}
