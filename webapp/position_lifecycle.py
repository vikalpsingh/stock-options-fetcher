"""Position lifecycle tracking for option-income trades."""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import risk_config as cfg


OPEN_POSITION_HEADERS = [
    "position_id",
    "entry_date",
    "symbol",
    "tradingsymbol",
    "option_type",
    "strike",
    "expiry",
    "quantity",
    "lot_size",
    "entry_premium",
    "current_premium",
    "target_exit_premium",
    "warning_premium",
    "hard_stop_premium",
    "underlying_entry_price",
    "current_underlying_price",
    "status",
    "reason",
    "last_checked_at",
]


EXIT_ELIGIBLE_STATUSES = {"PROFIT_TARGET_HIT", "WARNING", "EXIT_NOW", "ROLL_CANDIDATE"}


def recommended_action_for_status(status: str) -> str:
    """Map lifecycle status to the action a trader should consider."""
    status = str(status or "").upper()
    return {
        "PROFIT_TARGET_HIT": "BOOK_PROFIT",
        "WARNING": "WATCH_CLOSELY",
        "EXIT_NOW": "EXIT_NOW",
        "ROLL_CANDIDATE": "ROLL_OR_EXIT",
        "OPEN": "HOLD",
        "CLOSED": "NONE",
        "DATA_MISSING": "WAIT_FOR_LTP",
    }.get(status, "HOLD")


