"""DHAN-IT pair order persistence and hedge-first execution."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kite_option_liquidity import preview_has_bilateral_order_depth
from kite_pair_execution import build_kite_order_payload, dhan_initial_sell_limit_price, round_limit_price_to_tick
import risk_config


OUTPUT_DIR = Path(__file__).resolve().parent / "dhan_it_outputs"


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DhanItPairRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS dhan_it_pair_orders (
                    pair_id TEXT PRIMARY KEY,
                    screen_name TEXT NOT NULL DEFAULT 'DHAN-IT',
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
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_checked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS dhan_it_execution_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair_id TEXT,
                    action TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def create_pair(self, preview: dict[str, Any], mode: str, user_confirmed: bool, execution_mode: str = "HEDGE_FIRST") -> str:
        pair_id = str(preview.get("pair_id") or f"DIT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}")
        stamp = now_text()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO dhan_it_pair_orders(
                    pair_id, strategy_type, symbol, expiry, lots, lot_size, quantity,
                    sell_leg_tradingsymbol, buy_leg_tradingsymbol, sell_leg_status, buy_leg_status,
                    pair_status, net_credit_expected, net_credit_actual, max_gain, max_loss,
                    breakeven, pop_estimate, risk_decision, user_confirmed, mode, execution_mode,
                    payload_json, created_at, updated_at
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
        params = list(updates.values()) + [pair_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE dhan_it_pair_orders SET {', '.join(f'{key}=?' for key in updates)} WHERE pair_id=?", params)

    def list_pairs(self, include_closed: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM dhan_it_pair_orders"
        if not include_closed:
            query += " WHERE pair_status NOT IN ('CLOSED','CANCELLED','FAILED','BOTH_FILLED')"
        query += " ORDER BY created_at DESC"
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query).fetchall()]

    def get_pair(self, pair_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM dhan_it_pair_orders WHERE pair_id=?", (pair_id,)).fetchone()
        return dict(row) if row else None

    def log(self, pair_id: str, action: str, detail: str = "") -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO dhan_it_execution_log(pair_id, action, detail, created_at) VALUES (?, ?, ?, ?)", (pair_id, action, detail, now_text()))

    def clear_pair_monitor(self) -> dict[str, int]:
        with self.connect() as conn:
            order_cur = conn.execute("DELETE FROM dhan_it_pair_orders")
            log_cur = conn.execute("DELETE FROM dhan_it_execution_log")
        return {
            "pair_orders_deleted": int(order_cur.rowcount or 0),
            "execution_logs_deleted": int(log_cur.rowcount or 0),
        }

    def export_outputs(self, candidates: list[dict[str, Any]] | None = None) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if candidates is not None:
            self._write_csv(OUTPUT_DIR / "dhan_it_candidates.csv", candidates)
            self._write_csv(OUTPUT_DIR / "dhan_it_spread_preview.csv", candidates)
            self._write_csv(OUTPUT_DIR / "dhan_it_rejections.csv", [row for row in candidates if row.get("risk_decision") != "APPROVED"])
            rows = []
            for row in candidates:
                for key, label in (("current_month", "CURRENT_MONTH"), ("next_month", "NEXT_MONTH")):
                    month = row.get(key) if isinstance(row.get(key), dict) else {}
                    if month.get("expiry"):
                        rows.append({"timestamp": now_text(), "symbol": row.get("symbol"), "strategy_type": row.get("strategy_type"), "expiry_type": label, **month, "recommendation": row.get("recommended_expiry")})
            self._write_csv(OUTPUT_DIR / "dhan_it_expiry_comparison.csv", rows)
        self._write_csv(OUTPUT_DIR / "dhan_it_pair_orders.csv", self.list_pairs())
        with self.connect() as conn:
            logs = [dict(row) for row in conn.execute("SELECT * FROM dhan_it_execution_log ORDER BY id DESC LIMIT 500").fetchall()]
        self._write_csv(OUTPUT_DIR / "dhan_it_execution_log.csv", logs)

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        flat = [{k: json.dumps(v, default=str) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in rows]
        headers = sorted({key for row in flat for key in row}) or ["empty"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(flat)


def submit_dhan_it_pair(preview: dict[str, Any], repository: DhanItPairRepository, broker: Any, user_confirmed: bool, mode: str = "PAPER") -> dict[str, Any]:
    if not user_confirmed:
        raise ValueError("Explicit confirmation is required before placing a DHAN-IT paired spread.")
    is_live = str(mode or "PAPER").upper() == "LIVE"
    liquidity_depth_clear = preview_has_bilateral_order_depth(preview)
    if is_live and (
        str(preview.get("pair_liquidity_condition") or "").upper() == "RED"
        or preview.get("liquidity_order_allowed") is False
    ) and not liquidity_depth_clear:
        repository.log("", "LIQUIDITY_RED_ORDER_BLOCKED", str(preview.get("liquidity_reason") or "RED liquidity blocked order"))
        raise ValueError("LIQUIDITY_RED_ORDER_BLOCKED: DHAN-IT blocks RED liquidity in live mode.")
    quote_stamp = str(preview.get("option_quote_generated_at") or "").strip()
    if quote_stamp:
        try:
            generated_at = datetime.fromisoformat(quote_stamp.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - generated_at.astimezone(timezone.utc)).total_seconds()
        except ValueError:
            age = float("inf")
        if age > float(getattr(risk_config, "DHAN_IT_QUOTE_TTL_SECONDS", 30)):
            repository.log("", "QUOTE_STALE_ORDER_BLOCKED", f"Quote age {age:.0f}s")
            raise ValueError("QUOTE_STALE_ORDER_BLOCKED: refresh DHAN-IT liquidity before submitting.")
    accepted_risk_warnings: list[str] = []
    if float(preview.get("pop_estimate") or 0) < float(getattr(risk_config, "DHAN_IT_MIN_POP", 70.0)):
        accepted_risk_warnings.append("POP below DHAN-IT minimum")
    if float(preview.get("return_on_risk_pct") or 0) < float(getattr(risk_config, "DHAN_IT_MIN_RETURN_ON_RISK_PCT", 8.0)):
        accepted_risk_warnings.append("return on risk below DHAN-IT minimum")
    if float(preview.get("max_loss") or 0) > float(getattr(risk_config, "DHAN_IT_MAX_ACCEPTABLE_PAIR_LOSS_INR", 40_000)):
        accepted_risk_warnings.append("max loss above configured limit")
    hard_reasons: list[str] = []
    if str(preview.get("event_risk") or "").upper() == "YES":
        hard_reasons.append("event risk")
    if str(preview.get("dma_status") or "").upper() == "RED":
        hard_reasons.append("DMA/technical gate RED")
    if hard_reasons:
        reason = "; ".join(hard_reasons)
        repository.log("", "DHAN_IT_RISK_REWARD_BLOCKED", reason)
        raise ValueError(f"DHAN_IT_RISK_REWARD_BLOCKED: {reason}")
    if accepted_risk_warnings:
        repository.log("", "DHAN_IT_ACCEPTED_RISK_WARNINGS", "; ".join(accepted_risk_warnings))
    if str(preview.get("risk_decision") or "").upper() != "APPROVED":
        risk_reason = str(preview.get("risk_reason") or preview.get("reason") or "")
        blocking_codes = (
            "CMP_UNAVAILABLE",
            "CONTRACT_UNRESOLVED",
            "OPTION_PREMIUM_UNAVAILABLE",
            "NET_CREDIT_NON_POSITIVE",
            "MAX_LOSS_INVALID",
            "CALENDAR_HEDGE_EXPIRES_BEFORE_SHORT",
            "EVENT_RISK",
        )
        if liquidity_depth_clear and not any(code in risk_reason for code in blocking_codes):
            preview = dict(preview)
            preview["risk_override"] = "DHAN_IT_BILATERAL_DEPTH_CLEAR"
            preview["risk_decision_original"] = preview.get("risk_decision")
            preview["risk_reason_original"] = risk_reason
            preview["risk_decision"] = "APPROVED"
            preview["risk_reason"] = (
                "User confirmed defined-risk pair; liquidity cleared by bilateral depth "
                f">= {int(getattr(risk_config, 'LIQUIDITY_AMBER_MIN_TOTAL_ORDERS', 20) or 20)} buy and sell orders on both legs."
            )
            preview["reason"] = preview["risk_reason"]
        else:
            raise ValueError(f"DHAN-IT spread is blocked: {preview.get('risk_reason') or preview.get('reason')}")
    pair_id = repository.create_pair(preview, mode=mode, user_confirmed=True, execution_mode="HEDGE_FIRST")
    tag = pair_id[-20:]
    buy_payload = build_kite_order_payload(preview["buy_leg_tradingsymbol"], "BUY", preview["quantity"], preview["buy_limit_price"], tag)
    sell_cmp_limit_price = round_limit_price_to_tick(float(preview["sell_limit_price"]))
    sell_initial_limit_price = dhan_initial_sell_limit_price(sell_cmp_limit_price)
    sell_payload = build_kite_order_payload(preview["sell_leg_tradingsymbol"], "SELL", preview["quantity"], sell_initial_limit_price, tag)
    buy_result = broker.place_order(buy_payload)
    sell_result = broker.place_order(sell_payload)
    repository.update_pair(
        pair_id,
        buy_leg_order_id=buy_result["order_id"],
        sell_leg_order_id=sell_result["order_id"],
        buy_leg_status=buy_result.get("status", "OPEN"),
        sell_leg_status=sell_result.get("status", "OPEN"),
        sell_leg_placed=1,
        pair_status="SUBMITTED_WAITING_HEDGE",
        payload_json=json.dumps(
            {
                **preview,
                "accepted_risk_warnings": accepted_risk_warnings,
                "buy_order_payload": buy_payload,
                "sell_order_payload": sell_payload,
                "sell_cmp_limit_price": sell_cmp_limit_price,
                "sell_initial_limit_price": sell_initial_limit_price,
                "sell_reprice_after_hedge": True,
            },
            default=str,
        ),
    )
    repository.log(pair_id, "BUY_HEDGE_SUBMITTED", buy_result["order_id"])
    repository.log(pair_id, "SELL_PARKED_ABOVE_CMP", f"{sell_result['order_id']} @ {sell_initial_limit_price}; reprice to {sell_cmp_limit_price} after hedge fill")
    return {"pair_id": pair_id, "buy_leg_order_id": buy_result["order_id"], "sell_leg_order_id": sell_result["order_id"], "mode": mode}
