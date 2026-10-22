"""Deterministic pre-market and live opportunity scoring for TRADE.

Scores are advisory and never approve an order. Probability uses a lognormal
risk-neutral terminal-price model with constant IV/rate and no jump/dividend
model; it is therefore labelled an estimate, not historical POP.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
PREMARKET_WEIGHTS = {"technical": 30, "structure": 20, "alignment": 15, "probability": 15, "risk_adjusted_credit": 20}
LIVE_WEIGHTS = {"gap_price_action": 25, "premium_retained": 20, "probability": 20, "liquidity": 15, "momentum": 10, "capital_efficiency": 10}
DEFAULTS = {"max_spread_pct": 5.0, "warning_spread_pct": 3.0, "normal_gap_pct": 1.0, "large_gap_pct": 2.0, "premium_collapse_pct": -30.0, "quote_stale_seconds": 30}


def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def terminal_otm_probability(spot: float, strike: float, dte: int, iv: float, option_type: str, rate: float = 0.065) -> float | None:
    """Risk-neutral probability the option expires OTM under stated assumptions."""
    if min(spot, strike, dte, iv) <= 0:
        return None
    years = max(dte / 365.0, 1 / 365.0)
    sigma_t = iv * math.sqrt(years)
    z = (math.log(strike / spot) - (rate - 0.5 * iv * iv) * years) / sigma_t
    cdf = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    probability = cdf if str(option_type).upper() == "CE" else 1 - cdf
    return round(max(0.0, min(1.0, probability)) * 100, 2)


def liquidity_state(bid: float, ask: float, ltp: float, volume: float, oi: float, config: dict[str, float] | None = None) -> tuple[str, str, float | None]:
    cfg = {**DEFAULTS, **(config or {})}
    if min(bid, ask, ltp) <= 0 or ask < bid:
        return "BLOCK", "Executable bid/ask is unavailable.", None
    spread = (ask - bid) / ltp * 100
    if spread > cfg["max_spread_pct"] or volume <= 0 or oi <= 0:
        return "BLOCK", f"Spread {spread:.2f}% or displayed volume/OI fails liquidity limits.", round(spread, 2)
    if spread > cfg["warning_spread_pct"]:
        return "WARNING", f"Spread {spread:.2f}% requires caution.", round(spread, 2)
    return "PASS", f"Spread {spread:.2f}% with displayed volume and OI.", round(spread, 2)


def premarket_score(*, technical_score: float, structure_score: float, alignment_score: float,
                    model_probability: float | None, net_credit_yield: float | None,
                    mandatory_complete: bool) -> dict[str, Any]:
    probability_quality = 0.0 if model_probability is None else max(0.0, min(100.0, 100 - abs(70 - model_probability) * 1.5))
    credit_quality = 0.0 if net_credit_yield is None else max(0.0, min(100.0, net_credit_yield / 5.0 * 100))
    components = {
        "technical": min(100.0, max(0.0, technical_score)), "structure": min(100.0, max(0.0, structure_score)),
        "alignment": min(100.0, max(0.0, alignment_score)), "probability": probability_quality,
        "risk_adjusted_credit": credit_quality,
    }
    score = round(sum(components[key] * weight / 100 for key, weight in PREMARKET_WEIGHTS.items()), 2)
    return {"score": score, "components": components, "data_complete": mandatory_complete,
            "status": "CANDIDATE" if mandatory_complete else "UNRESOLVED"}


def assess_live_entry(baseline: dict[str, Any], live: dict[str, Any], config: dict[str, float] | None = None) -> dict[str, Any]:
    cfg = {**DEFAULTS, **(config or {})}
    previous_close, cmp = _f(baseline.get("previous_close")), _f(live.get("cmp"))
    open_price = _f(live.get("open")) or cmp
    gap_pct = round((open_price - previous_close) / previous_close * 100, 2) if previous_close > 0 and open_price > 0 else None
    previous_premium, bid, ask = _f(baseline.get("option_close")), _f(live.get("bid")), _f(live.get("ask"))
    premium_change = round((bid - previous_premium) / previous_premium * 100, 2) if previous_premium > 0 and bid > 0 else None
    liq_status, liq_reason, spread = liquidity_state(bid, ask, _f(live.get("ltp")), _f(live.get("volume")), _f(live.get("oi")), cfg)
    reasons: list[str] = []
    status = "LIVE CANDIDATE"
    if gap_pct is None:
        status, reasons = "WAIT", ["Opening gap cannot be calculated."]
    elif abs(gap_pct) > cfg["large_gap_pct"]:
        status, reasons = "WAIT", [f"Large opening gap {gap_pct:+.2f}% requires opening-range review."]
    if premium_change is None:
        status, reasons = "WAIT", reasons + ["Baseline/current executable premium is unavailable."]
    elif premium_change <= cfg["premium_collapse_pct"]:
        status = "MISSED — DO NOT CHASE"
        reasons.append(f"Executable premium changed {premium_change:+.2f}% from baseline.")
    minimum_credit = _f(baseline.get("minimum_credit"))
    if minimum_credit > 0 and bid < minimum_credit:
        status = "MISSED — LOW PREMIUM"
        reasons.append(f"Current bid {bid:.2f} is below minimum credit {minimum_credit:.2f}.")
    if liq_status == "BLOCK":
        status = "BLOCKED"
    reasons.append(liq_reason)
    mandatory = all([live.get("quote_fresh") is True, live.get("earnings_status") == "PASS", liq_status != "BLOCK", live.get("risk_status") == "PASS", live.get("capital_available") is True])
    component = {
        "gap_price_action": 80 if gap_pct is not None and abs(gap_pct) < cfg["normal_gap_pct"] else 40,
        "premium_retained": 0 if premium_change is None else max(0.0, min(100.0, 100 + premium_change)),
        "probability": _f(live.get("probability_quality")),
        "liquidity": 100 if liq_status == "PASS" else 50 if liq_status == "WARNING" else 0,
        "momentum": _f(live.get("momentum_score")), "capital_efficiency": _f(live.get("capital_efficiency_score")),
    }
    live_score = round(sum(component[key] * weight / 100 for key, weight in LIVE_WEIGHTS.items()), 2)
    premarket = _f(baseline.get("premarket_score"))
    combined = round(0.4 * premarket + 0.6 * live_score, 2) if mandatory else None
    return {"gap_pct": gap_pct, "premium_change_pct": premium_change, "spread_pct": spread,
            "liquidity_status": liq_status, "live_entry_score": live_score, "combined_score": combined,
            "mandatory_complete": mandatory, "status": status, "reasons": reasons, "components": component}


class TradeOpportunityRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path); conn.row_factory = sqlite3.Row; return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS trade_opportunity_baseline(
              account_id TEXT NOT NULL, trade_date TEXT NOT NULL, created_at TEXT NOT NULL,
              rows_json TEXT NOT NULL, PRIMARY KEY(account_id,trade_date));
            CREATE TABLE IF NOT EXISTS trade_opportunity_snapshot(
              id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, trade_date TEXT NOT NULL,
              created_at TEXT NOT NULL, mode TEXT NOT NULL, rows_json TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_trade_opp_snap ON trade_opportunity_snapshot(account_id,trade_date,id DESC);
            """)

    def save_baseline_once(self, account_id: str, trade_date: str, rows: list[dict[str, Any]]) -> bool:
        self.ensure_schema()
        with self.connect() as conn:
            cursor = conn.execute("INSERT OR IGNORE INTO trade_opportunity_baseline VALUES(?,?,?,?)", (account_id, trade_date, datetime.now(IST).isoformat(timespec="seconds"), json.dumps(rows, default=str)))
        return cursor.rowcount == 1

    def baseline(self, account_id: str, trade_date: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM trade_opportunity_baseline WHERE account_id=? AND trade_date=?", (account_id, trade_date)).fetchone()
        if not row: return None
        result = dict(row); result["rows"] = json.loads(result.pop("rows_json") or "[]"); return result

    def save_snapshot(self, account_id: str, trade_date: str, mode: str, rows: list[dict[str, Any]]) -> int:
        self.ensure_schema()
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO trade_opportunity_snapshot(account_id,trade_date,created_at,mode,rows_json) VALUES(?,?,?,?,?)", (account_id, trade_date, datetime.now(IST).isoformat(timespec="seconds"), mode, json.dumps(rows, default=str)))
            return int(cur.lastrowid)


def scan_max_profit(bid, ask, lot_size):
    """Gross short-leg expiry profit for one current master lot, before hedge/fees.

    Scan has no confirmed hedge/cover yet: this is not protected-strategy net profit
    and must never alter eligibility or risk approval. No LTP fallback.
    """
    try:
        bid, ask, quantity = float(bid), float(ask), float(lot_size)
        if not all(math.isfinite(n) for n in (bid,ask,quantity)) or not 0 < bid <= ask or quantity <= 0 or not quantity.is_integer():
            return None
        return round(bid*int(quantity),2)
    except (ValueError,TypeError):
        return None
