"""SQLite repository for Kite spread watchlist and pair orders."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kite_spread_config as spread_cfg


def default_db_path() -> Path:
    return Path(__file__).resolve().with_name("vikalp_income.db")


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class KiteSpreadRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kite_spread_watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    company_name TEXT,
                    source TEXT NOT NULL,
                    is_current_holding INTEGER NOT NULL DEFAULT 0,
                    holding_qty REAL NOT NULL DEFAULT 0,
                    fno_enabled INTEGER NOT NULL DEFAULT 1,
                    active INTEGER NOT NULL DEFAULT 1,
                    gpt_view TEXT,
                    gpt_reason TEXT,
                    event_risk_flag INTEGER NOT NULL DEFAULT 0,
                    result_event_date TEXT,
                    sector_event_flag INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_gpt_review_date TEXT,
                    UNIQUE(symbol, source)
                );

                CREATE TABLE IF NOT EXISTS kite_pair_orders (
                    pair_id TEXT PRIMARY KEY,
                    strategy_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    expiry TEXT NOT NULL,
                    lots INTEGER NOT NULL,
                    lot_size INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    sell_leg_tradingsymbol TEXT,
                    buy_leg_tradingsymbol TEXT,
                    sell_leg_order_id TEXT,
                    buy_leg_order_id TEXT,
                    sell_leg_status TEXT,
                    buy_leg_status TEXT,
                    pair_status TEXT NOT NULL,
                    net_credit_expected REAL,
                    net_credit_actual REAL,
                    max_gain REAL,
                    max_loss REAL,
                    breakeven REAL,
                    pop_estimate REAL,
                    risk_decision TEXT,
                    user_confirmed INTEGER NOT NULL DEFAULT 0,
                    mode TEXT NOT NULL DEFAULT 'PAPER',
                    execution_mode TEXT NOT NULL DEFAULT 'HEDGE_FIRST',
                    sell_leg_placed INTEGER NOT NULL DEFAULT 0,
                    sell_leg_modified_at TEXT,
                    buy_leg_modified_at TEXT,
                    one_leg_filled_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_checked_at TEXT
                );

                CREATE TABLE IF NOT EXISTS kite_pair_execution_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair_id TEXT,
                    action TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def upsert_watchlist(self, symbol: str, company_name: str = "", source: str = "MANUAL", **kwargs: Any) -> int:
        clean = str(symbol or "").strip().upper()
        if not clean:
            raise ValueError("Symbol is required.")
        stamp = now_text()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO kite_spread_watchlist(
                    symbol, company_name, source, is_current_holding, holding_qty,
                    fno_enabled, active, gpt_view, gpt_reason, event_risk_flag,
                    result_event_date, sector_event_flag, created_at, updated_at, last_gpt_review_date
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, source) DO UPDATE SET
                    company_name = excluded.company_name,
                    is_current_holding = excluded.is_current_holding,
                    holding_qty = excluded.holding_qty,
                    fno_enabled = excluded.fno_enabled,
                    active = 1,
                    gpt_view = excluded.gpt_view,
                    gpt_reason = excluded.gpt_reason,
                    event_risk_flag = excluded.event_risk_flag,
                    result_event_date = excluded.result_event_date,
                    sector_event_flag = excluded.sector_event_flag,
                    updated_at = excluded.updated_at,
                    last_gpt_review_date = excluded.last_gpt_review_date
                """,
                (
                    clean,
                    company_name or clean,
                    source,
                    1 if kwargs.get("is_current_holding") else 0,
                    float(kwargs.get("holding_qty") or 0),
                    1 if kwargs.get("fno_enabled", True) else 0,
                    kwargs.get("gpt_view") or "UNKNOWN",
                    kwargs.get("gpt_reason") or "",
                    1 if kwargs.get("event_risk_flag") else 0,
                    kwargs.get("result_event_date") or "",
                    1 if kwargs.get("sector_event_flag") else 0,
                    stamp,
                    stamp,
                    stamp if source == "GPT" else "",
                ),
            )
            row = conn.execute("SELECT id FROM kite_spread_watchlist WHERE symbol=? AND source=?", (clean, source)).fetchone()
        return int(row["id"]) if row else 0

    def deactivate_watchlist(self, row_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("UPDATE kite_spread_watchlist SET active=0, updated_at=? WHERE id=?", (now_text(), int(row_id)))
        return cur.rowcount > 0

    def list_watchlist(self, active_only: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM kite_spread_watchlist"
        if active_only:
            query += " WHERE active=1"
        query += " ORDER BY is_current_holding DESC, active DESC, source, symbol"
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query).fetchall()]

    def create_pair(self, preview: dict[str, Any], mode: str = "PAPER", user_confirmed: bool = True, execution_mode: str = "HEDGE_FIRST") -> str:
        pair_id = str(preview.get("pair_id") or f"KSP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}")
        stamp = now_text()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO kite_pair_orders(
                    pair_id, strategy_type, symbol, expiry, lots, lot_size, quantity,
                    sell_leg_tradingsymbol, buy_leg_tradingsymbol, sell_leg_status,
                    buy_leg_status, pair_status, net_credit_expected, net_credit_actual,
                    max_gain, max_loss, breakeven, pop_estimate, risk_decision,
                    user_confirmed, mode, execution_mode, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pair_id, preview["strategy_type"], preview["symbol"], preview["expiry"],
                    int(preview.get("selected_lots") or preview.get("lots") or 1),
                    int(preview.get("lot_size") or 0), int(preview.get("quantity") or 0),
                    preview.get("sell_leg_tradingsymbol"), preview.get("buy_leg_tradingsymbol"),
                    "PENDING", "PENDING", "CREATED", float(preview.get("net_credit") or 0), 0,
                    float(preview.get("max_gain") or 0), float(preview.get("max_loss") or 0),
                    float(preview.get("breakeven") or 0), float(preview.get("pop_estimate") or 0),
                    preview.get("risk_decision"), 1 if user_confirmed else 0, mode, execution_mode,
                    json.dumps(preview, default=str), stamp, stamp,
                ),
            )
        self.log(pair_id, "CREATE_PAIR", f"{mode} {execution_mode}")
        return pair_id

    def update_pair(self, pair_id: str, **updates: Any) -> None:
        if not updates:
            return
        updates["updated_at"] = now_text()
        assignments = ", ".join(f"{key}=?" for key in updates)
        params = list(updates.values()) + [pair_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE kite_pair_orders SET {assignments} WHERE pair_id=?", params)

    def get_pair(self, pair_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM kite_pair_orders WHERE pair_id=?", (pair_id,)).fetchone()
        return dict(row) if row else None

    def list_pairs(self, include_closed: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM kite_pair_orders"
        if not include_closed:
            query += " WHERE pair_status NOT IN ('CLOSED','CANCELLED','FAILED','BOTH_FILLED')"
        query += " ORDER BY created_at DESC"
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query).fetchall()]

    def list_pair_orders(self, include_closed: bool = True) -> list[dict[str, Any]]:
        return self.list_pairs(include_closed=include_closed)

    def clear_pair_monitor(self) -> dict[str, int]:
        with self.connect() as conn:
            pair_count = int(conn.execute("SELECT COUNT(*) FROM kite_pair_orders").fetchone()[0])
            log_count = int(conn.execute("SELECT COUNT(*) FROM kite_pair_execution_log").fetchone()[0])
            conn.execute("DELETE FROM kite_pair_execution_log")
            conn.execute("DELETE FROM kite_pair_orders")
        return {"pair_orders_deleted": pair_count, "execution_logs_deleted": log_count}

    def log(self, pair_id: str, action: str, detail: str = "") -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO kite_pair_execution_log(pair_id, action, detail, created_at) VALUES (?, ?, ?, ?)", (pair_id, action, detail, now_text()))

    def export_outputs(self, candidates: list[dict[str, Any]] | None = None) -> None:
        out = spread_cfg.KITE_SPREAD_OUTPUT_DIR
        out.mkdir(parents=True, exist_ok=True)
        if candidates is not None:
            self._write_csv(out / "kite_spread_candidates.csv", candidates)
            self._write_csv(out / "kite_spread_preview.csv", candidates)
            self._write_csv(out / "kite_spread_rejections.csv", [row for row in candidates if row.get("risk_decision") == "BLOCKED"])
        self._write_csv(out / "kite_pair_orders.csv", self.list_pairs())
        with self.connect() as conn:
            logs = [dict(row) for row in conn.execute("SELECT * FROM kite_pair_execution_log ORDER BY id DESC LIMIT 500").fetchall()]
        self._write_csv(out / "kite_pair_execution_log.csv", logs)

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        flat = [{k: json.dumps(v, default=str) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in rows]
        headers = sorted({key for row in flat for key in row})
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(flat)
