"""52W AI Call Spread candidate import and defined-risk CE spread builder.

The UI page lives in ``app.py`` because this repository is a single local web
application.  This module keeps Screener CSV normalization, local persistence,
and the +5% SELL / +20% BUY hedge spread math isolated and testable.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from kite_option_resolver import KiteOptionResolver
from kite_pair_execution import round_limit_price_to_tick


SCREEN_ID = 3929697
SCREEN_URL = "https://www.screener.in/screens/3929697/future_top_nifty_ai/"
CSV_EXPORT_URL = f"{SCREEN_URL}?export=1"
PAGE_NAME = "52W AI Call Spread"
DEFAULT_SELL_OTM_PCT = 5.0
DEFAULT_HEDGE_OTM_PCT = 20.0
DEFAULT_BUY_LIMIT_DISCOUNT_PCT = 5.0
DEFAULT_SELL_LIMIT_MARKUP_PCT = 10.0
MIN_NET_CREDIT = 0.05
MAX_QUOTE_AGE_SECONDS = 180


class FiftyTwoWeekState(Enum):
    NORMAL = "NORMAL"
    NEAR_HIGH = "NEAR_HIGH"
    NEAR_HIGH_REJECTION = "NEAR_HIGH_REJECTION"
    FRESH_BREAKOUT = "FRESH_BREAKOUT"
    STRONG_BREAKOUT = "STRONG_BREAKOUT"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"


@dataclass(frozen=True)
class SellOnRiseConfig:
    near_52w_high_pct: float = 2.0
    strong_breakout_score: float = 70.0
    rsi_exhaustion_start: float = 68.0
    strong_adx: float = 25.0
    strong_volume_ratio: float = 1.5
    sell_a_plus_score: float = 85.0
    sell_a_score: float = 75.0
    watch_score: float = 65.0
    min_history_sessions: int = 120
    completed_52w_sessions: int = 252
    max_option_spread_pct: float = 18.0
    min_option_oi: int = 100
    min_option_volume: int = 1


@dataclass
class SellOnRiseEvaluation:
    symbol: str
    company: str = ""
    live_cmp: float = 0.0
    screener_cmp: float | None = None
    previous_52w_high: float = 0.0
    current_52w_high: float = 0.0
    previous_52w_low: float = 0.0
    distance_high_pct: float = 0.0
    above_breakout_pct: float = 0.0
    today_high: float = 0.0
    today_low: float = 0.0
    state: FiftyTwoWeekState = FiftyTwoWeekState.NORMAL
    rsi: float | None = None
    rsi_slope: float | None = None
    adx: float | None = None
    adx_direction: str = "UNKNOWN"
    ema20: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    distance_from_ema20_pct: float | None = None
    distance_from_ema50_pct: float | None = None
    distance_from_ema200_pct: float | None = None
    return_5d_pct: float | None = None
    return_10d_pct: float | None = None
    return_20d_pct: float | None = None
    volume_ratio: float | None = None
    today_range_position_pct: float | None = None
    upper_wick_pct: float | None = None
    breakout_strength_score: float = 0.0
    rejection_score: float = 0.0
    momentum_exhaustion_score: float = 0.0
    relative_strength_score: float = 0.0
    option_quality_score: float = 0.0
    call_sell_score: float = 0.0
    sell_rank: int | None = None
    decision: str = "DATA_ERROR"
    fno_eligible: bool | None = None
    option_expiry: str = ""
    best_ce_symbol: str = ""
    best_ce_strike: float | None = None
    best_ce_bid: float | None = None
    best_ce_ask: float | None = None
    best_ce_ltp: float | None = None
    best_ce_oi: int | None = None
    best_ce_volume: int | None = None
    score_components: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    block_reasons: list[str] = field(default_factory=list)
    screener_import_timestamp: str = ""
    historical_cache_timestamp: str = ""
    kite_quote_timestamp: str = ""
    evaluation_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")
    )
    data_source: str = "KITE"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data


def _positive_float_or_none(value: Any) -> float | None:
    number = _as_float(value)
    return number if number > 0 else None


class ScreenerManualExportRequired(RuntimeError):
    """Raised when automatic Screener export cannot proceed safely."""


def ist_now_text() -> str:
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")


def normalize_column_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("%", " pct ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def parse_indian_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.upper() in {"NA", "N/A", "NONE", "-", "--"}:
        return None
    multiplier = 1.0
    lowered = text.lower()
    if "cr" in lowered or "crore" in lowered:
        multiplier = 1.0
    elif "lakh" in lowered:
        multiplier = 0.01
    text = re.sub(r"[₹,%\s]", "", text, flags=re.I)
    text = re.sub(r"(?i)(cr|crore|lakh|rs|inr)", "", text)
    text = text.replace(",", "")
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _first_present(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in row and str(row.get(name) or "").strip():
            return row.get(name)
    return None


def _symbol_from_row(row: dict[str, Any]) -> str:
    for key in ("nse_symbol", "nse_code", "symbol", "ticker", "nse"):
        value = str(row.get(key) or "").strip().upper()
        if value:
            return re.sub(r"[^A-Z0-9&-]", "", value)
    company = str(_first_present(row, ("company", "name", "company_name")) or "").strip().upper()
    return re.sub(r"[^A-Z0-9&-]", "", company.split()[0] if company else "")


def normalize_screener_csv(csv_text: str, source_status: str = "CSV_UPLOAD") -> list[dict[str, Any]]:
    handle = io.StringIO(csv_text or "")
    reader = csv.DictReader(handle)
    if not reader.fieldnames:
        return []
    imported_at = ist_now_text()
    rows: list[dict[str, Any]] = []
    for raw in reader:
        normalized = {normalize_column_name(key): value for key, value in (raw or {}).items()}
        company = str(_first_present(normalized, ("company", "name", "company_name")) or "").strip()
        symbol = _symbol_from_row(normalized)
        if not (company or symbol):
            continue
        cmp_value = parse_indian_number(_first_present(normalized, ("cmp", "current_price", "price", "last_price")))
        market_cap = parse_indian_number(_first_present(normalized, ("market_cap", "market_capitalization", "mkt_cap")))
        pat = parse_indian_number(_first_present(normalized, ("profit_after_tax", "pat", "net_profit", "np")))
        sales_growth = parse_indian_number(
            _first_present(normalized, ("sales_growth_3years", "sales_growth_3_years", "sales_growth_3y", "3y_sales_growth"))
        )
        distance_52w = parse_indian_number(
            _first_present(normalized, ("distance_from_52w_high", "distance_from_52_week_high", "from_52w_high", "52w_high_gap"))
        )
        row = {
            "company": company or symbol,
            "symbol": symbol,
            "screener_cmp": cmp_value,
            "market_cap": market_cap,
            "pat": pat,
            "sales_growth_3y_pct": sales_growth,
            "distance_from_52w_high_pct": distance_52w,
            "fno_eligible": None,
            "option_expiry": "",
            "data_timestamp": imported_at,
            "source_status": source_status,
            "extra_fields": {k: v for k, v in normalized.items() if k not in {"company", "name", "company_name", "symbol", "nse_symbol", "nse_code"}},
        }
        row["rank_score"] = rank_candidate(row)
        rows.append(row)
    return sorted(rows, key=lambda item: item.get("rank_score") or 0, reverse=True)


def rank_candidate(row: dict[str, Any]) -> float:
    parts: list[float] = []
    distance = parse_indian_number(row.get("distance_from_52w_high_pct"))
    sales = parse_indian_number(row.get("sales_growth_3y_pct"))
    pat = parse_indian_number(row.get("pat"))
    if distance is not None:
        parts.append(max(0.0, min(40.0, 40.0 - abs(distance))))
    if sales is not None:
        parts.append(max(0.0, min(30.0, sales)))
    if pat is not None:
        parts.append(max(0.0, min(30.0, pat / 100.0)))
    return round(sum(parts) / len(parts), 2) if parts else 0.0


class ScreenerClient:
    """Small safe interface for future authenticated Screener CSV export."""

    def __init__(self, email: str | None = None, password: str | None = None) -> None:
        self.email = email if email is not None else os.environ.get("SCREENER_EMAIL")
        self.password = password if password is not None else os.environ.get("SCREENER_PASSWORD")

    def fetch_screen(self, screen_id: int = SCREEN_ID) -> list[dict[str, Any]]:
        if not self.email or not self.password:
            raise ScreenerManualExportRequired("Manual login/export required")
        raise ScreenerManualExportRequired("Manual login/export required")


class FiftyTwoWeekAiRepository:
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
                CREATE TABLE IF NOT EXISTS ai52_candidate_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    imported_at TEXT NOT NULL,
                    source_status TEXT NOT NULL,
                    rows_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai52_spread_previews (
                    preview_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL,
                    expiry TEXT NOT NULL,
                    sell_strike REAL NOT NULL,
                    hedge_strike REAL NOT NULL,
                    lots INTEGER NOT NULL,
                    preview_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai52_sell_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    sell_rank INTEGER,
                    decision TEXT NOT NULL,
                    call_sell_score REAL NOT NULL,
                    state TEXT NOT NULL,
                    evaluation_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_candidate_snapshot(self, rows: list[dict[str, Any]], source_status: str) -> str:
        stamp = ist_now_text()
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        snapshot_id = f"AI52-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{digest}"
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ai52_candidate_snapshots(snapshot_id, imported_at, source_status, rows_json) VALUES (?, ?, ?, ?)",
                (snapshot_id, stamp, source_status, json.dumps(rows, default=str)),
            )
        return snapshot_id

    def latest_candidate_snapshot(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM ai52_candidate_snapshots ORDER BY imported_at DESC LIMIT 1").fetchone()
        if not row:
            return None
        result = dict(row)
        result["rows"] = json.loads(result.pop("rows_json") or "[]")
        return result

    def save_preview(self, preview: dict[str, Any], status: str = "PREVIEW") -> str:
        key = idempotency_key_for_preview(preview)
        preview_id = preview.get("preview_id") or f"AI52-PREV-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}"
        stamp = ist_now_text()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ai52_spread_previews(
                    preview_id, idempotency_key, symbol, expiry, sell_strike, hedge_strike,
                    lots, preview_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM ai52_spread_previews WHERE idempotency_key=?), ?), ?)
                """,
                (
                    preview_id,
                    key,
                    str(preview.get("symbol") or ""),
                    str(preview.get("expiry") or ""),
                    float(preview.get("sell_strike") or 0),
                    float(preview.get("buy_strike") or preview.get("hedge_strike") or 0),
                    int(preview.get("selected_lots") or preview.get("lots") or 1),
                    json.dumps(preview, default=str),
                    status,
                    key,
                    stamp,
                    stamp,
                ),
            )
        return preview_id

    def latest_previews(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM ai52_spread_previews ORDER BY updated_at DESC LIMIT ?", (int(limit),)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["preview"] = json.loads(item.pop("preview_json") or "{}")
            result.append(item)
        return result

    def clear_previews(self) -> int:
        """Clear only saved 52W AI preview cache rows.

        This deliberately does not touch imported candidates, pair order monitor
        rows, broker orders, credentials, or any runtime trading files.
        """

        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM ai52_spread_previews")
        return int(cursor.rowcount or 0)

    def save_evaluation(self, evaluation: SellOnRiseEvaluation | dict[str, Any]) -> str:
        payload = evaluation.to_dict() if isinstance(evaluation, SellOnRiseEvaluation) else dict(evaluation)
        symbol = str(payload.get("symbol") or "").strip().upper()
        stamp = str(payload.get("evaluation_timestamp") or ist_now_text())
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        evaluation_id = str(payload.get("evaluation_id") or f"AI52-EVAL-{symbol}-{digest}")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ai52_sell_evaluations(
                    evaluation_id, symbol, sell_rank, decision, call_sell_score, state, evaluation_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation_id,
                    symbol,
                    int(payload.get("sell_rank") or 0) or None,
                    str(payload.get("decision") or "DATA_ERROR"),
                    float(payload.get("call_sell_score") or 0),
                    str(payload.get("state") or ""),
                    json.dumps(payload, default=str),
                    stamp,
                ),
            )
        return evaluation_id

    def save_evaluations(self, evaluations: list[SellOnRiseEvaluation | dict[str, Any]]) -> list[str]:
        return [self.save_evaluation(item) for item in evaluations]

    def latest_evaluations(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.*
                FROM ai52_sell_evaluations e
                INNER JOIN (
                    SELECT symbol, MAX(created_at) AS created_at
                    FROM ai52_sell_evaluations
                    GROUP BY symbol
                ) latest
                  ON latest.symbol = e.symbol AND latest.created_at = e.created_at
                ORDER BY CASE WHEN e.sell_rank IS NULL THEN 9999 ELSE e.sell_rank END, e.call_sell_score DESC
                """
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            payload = json.loads(item.pop("evaluation_json") or "{}")
            payload.setdefault("evaluation_id", item.get("evaluation_id"))
            result.append(payload)
        return result

    def latest_evaluation_by_symbol(self) -> dict[str, dict[str, Any]]:
        return {str(row.get("symbol") or "").strip().upper(): row for row in self.latest_evaluations()}


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _expiry_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")[:10]


def _contract_symbol(contract: dict[str, Any]) -> str:
    return str(contract.get("tradingsymbol") or contract.get("symbol") or "").strip().upper()


def _quote_for_symbol(quotes: dict[str, Any], tradingsymbol: str) -> dict[str, Any]:
    return dict(quotes.get(f"NFO:{tradingsymbol}") or quotes.get(tradingsymbol) or {})


def _depth_price(quote: dict[str, Any], side: str) -> float:
    depth = quote.get("depth") if isinstance(quote.get("depth"), dict) else {}
    rows = depth.get(side) if isinstance(depth.get(side), list) else []
    if rows:
        return _as_float(rows[0].get("price"))
    for key in ((f"best_{'bid' if side == 'buy' else 'ask'}"), ("bid" if side == "buy" else "ask")):
        price = _as_float(quote.get(key))
        if price > 0:
            return price
    return _as_float(quote.get("last_price") or quote.get("ltp"))


def _depth_qty(quote: dict[str, Any], side: str) -> int:
    depth = quote.get("depth") if isinstance(quote.get("depth"), dict) else {}
    rows = depth.get(side) if isinstance(depth.get(side), list) else []
    if not rows:
        return 0
    return int(_as_float(rows[0].get("quantity") or rows[0].get("orders")))


def _contract_id(contract: dict[str, Any]) -> str:
    return str(contract.get("instrument_token") or contract.get("exchange_token") or contract.get("token") or "")


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
    return round(ema, 2)


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, current in zip(values[-period - 1 : -1], values[-period:]):
        change = current - prev
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _adx(candles: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(candles) <= period + 1:
        return None
    trs: list[float] = []
    pdm: list[float] = []
    ndm: list[float] = []
    for prev, current in zip(candles[-period - 1 : -1], candles[-period:]):
        high = _as_float(current.get("high"))
        low = _as_float(current.get("low"))
        prev_high = _as_float(prev.get("high"))
        prev_low = _as_float(prev.get("low"))
        prev_close = _as_float(prev.get("close"))
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        up_move = high - prev_high
        down_move = prev_low - low
        pdm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        ndm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
    atr = sum(trs) / period
    if atr <= 0:
        return None
    pdi = 100 * (sum(pdm) / period) / atr
    ndi = 100 * (sum(ndm) / period) / atr
    if pdi + ndi <= 0:
        return None
    return round(100 * abs(pdi - ndi) / (pdi + ndi), 2)


def _pct(current: float, base: float) -> float | None:
    return round(((current - base) / base) * 100, 2) if current > 0 and base > 0 else None


def _return_pct(values: list[float], sessions: int) -> float | None:
    if len(values) <= sessions or values[-sessions - 1] <= 0:
        return None
    return _pct(values[-1], values[-sessions - 1])


def _normalize_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _instrument_underlying(instrument: dict[str, Any]) -> str:
    return str(
        instrument.get("underlying")
        or instrument.get("name")
        or instrument.get("tradingsymbol")
        or instrument.get("symbol")
        or ""
    ).strip().upper()


def _nse_instrument_token(nse_instruments: list[dict[str, Any]], symbol: str) -> str | int | None:
    clean_symbol = str(symbol or "").strip().upper()
    for item in nse_instruments:
        tradingsymbol = str(item.get("tradingsymbol") or item.get("symbol") or "").strip().upper()
        if tradingsymbol == clean_symbol:
            return item.get("instrument_token") or item.get("exchange_token") or item.get("token")
    return None


def _current_month_ce_contracts(nfo_instruments: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    clean_symbol = str(symbol or "").strip().upper()
    rows = [
        dict(item)
        for item in nfo_instruments
        if str(item.get("instrument_type") or item.get("option_type") or "").upper() == "CE"
        and _instrument_underlying(item) == clean_symbol
    ]
    return sorted(rows, key=lambda row: (_expiry_text(row.get("expiry")), _as_float(row.get("strike"))))


def _historical_data(adapter: Any, instrument_token: Any, from_date: date, to_date: date) -> list[dict[str, Any]]:
    if hasattr(adapter, "historical_data"):
        return list(adapter.historical_data(instrument_token, from_date, to_date, "day"))
    client = adapter._client() if hasattr(adapter, "_client") else getattr(adapter, "kite", None)
    if client is not None and hasattr(client, "historical_data"):
        return list(client.historical_data(instrument_token, from_date, to_date, "day"))
    return []


def _quote_one(adapter: Any, key: str) -> dict[str, Any]:
    try:
        return dict((adapter.get_quote([key]) or {}).get(key) or {})
    except Exception:
        return {}


def _option_quality(
    *,
    adapter: Any,
    symbol: str,
    live_cmp: float,
    nfo_instruments: list[dict[str, Any]],
    config: SellOnRiseConfig,
) -> dict[str, Any]:
    contracts = _current_month_ce_contracts(nfo_instruments, symbol)
    if not contracts:
        return {"score": 0.0, "block_reasons": ["NOT_FNO"], "fno_eligible": False}
    target = Decimal(str(live_cmp)) * Decimal("1.05")
    expiry = _expiry_text(contracts[0].get("expiry"))
    expiry_contracts = [row for row in contracts if _expiry_text(row.get("expiry")) == expiry]
    candidates = [row for row in expiry_contracts if _as_float(row.get("strike")) >= float(target)]
    contract = min(candidates, key=lambda row: _as_float(row.get("strike"))) if candidates else expiry_contracts[-1]
    tradingsymbol = _contract_symbol(contract)
    quote_payload = _quote_one(adapter, f"NFO:{tradingsymbol}")
    bid = round_limit_price_to_tick(_depth_price(quote_payload, "buy"))
    ask = round_limit_price_to_tick(_depth_price(quote_payload, "sell"))
    ltp = round_limit_price_to_tick(_as_float(quote_payload.get("last_price") or quote_payload.get("ltp") or contract.get("last_price")))
    oi = int(_as_float(quote_payload.get("oi") or contract.get("oi")))
    volume = int(_as_float(quote_payload.get("volume") or contract.get("volume")))
    premium_ref = ask or ltp or bid
    spread_pct = ((ask - bid) / premium_ref * 100) if bid > 0 and ask > 0 and premium_ref > 0 else 100.0
    score = 20.0
    if oi >= config.min_option_oi:
        score += 30
    if volume >= config.min_option_volume:
        score += 25
    if bid > 0 and ask > 0 and spread_pct <= config.max_option_spread_pct:
        score += 25
    block_reasons: list[str] = []
    if bid <= 0 or ask <= 0 or spread_pct > config.max_option_spread_pct:
        block_reasons.append("OPTION_SPREAD_TOO_WIDE")
    if oi < config.min_option_oi and volume < config.min_option_volume:
        block_reasons.append("OPTION_LIQUIDITY_TOO_LOW")
    return {
        "score": _normalize_score(score),
        "block_reasons": block_reasons,
        "fno_eligible": True,
        "option_expiry": expiry,
        "best_ce_symbol": tradingsymbol,
        "best_ce_strike": _as_float(contract.get("strike")),
        "best_ce_bid": bid or None,
        "best_ce_ask": ask or None,
        "best_ce_ltp": ltp or None,
        "best_ce_oi": oi,
        "best_ce_volume": volume,
    }


class SellOnRiseEvaluator:
    """Evaluate Screener 52W ideas using Kite as the authoritative market source."""

    def __init__(self, adapter: Any, config: SellOnRiseConfig | None = None, today: date | None = None) -> None:
        self.adapter = adapter
        self.config = config or SellOnRiseConfig()
        self.today = today or date.today()
        self._nse_instruments: list[dict[str, Any]] | None = None
        self._nfo_instruments: list[dict[str, Any]] | None = None

    def nse_instruments(self) -> list[dict[str, Any]]:
        if self._nse_instruments is None:
            self._nse_instruments = list(self.adapter.get_instruments("NSE"))
        return self._nse_instruments

    def nfo_instruments(self) -> list[dict[str, Any]]:
        if self._nfo_instruments is None:
            self._nfo_instruments = list(self.adapter.get_instruments("NFO"))
        return self._nfo_instruments

    def evaluate_many(self, candidates: Iterable[dict[str, Any]]) -> list[SellOnRiseEvaluation]:
        evaluations = [self.evaluate(str(candidate.get("symbol") or ""), candidate) for candidate in candidates]
        return rank_sell_on_rise_evaluations(evaluations)

    def evaluate(self, symbol: str, screener_candidate: dict[str, Any] | None = None) -> SellOnRiseEvaluation:
        candidate = dict(screener_candidate or {})
        clean_symbol = str(symbol or candidate.get("symbol") or "").strip().upper()
        company = str(candidate.get("company") or candidate.get("company_name") or clean_symbol)
        base_kwargs = {
            "symbol": clean_symbol,
            "company": company,
            "screener_cmp": parse_indian_number(candidate.get("screener_cmp")),
            "screener_import_timestamp": str(candidate.get("data_timestamp") or ""),
            "evaluation_timestamp": ist_now_text(),
        }
        if not clean_symbol:
            return SellOnRiseEvaluation(**base_kwargs, decision="DATA_ERROR", block_reasons=["SYMBOL_MISSING"])
        nfo_instruments = self.nfo_instruments()
        option_contracts = _current_month_ce_contracts(nfo_instruments, clean_symbol)
        if not option_contracts:
            return SellOnRiseEvaluation(**base_kwargs, decision="BLOCKED", fno_eligible=False, block_reasons=["NOT_FNO"])
        quote = _quote_one(self.adapter, f"NSE:{clean_symbol}")
        live_cmp = _as_float(quote.get("last_price") or quote.get("ltp"))
        today_ohlc = quote.get("ohlc") if isinstance(quote.get("ohlc"), dict) else {}
        today_high = _as_float(today_ohlc.get("high") or quote.get("high") or live_cmp)
        today_low = _as_float(today_ohlc.get("low") or quote.get("low") or live_cmp)
        if live_cmp <= 0:
            return SellOnRiseEvaluation(**base_kwargs, decision="DATA_ERROR", fno_eligible=True, block_reasons=["LIVE_QUOTE_MISSING"])
        token = _nse_instrument_token(self.nse_instruments(), clean_symbol)
        candles = _historical_data(self.adapter, token, self.today - timedelta(days=430), self.today - timedelta(days=1)) if token else []
        completed = [dict(row) for row in candles if _as_float(row.get("close")) > 0]
        if len(completed) < self.config.min_history_sessions:
            return SellOnRiseEvaluation(
                **base_kwargs,
                live_cmp=live_cmp,
                today_high=today_high,
                today_low=today_low,
                fno_eligible=True,
                decision="DATA_ERROR",
                block_reasons=["DATA_INSUFFICIENT"],
            )
        recent = completed[-self.config.completed_52w_sessions :]
        closes = [_as_float(row.get("close")) for row in completed]
        previous_52w_high = max(_as_float(row.get("high")) for row in recent)
        previous_52w_low = min(_as_float(row.get("low")) for row in recent if _as_float(row.get("low")) > 0)
        current_52w_high = max(previous_52w_high, today_high)
        distance_high_pct = round(((previous_52w_high - live_cmp) / previous_52w_high) * 100, 2) if previous_52w_high > 0 else 0.0
        above_breakout_pct = round(((live_cmp - previous_52w_high) / previous_52w_high) * 100, 2) if previous_52w_high > 0 else 0.0
        rsi = _rsi(closes)
        prior_rsi = _rsi(closes[:-3]) if len(closes) > 20 else None
        rsi_slope = round((rsi or 0) - (prior_rsi or rsi or 0), 2) if rsi is not None else None
        adx = _adx(completed)
        prior_adx = _adx(completed[:-3]) if len(completed) > 25 else None
        adx_direction = "RISING" if adx is not None and prior_adx is not None and adx > prior_adx else "FALLING" if adx is not None and prior_adx is not None else "UNKNOWN"
        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50)
        ema200 = _ema(closes, 200)
        volumes = [_as_float(row.get("volume")) for row in completed if _as_float(row.get("volume")) > 0]
        avg_volume = sum(volumes[-20:]) / min(len(volumes), 20) if volumes else 0
        volume_ratio = round(_as_float(quote.get("volume")) / avg_volume, 2) if avg_volume > 0 and _as_float(quote.get("volume")) > 0 else None
        day_range = today_high - today_low
        today_range_position_pct = round(((live_cmp - today_low) / day_range) * 100, 2) if day_range > 0 else None
        upper_wick_pct = round(((today_high - live_cmp) / today_high) * 100, 2) if today_high > 0 else None
        breakout_intraday_pct = round(((today_high - previous_52w_high) / previous_52w_high) * 100, 2) if previous_52w_high > 0 else 0.0
        failed_breakout = today_high > previous_52w_high and live_cmp < previous_52w_high
        near_high = 0 <= distance_high_pct <= self.config.near_52w_high_pct
        fresh_breakout = live_cmp > previous_52w_high and breakout_intraday_pct > 0
        breakout_strength = 0.0
        if live_cmp > previous_52w_high:
            breakout_strength += min(max(above_breakout_pct * 12, 0), 25)
        if volume_ratio and volume_ratio >= self.config.strong_volume_ratio:
            breakout_strength += 20
        if adx and adx >= self.config.strong_adx:
            breakout_strength += 20
        if adx_direction == "RISING":
            breakout_strength += 10
        if today_range_position_pct and today_range_position_pct >= 75:
            breakout_strength += 15
        if ema20 and ema50 and ema200 and live_cmp > ema20 > ema50 > ema200:
            breakout_strength += 10
        breakout_strength = _normalize_score(breakout_strength)
        rejection = 0.0
        if failed_breakout:
            rejection += 45
        if upper_wick_pct and upper_wick_pct >= 1:
            rejection += 15
        if today_range_position_pct is not None and today_range_position_pct <= 55:
            rejection += 10
        if rsi and rsi >= self.config.rsi_exhaustion_start and (rsi_slope or 0) < 0:
            rejection += 15
        if volume_ratio is not None and volume_ratio < 1.0:
            rejection += 10
        if near_high:
            rejection += 5
        rejection = _normalize_score(rejection)
        exhaustion = 0.0
        if rsi and self.config.rsi_exhaustion_start <= rsi <= 82:
            exhaustion += 25
        if rsi_slope is not None and rsi_slope < 0:
            exhaustion += 20
        ema20_distance = _pct(live_cmp, ema20 or 0) if ema20 else None
        ema50_distance = _pct(live_cmp, ema50 or 0) if ema50 else None
        ema200_distance = _pct(live_cmp, ema200 or 0) if ema200 else None
        if ema20_distance and ema20_distance > 5:
            exhaustion += 20
        if upper_wick_pct and upper_wick_pct >= 1:
            exhaustion += 15
        if failed_breakout:
            exhaustion += 20
        exhaustion = _normalize_score(exhaustion)
        relative_strength_score = 50.0
        ret_5 = _return_pct(closes, 5)
        ret_10 = _return_pct(closes, 10)
        ret_20 = _return_pct(closes, 20)
        if ret_5 is not None and ret_5 < 0:
            relative_strength_score += 15
        if ret_10 is not None and ret_10 < 0:
            relative_strength_score += 15
        if ret_20 is not None and ret_20 < 0:
            relative_strength_score += 10
        if ret_5 is not None and ret_5 > 5:
            relative_strength_score -= 15
        relative_strength_score = _normalize_score(relative_strength_score)
        option = _option_quality(adapter=self.adapter, symbol=clean_symbol, live_cmp=live_cmp, nfo_instruments=nfo_instruments, config=self.config)
        if breakout_strength >= self.config.strong_breakout_score:
            state = FiftyTwoWeekState.STRONG_BREAKOUT
        elif failed_breakout:
            state = FiftyTwoWeekState.FAILED_BREAKOUT
        elif near_high and rejection >= 45:
            state = FiftyTwoWeekState.NEAR_HIGH_REJECTION
        elif fresh_breakout:
            state = FiftyTwoWeekState.FRESH_BREAKOUT
        elif near_high:
            state = FiftyTwoWeekState.NEAR_HIGH
        else:
            state = FiftyTwoWeekState.NORMAL
        setup_score = {
            FiftyTwoWeekState.FAILED_BREAKOUT: 30.0,
            FiftyTwoWeekState.NEAR_HIGH_REJECTION: 23.0,
            FiftyTwoWeekState.NEAR_HIGH: 10.0,
            FiftyTwoWeekState.FRESH_BREAKOUT: 5.0,
            FiftyTwoWeekState.STRONG_BREAKOUT: 0.0,
            FiftyTwoWeekState.NORMAL: 0.0,
        }[state]
        score = setup_score + exhaustion * 0.15 + rejection * 0.20 + max(0.0, min(10.0, (ema20_distance or 0))) + relative_strength_score * 0.10 + float(option.get("score") or 0) * 0.15
        if volume_ratio and volume_ratio >= self.config.strong_volume_ratio and live_cmp > previous_52w_high:
            score -= 15
        if adx and adx > 30 and adx_direction == "RISING":
            score -= 10
        call_sell_score = _normalize_score(score)
        block_reasons = list(option.get("block_reasons") or [])
        if state == FiftyTwoWeekState.STRONG_BREAKOUT:
            block_reasons.append("STRONG_BREAKOUT")
        if state == FiftyTwoWeekState.FRESH_BREAKOUT:
            block_reasons.append("FRESH_BREAKOUT_WAIT")
        decision = "BLOCKED" if block_reasons else "A+ SELL" if call_sell_score >= self.config.sell_a_plus_score else "A SELL" if call_sell_score >= self.config.sell_a_score else "WATCH FOR REJECTION" if call_sell_score >= self.config.watch_score else "WAIT" if call_sell_score >= 50 else "AVOID"
        components = [
            f"52W setup {state.value}: {setup_score:.1f}/30",
            f"Momentum exhaustion: {exhaustion:.1f}/100",
            f"Rejection: {rejection:.1f}/100",
            f"Relative weakness: {relative_strength_score:.1f}/100",
            f"Option quality: {float(option.get('score') or 0):.1f}/100",
        ]
        warnings = []
        if state == FiftyTwoWeekState.STRONG_BREAKOUT:
            warnings.append("STRONG 52W BREAKOUT — DO NOT SELL CE")
        elif state == FiftyTwoWeekState.NEAR_HIGH:
            warnings.append("Near high without full rejection; wait for confirmation.")
        return SellOnRiseEvaluation(
            **base_kwargs,
            live_cmp=round(live_cmp, 2),
            previous_52w_high=round(previous_52w_high, 2),
            current_52w_high=round(current_52w_high, 2),
            previous_52w_low=round(previous_52w_low, 2),
            distance_high_pct=distance_high_pct,
            above_breakout_pct=above_breakout_pct,
            today_high=round(today_high, 2),
            today_low=round(today_low, 2),
            state=state,
            rsi=rsi,
            rsi_slope=rsi_slope,
            adx=adx,
            adx_direction=adx_direction,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            distance_from_ema20_pct=ema20_distance,
            distance_from_ema50_pct=ema50_distance,
            distance_from_ema200_pct=ema200_distance,
            return_5d_pct=ret_5,
            return_10d_pct=ret_10,
            return_20d_pct=ret_20,
            volume_ratio=volume_ratio,
            today_range_position_pct=today_range_position_pct,
            upper_wick_pct=upper_wick_pct,
            breakout_strength_score=breakout_strength,
            rejection_score=rejection,
            momentum_exhaustion_score=exhaustion,
            relative_strength_score=relative_strength_score,
            option_quality_score=float(option.get("score") or 0),
            call_sell_score=call_sell_score,
            decision=decision,
            fno_eligible=bool(option.get("fno_eligible")),
            option_expiry=str(option.get("option_expiry") or ""),
            best_ce_symbol=str(option.get("best_ce_symbol") or ""),
            best_ce_strike=_positive_float_or_none(option.get("best_ce_strike")),
            best_ce_bid=_positive_float_or_none(option.get("best_ce_bid")),
            best_ce_ask=_positive_float_or_none(option.get("best_ce_ask")),
            best_ce_ltp=_positive_float_or_none(option.get("best_ce_ltp")),
            best_ce_oi=int(option.get("best_ce_oi") or 0),
            best_ce_volume=int(option.get("best_ce_volume") or 0),
            score_components=components,
            warnings=warnings,
            block_reasons=sorted(set(block_reasons)),
            historical_cache_timestamp=ist_now_text(),
            kite_quote_timestamp=ist_now_text(),
        )


def rank_sell_on_rise_evaluations(evaluations: list[SellOnRiseEvaluation]) -> list[SellOnRiseEvaluation]:
    sorted_rows = sorted(
        evaluations,
        key=lambda row: (
            0 if row.decision == "BLOCKED" or row.block_reasons else 1,
            row.call_sell_score,
            row.rejection_score,
            row.option_quality_score,
        ),
        reverse=True,
    )
    rank = 1
    ranked: list[SellOnRiseEvaluation] = []
    for row in sorted_rows:
        if row.decision not in {"BLOCKED", "DATA_ERROR"} and not row.block_reasons and row.fno_eligible:
            row.sell_rank = rank
            rank += 1
        else:
            row.sell_rank = None
        ranked.append(row)
    return ranked


def _ceiling_contract(resolver: KiteOptionResolver, symbol: str, expiry: str | date, target: float) -> dict[str, Any] | None:
    contracts = resolver.option_contracts(symbol, "CE", expiry)
    above = [row for row in contracts if _as_float(row.get("strike")) >= target]
    return min(above, key=lambda row: _as_float(row.get("strike"))) if above else None


def _listed_hedge_contract(
    resolver: KiteOptionResolver,
    symbol: str,
    expiry: str | date,
    target: float,
    sell_strike: float,
) -> tuple[dict[str, Any] | None, bool]:
    """Return +20% CE hedge if available, otherwise farthest listed CE above sell.

    Some F&O stocks do not list a full +20% OTM CE chain for every expiry.  In
    that case a strict +20% rule creates a blank ticket even though a safer
    defined-risk hedge exists above the selected short CE.  The fallback keeps
    the hedge on the live Zerodha instrument master and never fabricates a
    strike.
    """

    target_contract = _ceiling_contract(resolver, symbol, expiry, target)
    if target_contract is not None:
        return target_contract, False
    contracts = resolver.option_contracts(symbol, "CE", expiry)
    above_sell = [row for row in contracts if _as_float(row.get("strike")) > sell_strike]
    if not above_sell:
        return None, False
    return max(above_sell, key=lambda row: _as_float(row.get("strike"))), True


def idempotency_key_for_preview(preview: dict[str, Any], account: str = "KITE") -> str:
    parts = [
        account,
        str(preview.get("symbol") or "").upper(),
        str(preview.get("expiry") or ""),
        str(preview.get("sell_strike") or ""),
        str(preview.get("buy_strike") or preview.get("hedge_strike") or ""),
        "BEAR_CALL_SPREAD",
        str(preview.get("selected_lots") or preview.get("lots") or 1),
        datetime.now(timezone.utc).date().isoformat(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def build_52w_ai_call_spread_preview(
    *,
    symbol: str,
    spot: float,
    lots: int,
    option_chain_data: list[dict[str, Any]],
    kite_adapter: Any | None = None,
    expiry: str | date | None = None,
    buy_limit_discount_pct: float = DEFAULT_BUY_LIMIT_DISCOUNT_PCT,
    sell_limit_markup_pct: float = DEFAULT_SELL_LIMIT_MARKUP_PCT,
    today: date | None = None,
) -> dict[str, Any]:
    clean_symbol = str(symbol or "").strip().upper()
    clean_spot = _as_float(spot)
    clean_lots = max(int(lots or 1), 1)
    resolver = KiteOptionResolver(instruments=option_chain_data, broker=kite_adapter, today=today or date.today())
    selected_expiry = resolver.selected_expiry(clean_symbol, expiry)
    base_preview: dict[str, Any] = {
        "screen_name": PAGE_NAME,
        "strategy_type": "BEAR_CALL_SPREAD",
        "symbol": clean_symbol,
        "spot": clean_spot,
        "cmp": clean_spot,
        "selected_lots": clean_lots,
        "lots": clean_lots,
        "sell_otm_pct": DEFAULT_SELL_OTM_PCT,
        "hedge_otm_pct": DEFAULT_HEDGE_OTM_PCT,
        "risk_decision": "BLOCKED",
    }
    if not clean_symbol or clean_spot <= 0 or selected_expiry is None:
        return {**base_preview, "risk_reason": "CMP_UNAVAILABLE_OR_EXPIRY_MISSING"}
    spot_decimal = Decimal(str(clean_spot))
    sell_target = spot_decimal * Decimal("1.05")
    hedge_target = spot_decimal * Decimal("1.20")
    sell_contract = _ceiling_contract(resolver, clean_symbol, selected_expiry, float(sell_target))
    if not sell_contract:
        return {**base_preview, "expiry": _expiry_text(selected_expiry), "risk_reason": "CONTRACT_UNRESOLVED"}
    sell_strike = _as_float(sell_contract.get("strike"))
    hedge_contract, hedge_fallback_used = _listed_hedge_contract(
        resolver,
        clean_symbol,
        selected_expiry,
        float(hedge_target),
        sell_strike,
    )
    if not hedge_contract:
        return {**base_preview, "expiry": _expiry_text(selected_expiry), "risk_reason": "HEDGE_CONTRACT_UNRESOLVED"}
    hedge_strike = _as_float(hedge_contract.get("strike"))
    if hedge_strike <= sell_strike:
        return {**base_preview, "expiry": _expiry_text(selected_expiry), "risk_reason": "HEDGE_STRIKE_NOT_ABOVE_SELL_STRIKE"}
    sell_symbol = _contract_symbol(sell_contract)
    hedge_symbol = _contract_symbol(hedge_contract)
    lot_size = int(_as_float(sell_contract.get("lot_size") or hedge_contract.get("lot_size")))
    quantity = lot_size * clean_lots
    quotes: dict[str, Any] = {}
    if kite_adapter is not None:
        try:
            quotes = kite_adapter.get_quote([f"NFO:{sell_symbol}", f"NFO:{hedge_symbol}"])
        except Exception:
            quotes = {}
    sell_quote = _quote_for_symbol(quotes, sell_symbol)
    hedge_quote = _quote_for_symbol(quotes, hedge_symbol)
    sell_bid = round_limit_price_to_tick(_depth_price(sell_quote, "buy") or _as_float(sell_contract.get("last_price") or sell_contract.get("ltp")))
    sell_ask = round_limit_price_to_tick(_depth_price(sell_quote, "sell"))
    buy_ask = round_limit_price_to_tick(_depth_price(hedge_quote, "sell") or _as_float(hedge_contract.get("last_price") or hedge_contract.get("ltp")))
    buy_bid = round_limit_price_to_tick(_depth_price(hedge_quote, "buy"))
    sell_ltp = round_limit_price_to_tick(_as_float(sell_quote.get("last_price") or sell_quote.get("ltp") or sell_bid))
    buy_ltp = round_limit_price_to_tick(_as_float(hedge_quote.get("last_price") or hedge_quote.get("ltp") or buy_ask))
    clean_buy_discount = max(0.0, min(float(buy_limit_discount_pct or 0), 50.0))
    clean_sell_markup = max(0.0, min(float(sell_limit_markup_pct or 0), 100.0))
    buy_reference_price = buy_ask or buy_ltp
    sell_reference_price = sell_bid or sell_ltp
    buy_limit_price = round_limit_price_to_tick(buy_reference_price * (1 - clean_buy_discount / 100))
    sell_limit_price = round_limit_price_to_tick(sell_reference_price)
    sell_initial_limit_price = round_limit_price_to_tick(sell_limit_price * (1 + clean_sell_markup / 100))
    net_credit = round_limit_price_to_tick(sell_limit_price - buy_limit_price)
    width = hedge_strike - sell_strike
    max_profit = max(net_credit, 0) * quantity
    max_loss = (width - net_credit) * quantity
    breakeven = sell_strike + net_credit
    sell_volume = int(_as_float(sell_quote.get("volume") or sell_contract.get("volume")))
    buy_volume = int(_as_float(hedge_quote.get("volume") or hedge_contract.get("volume")))
    sell_oi = int(_as_float(sell_quote.get("oi") or sell_contract.get("oi")))
    buy_oi = int(_as_float(hedge_quote.get("oi") or hedge_contract.get("oi")))
    sell_spread = round_limit_price_to_tick(max(sell_ask - sell_bid, 0)) if sell_ask and sell_bid else 0.0
    buy_spread = round_limit_price_to_tick(max(buy_ask - buy_bid, 0)) if buy_ask and buy_bid else 0.0
    liquidity_ok = bool(sell_limit_price > 0 and buy_limit_price > 0 and (sell_volume > 0 or sell_oi > 0) and (buy_volume > 0 or buy_oi > 0))
    reasons: list[str] = []
    if lot_size <= 0 or quantity <= 0:
        reasons.append("LOT_SIZE_UNAVAILABLE")
    if net_credit <= 0:
        reasons.append("NET_CREDIT_NON_POSITIVE")
    if max_loss <= 0:
        reasons.append("MAX_LOSS_INVALID")
    if not liquidity_ok:
        reasons.append("LIQUIDITY_WEAK")
    risk_decision = "APPROVED" if not reasons else "BLOCKED"
    expiry_text = _expiry_text(selected_expiry)
    dte = None
    try:
        parsed_expiry = datetime.fromisoformat(expiry_text).date()
        dte = (parsed_expiry - (today or date.today())).days
    except Exception:
        dte = None
    preview = {
        **base_preview,
        "expiry": expiry_text,
        "sell_expiry": expiry_text,
        "buy_expiry": expiry_text,
        "dte": dte,
        "lot_size": lot_size,
        "quantity": quantity,
        "sell_target_strike": round(float(sell_target), 2),
        "hedge_target_strike": round(float(hedge_target), 2),
        "sell_strike": sell_strike,
        "buy_strike": hedge_strike,
        "hedge_strike": hedge_strike,
        "sell_leg_tradingsymbol": sell_symbol,
        "buy_leg_tradingsymbol": hedge_symbol,
        "sell_instrument_token": _contract_id(sell_contract),
        "buy_instrument_token": _contract_id(hedge_contract),
        "sell_limit_price": sell_limit_price,
        "buy_limit_price": buy_limit_price,
        "sell_initial_limit_price": sell_initial_limit_price,
        "buy_reference_price": buy_reference_price,
        "sell_reference_price": sell_reference_price,
        "buy_limit_discount_pct": clean_buy_discount,
        "sell_limit_markup_pct": clean_sell_markup,
        "sell_leg_premium": sell_ltp,
        "buy_leg_premium": buy_ltp,
        "sell_bid": sell_bid,
        "sell_ask": sell_ask,
        "buy_bid": buy_bid,
        "buy_ask": buy_ask,
        "sell_ltp": sell_ltp,
        "buy_ltp": buy_ltp,
        "sell_volume": sell_volume,
        "buy_volume": buy_volume,
        "sell_oi": sell_oi,
        "buy_oi": buy_oi,
        "sell_bid_ask_spread": sell_spread,
        "buy_bid_ask_spread": buy_spread,
        "width": width,
        "net_credit": net_credit,
        "max_gain": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "breakeven": round(breakeven, 2),
        "pop_estimate": 70.0 if risk_decision == "APPROVED" else 0.0,
        "return_on_risk_pct": round((max_profit / max_loss) * 100, 2) if max_loss > 0 else 0.0,
        "pair_liquidity_condition": "GREEN" if liquidity_ok else "RED",
        "liquidity_order_allowed": liquidity_ok,
        "option_quote_generated_at": ist_now_text(),
        "quote_age_seconds": 0,
        "event_risk": "NO",
        "dma_status": "AMBER",
        "risk_decision": risk_decision,
        "hedge_fallback_used": hedge_fallback_used,
        "risk_reason": (
            "; ".join(reasons)
            if reasons
            else "52W AI +5%/+20% CE spread checks passed."
            if not hedge_fallback_used
            else "52W AI +5% CE spread checks passed; +20% hedge was unavailable, so the farthest listed CE above the SELL strike was used."
        ),
    }
    preview["idempotency_key"] = idempotency_key_for_preview(preview)
    return preview
