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

                CREATE TABLE IF NOT EXISTS kite_spread_opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    screen_name TEXT NOT NULL DEFAULT 'DHAN',
                    row_index INTEGER NOT NULL,
                    symbol TEXT,
                    strategy_type TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    generated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS dhan_fno_sheet_import_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_file_name TEXT,
                    generated_at TEXT,
                    ce_rows_read INTEGER NOT NULL DEFAULT 0,
                    pe_rows_read INTEGER NOT NULL DEFAULT 0,
                    rows_after_basic_filter INTEGER NOT NULL DEFAULT 0,
                    rows_after_sheet_score INTEGER NOT NULL DEFAULT 0,
                    rows_after_live_validation INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS dhan_fno_top10_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    rank INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    source_tab TEXT,
                    dhan_strategy TEXT,
                    sheet_score REAL,
                    dhan_evaluation_score REAL,
                    final_score REAL,
                    recommended_expiry TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    selected_for_watchlist INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES dhan_fno_sheet_import_runs(id)
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

    def save_dhan_fno_top10_run(self, result: dict[str, Any]) -> int:
        stamp = now_text()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO dhan_fno_sheet_import_runs(
                    source_file_name, generated_at, ce_rows_read, pe_rows_read,
                    rows_after_basic_filter, rows_after_sheet_score,
                    rows_after_live_validation, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.get("source_file_name") or "",
                    result.get("generated_at") or stamp,
                    int(result.get("ce_rows_read") or 0),
                    int(result.get("pe_rows_read") or 0),
                    int(result.get("rows_after_basic_filter") or 0),
                    int(result.get("rows_after_sheet_score") or 0),
                    int(result.get("rows_after_live_validation") or 0),
                    stamp,
                ),
            )
            run_id = int(cur.lastrowid)
            for row in result.get("top10") or []:
                conn.execute(
                    """
                    INSERT INTO dhan_fno_top10_candidates(
                        run_id, rank, symbol, source_tab, dhan_strategy, sheet_score,
                        dhan_evaluation_score, final_score, recommended_expiry,
                        payload_json, selected_for_watchlist, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        run_id,
                        int(row.get("rank") or 0),
                        str(row.get("symbol") or "").upper(),
                        row.get("source_tab") or "",
                        row.get("dhan_strategy") or "",
                        float(row.get("sheet_score") or row.get("final_sheet_score") or 0),
                        float(row.get("dhan_evaluation_score") or 0),
                        float(row.get("final_score") or 0),
                        row.get("recommended_expiry") or "",
                        json.dumps(row, default=str),
                        stamp,
                    ),
                )
        return run_id

    def latest_dhan_fno_top10_run(self) -> dict[str, Any]:
        with self.connect() as conn:
            run = conn.execute("SELECT * FROM dhan_fno_sheet_import_runs ORDER BY id DESC LIMIT 1").fetchone()
            if not run:
                return {}
            rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM dhan_fno_top10_candidates WHERE run_id=? ORDER BY rank, id",
                    (int(run["id"]),),
                ).fetchall()
            ]
        candidates = []
        for row in rows:
            payload = json.loads(row.get("payload_json") or "{}")
            payload["candidate_id"] = row["id"]
            payload["selected_for_watchlist"] = row["selected_for_watchlist"]
            candidates.append(payload)
        out = dict(run)
        out["top10"] = candidates
        return out

    def add_dhan_fno_top10_to_watchlist(self, candidate_ids: list[int]) -> dict[str, int]:
        if not candidate_ids:
            return {"added": 0, "updated": 0, "missing": 0}
        added = 0
        updated = 0
        missing = 0
        with self.connect() as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    f"SELECT * FROM dhan_fno_top10_candidates WHERE id IN ({','.join('?' for _ in candidate_ids)})",
                    [int(item) for item in candidate_ids],
                ).fetchall()
            ]
            by_id = {int(row["id"]): row for row in rows}
            for candidate_id in candidate_ids:
                row = by_id.get(int(candidate_id))
                if not row:
                    missing += 1
                    continue
                payload = json.loads(row.get("payload_json") or "{}")
                symbol = str(row.get("symbol") or payload.get("symbol") or "").upper()
                existed = conn.execute(
                    "SELECT 1 FROM kite_spread_watchlist WHERE symbol=? AND source='FNO_SHEET'",
                    (symbol,),
                ).fetchone()
                reason = (
                    f"{payload.get('trader_comment') or 'F&O sheet Top 10 candidate'} "
                    f"| source {payload.get('source_file_name') or ''} | score {payload.get('final_score') or row.get('final_score')}"
                )
                conn.execute(
                    """
                    INSERT INTO kite_spread_watchlist(
                        symbol, company_name, source, is_current_holding, holding_qty,
                        fno_enabled, active, gpt_view, gpt_reason, event_risk_flag,
                        result_event_date, sector_event_flag, created_at, updated_at, last_gpt_review_date
                    ) VALUES (?, ?, 'FNO_SHEET', 0, 0, 1, 1, ?, ?, ?, '', 0, ?, ?, '')
                    ON CONFLICT(symbol, source) DO UPDATE SET
                        company_name=excluded.company_name,
                        active=1,
                        gpt_view=excluded.gpt_view,
                        gpt_reason=excluded.gpt_reason,
                        event_risk_flag=excluded.event_risk_flag,
                        updated_at=excluded.updated_at
                    """,
                    (
                        symbol,
                        payload.get("company_name") or symbol,
                        "CE_SELL" if row.get("dhan_strategy") == "BEAR_CALL_SPREAD" else "PE_SELL",
                        reason,
                        1 if payload.get("event_risk_flag") else 0,
                        now_text(),
                        now_text(),
                    ),
                )
                conn.execute("UPDATE dhan_fno_top10_candidates SET selected_for_watchlist=1 WHERE id=?", (int(candidate_id),))
                updated += 1 if existed else 0
                added += 0 if existed else 1
        return {"added": added, "updated": updated, "missing": missing}

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

    def save_opportunities(self, opportunities: list[dict[str, Any]], generated_at: str = "", screen_name: str = "DHAN") -> int:
        stamp = generated_at or now_text()
        now = now_text()
        clean_screen = str(screen_name or "DHAN").strip().upper()
        with self.connect() as conn:
            conn.execute("DELETE FROM kite_spread_opportunities WHERE screen_name=?", (clean_screen,))
            for idx, row in enumerate(opportunities):
                conn.execute(
                    """
                    INSERT INTO kite_spread_opportunities(
                        screen_name, row_index, symbol, strategy_type, payload_json,
                        generated_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clean_screen,
                        idx,
                        str(row.get("symbol") or "").strip().upper(),
                        str(row.get("strategy_type") or ""),
                        json.dumps(row, default=str),
                        stamp,
                        now,
                        now,
                    ),
                )
        return len(opportunities)

    def list_opportunities(self, screen_name: str = "DHAN") -> tuple[list[dict[str, Any]], str]:
        clean_screen = str(screen_name or "DHAN").strip().upper()
        with self.connect() as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT payload_json, generated_at
                    FROM kite_spread_opportunities
                    WHERE screen_name=?
                    ORDER BY row_index, id
                    """,
                    (clean_screen,),
                ).fetchall()
            ]
        opportunities: list[dict[str, Any]] = []
        generated_at = ""
        for row in rows:
            if not generated_at:
                generated_at = str(row.get("generated_at") or "")
            try:
                parsed = json.loads(str(row.get("payload_json") or "{}"))
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                opportunities.append(parsed)
        return opportunities, generated_at

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
            self._write_csv(out / "kite_spread_expiry_comparison.csv", self._expiry_comparison_rows(candidates))
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

    def _expiry_comparison_rows(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        timestamp = now_text()
        for candidate in candidates:
            for expiry_type, month_key in (("CURRENT_MONTH", "current_month"), ("NEXT_MONTH", "next_month")):
                month = candidate.get(month_key)
                if not isinstance(month, dict) or not month.get("expiry"):
                    continue
                rows.append(
                    {
                        "timestamp": timestamp,
                        "symbol": candidate.get("symbol"),
                        "strategy_type": candidate.get("strategy_type"),
                        "expiry_type": expiry_type,
                        "expiry": month.get("expiry"),
                        "dte": month.get("dte"),
                        "sell_leg": month.get("sell_leg_tradingsymbol"),
                        "buy_leg": month.get("buy_leg_tradingsymbol"),
                        "net_credit": month.get("net_credit"),
                        "max_gain": month.get("max_gain"),
                        "max_loss": month.get("max_loss"),
                        "breakeven": month.get("breakeven"),
                        "pop": month.get("pop"),
                        "return_on_risk_pct": month.get("return_on_risk_pct"),
                        "margin_required": month.get("margin_required"),
                        "risk_decision": month.get("risk_decision"),
                        "risk_reason": month.get("risk_reason"),
                    }
                )
        return rows
