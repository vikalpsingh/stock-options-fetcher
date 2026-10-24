"""Durable, manually approved protected execution. Monitoring never places orders."""

from __future__ import annotations
from observability.usage_tracker import tracked

import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Callable


class ProtectedExecutionRepository:
    def __init__(self, path):
        self.path = path
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS trade_protected_execution (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, request_key TEXT NOT NULL,
                version INTEGER NOT NULL, data TEXT NOT NULL,
                UNIQUE(account_id, request_key))""")

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, account, execution_id):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT data FROM trade_protected_execution WHERE account_id=? AND id=?",
                (account, execution_id),
            ).fetchone()
        if not row:
            raise PermissionError("Execution not found for this account.")
        return json.loads(row["data"])

    def recent(self, account):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT data FROM trade_protected_execution WHERE account_id=? ORDER BY rowid DESC LIMIT 100",
                (account,),
            ).fetchall()
        return [data for row in rows if (data := json.loads(row["data"])).get("kind") != "BASKET"]

    def recent_baskets(self, account):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT data FROM trade_protected_execution WHERE account_id=? ORDER BY rowid DESC",
                (account,)).fetchall()
        return [data for row in rows if (data := json.loads(row["data"])).get("kind") == "BASKET" and not data.get("review_archived")]

    def clear_basket_reviews(self, account=None, *, before=None):
        """Archive unsubmitted reviews atomically; never touch orders or fills."""
        count = 0
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows = conn.execute('SELECT data FROM trade_protected_execution' +
                (' WHERE account_id=?' if account is not None else ''),
                (account,) if account is not None else ()).fetchall()
            for row in rows:
                record = json.loads(row['data'])
                if record.get('kind') != 'BASKET' or record.get('state') != 'REVIEW':
                    continue
                if any(leg.get('order_id') or leg.get('filled') or leg.get('status') != 'NOT_SUBMITTED'
                       for leg in record.get('legs', [])) or record.get('exit_legs'):
                    continue
                if before is not None:
                    try:
                        stamp = datetime.fromisoformat(record['reviewed_at'])
                        if stamp.tzinfo is None or stamp >= before:
                            continue
                    except (ValueError, TypeError, KeyError):
                        continue
                record.update(state='CLOSED', review_archived=True,
                    note='Unsubmitted review cleared; create a new review before GO.',
                    version=record['version']+1, updated_at=datetime.now(timezone.utc).isoformat())
                conn.execute('UPDATE trade_protected_execution SET version=?,data=? WHERE id=?',
                             (record['version'],json.dumps(record),record['id']))
                count += 1
        return count

    def clear_previous_session_reviews(self, now=None):
        from zoneinfo import ZoneInfo
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError('Cleanup clock must be timezone aware.')
        current = current.astimezone(ZoneInfo('Asia/Kolkata'))
        cutoff = current.replace(hour=9,minute=0,second=0,microsecond=0)
        if current.weekday() >= 5 or current < cutoff:
            return 0
        return self.clear_basket_reviews(before=cutoff)

    def create_basket_review(self, account, preview, mode):
        """Save authoritative review before countdown; no order is sent here."""
        _validate_basket(preview)
        if not account or mode not in {"PAPER", "LIVE"}:
            raise ValueError("Explicit account and execution mode required.")
        eid = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        record = dict(id=eid, account_id=account, mode=mode, version=0, kind="BASKET",
                      preview=preview, state="REVIEW", reviewed_at=now, updated_at=now, note="",
                      legs=[dict(payload=payload, tag="NB" + eid[:15] + str(index),
                                 order_id="", status="NOT_SUBMITTED", filled=0, average=0)
                            for index, payload in enumerate(preview["order_payloads"])])
        with self.connect() as conn:
            conn.execute("INSERT INTO trade_protected_execution VALUES (?,?,?,?,?)",
                         (eid, account, "BASKET-" + eid, 0, json.dumps(record)))
        return record

    def claim_basket(self, record):
        """Reserve symbols across workflows atomically with the first BUY claim."""
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            symbols = {leg["payload"]["tradingsymbol"] for leg in record["legs"]}
            for row in conn.execute("SELECT data FROM trade_protected_execution WHERE account_id=? AND id<>?",
                                    (record["account_id"], record["id"])):
                other = json.loads(row["data"])
                if other["mode"] != record["mode"] or other["state"] in {"REVIEW", "CLOSED"}:
                    continue
                other_symbols = {leg["tradingsymbol"] for leg in other["preview"]["order_payloads"]}
                if symbols & other_symbols:
                    raise PermissionError("A contract is already reserved by an execution. Reconcile it first.")
            updated = {**record, "version": record["version"] + 1, "state": "VALIDATED"}
            count = conn.execute(
                "UPDATE trade_protected_execution SET version=?,data=? WHERE id=? AND account_id=? AND version=?",
                (updated["version"], json.dumps(updated), record["id"], record["account_id"], record["version"]),
            ).rowcount
            if count != 1:
                raise PermissionError("Execution changed; refresh before continuing.")
        return updated

    def create(self, account, request_key, preview, mode):
        if mode not in {"PAPER", "LIVE"} or not request_key:
            raise ValueError("Execution mode and request key are required.")
        execution_id = uuid.uuid4().hex
        record = dict(id=execution_id, account_id=account, mode=mode, version=0,
                      preview=preview, state="HEDGE_SUBMITTING", hedge_order_id="",
                      sell_order_id="", hedge_filled=0, short_filled=0,
                      hedge_average_price=0, hedge_status="SUBMITTING", short_status="NOT_SUBMITTED",
                      hedge_tag="TP" + execution_id[:16] + "H",
                      short_tag="TP" + execution_id[:16] + "S",
                      updated_at=datetime.now(timezone.utc).isoformat(), note="")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute(
                "SELECT data FROM trade_protected_execution WHERE account_id=? AND request_key=?",
                (account, request_key),
            ).fetchone()
            if prior:
                return json.loads(prior["data"]), False
            # Conservative account-wide reservation: no sharing a hedge contract
            # across executions, including active spreads and ambiguous submissions.
            for row in conn.execute("SELECT data FROM trade_protected_execution WHERE account_id=?", (account,)):
                existing = json.loads(row["data"])
                if (existing["mode"] == mode and existing["state"] not in {"REVIEW", "CLOSED"}
                        and preview["hedge_symbol"] in {
                            leg["tradingsymbol"] for leg in existing["preview"]["order_payloads"]
                            if leg["transaction_type"] == "BUY"}):
                    raise PermissionError("This hedge contract already belongs to an execution. Reconcile it first.")
            conn.execute("INSERT INTO trade_protected_execution VALUES (?,?,?,?,?)",
                         (execution_id, account, request_key, 0, json.dumps(record)))
        return record, True

    def save(self, record):
        old_version = record["version"]
        updated = {**record, "version": old_version + 1,
                   "updated_at": datetime.now(timezone.utc).isoformat()}
        with self.connect() as conn:
            changed = conn.execute(
                """UPDATE trade_protected_execution SET version=?,data=?
                   WHERE account_id=? AND id=? AND version=?""",
                (updated["version"], json.dumps(updated), record["account_id"], record["id"], old_version),
            ).rowcount
            if changed != 1:
                raise PermissionError("Execution changed in another request. Reconcile before continuing.")
        return updated


def _validate_preview(preview):
    quantity, lot = preview.get("quantity", 0), preview.get("lot_size", 0)
    legs = preview.get("order_payloads") or []
    if (not preview.get("hedged_order_acknowledged") or not preview.get("eligible")
            or preview.get("strategy_type") not in {"BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"}
            or not isinstance(quantity, int) or quantity <= 0 or lot <= 0 or quantity % lot
            or len(legs) != 2):
        raise PermissionError("An acknowledged, eligible protected spread is required.")
    call_spread = preview["strategy_type"] == "BEAR_CALL_SPREAD"
    width = (float(preview["hedge_strike"]) - float(preview["short_strike"])) * (1 if call_spread else -1)
    option_type = "CE" if call_spread else "PE"
    if (not math.isfinite(width) or width <= 0
            or not all(str(preview[key]).endswith(option_type) for key in ("hedge_symbol", "short_symbol"))):
        raise PermissionError("Protective strike direction and option type must match the spread.")
    for leg, side, symbol in zip(legs, ("BUY", "SELL"), (preview["hedge_symbol"], preview["short_symbol"])):
        if (leg.get("transaction_type") != side or leg.get("tradingsymbol") != symbol
                or leg.get("quantity") != quantity or leg.get("order_type") != "LIMIT"
                or leg.get("exchange") != "NFO" or leg.get("product") != "NRML"
                or not math.isfinite(float(leg.get("price", 0))) or leg["price"] <= 0):
            raise PermissionError("Protected execution requires verified, matching LIMIT legs.")


def _check_mode(record, broker):
    if (record["mode"] == "PAPER") != bool(broker.paper_trading) or getattr(broker, "dry_run", False):
        raise PermissionError("Broker mode does not match the saved execution.")


@tracked("trade_protected_execution:start_execution", boundary="start_execution")
def start_execution(repo, account, request_key, preview, mode, broker, validator):
    _validate_preview(preview)
    _check_mode({"mode": mode}, broker)
    validator(preview)
    record, created = repo.create(account, request_key, preview, mode)
    if not created:
        return record
    # Intent is committed before the network call. A crash is reconciled by tag.
    payload = {**preview["order_payloads"][0], "tag": record["hedge_tag"]}
    try:
        response = broker.place_order(payload)
        record["hedge_order_id"] = str(response.get("order_id") or "")
        if record["mode"] == "PAPER" and record["hedge_order_id"]:
            record["hedge_order_id"] = "PAPER-" + record["hedge_tag"]
        record["state"] = "HEDGE_PENDING" if record["hedge_order_id"] else "HEDGE_SUBMISSION_UNKNOWN"
        record["hedge_status"] = "PENDING"
    except Exception:
        record["state"] = "HEDGE_SUBMISSION_UNKNOWN"
        record["note"] = "BUY outcome unknown. Reconcile broker orders; do not resubmit."
    return repo.save(record)


def _leg(record, broker, orders, side, include_trades=False):
    hedge = side == "hedge"
    payload = record["preview"]["order_payloads"][0 if hedge else 1]
    order_id = record["hedge_order_id" if hedge else "sell_order_id"]
    tag = record["hedge_tag" if hedge else "short_tag"]
    if record["mode"] == "PAPER":
        if not order_id:
            raise ValueError("No simulated submission receipt.")
        result = (order_id, "COMPLETE", payload["quantity"], float(payload["price"]))
        trades = [{**payload, "order_id": order_id, "trade_id": order_id + "-FILL",
                   "average_price": payload["price"],
                   "fill_timestamp": record.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                   "fees": 0}]
        return (*result, trades) if include_trades else result
    matches = [o for o in orders if (str(o.get("order_id")) == order_id if order_id else o.get("tag") == tag)]
    if len(matches) != 1:
        raise ValueError("Order identity is unresolved.")
    order = matches[0]
    if any(order.get(k) != payload[k] for k in
           ("tradingsymbol", "exchange", "product", "transaction_type", "quantity", "order_type")):
        raise ValueError("Order differs from authorised leg.")
    order_id = str(order["order_id"])
    seen, filled, cost = set(), 0, 0.0
    trades = broker.get_order_trades(order_id)
    for trade in trades:
        trade_id = str(trade.get("trade_id") or "")
        qty, price = trade.get("quantity", 0), float(trade.get("average_price") or trade.get("price") or 0)
        if (not trade_id or trade_id in seen or not isinstance(qty, int) or qty <= 0
                or not math.isfinite(price) or price <= 0 or str(trade.get("order_id")) != order_id
                or any(trade.get(k) != payload[k] for k in
                       ("tradingsymbol", "exchange", "product", "transaction_type"))):
            raise ValueError("Fill identity is unresolved.")
        seen.add(trade_id)
        filled += qty
        cost += qty * price
    status = str(order.get("status") or "").upper()
    if filled > payload["quantity"] or order.get("filled_quantity") != filled:
        raise ValueError("Order and trade quantities disagree.")
    if status == "COMPLETE" and filled != payload["quantity"]:
        raise ValueError("Complete order lacks full trade confirmation.")
    result = (order_id, status, filled, cost / filled if filled else 0.0)
    return (*result, trades) if include_trades else result


def reconcile_execution(repo, account, execution_id, broker):
    record = repo.get(account, execution_id)
    _check_mode(record, broker)
    try:
        orders = [] if record["mode"] == "PAPER" else broker.get_orders()
        oid, status, filled, average = _leg(record, broker, orders, "hedge")
        record.update(hedge_order_id=oid, hedge_status=status, hedge_filled=filled,
                      hedge_average_price=average)
        short_attempted = record["short_status"] != "NOT_SUBMITTED"
        if short_attempted:
            oid, status, filled, average = _leg(record, broker, orders, "short")
            record.update(sell_order_id=oid, short_status=status, short_filled=filled,
                          short_average_price=average)
            record["state"] = ("SPREAD_ACTIVE" if status == "COMPLETE" else
                               "SHORT_" + status if status in {"REJECTED", "CANCELLED"} else "SELL_PENDING")
        elif status == "COMPLETE":
            record["state"] = "HEDGE_FILLED"
        elif status in {"CANCELLED", "REJECTED"}:
            record["state"] = "HEDGE_" + status
        else:
            record["state"] = "PARTIAL_HEDGE" if filled else "HEDGE_PENDING"
        record["note"] = ""
    except Exception:
        record["state"] = "RECONCILIATION_REQUIRED"
        record["note"] = "Broker order/trade verification is incomplete. No order was submitted."
    return repo.save(record)


@tracked("trade_protected_execution:confirm_short", boundary="confirm_short")
def confirm_short(repo, account, execution_id, broker, validator: Callable[[dict], dict], acknowledged=False):
    if not acknowledged:
        raise PermissionError("Explicit renewed SELL risk acceptance is required.")
    record = reconcile_execution(repo, account, execution_id, broker)
    if record["state"] != "HEDGE_FILLED" or record["short_status"] != "NOT_SUBMITTED":
        raise PermissionError("A full verified, uncommitted hedge fill is required.")
    # Fresh approval runs immediately before the durable submission claim.
    approval = validator(record)
    payload = dict(record["preview"]["order_payloads"][1])
    if approval.get("quantity") != payload["quantity"] or approval.get("price") != payload["price"]:
        raise PermissionError("SELL exceeds the saved contract/quantity/price authorisation.")
    if record["mode"] == "LIVE":
        if any(o.get("tradingsymbol") == record["preview"]["hedge_symbol"]
               and o.get("transaction_type") == "SELL"
               and o.get("status") not in {"COMPLETE", "REJECTED", "CANCELLED"}
               for o in broker.get_orders()):
            raise PermissionError("A pending SELL may consume the hedge coverage.")
        positions = broker.get_positions().get("net") or []
        coverage = sum(int(p.get("quantity") or 0) for p in positions
                       if p.get("tradingsymbol") == record["preview"]["hedge_symbol"]
                       and p.get("exchange") == "NFO" and p.get("product") == "NRML")
        if coverage < payload["quantity"]:
            raise PermissionError("Confirmed hedge is no longer available in broker positions.")
    record.update(state="SELL_SUBMITTING", short_status="SUBMITTING", risk_approval=approval)
    record = repo.save(record)  # CAS prevents concurrent confirmations from placing twice.
    try:
        response = broker.place_order({**payload, "tag": record["short_tag"]})
        record["sell_order_id"] = str(response.get("order_id") or "")
        if record["mode"] == "PAPER" and record["sell_order_id"]:
            record["sell_order_id"] = "PAPER-" + record["short_tag"]
        record["state"] = "SELL_PENDING" if record["sell_order_id"] else "SHORT_SUBMISSION_UNKNOWN"
        record["short_status"] = "PENDING"
    except Exception:
        record["state"] = "SHORT_SUBMISSION_UNKNOWN"
        record["note"] = "SELL outcome unknown. Reconcile broker orders; do not retry."
    return repo.save(record)


def _validate_basket(preview):
    """Use verified master legs; reject undefined structures before persistence."""
    from nifty_options_engine.reconciliation import reconcile_nifty_positions
    legs = preview.get("legs") or []
    payloads = preview.get("order_payloads") or []
    if len(legs) not in {2, 4} or len(payloads) != len(legs):
        raise PermissionError("Two or four verified spread legs are required.")
    signed = []
    for leg, payload in zip(legs, payloads):
        qty, lot = leg.get("quantity"), leg.get("lot_size")
        if (not isinstance(qty, int) or qty <= 0 or not isinstance(lot, int) or lot <= 0 or qty % lot
                or not leg.get("instrument_token") or payload.get("quantity") != qty
                or payload.get("tradingsymbol") != leg.get("tradingsymbol")
                or payload.get("transaction_type") != leg.get("transaction_type")
                or payload.get("transaction_type") not in {"BUY", "SELL"}
                or payload.get("exchange") != "NFO" or payload.get("product") != "NRML"
                or payload.get("order_type") != "LIMIT"
                or not math.isfinite(float(payload.get("price", 0))) or payload["price"] <= 0):
            raise PermissionError("Verified LIMIT legs and master lot quantities are required.")
        signed.append({**leg, "strategy_id": "REVIEW", "quantity": qty * (-1 if payload["transaction_type"] == "SELL" else 1)})
    if (len({str(leg["expiry"]) for leg in legs}) != 1
            or len({leg["quantity"] for leg in legs}) != 1
            or len({leg["tradingsymbol"] for leg in legs}) != len(legs)
            or reconcile_nifty_positions(signed)["block_new_entries"]
            or not any(leg["transaction_type"] == "SELL" for leg in legs)):
        raise PermissionError("Only fully protected same-expiry spreads are executable.")


def _basket_order(record, leg, broker):
    """Persist intent before broker access. A timeout is never retried blindly."""
    try:
        result = broker.place_order({**leg["payload"], "tag": leg["tag"]})
        leg["order_id"] = ("PAPER-" + leg["tag"] if record["mode"] == "PAPER"
                           and result.get("order_id") else str(result.get("order_id") or ""))
        leg["status"] = "PENDING" if leg["order_id"] else "SUBMISSION_UNKNOWN"
    except Exception:
        leg["status"] = "SUBMISSION_UNKNOWN"
        record["note"] = "Submission outcome unknown. Reconcile; do not retry the order."


@tracked("trade_protected_execution:submit_basket_hedges", boundary="submit_basket_hedges")
def submit_basket_hedges(repo, account, eid, broker, validator, acknowledged=False, now=None):
    record = repo.get(account, eid)
    _check_mode(record, broker)
    if not acknowledged or record.get("kind") != "BASKET" or record["state"] != "REVIEW":
        raise PermissionError("A saved review and explicit GO acknowledgement are required.")
    age = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(record["reviewed_at"])).total_seconds()
    if age < 10 or age > 300:
        raise PermissionError("Wait the full 10 seconds; reviews expire after five minutes.")
    _validate_basket(record["preview"])
    validator(record, "ENTRY")
    record = repo.claim_basket(record)
    for index in range(len(record["legs"])):
        if record["legs"][index]["payload"]["transaction_type"] != "BUY":
            continue
        record["legs"][index]["status"] = "SUBMITTING"
        record["state"] = "HEDGE_PENDING"
        record = repo.save(record)
        _basket_order(record, record["legs"][index], broker)
        record = repo.save(record)
        if record["legs"][index]["status"] == "SUBMISSION_UNKNOWN":
            break
    return record


def basket_remaining(record, entry):
    symbol = entry["payload"]["tradingsymbol"]
    return entry["filled"] - sum(leg["filled"] for leg in record.get("exit_legs", [])
                                 if leg["payload"]["tradingsymbol"] == symbol)


@tracked("trade_protected_execution:reconcile_basket", boundary="reconcile_basket")
def reconcile_basket(repo, account, eid, broker):
    record = repo.get(account, eid)
    _check_mode(record, broker)
    if record.get("kind") not in {"BASKET", "TRADE_PAIR"}:
        raise PermissionError("Not a basket execution.")
    if record["state"] == "REVIEW":
        return record
    try:
        orders = [] if record["mode"] == "PAPER" else broker.get_orders()
        for leg in record["legs"] + record.get("exit_legs", []):
            if leg["status"] == "NOT_SUBMITTED":
                continue
            if leg["status"] == "COMPLETE" and "trades" in leg:
                continue  # durable fills survive the broker's day-only order book
            proxy = {"mode": record["mode"], "preview": {"order_payloads": [leg["payload"]]},
                     "hedge_order_id": leg["order_id"], "hedge_tag": leg["tag"], "updated_at": record["updated_at"]}
            oid, status, filled, average, trades = _leg(proxy, broker, orders, "hedge", include_trades=True)
            if filled < leg["filled"]:
                raise ValueError("Confirmed fills cannot decrease.")
            leg.update(order_id=oid, status=status, filled=filled, average=average,
                       trades=json.loads(json.dumps(trades, default=str)))
        buys = [leg for leg in record["legs"] if leg["payload"]["transaction_type"] == "BUY"]
        sells = [leg for leg in record["legs"] if leg["payload"]["transaction_type"] == "SELL"]
        full = lambda group: bool(group) and all(leg["status"] == "COMPLETE" and leg["filled"] == leg["payload"]["quantity"] for leg in group)
        if record.get("exit_legs"):
            exits = record["exit_legs"]
            remaining = [basket_remaining(record, leg) for leg in record["legs"]]
            if any(qty < 0 for qty in remaining):
                raise ValueError("Exit fills exceed owned entry quantity.")
            pending = any(leg["status"] not in {"COMPLETE", "REJECTED", "CANCELLED", "NOT_SUBMITTED"} for leg in exits)
            shorts_closed = all(basket_remaining(record, leg) == 0 for leg in sells)
            record["state"] = (
                ("PARTIALLY_CLOSED" if any(leg["filled"] for leg in exits) else "EXIT_PENDING") if pending
                else "CLOSED" if not any(remaining)
                else "SHORT_CLOSED_HEDGE_OPEN" if shorts_closed
                else "EXIT_RECOVERY_READY")
        elif (any(leg["status"] in {"REJECTED", "CANCELLED"} for leg in record["legs"])
              and all(leg["status"] in {"COMPLETE", "REJECTED", "CANCELLED", "NOT_SUBMITTED"}
                      for leg in record["legs"])):
            # Cleanup only after every submitted entry is terminal. Filled
            # quantities remain owned; no failed entry order is retried.
            record["state"] = "RECOVERY_READY" if any(leg["filled"] for leg in record["legs"]) else "CLOSED"
        elif full(buys) and full(sells):
            record["state"] = "OPEN"
        elif full(buys):
            record["state"] = ("HEDGE_FILLED" if all(leg["status"] == "NOT_SUBMITTED" for leg in sells)
                               else "SHORT_PARTIAL" if any(leg["filled"] for leg in sells) else "SHORT_PENDING")
        else:
            record["state"] = "HEDGE_PARTIAL" if any(leg["filled"] for leg in buys) else "HEDGE_PENDING"
        record["note"] = ""
    except Exception:
        record["state"] = "RECONCILIATION_REQUIRED"
        record["note"] = "Broker order/trade identity or quantity is unresolved. No order was placed."
    return repo.save(record)


def confirm_basket_shorts(repo, account, eid, broker, validator, acknowledged=False):
    if not acknowledged:
        raise PermissionError("Renewed risk acceptance is required before SELL.")
    record = reconcile_basket(repo, account, eid, broker)
    if record["state"] not in {"HEDGE_FILLED", "SHORT_PENDING", "SHORT_PARTIAL"}:
        raise PermissionError("Every hedge must be fully filled before any short submission.")
    # Resume only untouched legs after a previous approval interruption. Unknown
    # submissions must first reconcile to an identified broker order; never retry.
    if any(leg["status"] in {"SUBMITTING", "SUBMISSION_UNKNOWN"}
           for leg in record["legs"]):
        raise PermissionError("Resolve uncertain submissions before continuing.")
    for index in range(len(record["legs"])):
        leg = record["legs"][index]
        if leg["payload"]["transaction_type"] != "SELL" or leg["status"] != "NOT_SUBMITTED":
            continue
        validator(record, "SELL")  # fresh risk approval before EACH short, including condors
        if record["mode"] == "LIVE":
            positions = broker.get_positions().get("net") or []
            orders = broker.get_orders()
            for hedge in (item for item in record["legs"] if item["payload"]["transaction_type"] == "BUY"):
                symbol = hedge["payload"]["tradingsymbol"]
                coverage = sum(int(row.get("quantity") or 0) for row in positions
                               if row.get("tradingsymbol") == symbol and row.get("product") == "NRML"
                               and row.get("exchange") == "NFO")
                if coverage < hedge["filled"] or any(
                        order.get("tradingsymbol") == symbol and order.get("transaction_type") == "SELL"
                        and order.get("status") not in {"COMPLETE", "CANCELLED", "REJECTED"} for order in orders):
                    raise PermissionError("Hedge coverage is missing or reserved for disposal.")
        leg["status"] = "SUBMITTING"
        record["state"] = "SHORT_PENDING"
        record = repo.save(record)  # compare-and-swap prevents duplicate concurrent SELL
        _basket_order(record, record["legs"][index], broker)
        record = repo.save(record)
        if record["legs"][index]["status"] == "SUBMISSION_UNKNOWN":
            break
    return record


@tracked("trade_protected_execution:submit_basket_exit", boundary="submit_basket_exit")
def submit_basket_exit(repo, account, eid, broker, validator, prices, acknowledged=False, close_hedges=False):
    """Close shorts first. Separate confirmation disposes hedges only after fills."""
    if not acknowledged:
        raise PermissionError("Explicit exit confirmation is required.")
    record = reconcile_basket(repo, account, eid, broker)
    required = {"SHORT_CLOSED_HEDGE_OPEN"} if close_hedges else {"OPEN", "HEDGE_FILLED", "RECOVERY_READY", "EXIT_RECOVERY_READY"}
    if record["state"] not in required:
        raise PermissionError("Reconcile all entry/close fills before this exit stage.")
    validator(record, "EXIT_HEDGES" if close_hedges else "EXIT_SHORTS")
    if not record.get("exit_legs"):
        exits = []
        for index, leg in enumerate(record["legs"]):
            if not leg["filled"]:
                continue
            original = leg["payload"]
            side = "BUY" if original["transaction_type"] == "SELL" else "SELL"
            price = float(prices.get(original["tradingsymbol"], 0))
            if not math.isfinite(price) or price <= 0:
                raise PermissionError("Fresh executable exit prices required for every leg.")
            exits.append(dict(payload={**original, "transaction_type": side, "quantity": leg["filled"], "price": price},
                              tag="NX" + eid[:15] + str(index), order_id="", status="NOT_SUBMITTED", filled=0, average=0))
        record["exit_legs"] = exits
        record = repo.save(record)
    target_side = "SELL" if close_hedges else "BUY"
    # A filled hedge with no shorts is an explicit orphan cleanup action.
    if not any(leg["filled"] for leg in record["legs"] if leg["payload"]["transaction_type"] == "SELL"):
        target_side = "SELL"
    # A new explicit action may replace only terminal failed exits. Keep every
    # original order/fill for accounting and submit only the remaining quantity.
    for entry in record["legs"]:
        original = entry["payload"]
        closing_side = "BUY" if original["transaction_type"] == "SELL" else "SELL"
        remaining = basket_remaining(record, entry)
        if closing_side != target_side or remaining <= 0:
            continue
        attempts = [leg for leg in record["exit_legs"] if leg["payload"]["tradingsymbol"] == original["tradingsymbol"]]
        if any(leg["status"] == "NOT_SUBMITTED" for leg in attempts):
            continue
        if any(leg["status"] not in {"COMPLETE", "REJECTED", "CANCELLED"} for leg in attempts):
            raise PermissionError("An exit is still pending or uncertain; reconcile before recovery.")
        price = float(prices.get(original["tradingsymbol"], 0))
        if not math.isfinite(price) or price <= 0:
            raise PermissionError("Fresh executable recovery price required.")
        record["exit_legs"].append(dict(
            payload={**original, "transaction_type": closing_side, "quantity": remaining, "price": price},
            tag="NR" + eid[:15] + format(len(record["exit_legs"]), "x"),
            order_id="", status="NOT_SUBMITTED", filled=0, average=0))
    record = repo.save(record)
    for index, leg in enumerate(record["exit_legs"]):
        if leg["payload"]["transaction_type"] != target_side or leg["status"] != "NOT_SUBMITTED":
            continue
        price = float(prices.get(leg["payload"]["tradingsymbol"], 0))
        if not math.isfinite(price) or price <= 0:
            raise PermissionError("Fresh executable closing price required.")
        leg["payload"]["price"] = price
        leg["status"] = "SUBMITTING"
        record["state"] = "EXIT_PENDING"
        record = repo.save(record)
        _basket_order(record, record["exit_legs"][index], broker)
        record = repo.save(record)
        if record["exit_legs"][index]["status"] == "SUBMISSION_UNKNOWN":
            break
    return record