@dataclass
class PositionRecord:
    position_id: str
    entry_date: str
    symbol: str
    tradingsymbol: str
    option_type: str
    strike: float
    expiry: str
    quantity: int
    lot_size: int
    entry_premium: float
    current_premium: float
    target_exit_premium: float
    warning_premium: float
    hard_stop_premium: float
    underlying_entry_price: float
    current_underlying_price: float
    status: str = "OPEN"
    reason: str = ""
    last_checked_at: str = ""


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        for fmt in ("%Y-%m-%d", "%d %b %Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass
    return None


def days_to_expiry(expiry: Any, today: date | None = None) -> int | None:
    expiry_date = _parse_date(expiry)
    if not expiry_date:
        return None
    today = today or date.today()
    return (expiry_date - today).days


class PositionLifecycleManager:
    def __init__(self, path: str | Path = "open_positions.csv"):
        self.path = Path(path)

    def load_positions(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def save_positions(self, rows: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OPEN_POSITION_HEADERS, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in OPEN_POSITION_HEADERS})

    def add_position(self, position: dict[str, Any]) -> dict[str, Any]:
        rows = self.load_positions()
        record = {
            "position_id": position.get("position_id") or str(uuid.uuid4()),
            "entry_date": position.get("entry_date") or date.today().isoformat(),
            "symbol": position.get("symbol") or "",
            "tradingsymbol": position.get("tradingsymbol") or "",
            "option_type": str(position.get("option_type") or "").upper(),
            "strike": _float(position.get("strike")),
            "expiry": position.get("expiry") or "",
            "quantity": _int(position.get("quantity")),
            "lot_size": _int(position.get("lot_size")),
            "entry_premium": _float(position.get("entry_premium")),
            "current_premium": _float(position.get("current_premium") or position.get("entry_premium")),
            "target_exit_premium": _float(position.get("target_exit_premium")),
            "warning_premium": _float(position.get("warning_premium")),
            "hard_stop_premium": _float(position.get("hard_stop_premium")),
            "underlying_entry_price": _float(position.get("underlying_entry_price")),
            "current_underlying_price": _float(position.get("current_underlying_price")),
            "status": position.get("status") or "OPEN",
            "reason": position.get("reason") or "",
            "last_checked_at": position.get("last_checked_at") or datetime.now().isoformat(timespec="seconds"),
        }
        rows.append(record)
        self.save_positions(rows)
        return record

    def evaluate_position(
        self,
        position: dict[str, Any],
        technical_data: dict[str, Any] | None = None,
        today: date | None = None,
    ) -> dict[str, Any]:
        row = dict(position)
        if str(row.get("status") or "").upper() == "CLOSED":
            return row
        option_type = str(row.get("option_type") or "").upper()
        entry = _float(row.get("entry_premium"))
        current = _float(row.get("current_premium"))
        strike = _float(row.get("strike"))
        underlying = _float(row.get("current_underlying_price"))
        tech = technical_data or {}
        status = "OPEN"
        reason = "Premium is between target and risk thresholds."
        if entry <= 0 or current <= 0:
            row["status"] = "DATA_MISSING"
            row["reason"] = "Entry premium or current option LTP is unavailable."
            row["recommended_action"] = recommended_action_for_status("DATA_MISSING")
            row["last_checked_at"] = datetime.now().isoformat(timespec="seconds")
            return row
        if option_type == "CE" and entry > 0 and current <= entry * 0.50:
            status, reason = "PROFIT_TARGET_HIT", "CE premium decayed 50% or more."
        elif option_type == "PE" and entry > 0 and current <= entry * 0.25:
            status, reason = "PROFIT_TARGET_HIT", "PE premium decayed 75% or more."
        if entry > 0 and current >= entry * 3:
            status, reason = "EXIT_NOW", "Premium reached hard-stop level."
        elif entry > 0 and current >= entry * 2 and status != "EXIT_NOW":
            status, reason = "WARNING", "Premium doubled from entry."
        dte = days_to_expiry(row.get("expiry"), today)
        if dte is not None and dte <= cfg.EXIT_BEFORE_EXPIRY_DAYS and status not in {"EXIT_NOW", "PROFIT_TARGET_HIT"}:
            status, reason = "ROLL_CANDIDATE", "Expiry week risk; roll or exit."
        rsi = _float(tech.get("rsi"))
        ema50 = _float(tech.get("ema50"))
        volume = _float(tech.get("volume"))
        avg_volume = _float(tech.get("avg_volume_20d") or tech.get("20_day_average_volume"))
        resistance = _float(tech.get("recent_resistance") or tech.get("high_20d"))
        if option_type == "CE" and underlying > 0 and strike > 0 and (underlying >= strike or (resistance > 0 and underlying > resistance and rsi > 65)):
            status, reason = "ROLL_CANDIDATE", "Underlying is testing strike/resistance."
        if option_type == "PE" and underlying > 0 and ema50 > 0 and underlying < ema50 and volume > 1.5 * avg_volume > 0:
            status, reason = "EXIT_NOW", "Underlying closed below EMA50 on high volume."
        row["status"] = status
        row["reason"] = reason
        row["recommended_action"] = recommended_action_for_status(status)
        row["last_checked_at"] = datetime.now().isoformat(timespec="seconds")
        return row

    def refresh_positions(
        self,
        premiums_by_symbol: dict[str, float] | None = None,
        underlying_by_symbol: dict[str, float] | None = None,
        technical_by_symbol: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        premiums = premiums_by_symbol or {}
        underlyings = underlying_by_symbol or {}
        technical = technical_by_symbol or {}
        refreshed = []
        for row in self.load_positions():
            symbol = str(row.get("tradingsymbol") or "")
            if symbol in premiums:
                row["current_premium"] = premiums[symbol]
            if symbol in underlyings:
                row["current_underlying_price"] = underlyings[symbol]
            refreshed.append(self.evaluate_position(row, technical.get(symbol, {})))
        self.save_positions(refreshed)
        return refreshed

    def mark_closed(self, position_id: str) -> bool:
        rows = self.load_positions()
        changed = False
        for row in rows:
            if str(row.get("position_id")) == str(position_id):
                row["status"] = "CLOSED"
                row["reason"] = "Marked closed by user."
                row["last_checked_at"] = datetime.now().isoformat(timespec="seconds")
                changed = True
        if changed:
            self.save_positions(rows)
        return changed

    def summary(self, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        rows = rows if rows is not None else self.load_positions()
        open_rows = [row for row in rows if str(row.get("status") or "").upper() != "CLOSED"]
        def count(status: str) -> int:
            return sum(1 for row in open_rows if row.get("status") == status)
        pnl = 0.0
        for row in open_rows:
            qty = abs(_int(row.get("quantity")))
            pnl += (_float(row.get("entry_premium")) - _float(row.get("current_premium"))) * qty
        return {
            "total_open_positions": len(open_rows),
            "profit_target": count("PROFIT_TARGET_HIT"),
            "warning": count("WARNING"),
            "exit_now": count("EXIT_NOW"),
            "roll_candidate": count("ROLL_CANDIDATE"),
            "data_missing": count("DATA_MISSING"),
            "total_unrealized_option_pnl": pnl,
        }

    def generate_exit_orders(
        self,
        selected_position_ids: list[str] | None = None,
        manual_prices: dict[str, float] | None = None,
    ) -> tuple[str, str]:
        selected = set(selected_position_ids or [])
        manual_prices = manual_prices or {}
        rows = self.load_positions()
        output = []
        report = []
        for row in rows:
            if selected and row.get("position_id") not in selected:
                continue
            if row.get("status") not in EXIT_ELIGIBLE_STATUSES:
                continue
            qty = abs(_int(row.get("quantity")))
            if qty <= 0 or row.get("status") == "CLOSED":
                continue
            price = _float(row.get("current_premium")) or _float(manual_prices.get(row.get("position_id")))
            if price <= 0:
                report.append({"tradingsymbol": row.get("tradingsymbol"), "reason": "LTP unavailable; enter manual price."})
                continue
            output.append(
                {
                    "exchange": "NFO",
                    "tradingsymbol": row.get("tradingsymbol"),
                    "quantity": qty,
                    "transaction_type": "BUY",
                    "product": "NRML",
                    "order_type": "LIMIT",
                    "price": round(price, 2),
                    "validity": "DAY",
                }
            )
            report.append(
                {
                    "symbol": row.get("symbol"),
                    "tradingsymbol": row.get("tradingsymbol"),
                    "status": row.get("status"),
                    "recommended_action": recommended_action_for_status(str(row.get("status") or "")),
                    "entry_premium": row.get("entry_premium"),
                    "current_premium": row.get("current_premium"),
                    "reason": row.get("reason"),
                    "generated_exit_price": round(price, 2),
                }
            )
        csv_text = "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity\n"
        for row in output:
            csv_text += ",".join(str(row[key]) for key in ["exchange", "tradingsymbol", "quantity", "transaction_type", "product", "order_type", "price", "validity"]) + "\n"
        report_headers = [
            "symbol",
            "tradingsymbol",
            "status",
            "recommended_action",
            "entry_premium",
            "current_premium",
            "reason",
            "generated_exit_price",
        ]
        report_text = ",".join(report_headers) + "\n" + "\n".join(
            ",".join(str(item.get(key, "")).replace(",", ";") for key in report_headers)
            for item in report
        )
        return csv_text, report_text + ("\n" if report else "")
