"""Persistent TRADE wizard drafts and decision-quality scoring.

This module stores research/process state only.  It deliberately contains no
broker client and cannot place, modify, or cancel an order.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
VALID_STAGES = {"best", "intelligence", "chart", "validate"}
DEFAULT_THRESHOLDS = {"excellent": 90, "good": 80, "needs_improvement": 60}


def _now() -> datetime:
    return datetime.now(IST)


class TradeWorkflowRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS trade_workflow_draft (
              draft_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, symbol TEXT NOT NULL,
              stage TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL, expires_at TEXT NOT NULL, data_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trade_workflow_account
              ON trade_workflow_draft(account_id, updated_at DESC);
            CREATE TABLE IF NOT EXISTS trade_workflow_audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT, draft_id TEXT NOT NULL,
              account_id TEXT NOT NULL, created_at TEXT NOT NULL, event TEXT NOT NULL,
              details_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trade_discipline_assessment (
              id INTEGER PRIMARY KEY AUTOINCREMENT, draft_id TEXT NOT NULL,
              account_id TEXT NOT NULL, symbol TEXT NOT NULL, created_at TEXT NOT NULL,
              position_status TEXT NOT NULL, process_score REAL NOT NULL,
              process_band TEXT NOT NULL, financial_outcome TEXT NOT NULL,
              classification TEXT NOT NULL, dimensions_json TEXT NOT NULL,
              hard_violation INTEGER NOT NULL DEFAULT 0, pnl REAL
            );
            """)

    def create(self, account_id: str, symbol: str, source: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ensure_schema()
        now = _now()
        draft_id = secrets.token_urlsafe(18)
        data = {"source": source or {}, "discipline": {"screened": True}}
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO trade_workflow_draft VALUES (?,?,?,?,?,?,?,?,?)",
                (draft_id, account_id, symbol.upper(), "intelligence", 1,
                 now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"),
                 (now + timedelta(hours=8)).isoformat(timespec="seconds"), json.dumps(data, default=str)),
            )
            self._audit_conn(conn, draft_id, account_id, "DRAFT_CREATED", {"symbol": symbol.upper()})
        return self.get(draft_id, account_id) or {}

    def get(self, draft_id: str, account_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM trade_workflow_draft WHERE draft_id=? AND account_id=?",
                (draft_id, account_id),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        if datetime.fromisoformat(result["expires_at"]) < _now():
            return None
        result["data"] = json.loads(result.pop("data_json") or "{}")
        return result

    def update(self, draft_id: str, account_id: str, *, stage: str | None = None,
               changes: dict[str, Any] | None = None, event: str = "DRAFT_UPDATED") -> dict[str, Any]:
        current = self.get(draft_id, account_id)
        if not current:
            raise ValueError("TRADE workflow draft is missing or expired. Return to Find BEST.")
        next_stage = stage or current["stage"]
        if next_stage not in VALID_STAGES:
            raise ValueError("Invalid TRADE workflow stage.")
        data = dict(current["data"])
        data.update(changes or {})
        now = _now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                "UPDATE trade_workflow_draft SET stage=?,version=version+1,updated_at=?,data_json=? WHERE draft_id=? AND account_id=?",
                (next_stage, now, json.dumps(data, default=str), draft_id, account_id),
            )
            self._audit_conn(conn, draft_id, account_id, event, changes or {})
        return self.get(draft_id, account_id) or {}

    def record_no_trade(self, draft_id: str, account_id: str, reason: str) -> dict[str, Any]:
        draft = self.get(draft_id, account_id)
        if not draft:
            raise ValueError("TRADE workflow draft is missing or expired.")
        dimensions = {"selection": 20, "evidence": 20, "plan": 20, "risk": 25, "execution": 15}
        assessment = score_discipline(dimensions, hard_violation=False, outcome="NO_TRADE")
        self.save_assessment(draft, assessment, "NO_TRADE", None)
        self.update(draft_id, account_id, changes={"no_trade_reason": reason, "completed": True}, event="GOOD_NO_TRADE")
        return assessment

    def save_assessment(self, draft: dict[str, Any], assessment: dict[str, Any],
                        position_status: str, pnl: float | None) -> None:
        self.ensure_schema()
        with self.connect() as conn:
            conn.execute("""INSERT INTO trade_discipline_assessment(
              draft_id,account_id,symbol,created_at,position_status,process_score,
              process_band,financial_outcome,classification,dimensions_json,hard_violation,pnl
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
                draft["draft_id"], draft["account_id"], draft["symbol"], _now().isoformat(timespec="seconds"),
                position_status, assessment["score"], assessment["band"], assessment["financial_outcome"],
                assessment["classification"], json.dumps(assessment["dimensions"]),
                1 if assessment["hard_violation"] else 0, pnl,
            ))

    @staticmethod
    def _audit_conn(conn: sqlite3.Connection, draft_id: str, account_id: str,
                    event: str, details: dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO trade_workflow_audit(draft_id,account_id,created_at,event,details_json) VALUES(?,?,?,?,?)",
            (draft_id, account_id, _now().isoformat(timespec="seconds"), event, json.dumps(details, default=str)),
        )


def score_discipline(dimensions: dict[str, float], *, hard_violation: bool,
                     outcome: str = "OPEN", thresholds: dict[str, int] | None = None) -> dict[str, Any]:
    caps = {"selection": 20, "evidence": 20, "plan": 20, "risk": 25, "execution": 15}
    clean = {key: max(0.0, min(float(dimensions.get(key, 0)), cap)) for key, cap in caps.items()}
    score = round(sum(clean.values()), 1)
    limits = thresholds or DEFAULT_THRESHOLDS
    band = ("Excellent discipline" if score >= limits["excellent"] else
            "Good discipline" if score >= limits["good"] else
            "Needs improvement" if score >= limits["needs_improvement"] else "Poor discipline")
    if hard_violation and band in {"Excellent discipline", "Good discipline"}:
        band = "Needs improvement"
    outcome = str(outcome or "OPEN").upper()
    process_followed = score >= limits["good"] and not hard_violation
    if outcome == "NO_TRADE":
        classification = "GOOD NO-TRADE DECISION" if process_followed else "POOR NO-TRADE PROCESS"
    elif outcome in {"PROFIT", "LOSS"}:
        classification = f"{'GOOD' if process_followed else 'POOR'} DECISION — {outcome}"
    else:
        classification = "PROVISIONAL PROCESS ASSESSMENT"
    return {"score": score, "band": band, "dimensions": clean, "hard_violation": hard_violation,
            "financial_outcome": outcome, "classification": classification}
