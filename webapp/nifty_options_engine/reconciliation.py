"""Pure reconciliation of verified NIFTY legs. No broker calls or DB writes.

Contract compatibility alone is not strategy ownership. A strategy_id must come
from recorded fill allocations; unassigned shorts require review, not guessing.
"""
from collections import defaultdict
from datetime import date
import math


def finite_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def normalize_leg(row):
    leg = dict(row)
    leg["tradingsymbol"] = str(row.get("tradingsymbol") or "").upper()
    leg["account_id"] = str(row.get("account_id") or "")
    leg["strategy_id"] = str(row.get("strategy_id") or "")
    leg["option_type"] = str(row.get("option_type") or row.get("instrument_type") or "").upper()
    leg["strike"] = finite_number(row.get("strike"))
    leg["quantity"] = finite_number(row.get("quantity"))
    leg["average_price"] = finite_number(row.get("average_price"))
    try:
        leg["expiry"] = date.fromisoformat(str(row.get("expiry") or row.get("expiry_date"))[:10]).isoformat()
    except (TypeError, ValueError):
        leg["expiry"] = ""
    leg["valid"] = (
        leg["option_type"] in {"CE", "PE"} and bool(leg["expiry"])
        and leg["strike"] is not None and leg["strike"] > 0
        and leg["quantity"] is not None and leg["quantity"].is_integer()
        and not row.get("reconciliation_error")
    )
    return leg


def allocate_nifty_positions(broker_positions, strategy_allocations, pending_orders=None):
    """Reconcile recorded fill allocations against one fresh broker net snapshot.

    Allocations must carry persistent IDs and fill IDs, never inferred pairings.
    A shared symbol may be split between strategies only while the summed signed
    allocation fits its actual broker net position. Ambiguity blocks the entire
    affected position. Pending hedge disposal also invalidates protection.
    """
    broker = defaultdict(list)
    allocations = defaultdict(list)
    errors = []
    seen_allocations, seen_fills = {}, {}
    bad_keys = set()

    def key(row):
        return (str(row.get("account_id") or ""),
                str(row.get("tradingsymbol") or "").upper(),
                str(row.get("product") or "NRML").upper())

    for row in broker_positions:
        broker[key(row)].append(dict(row))
    for row in strategy_allocations:
        identity = key(row)
        allocation_id = (identity[0], str(row.get("allocation_id") or ""))
        fill_ids = [(identity[0], str(item)) for item in row.get("fill_ids") or []]
        if (not identity[0] or not row.get("strategy_id") or not allocation_id[1]
                or not fill_ids or any(not item[1] for item in fill_ids)
                or allocation_id in seen_allocations
                or any(item in seen_fills for item in fill_ids)):
            bad_keys.add(identity)
            if allocation_id in seen_allocations:
                bad_keys.add(seen_allocations[allocation_id])
            for item in fill_ids:
                if item in seen_fills:
                    bad_keys.add(seen_fills[item])
            errors.append("DUPLICATE_OR_UNVERIFIED_ALLOCATION")
        seen_allocations[allocation_id] = identity
        seen_fills.update({item: identity for item in fill_ids})
        allocations[identity].append(dict(row))
    pending_disposals = set()
    pending_shorts = False
    for order in pending_orders or []:
        if str(order.get("status") or "").upper() in {"COMPLETE", "CANCELLED", "REJECTED"}:
            continue
        # Includes UNKNOWN statuses: they must be reconciled before entry.
        if str(order.get("transaction_type") or "").upper() == "SELL":
            pending_disposals.add(key(order))
            pending_shorts = True
    output = []
    for identity in broker.keys() | allocations.keys():
        snapshots = broker.get(identity) or []
        assigned = allocations.get(identity) or []
        base = snapshots[0] if len(snapshots) == 1 else (assigned[0] if assigned else {})
        broker_qty = finite_number(base.get("quantity")) if len(snapshots) == 1 else None
        qtys = [finite_number(row.get("quantity")) for row in assigned]
        invalid = (identity in bad_keys or len(snapshots) != 1 or broker_qty is None
                   or any(row.get("reconciliation_error") for row in assigned))
        invalid = invalid or any(qty is None or not qty.is_integer() for qty in qtys)
        if not invalid:
            invalid = (any(qty and qty * broker_qty <= 0 for qty in qtys)
                       or abs(sum(qtys)) > abs(broker_qty))
        if not invalid:
            for row in assigned:
                # Instrument identity must agree with the broker/master row.
                if any((finite_number(row.get(field)) != finite_number(base.get(field))
                        if field in {"instrument_token", "strike"}
                        else str(row.get(field))[:10] != str(base.get(field))[:10])
                       for field in ("instrument_token", "expiry", "strike", "option_type")
                       if row.get(field) is not None):
                    invalid = True
        if invalid:
            errors.append("ALLOCATION_DOES_NOT_MATCH_BROKER_NET")
            output.append({**base, "strategy_id": "", "reconciliation_error": True})
            continue
        disposal = identity in pending_disposals and broker_qty > 0
        if disposal:
            errors.append("HEDGE_DISPOSAL_PENDING")

        def allocated_row(row, quantity):
            result = {**base, **row, "quantity": quantity, "reconciliation_error": disposal}
            # Broker MTM is per net symbol, not per strategy allocation.
            for field in ("pnl", "realised", "unrealised"):
                value = finite_number(base.get(field))
                if value is not None and broker_qty:
                    result[field] = value * abs(quantity / broker_qty)
            return result

        for row in assigned:
            if row["quantity"]:
                output.append(allocated_row(row, row["quantity"]))
        residual = broker_qty - sum(qtys)
        if residual:
            output.append(allocated_row({"strategy_id": ""}, residual))
    return {"positions": output, "errors": sorted(set(errors)),
            "pending_sell_present": pending_shorts,
            "block_new_entries": bool(errors) or pending_shorts}


