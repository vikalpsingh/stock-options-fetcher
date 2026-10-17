"""Persistent monthly P&L risk control and central order gate.

This module is deliberately broker-agnostic.  It reads the application's local
SQLite P&L data and returns structured allow/block decisions.  New risk fails
closed when a persisted hard lock exists or the risk state cannot be loaded.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


DEFAULT_MONTHLY_MAX_LOSS = 200_000.0
DEFAULT_ACCOUNT_ID = "DEFAULT"

RISK_INCREASING = "RISK_INCREASING"
RISK_REDUCING = "RISK_REDUCING"
RISK_NEUTRAL = "RISK_NEUTRAL"
PROTECTIVE_HEDGE = "PROTECTIVE_HEDGE"
UNKNOWN = "UNKNOWN"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def month_key(day: date | None = None) -> str:
    return (day or date.today()).strftime("%Y-%m")


@dataclass(frozen=True)
class MonthlyRiskConfig:
    account_id: str = DEFAULT_ACCOUNT_ID
    monthly_max_loss_inr: float = DEFAULT_MONTHLY_MAX_LOSS
    warning_percent: float = 50.0
    reduce_risk_percent: float = 75.0
    hard_stop_percent: float = 100.0
    giveback_warning_percent: float = 30.0
    giveback_reduce_percent: float = 40.0
    giveback_lock_percent: float = 60.0
    loss_streak_threshold: int = 2
    cooldown_minutes: int = 30
    enabled: bool = True


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    risk_change: str
    risk_state: str
    reason: str
    account_id: str
    month_key: str
    booked_pnl: float
    risk_mtd_pnl: float
    monthly_loss_limit: float
    remaining_loss_budget: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MonthlyRiskRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS monthly_risk_config (
                    account_id TEXT PRIMARY KEY,
                    monthly_max_loss_inr REAL NOT NULL DEFAULT 200000,
                    warning_percent REAL NOT NULL DEFAULT 50,
                    reduce_risk_percent REAL NOT NULL DEFAULT 75,
                    hard_stop_percent REAL NOT NULL DEFAULT 100,
                    giveback_warning_percent REAL NOT NULL DEFAULT 30,
                    giveback_reduce_percent REAL NOT NULL DEFAULT 40,
                    giveback_lock_percent REAL NOT NULL DEFAULT 60,
                    loss_streak_threshold INTEGER NOT NULL DEFAULT 2,
                    cooldown_minutes INTEGER NOT NULL DEFAULT 30,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS monthly_risk_ledger (
                    month_key TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    booked_pnl REAL NOT NULL DEFAULT 0,
                    unrealised_pnl REAL NOT NULL DEFAULT 0,
                    risk_mtd_pnl REAL NOT NULL DEFAULT 0,
                    peak_month_pnl REAL NOT NULL DEFAULT 0,
                    giveback_amount REAL NOT NULL DEFAULT 0,
                    giveback_percent REAL NOT NULL DEFAULT 0,
                    max_monthly_loss REAL NOT NULL DEFAULT 200000,
                    loss_used REAL NOT NULL DEFAULT 0,
                    remaining_loss_budget REAL NOT NULL DEFAULT 200000,
                    risk_utilisation_percent REAL NOT NULL DEFAULT 0,
                    risk_state TEXT NOT NULL DEFAULT 'GREEN',
                    hard_locked INTEGER NOT NULL DEFAULT 0,
                    hard_lock_timestamp TEXT,
                    data_status TEXT NOT NULL DEFAULT 'LOCAL_LEDGER',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(month_key, account_id)
                );
                CREATE TABLE IF NOT EXISTS monthly_risk_event_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_at TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    month_key TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    symbol TEXT,
                    strategy TEXT,
                    risk_change TEXT,
                    order_details_json TEXT NOT NULL DEFAULT '{}',
                    monthly_booked_pnl REAL NOT NULL DEFAULT 0,
                    monthly_risk_pnl REAL NOT NULL DEFAULT 0,
                    monthly_loss_limit REAL NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL,
                    user_action TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_monthly_risk_event_account
                    ON monthly_risk_event_log(account_id, event_at);
                """
            )

    def get_config(self, account_id: str = DEFAULT_ACCOUNT_ID) -> MonthlyRiskConfig:
        self.ensure_schema()
        account = str(account_id or DEFAULT_ACCOUNT_ID)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM monthly_risk_config WHERE account_id=?", (account,)
            ).fetchone()
            if not row:
                cfg = MonthlyRiskConfig(account_id=account)
                self.save_config(cfg)
                return cfg
        data = dict(row)
        data["enabled"] = bool(data.get("enabled"))
        data.pop("updated_at", None)
        return MonthlyRiskConfig(**data)

    def save_config(self, config: MonthlyRiskConfig) -> MonthlyRiskConfig:
        self.ensure_schema()
        if config.monthly_max_loss_inr <= 0:
            raise ValueError("Monthly maximum loss must be greater than zero.")
        if not (0 <= config.warning_percent <= config.reduce_risk_percent <= config.hard_stop_percent):
            raise ValueError("Risk thresholds must be ordered warning <= reduce <= hard stop.")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO monthly_risk_config VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    monthly_max_loss_inr=excluded.monthly_max_loss_inr,
                    warning_percent=excluded.warning_percent,
                    reduce_risk_percent=excluded.reduce_risk_percent,
                    hard_stop_percent=excluded.hard_stop_percent,
                    giveback_warning_percent=excluded.giveback_warning_percent,
                    giveback_reduce_percent=excluded.giveback_reduce_percent,
                    giveback_lock_percent=excluded.giveback_lock_percent,
                    loss_streak_threshold=excluded.loss_streak_threshold,
                    cooldown_minutes=excluded.cooldown_minutes,
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at
                """,
                (
                    config.account_id, config.monthly_max_loss_inr,
                    config.warning_percent, config.reduce_risk_percent,
                    config.hard_stop_percent, config.giveback_warning_percent,
                    config.giveback_reduce_percent, config.giveback_lock_percent,
                    int(config.loss_streak_threshold), int(config.cooldown_minutes),
                    int(config.enabled), _now(),
                ),
            )
        return config

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        return bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone())

    def calculate_booked_pnl(self, account_id: str, key: str) -> tuple[float, str]:
        """Use the most authoritative available local realised-P&L ledger once."""
        self.ensure_schema()
        with self.connect() as conn:
            if self._table_exists(conn, "pnl_kite_monthly"):
                imported = conn.execute(
                    "SELECT net_realized_pnl FROM pnl_kite_monthly WHERE account_id=? AND month_key=?",
                    (account_id, key),
                ).fetchone()
                if imported:
                    return round(_float(imported["net_realized_pnl"]), 2), "KITE_PNL_IMPORT"
            if self._table_exists(conn, "closed_trade_pnl"):
                count = conn.execute(
                    "SELECT COUNT(*) FROM closed_trade_pnl WHERE account_id=? AND month_key=?",
                    (account_id, key),
                ).fetchone()[0]
                if count:
                    value = conn.execute(
                        "SELECT COALESCE(SUM(net_realised_pnl),0) FROM closed_trade_pnl WHERE account_id=? AND month_key=?",
                        (account_id, key),
                    ).fetchone()[0]
                    return round(_float(value), 2), "CLOSED_TRADE_LEDGER"
            if self._table_exists(conn, "booked_pnl"):
                columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(booked_pnl)").fetchall()}
                if "account_id" in columns:
                    value = conn.execute(
                        "SELECT COALESCE(SUM(pnl),0) FROM booked_pnl WHERE account_id=? AND month_key=?",
                        (account_id, key),
                    ).fetchone()[0]
                    return round(_float(value), 2), "BOOKED_PNL_LEDGER"
                if account_id == DEFAULT_ACCOUNT_ID:
                    value = conn.execute(
                        "SELECT COALESCE(SUM(pnl),0) FROM booked_pnl WHERE month_key=?", (key,)
                    ).fetchone()[0]
                    return round(_float(value), 2), "BOOKED_PNL_LEDGER_LEGACY_ACCOUNT"
            if self._table_exists(conn, "pnl_account_daily_summary"):
                summary_row = conn.execute(
                    """SELECT COUNT(*) AS row_count,
                              COALESCE(SUM(net_realized_pnl),0) AS pnl
                       FROM pnl_account_daily_summary
                       WHERE account_id=? AND substr(trade_date,1,7)=?""",
                    (account_id, key),
                ).fetchone()
                if summary_row and int(summary_row["row_count"] or 0) > 0:
                    return round(_float(summary_row["pnl"]), 2), "ACCOUNT_DAILY_SUMMARY"
            if self._table_exists(conn, "pnl_daily_snapshot"):
                value = conn.execute(
                    "SELECT COALESCE(SUM(net_realized_pnl),0) FROM pnl_daily_snapshot WHERE account_id=? AND substr(trade_date,1,7)=?",
                    (account_id, key),
                ).fetchone()[0]
                return round(_float(value), 2), "DAILY_SNAPSHOT_FALLBACK"
        return 0.0, "NO_REALISED_DATA"

    def calculate_unrealised_pnl(self, account_id: str) -> tuple[float, str]:
        self.ensure_schema()
        with self.connect() as conn:
            if not self._table_exists(conn, "pnl_daily_snapshot"):
                return 0.0, "NO_OPEN_PNL_DATA"
            latest = conn.execute(
                "SELECT MAX(trade_date) FROM pnl_daily_snapshot WHERE account_id=?", (account_id,)
            ).fetchone()[0]
            if not latest:
                return 0.0, "NO_OPEN_PNL_DATA"
            value = conn.execute(
                "SELECT COALESCE(SUM(unrealized_pnl),0) FROM pnl_daily_snapshot WHERE account_id=? AND trade_date=?",
                (account_id, latest),
            ).fetchone()[0]
        return round(_float(value), 2), f"POSITION_SNAPSHOT:{latest}"

    def upsert_snapshot(self, account_id: str, day: date | None = None) -> dict[str, Any]:
        cfg = self.get_config(account_id)
        key = month_key(day)
        booked, booked_source = self.calculate_booked_pnl(account_id, key)
        if key == month_key():
            unrealised, open_source = self.calculate_unrealised_pnl(account_id)
        else:
            unrealised, open_source = 0.0, "HISTORICAL_MONTH_CLOSED"
        risk_mtd = round(booked + unrealised, 2)
        now = _now()
        with self.connect() as conn:
            prior = conn.execute(
                "SELECT * FROM monthly_risk_ledger WHERE month_key=? AND account_id=?",
                (key, account_id),
            ).fetchone()
            prior_peak = _float(prior["peak_month_pnl"]) if prior else 0.0
            was_locked = bool(prior["hard_locked"]) if prior else False
            peak = max(prior_peak, risk_mtd, 0.0)
            giveback = max(0.0, peak - risk_mtd) if peak > 0 else 0.0
            giveback_pct = (giveback / peak * 100.0) if peak > 0 else 0.0
            loss_used = max(0.0, -booked)
            utilisation = loss_used / cfg.monthly_max_loss_inr * 100.0
            hard_locked = was_locked or (cfg.enabled and utilisation >= cfg.hard_stop_percent)
            state = "RED" if hard_locked else "ORANGE" if utilisation >= cfg.reduce_risk_percent else "AMBER" if utilisation >= cfg.warning_percent else "GREEN"
            remaining = max(0.0, cfg.monthly_max_loss_inr - loss_used)
            lock_at = prior["hard_lock_timestamp"] if prior else None
            if hard_locked and not lock_at:
                lock_at = now
            data_status = f"{booked_source}|{open_source}"
            conn.execute(
                """
                INSERT INTO monthly_risk_ledger(
                    month_key, account_id, booked_pnl, unrealised_pnl, risk_mtd_pnl,
                    peak_month_pnl, giveback_amount, giveback_percent, max_monthly_loss,
                    loss_used, remaining_loss_budget, risk_utilisation_percent, risk_state,
                    hard_locked, hard_lock_timestamp, data_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(month_key, account_id) DO UPDATE SET
                    booked_pnl=excluded.booked_pnl,
                    unrealised_pnl=excluded.unrealised_pnl,
                    risk_mtd_pnl=excluded.risk_mtd_pnl,
                    peak_month_pnl=excluded.peak_month_pnl,
                    giveback_amount=excluded.giveback_amount,
                    giveback_percent=excluded.giveback_percent,
                    max_monthly_loss=excluded.max_monthly_loss,
                    loss_used=excluded.loss_used,
                    remaining_loss_budget=excluded.remaining_loss_budget,
                    risk_utilisation_percent=excluded.risk_utilisation_percent,
                    risk_state=excluded.risk_state,
                    hard_locked=excluded.hard_locked,
                    hard_lock_timestamp=excluded.hard_lock_timestamp,
                    data_status=excluded.data_status,
                    updated_at=excluded.updated_at
                """,
                (key, account_id, booked, unrealised, risk_mtd, peak, giveback,
                 round(giveback_pct, 2), cfg.monthly_max_loss_inr, loss_used,
                 remaining, round(utilisation, 2), state, int(hard_locked), lock_at,
                 data_status, prior["created_at"] if prior else now, now),
            )
            row = conn.execute(
                "SELECT * FROM monthly_risk_ledger WHERE month_key=? AND account_id=?",
                (key, account_id),
            ).fetchone()
        return dict(row)

    def latest_snapshot(self, account_id: str, day: date | None = None) -> dict[str, Any]:
        return self.upsert_snapshot(str(account_id or DEFAULT_ACCOUNT_ID), day)

    def monthly_history(self, account_id: str, limit: int = 24) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM monthly_risk_ledger WHERE account_id=? ORDER BY month_key DESC LIMIT ?",
                (account_id, max(1, min(int(limit), 120))),
            ).fetchall()
        return [dict(row) for row in rows]

    def period_history(self, account_id: str, period: str) -> list[dict[str, Any]]:
        """Aggregate persisted monthly ledgers without recomputing old broker data."""
        period_name = str(period or "").strip().lower()
        if period_name not in {"quarter", "year"}:
            raise ValueError("period must be quarter or year")
        rows = list(reversed(self.monthly_history(account_id, limit=120)))
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row.get("month_key") or "")
            try:
                year, month = (int(part) for part in key.split("-", 1))
            except (TypeError, ValueError):
                continue
            label = str(year) if period_name == "year" else f"{year}-Q{((month - 1) // 3) + 1}"
            bucket = grouped.setdefault(
                label,
                {
                    "period": label,
                    "booked_pnl": 0.0,
                    "risk_pnl": 0.0,
                    "peak_month_pnl": None,
                    "months": 0,
                    "locked_months": 0,
                },
            )
            bucket["booked_pnl"] += _float(row.get("booked_pnl"))
            bucket["risk_pnl"] += _float(row.get("risk_mtd_pnl"))
            month_peak = _float(row.get("peak_month_pnl"))
            current_peak = bucket["peak_month_pnl"]
            bucket["peak_month_pnl"] = month_peak if current_peak is None else max(current_peak, month_peak)
            bucket["months"] += 1
            bucket["locked_months"] += int(bool(row.get("hard_locked")))
        return [grouped[key] for key in sorted(grouped, reverse=True)]

    def log_event(self, decision: RiskDecision, context: dict[str, Any], event_type: str) -> None:
        self.ensure_schema()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO monthly_risk_event_log(
                    event_at, account_id, month_key, event_type, severity, symbol,
                    strategy, risk_change, order_details_json, monthly_booked_pnl,
                    monthly_risk_pnl, monthly_loss_limit, reason, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (_now(), decision.account_id, decision.month_key, event_type,
                 "BLOCK" if not decision.allowed else "INFO",
                 str(context.get("tradingsymbol") or context.get("symbol") or ""),
                 str(context.get("strategy") or context.get("tag") or ""),
                 decision.risk_change, json.dumps(context, default=str, sort_keys=True),
                 decision.booked_pnl, decision.risk_mtd_pnl,
                 decision.monthly_loss_limit, decision.reason, "{}"),
            )

    def log_admin_event(
        self,
        account_id: str,
        event_type: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        snapshot = self.latest_snapshot(account_id)
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO monthly_risk_event_log(
                    event_at, account_id, month_key, event_type, severity, symbol,
                    strategy, risk_change, order_details_json, monthly_booked_pnl,
                    monthly_risk_pnl, monthly_loss_limit, reason, user_action,
                    metadata_json
                ) VALUES (?, ?, ?, ?, 'WARNING', '', '', '', '{}', ?, ?, ?, ?, ?, ?)""",
                (_now(), account_id, str(snapshot.get("month_key") or month_key()), event_type,
                 _float(snapshot.get("booked_pnl")), _float(snapshot.get("risk_mtd_pnl")),
                 _float(snapshot.get("max_monthly_loss")), reason, "ADMIN_CONFIG_CHANGE",
                 json.dumps(metadata or {}, default=str, sort_keys=True)),
            )


