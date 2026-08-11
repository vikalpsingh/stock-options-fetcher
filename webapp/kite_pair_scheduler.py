"""Kite spread pair scheduler and order-status monitor."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import kite_spread_config as spread_cfg
from kite_pair_execution import build_kite_order_payload, round_limit_price_to_tick
from kite_spread_repository import KiteSpreadRepository


COMPLETE = {"COMPLETE"}
FAILED = {"REJECTED", "CANCELLED"}


def order_status_lookup(orders: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("order_id") or row.get("orderId") or ""): row for row in orders if row.get("order_id") or row.get("orderId")}


def status(row: dict[str, Any] | None, fallback: str = "OPEN") -> str:
    return str((row or {}).get("status") or fallback or "OPEN").upper()


def run_kite_pair_scheduler_once(repository: KiteSpreadRepository, broker: Any, now: datetime | None = None) -> dict[str, int]:
    current = now or datetime.now(timezone.utc)
    by_id = order_status_lookup(broker.get_orders())
    checked = placed = modified = failed = exit_required = both = 0
    for pair in repository.list_pairs(include_closed=False):
        checked += 1
        pair_id = pair["pair_id"]
        buy_id = str(pair.get("buy_leg_order_id") or "")
        sell_id = str(pair.get("sell_leg_order_id") or "")
        buy_status = status(by_id.get(buy_id), pair.get("buy_leg_status") or "OPEN")
        sell_status = status(by_id.get(sell_id), pair.get("sell_leg_status") or "PENDING")
        payload = json.loads(pair.get("payload_json") or "{}")
        if buy_status in FAILED:
            if sell_id and sell_status not in COMPLETE:
                broker.cancel_order("regular", sell_id)
            repository.update_pair(pair_id, buy_leg_status=buy_status, sell_leg_status=sell_status, pair_status="FAILED", last_checked_at=current.isoformat(timespec="seconds"))
            failed += 1
            continue
        if sell_status in FAILED:
            repository.update_pair(pair_id, buy_leg_status=buy_status, sell_leg_status=sell_status, pair_status="FAILED", last_checked_at=current.isoformat(timespec="seconds"))
            failed += 1
            continue
        execution_mode = str(pair.get("execution_mode") or "HEDGE_FIRST")
        if execution_mode == "HEDGE_FIRST":
            if buy_status in COMPLETE and sell_id and sell_status not in COMPLETE and not pair.get("sell_leg_modified_at"):
                target_price = round_limit_price_to_tick(
                    float(payload.get("sell_cmp_limit_price") or payload.get("sell_limit_price") or payload.get("sell_leg_premium") or 0)
                )
                broker.modify_order("regular", sell_id, {"order_type": "LIMIT", "price": target_price})
                repository.update_pair(
                    pair_id,
                    buy_leg_status=buy_status,
                    sell_leg_status=sell_status,
                    sell_leg_modified_at=current.isoformat(timespec="seconds"),
                    pair_status="HEDGE_FILLED_SELL_REPRICED",
                    last_checked_at=current.isoformat(timespec="seconds"),
                )
                repository.log(pair_id, "SELL_REPRICED_TO_CMP_AFTER_HEDGE", f"{sell_id} @ {target_price}")
                modified += 1
                continue
            if buy_status in COMPLETE and not int(pair.get("sell_leg_placed") or 0):
                sell_payload = payload.get("sell_order_payload") or build_kite_order_payload(pair["sell_leg_tradingsymbol"], "SELL", int(pair["quantity"]), float(payload.get("sell_limit_price") or payload.get("sell_leg_premium") or 0), pair_id[-20:])
                result = broker.place_order(sell_payload)
                repository.update_pair(pair_id, sell_leg_order_id=result["order_id"], sell_leg_status=result.get("status", "OPEN"), sell_leg_placed=1, pair_status="HEDGE_FILLED_WAITING_SELL", last_checked_at=current.isoformat(timespec="seconds"))
                repository.log(pair_id, "SELL_SUBMITTED_AFTER_HEDGE", result["order_id"])
                placed += 1
                continue
            if buy_status not in COMPLETE and (current - datetime.fromisoformat(pair["created_at"])).total_seconds() >= spread_cfg.PAIR_LEG_TIMEOUT_SECONDS:
                if buy_id:
                    broker.cancel_order("regular", buy_id)
                if sell_id and sell_status not in COMPLETE:
                    broker.cancel_order("regular", sell_id)
                repository.update_pair(pair_id, pair_status="FAILED", buy_leg_status=buy_status, sell_leg_status=sell_status, last_checked_at=current.isoformat(timespec="seconds"))
                failed += 1
                continue
        if buy_status in COMPLETE and sell_status in COMPLETE:
            repository.update_pair(pair_id, buy_leg_status=buy_status, sell_leg_status=sell_status, pair_status="BOTH_FILLED", last_checked_at=current.isoformat(timespec="seconds"))
            both += 1
            continue
        if execution_mode == "SIMULTANEOUS" and ((sell_status in COMPLETE) != (buy_status in COMPLETE)):
            if sell_status in COMPLETE and buy_status not in COMPLETE and not pair.get("buy_leg_modified_at"):
                broker.modify_order("regular", buy_id, {"order_type": "MARKET", "price": 0})
                repository.update_pair(pair_id, buy_leg_modified_at=current.isoformat(timespec="seconds"), pair_status="ONE_LEG_FILLED")
                modified += 1
                continue
            if buy_status in COMPLETE and sell_status not in COMPLETE and not pair.get("sell_leg_modified_at"):
                broker.modify_order("regular", sell_id, {"order_type": "MARKET", "price": 0})
                repository.update_pair(pair_id, sell_leg_modified_at=current.isoformat(timespec="seconds"), pair_status="ONE_LEG_FILLED")
                modified += 1
                continue
        if sell_status in COMPLETE and buy_status not in COMPLETE:
            repository.update_pair(pair_id, pair_status="EXIT_REQUIRED", last_checked_at=current.isoformat(timespec="seconds"))
            exit_required += 1
    repository.export_outputs()
    return {"checked": checked, "placed": placed, "modified": modified, "failed": failed, "exit_required": exit_required, "both_filled": both}
