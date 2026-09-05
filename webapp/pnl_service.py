from __future__ import annotations

import csv
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


PNL_MONTHLY_TARGET = 200_000.0
PNL_SCHEMA_VERSION = 1


STRATEGY_THEME_MAP: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("DHAN-IT", "IT_CALL", "IT_CE", "TECHM", "TCS", "INFY", "HCLTECH"), "DHAN-IT", "Information Technology"),
    (("SECTOR", "SECTOR-INCOME"), "SECTOR-Income", "Sector SELL-on-rise"),
    (("52W", "AI52", "52W AI"), "52W AI Call Spread", "52W SELL-on-rise"),
    (("NIFTY", "BANKNIFTY", "FINNIFTY"), "NIFTY Income", "Index Income"),
    (("DHAN", "BEAR_CALL", "BULL_PUT"), "DHAN", "F&O Stock Spread"),
    (("CNC", "EQUITY", "VALUE"), "Equity", "Equity Investing"),
)


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        if isinstance(value, str):
            value = value.replace(",", "").replace("₹", "").strip()
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y"):
        try:
            return datetime.strptime(text[:11], fmt).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        return None


def calculate_daily_roi(net_realized_pnl: float, capital_deployed: float) -> float | None:
    capital = safe_float(capital_deployed)
    if capital <= 0:
        return None
    return round((safe_float(net_realized_pnl) / capital) * 100.0, 4)


def profit_factor(pnl_values: Iterable[float]) -> float | None:
    values = [safe_float(item) for item in pnl_values]
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses <= 0:
        return round(gains, 4) if gains > 0 else None
    return round(gains / losses, 4)