def classify_order_risk_change(
    order_context: dict[str, Any],
    current_positions: list[dict[str, Any]] | None = None,
) -> str:
    hint = str(order_context.get("risk_change") or order_context.get("_risk_change") or "").upper()
    if hint in {RISK_REDUCING, RISK_NEUTRAL, PROTECTIVE_HEDGE, RISK_INCREASING}:
        return hint
    side = str(order_context.get("transaction_type") or order_context.get("side") or "").upper()
    symbol = str(order_context.get("tradingsymbol") or order_context.get("symbol") or "").upper()
    quantity = abs(int(_float(order_context.get("quantity"))))
    if side not in {"BUY", "SELL"} or not symbol or quantity <= 0:
        return UNKNOWN
    current_qty = 0
    for row in current_positions or []:
        if str(row.get("tradingsymbol") or row.get("symbol") or "").upper() == symbol:
            current_qty += int(_float(row.get("quantity") or row.get("net_quantity")))
    signed_order = quantity if side == "BUY" else -quantity
    proposed_qty = current_qty + signed_order
    if current_qty and abs(proposed_qty) < abs(current_qty):
        return RISK_REDUCING
    if current_qty and proposed_qty == 0:
        return RISK_REDUCING
    if abs(proposed_qty) > abs(current_qty):
        return RISK_INCREASING
    return UNKNOWN


