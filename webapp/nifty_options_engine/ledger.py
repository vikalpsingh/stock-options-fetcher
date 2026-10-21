"""Persistent strategy ownership using the application's existing SQLite database.

This repository never calls a broker. Order IDs are registered by the execution
service, and only fills for those IDs can be attributed automatically.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from .reconciliation import finite_number, normalize_leg, reconcile_nifty_positions


def _now():
    return datetime.now(timezone.utc).isoformat()


class NiftyStrategyRepository:
    def __init__(self, db_path):
        self.db_path = Path(db_path)

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def ensure_schema(self):
        """Additive migration only; existing application tables are untouched."""
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS nifty_strategies (
                    strategy_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    request_key TEXT NOT NULL,
                    strategy_type TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK(mode IN ('PAPER','LIVE')),
                    created_at TEXT NOT NULL,
                    UNIQUE(account_id, request_key)
                );
                CREATE TABLE IF NOT EXISTS nifty_strategy_legs (
                    leg_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL REFERENCES nifty_strategies(strategy_id),
                    tradingsymbol TEXT NOT NULL,
                    entry_side TEXT NOT NULL CHECK(entry_side IN ('BUY','SELL')),
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    metadata TEXT NOT NULL,
                    UNIQUE(strategy_id, tradingsymbol)
                );
                CREATE TABLE IF NOT EXISTS nifty_order_events (
                    account_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    leg_id TEXT NOT NULL REFERENCES nifty_strategy_legs(leg_id),
                    purpose TEXT NOT NULL CHECK(purpose IN ('ENTRY','EXIT')),
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(account_id, order_id)
                );
                CREATE TABLE IF NOT EXISTS nifty_fills (
                    account_id TEXT NOT NULL,
                    trade_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    price REAL NOT NULL CHECK(price >= 0),
                    fees REAL,
                    filled_at TEXT NOT NULL,
                    PRIMARY KEY(account_id, trade_id),
                    FOREIGN KEY(account_id, order_id)
                      REFERENCES nifty_order_events(account_id, order_id)
                );
            """)

    def create_strategy(self, account_id, request_key, strategy_type, legs, mode="PAPER"):
        if (not account_id or not request_key or mode not in {"PAPER", "LIVE"}
                or strategy_type not in {"BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "IRON_CONDOR"}):
            raise ValueError("Account, request key, supported strategy and explicit mode required.")
        if len(legs) != (4 if strategy_type == "IRON_CONDOR" else 2):
            raise ValueError("A protected strategy requires two or four verified legs.")
        cleaned = []
        for raw in legs:
            leg = normalize_leg(raw)
            side = str(raw.get("transaction_type") or "").upper()
            lot = finite_number(raw.get("lot_size"))
            if (not leg["valid"] or not raw.get("instrument_token") or not lot or lot <= 0
                    or leg["quantity"] <= 0 or leg["quantity"] % lot
                    or side not in {"BUY", "SELL"} or not leg["tradingsymbol"]
                    or str(raw.get("product") or "NRML") != "NRML"):
                raise ValueError("Each leg requires verified instrument metadata, lot size and quantity.")
            cleaned.append({**raw, **leg, "transaction_type": side, "product": "NRML"})
        # Validate ownership/geometry without inventing quote or fill prices.
        geometry = reconcile_nifty_positions([
            {**leg, "strategy_id": "TICKET", "account_id": account_id,
             "quantity": leg["quantity"] * (-1 if leg["transaction_type"] == "SELL" else 1)}
            for leg in cleaned
        ])
        short_types = {leg["option_type"] for leg in cleaned if leg["transaction_type"] == "SELL"}
        expected_types = {"PE", "CE"} if strategy_type == "IRON_CONDOR" else {
            "PE" if strategy_type == "BULL_PUT_SPREAD" else "CE"}
        if geometry["block_new_entries"] or short_types != expected_types:
            raise ValueError("Legs do not form a fully protected same-expiry strategy.")
        cleaned = json.loads(json.dumps(cleaned, default=str))
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute(
                "SELECT * FROM nifty_strategies WHERE account_id=? AND request_key=?",
                (account_id, request_key)).fetchone()
            if prior:
                existing = conn.execute(
                    "SELECT metadata FROM nifty_strategy_legs WHERE strategy_id=? ORDER BY tradingsymbol",
                    (prior["strategy_id"],)).fetchall()
                canonical = sorted(cleaned, key=lambda row: row["tradingsymbol"])
                if (prior["strategy_type"] != strategy_type or prior["mode"] != mode
                        or [json.loads(row["metadata"]) for row in existing] != canonical):
                    raise ValueError("Request key already belongs to a different ticket.")
                return prior["strategy_id"]
            strategy_id = uuid.uuid4().hex
            conn.execute("INSERT INTO nifty_strategies VALUES (?,?,?,?,?,?)",
                         (strategy_id, account_id, request_key, strategy_type, mode, _now()))
            for leg in cleaned:
                conn.execute("INSERT INTO nifty_strategy_legs VALUES (?,?,?,?,?,?)",
                             (uuid.uuid4().hex, strategy_id, leg["tradingsymbol"],
                              leg["transaction_type"], int(leg["quantity"]), json.dumps(leg, default=str)))
        return strategy_id

    def register_order(self, account_id, strategy_id, symbol, order_id, purpose="ENTRY"):
        if not order_id or purpose not in {"ENTRY", "EXIT"}:
            raise ValueError("A broker/simulated order ID and explicit purpose are required.")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            leg = conn.execute("""
                SELECT l.* FROM nifty_strategy_legs l JOIN nifty_strategies s USING(strategy_id)
                WHERE s.account_id=? AND s.strategy_id=? AND l.tradingsymbol=?
            """, (account_id, strategy_id, symbol)).fetchone()
            if not leg:
                raise ValueError("Leg not owned by this account and strategy.")
            prior = conn.execute("SELECT * FROM nifty_order_events WHERE account_id=? AND order_id=?",
                                 (account_id, order_id)).fetchone()
            if prior:
                if prior["leg_id"] != leg["leg_id"] or prior["purpose"] != purpose:
                    raise ValueError("Order is already allocated elsewhere.")
                return
            conn.execute("INSERT INTO nifty_order_events VALUES (?,?,?,?,?)",
                         (account_id, order_id, leg["leg_id"], purpose, _now()))

    def record_fill(self, account_id, fill):
        """Import a broker-confirmed fill idempotently; never manufacture a fill."""
        qty, price, fees = (finite_number(fill.get(key)) for key in ("quantity", "price", "fees"))
        if (not fill.get("trade_id") or not fill.get("order_id") or not fill.get("filled_at")
                or qty is None or qty <= 0 or not qty.is_integer() or price is None or price < 0
                or (fill.get("fees") is not None and (fees is None or fees < 0))):
            raise ValueError("Confirmed fill ID, order ID, time, quantity and price required.")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            order = conn.execute("""
                SELECT e.*, l.tradingsymbol, l.entry_side FROM nifty_order_events e
                JOIN nifty_strategy_legs l USING(leg_id) WHERE e.account_id=? AND e.order_id=?
            """, (account_id, fill["order_id"])).fetchone()
            if not order:
                raise ValueError("UNMATCHED fill: review ownership before importing.")
            side = order["entry_side"] if order["purpose"] == "ENTRY" else (
                "SELL" if order["entry_side"] == "BUY" else "BUY")
            if fill.get("tradingsymbol") != order["tradingsymbol"] or fill.get("transaction_type") != side:
                raise ValueError("Fill contract/side conflicts with registered order.")
            values = (account_id, str(fill["trade_id"]), str(fill["order_id"]), int(qty), price, fees,
                      str(fill["filled_at"]))
            prior = conn.execute("SELECT * FROM nifty_fills WHERE account_id=? AND trade_id=?",
                                 values[:2]).fetchone()
            if prior:
                if tuple(prior) != values:
                    raise ValueError("Conflicting duplicate broker trade ID.")
                return False
            conn.execute("INSERT INTO nifty_fills VALUES (?,?,?,?,?,?,?)", values)
        return True

    def position_allocations(self, account_id, mode="LIVE"):
        """Return open quantities from actual fills, separated by paper/live mode."""
        with self.connect() as conn:
            rows = conn.execute("""
                SELECT l.*, s.account_id FROM nifty_strategy_legs l
                JOIN nifty_strategies s USING(strategy_id) WHERE s.account_id=? AND s.mode=?
            """, (account_id, mode)).fetchall()
            output = []
            for leg in rows:
                fills = conn.execute("""
                    SELECT f.*, e.purpose FROM nifty_fills f
                    JOIN nifty_order_events e USING(account_id, order_id)
                    WHERE e.account_id=? AND e.leg_id=? ORDER BY f.filled_at, f.trade_id
                """, (account_id, leg["leg_id"])).fetchall()
                entries = [row for row in fills if row["purpose"] == "ENTRY"]
                exits = [row for row in fills if row["purpose"] == "EXIT"]
                entered = sum(row["quantity"] for row in entries)
                exited = sum(row["quantity"] for row in exits)
                remaining = entered - exited
                invalid = remaining < 0 or entered > leg["quantity"]
                if remaining or invalid:
                    output.append({
                        **json.loads(leg["metadata"]), "account_id": account_id,
                        "strategy_id": leg["strategy_id"], "allocation_id": leg["leg_id"],
                        "fill_ids": [row["trade_id"] for row in fills],
                        "quantity": remaining * (1 if leg["entry_side"] == "BUY" else -1),
                        "average_price": (sum(row["price"] * row["quantity"] for row in entries) / entered
                                          if entered else None),
                        "reconciliation_error": invalid,
                    })
            return output


    def strategies(self, account_id, mode="PAPER"):
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM nifty_strategies WHERE account_id=? AND mode=? ORDER BY created_at DESC",
                                (account_id, mode)).fetchall()
            result = []
            for row in rows:
                strategy = dict(row)
                strategy["legs"] = []
                for raw in conn.execute("SELECT * FROM nifty_strategy_legs WHERE strategy_id=?", (row["strategy_id"],)):
                    leg = {**dict(raw), **json.loads(raw["metadata"])}
                    leg["fills"] = [dict(fill) for fill in conn.execute("""
                        SELECT f.*, e.purpose FROM nifty_fills f JOIN nifty_order_events e USING(account_id, order_id)
                        WHERE e.account_id=? AND e.leg_id=? ORDER BY f.filled_at, f.trade_id
                    """, (account_id, raw["leg_id"]))]
                    strategy["legs"].append(leg)
                result.append(strategy)
            return result