def reconcile_nifty_positions(positions):
    """Allocate each owned hedge quantity once within its account and strategy.

    Input must be NIFTY-only with instrument-master metadata and broker signed
    quantities. Net broker positions must be split using recorded allocations
    before assigning strategy IDs. Missing metadata fails closed.
    """
    legs = [normalize_leg(row) for row in positions
            if row.get("quantity") != 0 or row.get("reconciliation_error")]
    groups = defaultdict(list)
    for index, leg in enumerate(legs):
        key = (leg["account_id"], leg["strategy_id"] or f"UNMATCHED:{index}")
        groups[key].append(leg)
    results, shorts = [], []
    for (account, strategy), members in groups.items():
        longs = [leg for leg in members if leg["valid"] and leg["quantity"] > 0]
        remaining = {id(leg): leg["quantity"] for leg in longs}
        checks = []
        for short in members:
            if short["quantity"] is not None and short["quantity"] >= 0:
                continue
            needed = abs(short["quantity"]) if short["quantity"] is not None else 0
            covered, allocations = 0, []
            if short["valid"] and short["strategy_id"]:
                for hedge in sorted(longs, key=lambda leg: abs(leg["strike"] - short["strike"])):
                    direction = 1 if short["option_type"] == "CE" else -1
                    if (hedge["expiry"] != short["expiry"]
                            or hedge["option_type"] != short["option_type"]
                            or direction * (hedge["strike"] - short["strike"]) <= 0):
                        continue
                    amount = min(remaining[id(hedge)], needed - covered)
                    if amount > 0:
                        allocations.append({"symbol": hedge["tradingsymbol"], "quantity": amount})
                        remaining[id(hedge)] -= amount
                        covered += amount
            status = ("OPEN_SPREAD" if covered == needed and needed > 0 and short["valid"]
                      else "PARTIAL_SPREAD" if covered else "UNHEDGED_SHORT")
            check = {"short_symbol": short["tradingsymbol"], "short_quantity": needed,
                     "hedge_quantity": covered, "allocations": allocations, "status": status,
                     "account_id": account, "strategy_id": short["strategy_id"]}
            checks.append(check)
            shorts.append(check)
        unknown = any(not leg["valid"] for leg in members)
        status = ("UNMATCHED" if unknown else
                  "HEDGE_REPAIR_REQUIRED" if any(c["status"] != "OPEN_SPREAD" for c in checks) else
                  "OPEN_IRON_CONDOR" if {leg["option_type"] for leg in members} == {"PE", "CE"} and checks else
                  "OPEN_SPREAD" if checks else "LONG_HEDGE_ONLY")
        results.append({"account_id": account, "strategy_id": strategy,
                        "status": status, "legs": members, "shorts": checks,
                        "unallocated_hedge_quantity": sum(remaining.values())})
    blocked = any(group["status"] in {"UNMATCHED", "HEDGE_REPAIR_REQUIRED"} for group in results)
    return {"groups": results, "shorts": shorts, "block_new_entries": blocked,
            "allow_exit_orders": True, "allow_hedge_repair_orders": True,
            "unhedged_short_symbols": [row["short_symbol"] for row in shorts if row["status"] != "OPEN_SPREAD"]}