class MonthlyRiskEngine:
    def __init__(self, db_path: str | Path):
        self.repository = MonthlyRiskRepository(db_path)

    def evaluate_order(
        self,
        order_context: dict[str, Any],
        *,
        account_id: str = DEFAULT_ACCOUNT_ID,
        current_positions: list[dict[str, Any]] | None = None,
        day: date | None = None,
    ) -> RiskDecision:
        account = str(account_id or DEFAULT_ACCOUNT_ID)
        risk_change = classify_order_risk_change(order_context, current_positions)
        try:
            snapshot = self.repository.latest_snapshot(account, day)
            locked = bool(snapshot.get("hard_locked"))
            allowed = not locked or risk_change in {RISK_REDUCING, RISK_NEUTRAL, PROTECTIVE_HEDGE}
            if locked and risk_change == UNKNOWN:
                allowed = False
            reason = (
                "Monthly hard loss limit reached; only exits, reductions and protective hedges are allowed."
                if not allowed else
                "Capital protection active; this order reduces or protects existing risk."
                if locked else
                "Monthly risk gate passed."
            )
            decision = RiskDecision(
                allowed=allowed, risk_change=risk_change,
                risk_state=str(snapshot.get("risk_state") or "UNKNOWN"), reason=reason,
                account_id=account, month_key=str(snapshot.get("month_key") or month_key(day)),
                booked_pnl=_float(snapshot.get("booked_pnl")),
                risk_mtd_pnl=_float(snapshot.get("risk_mtd_pnl")),
                monthly_loss_limit=_float(snapshot.get("max_monthly_loss")),
                remaining_loss_budget=_float(snapshot.get("remaining_loss_budget")),
            )
        except Exception as exc:
            # New risk fails closed. A clearly classified exit/hedge remains available.
            allowed = risk_change in {RISK_REDUCING, RISK_NEUTRAL, PROTECTIVE_HEDGE}
            decision = RiskDecision(
                allowed=allowed, risk_change=risk_change, risk_state="UNAVAILABLE",
                reason=("Risk state unavailable; new risk temporarily blocked. "
                        "Exit and hedge orders remain available."),
                account_id=account, month_key=month_key(day), booked_pnl=0,
                risk_mtd_pnl=0, monthly_loss_limit=0, remaining_loss_budget=0,
            )
            try:
                self.repository.log_event(decision, {**order_context, "error": type(exc).__name__}, "RISK_STATE_UNAVAILABLE")
            except Exception:
                pass
            return decision
        self.repository.log_event(
            decision, order_context,
            "ORDER_RISK_ALLOWED" if decision.allowed else "ORDER_RISK_BLOCKED",
        )
        return decision


def pre_order_risk_check(
    db_path: str | Path,
    order_context: dict[str, Any],
    *,
    account_id: str = DEFAULT_ACCOUNT_ID,
    current_positions: list[dict[str, Any]] | None = None,
) -> RiskDecision:
    return MonthlyRiskEngine(db_path).evaluate_order(
        order_context, account_id=account_id, current_positions=current_positions
    )
