"""Persistent state and server-side guardrails for the manual TRADE terminal."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class TradeTerminalRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS trade_watchlist (
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'MANUAL',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(account_id, symbol)
                );
                CREATE TABLE IF NOT EXISTS trade_execution_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    contract_symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    limit_price REAL NOT NULL,
                    consent_at TEXT,
                    risk_checks_json TEXT NOT NULL,
                    exit_plan TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    broker_order_id TEXT NOT NULL DEFAULT '',
                    broker_response_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_trade_audit_account_created
                    ON trade_execution_audit(account_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS trade_daily_scan (
                    account_id TEXT NOT NULL,
                    scan_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    rows_json TEXT NOT NULL,
                    PRIMARY KEY(account_id, scan_date)
                );
                CREATE TABLE IF NOT EXISTS trade_direction_snapshot (
                    account_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    analysis_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    PRIMARY KEY(account_id, symbol, analysis_date)
                );
                """
            )

    def sync_watchlist(self, account_id: str, symbols: list[str], source: str) -> None:
        self.ensure_schema()
        now = _now()
        rows = sorted({str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()})
        with self.connect() as conn:
            for symbol in rows:
                conn.execute(
                    """INSERT INTO trade_watchlist(account_id, symbol, source, active, created_at, updated_at)
                       VALUES (?, ?, ?, 1, ?, ?)
                       ON CONFLICT(account_id, symbol) DO UPDATE SET
                         active=1,
                         source=CASE WHEN trade_watchlist.source='MANUAL' THEN trade_watchlist.source ELSE excluded.source END,
                         updated_at=excluded.updated_at""",
                    (account_id, symbol, source, now, now),
                )

    def add_symbol(self, account_id: str, symbol: str) -> None:
        self.sync_watchlist(account_id, [symbol], "MANUAL")

    def symbols(self, account_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT symbol, source, updated_at FROM trade_watchlist WHERE account_id=? AND active=1 ORDER BY symbol",
                (account_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def idempotency_key(self, account_id: str, preview: dict[str, Any]) -> str:
        payload = "|".join(
            [
                account_id,
                str(preview.get("tradingsymbol") or ""),
                str(preview.get("side") or ""),
                str(preview.get("quantity") or ""),
                f"{_float(preview.get('limit_price')):.2f}",
                str(preview.get("review_nonce") or ""),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def reserve(self, account_id: str, preview: dict[str, Any], mode: str, checks: list[dict[str, Any]], exit_plan: str) -> tuple[int, str]:
        self.ensure_schema()
        key = self.idempotency_key(account_id, preview)
        now = _now()
        try:
            with self.connect() as conn:
                cursor = conn.execute(
                    """INSERT INTO trade_execution_audit(
                         account_id,idempotency_key,created_at,mode,symbol,contract_symbol,side,
                         quantity,limit_price,consent_at,risk_checks_json,exit_plan,status
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        account_id, key, now, mode, str(preview.get("symbol") or ""),
                        str(preview.get("tradingsymbol") or ""), str(preview.get("side") or ""),
                        int(preview.get("quantity") or 0), _float(preview.get("limit_price")), now,
                        json.dumps(checks, default=str), str(exit_plan or ""), "SUBMITTING",
                    ),
                )
                return int(cursor.lastrowid), key
        except sqlite3.IntegrityError as exc:
            raise PermissionError("Duplicate trade submission blocked. Refresh before trying again.") from exc

    def complete(self, audit_id: int, status: str, order_id: str, response: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE trade_execution_audit SET status=?, broker_order_id=?, broker_response_json=? WHERE id=?",
                (status, order_id, json.dumps(response, default=str), audit_id),
            )

    def recent(self, account_id: str, limit: int = 20) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trade_execution_audit WHERE account_id=? ORDER BY id DESC LIMIT ?",
                (account_id, max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_daily_scan(self, account_id: str, scan_date: str, rows: list[dict[str, Any]]) -> None:
        """Persist advisory scan output only; this never reserves or submits an order."""
        self.ensure_schema()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO trade_daily_scan(account_id, scan_date, created_at, rows_json)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(account_id, scan_date) DO UPDATE SET
                     created_at=excluded.created_at,
                     rows_json=excluded.rows_json""",
                (account_id, scan_date, _now(), json.dumps(rows, default=str)),
            )

    def daily_scan(self, account_id: str, scan_date: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT created_at, rows_json FROM trade_daily_scan WHERE account_id=? AND scan_date=?",
                (account_id, scan_date),
            ).fetchone()
        if not row:
            return None
        try:
            rows = json.loads(str(row["rows_json"] or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            rows = []
        return {"scan_date": scan_date, "created_at": row["created_at"], "rows": rows if isinstance(rows, list) else []}

    def save_direction_snapshot(self, account_id: str, symbol: str, analysis_date: str, result: dict[str, Any]) -> None:
        self.ensure_schema()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO trade_direction_snapshot(account_id, symbol, analysis_date, created_at, result_json)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(account_id, symbol, analysis_date) DO UPDATE SET
                     created_at=excluded.created_at,
                     result_json=excluded.result_json""",
                (account_id, symbol.upper(), analysis_date, _now(), json.dumps(result, default=str)),
            )

    def direction_snapshot(self, account_id: str, symbol: str, analysis_date: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT created_at, result_json FROM trade_direction_snapshot WHERE account_id=? AND symbol=? AND analysis_date=?",
                (account_id, symbol.upper(), analysis_date),
            ).fetchone()
        if not row:
            return None
        try:
            result = json.loads(str(row["result_json"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(result, dict):
            return None
        result["saved_at"] = row["created_at"]
        return result


def validation(name: str, status: str, reason: str) -> dict[str, str]:
    clean = str(status or "BLOCK").upper()
    return {"name": name, "status": clean if clean in {"PASS", "WARNING", "BLOCK"} else "BLOCK", "reason": reason}


def has_blocks(checks: list[dict[str, Any]]) -> bool:
    return any(str(item.get("status") or "").upper() == "BLOCK" for item in checks)


def score_validations(checks: list[dict[str, Any]]) -> tuple[float, str]:
    """Score each validation equally while preserving fail-closed hard blocks."""
    if not checks:
        return 0.0, "DO NOT PLACE"
    points = {"PASS": 100.0, "WARNING": 50.0, "BLOCK": 0.0}
    score = round(
        sum(points.get(str(item.get("status") or "BLOCK").upper(), 0.0) for item in checks)
        / len(checks),
        1,
    )
    if has_blocks(checks):
        return score, "DO NOT PLACE"
    return score, "ELIGIBLE TO PLACE" if score >= 75 else "PLACE WITH CAUTION"