def max_drawdown(pnl_values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in pnl_values:
        equity += safe_float(value)
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(max_dd, 2)


def classify_asset_class(row: dict[str, Any]) -> str:
    exchange = str(row.get("exchange") or row.get("segment") or "").upper()
    instrument_type = str(row.get("instrument_type") or "").upper()
    symbol = str(row.get("tradingsymbol") or row.get("symbol") or "").upper()
    product = str(row.get("product") or "").upper()
    looks_like_option_symbol = bool(re.search(r"\d+(?:CE|PE)$", symbol))
    if symbol.startswith(("NIFTY", "BANKNIFTY", "FINNIFTY")):
        return "INDEX_OPTIONS" if instrument_type in {"CE", "PE"} or looks_like_option_symbol else "INDEX"
    if exchange in {"NFO", "BFO"} or instrument_type in {"CE", "PE", "FUT"} or looks_like_option_symbol:
        return "FNO_OPTIONS" if instrument_type in {"CE", "PE"} or looks_like_option_symbol else "FNO_FUTURES"
    if product == "CNC" or exchange in {"NSE", "BSE"}:
        return "EQUITY"
    return "UNCLASSIFIED"


def underlying_from_symbol(symbol: str) -> str:
    text = str(symbol or "").upper().strip()
    if not text:
        return ""
    match = re.match(r"^([A-Z&-]+?)(?:\d{1,2}[A-Z]{3}|\d{5,}|26[A-Z]{3})", text)
    if match:
        return match.group(1).replace("-", "")
    return re.sub(r"[^A-Z&-].*$", "", text) or text


def classify_strategy_theme(row: dict[str, Any]) -> tuple[str, str]:
    haystack = " ".join(
        str(row.get(key) or "")
        for key in (
            "source",
            "tag",
            "order_tag",
            "strategy",
            "screen_name",
            "tradingsymbol",
            "symbol",
        )
    ).upper()
    for markers, strategy, theme in STRATEGY_THEME_MAP:
        if any(marker.upper() in haystack for marker in markers):
            return strategy, theme
    return "MANUAL", "Unclassified"


def estimate_position_capital(row: dict[str, Any]) -> float:
    for key in ("capital_deployed", "margin_used", "span_margin", "max_loss", "risk", "overnight_quantity"):
        value = safe_float(row.get(key))
        if value > 0 and key != "overnight_quantity":
            return round(value, 2)
    qty = abs(safe_float(row.get("quantity") or row.get("net_quantity") or row.get("overnight_quantity")))
    avg = abs(safe_float(row.get("average_price") or row.get("average") or row.get("buy_price")))
    ltp = abs(safe_float(row.get("last_price") or row.get("ltp")))
    price = avg or ltp
    if qty > 0 and price > 0:
        return round(qty * price, 2)
    return 0.0


def normalise_kite_position(
    row: dict[str, Any],
    *,
    account_id: str,
    trade_date: date,
    broker: str = "ZERODHA",
) -> dict[str, Any]:
    symbol = str(row.get("tradingsymbol") or row.get("symbol") or "").upper().strip()
    strategy, theme = classify_strategy_theme(row)
    realised = safe_float(row.get("realised") or row.get("realized") or row.get("realised_pnl"))
    unrealised = safe_float(row.get("unrealised") or row.get("unrealized") or row.get("unrealised_pnl"))
    total_pnl = safe_float(row.get("pnl"), realised + unrealised)
    if not unrealised and total_pnl and realised:
        unrealised = total_pnl - realised
    charges = safe_float(row.get("charges") or row.get("estimated_charges"))
    capital = estimate_position_capital(row)
    position_group_id = str(
        row.get("position_group_id")
        or row.get("pair_id")
        or row.get("parent_order_id")
        or row.get("tag")
        or symbol
    )
    return {
        "trade_date": trade_date.isoformat(),
        "account_id": account_id or "DEFAULT",
        "broker": broker,
        "source": "KITE_POSITIONS",
        "strategy": strategy,
        "theme": theme,
        "asset_class": classify_asset_class(row),
        "underlying": underlying_from_symbol(symbol),
        "tradingsymbol": symbol,
        "position_group_id": position_group_id,
        "realized_pnl": round(realised, 2),
        "unrealized_pnl": round(unrealised, 2),
        "gross_pnl": round(realised + unrealised if realised or unrealised else total_pnl, 2),
        "charges": round(charges, 2),
        "net_realized_pnl": round(realised - charges, 2),
        "capital_deployed": capital,
        "roi_pct": calculate_daily_roi(realised - charges, capital),
        "snapshot_at": _now_text(),
        "raw_json": json.dumps(row, default=str, sort_keys=True),
    }


def snapshot_from_kite_positions(
    positions: Iterable[dict[str, Any]],
    *,
    account_id: str,
    trade_date: date | None = None,
    broker: str = "ZERODHA",
) -> list[dict[str, Any]]:
    day = trade_date or datetime.now().date()
    records = []
    for item in positions or []:
        record = normalise_kite_position(dict(item), account_id=account_id, trade_date=day, broker=broker)
        if record["tradingsymbol"]:
            records.append(record)
    return records


def period_bounds(
    period: str,
    *,
    today: date | None = None,
    year: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> tuple[date, date]:
    day = today or datetime.now().date()
    label = (period or "This Month").strip().lower()
    if label == "today":
        return day, day
    if label == "this week":
        start = day - timedelta(days=day.weekday())
        return start, day
    if label == "this year":
        selected_year = int(year or day.year)
        return date(selected_year, 1, 1), date(selected_year, 12, 31)
    if label == "custom":
        start = parse_date(from_date) or day
        end = parse_date(to_date) or day
        return (start, end) if start <= end else (end, start)
    return date(day.year, day.month, 1), day


def _dedup_capital(records: list[dict[str, Any]]) -> float:
    seen: set[tuple[str, str, str, str]] = set()
    total = 0.0
    for row in records:
        key = (
            str(row.get("trade_date") or ""),
            str(row.get("account_id") or ""),
            str(row.get("strategy") or ""),
            str(row.get("position_group_id") or row.get("tradingsymbol") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        total += safe_float(row.get("capital_deployed"))
    return round(total, 2)


def aggregate_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    realized = round(sum(safe_float(row.get("realized_pnl")) for row in records), 2)
    unrealized = round(sum(safe_float(row.get("unrealized_pnl")) for row in records), 2)
    charges = round(sum(safe_float(row.get("charges")) for row in records), 2)
    net = round(sum(safe_float(row.get("net_realized_pnl")) for row in records), 2)
    capital = _dedup_capital(records)
    daily_net = aggregate_by_dimension(records, "trade_date")
    daily_values = [safe_float(row.get("net_realized_pnl")) for row in daily_net]
    winners = sum(1 for value in daily_values if value > 0)
    losers = sum(1 for value in daily_values if value < 0)
    return {
        "rows": len(records),
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "gross_pnl": round(realized + unrealized, 2),
        "charges": charges,
        "net_realized_pnl": net,
        "capital_deployed": capital,
        "roi_pct": calculate_daily_roi(net, capital),
        "profit_factor": profit_factor(daily_values),
        "max_drawdown": max_drawdown(daily_values),
        "winning_days": winners,
        "losing_days": losers,
        "win_rate_pct": round((winners / (winners + losers)) * 100.0, 2) if winners + losers else None,
        "monthly_target": PNL_MONTHLY_TARGET,
        "target_progress_pct": round((net / PNL_MONTHLY_TARGET) * 100.0, 2) if PNL_MONTHLY_TARGET else None,
    }


def aggregate_by_dimension(records: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        key = str(row.get(dimension) or "UNCLASSIFIED")
        groups.setdefault(key, []).append(row)
    output = []
    for key, items in groups.items():
        summary = aggregate_summary_shallow(items)
        summary[dimension] = key
        output.append(summary)
    return sorted(output, key=lambda item: safe_float(item.get("net_realized_pnl")), reverse=True)


def aggregate_summary_shallow(records: list[dict[str, Any]]) -> dict[str, Any]:
    net = round(sum(safe_float(row.get("net_realized_pnl")) for row in records), 2)
    realized = round(sum(safe_float(row.get("realized_pnl")) for row in records), 2)
    unrealized = round(sum(safe_float(row.get("unrealized_pnl")) for row in records), 2)
    capital = _dedup_capital(records)
    values = [safe_float(row.get("net_realized_pnl")) for row in records]
    return {
        "count": len(records),
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "net_realized_pnl": net,
        "capital_deployed": capital,
        "roi_pct": calculate_daily_roi(net, capital),
        "profit_factor": profit_factor(values),
        "max_drawdown": max_drawdown(values),
        "capital_efficiency": capital_efficiency_score(net, capital, values),
    }


def capital_efficiency_score(net_pnl: float, capital: float, pnl_values: Iterable[float]) -> float:
    roi = calculate_daily_roi(net_pnl, capital) or 0.0
    pf = profit_factor(pnl_values) or 0.0
    drawdown = abs(max_drawdown(pnl_values))
    penalty = min(drawdown / max(abs(safe_float(net_pnl)), 1.0), 1.0) * 20.0
    return round(max(0.0, min(100.0, (roi * 3.0) + min(pf * 10.0, 40.0) - penalty)), 2)


def month_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for row in records:
        day = parse_date(row.get("trade_date"))
        if day:
            clone = dict(row)
            clone["month"] = day.strftime("%Y-%m")
            enriched.append(clone)
    return aggregate_by_dimension(enriched, "month")


def calendar_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    daily = aggregate_by_dimension(records, "trade_date")
    return sorted(daily, key=lambda item: str(item.get("trade_date") or ""))


@dataclass
class PnlFilters:
    account_id: str = "ALL"
    period: str = "This Month"
    year: int | None = None
    from_date: str = ""
    to_date: str = ""
    strategy: str = "ALL"
    theme: str = "ALL"
    asset_class: str = "ALL"
    underlying: str = ""


class PnlRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pnl_daily_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    broker TEXT NOT NULL,
                    source TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    theme TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    underlying TEXT NOT NULL,
                    tradingsymbol TEXT NOT NULL,
                    position_group_id TEXT NOT NULL,
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    unrealized_pnl REAL NOT NULL DEFAULT 0,
                    gross_pnl REAL NOT NULL DEFAULT 0,
                    charges REAL NOT NULL DEFAULT 0,
                    net_realized_pnl REAL NOT NULL DEFAULT 0,
                    capital_deployed REAL NOT NULL DEFAULT 0,
                    roi_pct REAL,
                    snapshot_at TEXT NOT NULL,
                    raw_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(trade_date, account_id, broker, source, tradingsymbol, position_group_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pnl_daily_date ON pnl_daily_snapshot(trade_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pnl_daily_strategy ON pnl_daily_snapshot(strategy, theme)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pnl_daily_asset ON pnl_daily_snapshot(asset_class, underlying)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pnl_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    details_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pnl_order_strategy_map (
                    order_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    theme TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    underlying TEXT NOT NULL,
                    source_screen TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def upsert_daily_records(self, records: list[dict[str, Any]], *, audit_event: str = "SYNC") -> int:
        self.ensure_schema()
        now = _now_text()
        with self.connect() as conn:
            for row in records:
                payload = {
                    "trade_date": str(row.get("trade_date") or datetime.now().date().isoformat()),
                    "account_id": str(row.get("account_id") or "DEFAULT"),
                    "broker": str(row.get("broker") or "ZERODHA"),
                    "source": str(row.get("source") or "MANUAL"),
                    "strategy": str(row.get("strategy") or "MANUAL"),
                    "theme": str(row.get("theme") or "Unclassified"),
                    "asset_class": str(row.get("asset_class") or "UNCLASSIFIED"),
                    "underlying": str(row.get("underlying") or underlying_from_symbol(str(row.get("tradingsymbol") or ""))),
                    "tradingsymbol": str(row.get("tradingsymbol") or "").upper(),
                    "position_group_id": str(row.get("position_group_id") or row.get("tradingsymbol") or ""),
                    "realized_pnl": safe_float(row.get("realized_pnl")),
                    "unrealized_pnl": safe_float(row.get("unrealized_pnl")),
                    "gross_pnl": safe_float(row.get("gross_pnl")),
                    "charges": safe_float(row.get("charges")),
                    "net_realized_pnl": safe_float(row.get("net_realized_pnl")),
                    "capital_deployed": safe_float(row.get("capital_deployed")),
                    "roi_pct": row.get("roi_pct"),
                    "snapshot_at": str(row.get("snapshot_at") or now),
                    "raw_json": str(row.get("raw_json") or json.dumps(row, default=str, sort_keys=True)),
                }
                conn.execute(
                    """
                    INSERT INTO pnl_daily_snapshot (
                        trade_date, account_id, broker, source, strategy, theme, asset_class,
                        underlying, tradingsymbol, position_group_id, realized_pnl, unrealized_pnl,
                        gross_pnl, charges, net_realized_pnl, capital_deployed, roi_pct,
                        snapshot_at, raw_json, created_at, updated_at
                    ) VALUES (
                        :trade_date, :account_id, :broker, :source, :strategy, :theme, :asset_class,
                        :underlying, :tradingsymbol, :position_group_id, :realized_pnl, :unrealized_pnl,
                        :gross_pnl, :charges, :net_realized_pnl, :capital_deployed, :roi_pct,
                        :snapshot_at, :raw_json, :created_at, :updated_at
                    )
                    ON CONFLICT(trade_date, account_id, broker, source, tradingsymbol, position_group_id)
                    DO UPDATE SET
                        strategy=excluded.strategy,
                        theme=excluded.theme,
                        asset_class=excluded.asset_class,
                        underlying=excluded.underlying,
                        realized_pnl=excluded.realized_pnl,
                        unrealized_pnl=excluded.unrealized_pnl,
                        gross_pnl=excluded.gross_pnl,
                        charges=excluded.charges,
                        net_realized_pnl=excluded.net_realized_pnl,
                        capital_deployed=excluded.capital_deployed,
                        roi_pct=excluded.roi_pct,
                        snapshot_at=excluded.snapshot_at,
                        raw_json=excluded.raw_json,
                        updated_at=excluded.updated_at
                    """,
                    {**payload, "created_at": now, "updated_at": now},
                )
            account = str(records[0].get("account_id") or "DEFAULT") if records else "DEFAULT"
            conn.execute(
                "INSERT INTO pnl_audit_log(event_type, event_at, account_id, details_json) VALUES (?, ?, ?, ?)",
                (audit_event, now, account, json.dumps({"records": len(records)}, sort_keys=True)),
            )
        return len(records)

    def available_years(self) -> list[int]:
        self.ensure_schema()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT substr(trade_date, 1, 4) AS year FROM pnl_daily_snapshot ORDER BY year DESC"
            ).fetchall()
        years = [safe_int(row["year"]) for row in rows if safe_int(row["year"]) > 0]
        current_year = datetime.now().year
        return sorted(set(years + [current_year]), reverse=True)

    def option_values(self, column: str) -> list[str]:
        if column not in {"account_id", "strategy", "theme", "asset_class"}:
            raise ValueError("Unsupported P&L filter column.")
        self.ensure_schema()
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT {column} AS value FROM pnl_daily_snapshot WHERE {column} <> '' ORDER BY {column}"
            ).fetchall()
        return [str(row["value"]) for row in rows if row["value"]]

    def query_daily_records(self, filters: PnlFilters, *, today: date | None = None) -> list[dict[str, Any]]:
        self.ensure_schema()
        start, end = period_bounds(
            filters.period,
            today=today,
            year=filters.year,
            from_date=filters.from_date,
            to_date=filters.to_date,
        )
        clauses = ["trade_date BETWEEN ? AND ?"]
        params: list[Any] = [start.isoformat(), end.isoformat()]
        for column, value in (
            ("account_id", filters.account_id),
            ("strategy", filters.strategy),
            ("theme", filters.theme),
            ("asset_class", filters.asset_class),
        ):
            if value and value != "ALL":
                clauses.append(f"{column} = ?")
                params.append(value)
        if filters.underlying.strip():
            clauses.append("(underlying LIKE ? OR tradingsymbol LIKE ?)")
            query = f"%{filters.underlying.strip().upper()}%"
            params.extend([query, query])
        sql = (
            "SELECT * FROM pnl_daily_snapshot WHERE "
            + " AND ".join(clauses)
            + " ORDER BY trade_date DESC, strategy, underlying, tradingsymbol"
        )
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def export_csv(self, rows: list[dict[str, Any]], export_dir: str | Path) -> Path:
        target_dir = Path(export_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        output = target_dir / f"pnl_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        fieldnames = [
            "trade_date",
            "account_id",
            "strategy",
            "theme",
            "asset_class",
            "underlying",
            "tradingsymbol",
            "realized_pnl",
            "unrealized_pnl",
            "charges",
            "net_realized_pnl",
            "capital_deployed",
            "roi_pct",
            "source",
            "snapshot_at",
        ]
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({name: row.get(name, "") for name in fieldnames})
        return output


def sync_today_from_kite(
    kite: Any,
    db_path: str | Path,
    *,
    account_id: str = "DEFAULT",
    trade_date: date | None = None,
) -> int:
    raw = kite.positions().get("net", [])
    records = snapshot_from_kite_positions(raw, account_id=account_id, trade_date=trade_date)
    repo = PnlRepository(db_path)
    return repo.upsert_daily_records(records, audit_event="KITE_POSITION_SYNC")
