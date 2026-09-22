"""Intraday sell-on-rise timing monitor for the 52W AI Call Spread page.

This module is intentionally broker-neutral.  It builds completed OHLC candles
from timestamped quote observations, runs an explicit rebound/rejection state
machine, and persists monitor config/state/signals in the local application DB.
Order preview/submission remains in the existing 52W AI protected call-spread
workflow.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
VALID_TIMEFRAMES = {1, 3, 5, 10, 15}
MONITOR_PHASES = {
    "OBSERVING",
    "INITIAL_MOVE_IDENTIFIED",
    "REBOUND_IN_PROGRESS",
    "RESISTANCE_TEST",
    "REJECTION_CANDIDATE",
    "REJECTION_CONFIRMED",
    "INVALIDATED",
    "EXPIRED",
}


def now_ist() -> datetime:
    return datetime.now(timezone.utc).astimezone(IST)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_ist_time(value: str) -> time:
    hour_text, minute_text = str(value or "").strip().split(":", 1)
    return time(int(hour_text), int(minute_text), tzinfo=IST)


def parse_ist_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    else:
        return None
    return parsed.astimezone(IST) if parsed.tzinfo else parsed.replace(tzinfo=IST)


def ist_text(value: datetime | None = None) -> str:
    return (value or now_ist()).astimezone(IST).isoformat(timespec="seconds")


@dataclass
class SellOnRiseMonitorConfig:
    selected_symbols: list[str] = field(default_factory=list)
    monitor_mode: str = "START_NOW"
    monitor_start_time_ist: str = "09:30"
    monitor_duration_minutes: int = 150
    quote_check_interval_seconds: int = 10
    candle_timeframe_minutes: int = 1
    minimum_initial_decline_percent: float = 1.0
    minimum_rebound_percent_from_intraday_low: float = 0.75
    resistance_tolerance_percent: float = 0.25
    confirmation_buffer_percent: float = 0.05
    short_call_otm_percent: float = 5.0
    protective_call_otm_percent: float = 10.0
    expiry: str = ""
    number_of_lots: int = 1
    execution_mode: str = "ALERT_ONLY"
    order_type: str = "EXECUTABLE_LIMIT"
    max_signals_per_stock_per_day: int = 1
    cooldown_minutes: int = 30
    force_close_short_leg_time_ist: str = "15:15"
    auto_execute_armed: bool = False
    minimum_candles_before_pattern: int = 3
    minimum_rebound_candles: int = 2
    confirmation_must_occur_within_candles: int = 3

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "SellOnRiseMonitorConfig":
        raw = dict(raw or {})
        cfg = cls()
        for key in asdict(cfg):
            if key in raw:
                setattr(cfg, key, raw[key])
        cfg.selected_symbols = sorted({str(item).strip().upper() for item in cfg.selected_symbols if str(item).strip()})
        cfg.monitor_mode = str(cfg.monitor_mode or "START_NOW").upper()
        cfg.execution_mode = str(cfg.execution_mode or "ALERT_ONLY").upper()
        cfg.order_type = str(cfg.order_type or "EXECUTABLE_LIMIT").upper()
        cfg.monitor_duration_minutes = int(_to_float(cfg.monitor_duration_minutes, 150))
        cfg.quote_check_interval_seconds = int(_to_float(cfg.quote_check_interval_seconds, 10))
        cfg.candle_timeframe_minutes = int(_to_float(cfg.candle_timeframe_minutes, 1))
        cfg.number_of_lots = int(_to_float(cfg.number_of_lots, 1))
        cfg.max_signals_per_stock_per_day = int(_to_float(cfg.max_signals_per_stock_per_day, 1))
        cfg.cooldown_minutes = int(_to_float(cfg.cooldown_minutes, 30))
        return cfg

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QuoteObservation:
    symbol: str
    timestamp_ist: datetime
    price: float
    volume: int | None = None
    day_change_pct: float | None = None


@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp_ist: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None
    complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp_ist"] = self.timestamp_ist.astimezone(IST).isoformat(timespec="seconds")
        return payload


def validate_monitor_config(config: SellOnRiseMonitorConfig | dict[str, Any], portfolio_max_lots: int = 50) -> list[str]:
    cfg = config if isinstance(config, SellOnRiseMonitorConfig) else SellOnRiseMonitorConfig.from_dict(config)
    errors: list[str] = []
    if not cfg.selected_symbols:
        errors.append("Select at least one evaluated 52W AI stock.")
    try:
        parse_ist_time(cfg.monitor_start_time_ist)
    except Exception:
        errors.append("Start time must be HH:MM in Asia/Kolkata.")
    try:
        parse_ist_time(cfg.force_close_short_leg_time_ist)
    except Exception:
        errors.append("Force-close time must be HH:MM in Asia/Kolkata.")
    if not 5 <= cfg.quote_check_interval_seconds <= 300:
        errors.append("Quote-check interval must be between 5 and 300 seconds.")
    if not 5 <= cfg.monitor_duration_minutes <= 360:
        errors.append("Monitor duration must be between 5 and 360 minutes.")
    if cfg.candle_timeframe_minutes not in VALID_TIMEFRAMES:
        errors.append("Candle timeframe must be one of 1, 3, 5, 10, or 15 minutes.")
    if not 1 <= cfg.number_of_lots <= max(1, int(portfolio_max_lots)):
        errors.append(f"Lots must be between 1 and configured portfolio maximum {portfolio_max_lots}.")
    if not 3.0 <= float(cfg.short_call_otm_percent) <= 15.0:
        errors.append("Short CE OTM must be between 3% and 15%.")
    if float(cfg.protective_call_otm_percent) <= float(cfg.short_call_otm_percent):
        errors.append("Protective CE OTM must be greater than short CE OTM.")
    if cfg.execution_mode not in {"ALERT_ONLY", "PREVIEW_AND_CONFIRM", "AUTO_EXECUTE"}:
        errors.append("Execution mode must be ALERT_ONLY, PREVIEW_AND_CONFIRM, or AUTO_EXECUTE.")
    if cfg.execution_mode == "AUTO_EXECUTE" and not cfg.auto_execute_armed:
        errors.append("AUTO_EXECUTE requires session-specific arming.")
    return errors


def monitoring_window(
    config: SellOnRiseMonitorConfig | dict[str, Any],
    *,
    trading_day: date | None = None,
    started_now_at: datetime | None = None,
) -> dict[str, Any]:
    cfg = config if isinstance(config, SellOnRiseMonitorConfig) else SellOnRiseMonitorConfig.from_dict(config)
    base_day = trading_day or (started_now_at.astimezone(IST).date() if started_now_at else now_ist().date())
    if cfg.monitor_mode == "START_NOW" and started_now_at:
        start_dt = started_now_at.astimezone(IST)
    else:
        t = parse_ist_time(cfg.monitor_start_time_ist)
        start_dt = datetime.combine(base_day, t.replace(tzinfo=None), tzinfo=IST)
    end_dt = start_dt + timedelta(minutes=cfg.monitor_duration_minutes)
    return {
        "configured_start_time_ist": cfg.monitor_start_time_ist,
        "actual_start_timestamp_ist": start_dt.isoformat(timespec="seconds"),
        "expected_end_timestamp_ist": end_dt.isoformat(timespec="seconds"),
        "duration_minutes": cfg.monitor_duration_minutes,
    }


def build_completed_candles_from_quotes(
    observations: Iterable[QuoteObservation | dict[str, Any]],
    timeframe_minutes: int,
    *,
    now: datetime | None = None,
) -> list[Candle]:
    if timeframe_minutes not in VALID_TIMEFRAMES:
        raise ValueError("Unsupported candle timeframe")
    normalized: list[QuoteObservation] = []
    seen: set[tuple[str, str, float]] = set()
    for item in observations:
        if isinstance(item, QuoteObservation):
            obs = item
        else:
            ts = parse_ist_datetime(item.get("timestamp_ist") or item.get("quote_timestamp_ist"))
            obs = QuoteObservation(
                symbol=str(item.get("symbol") or "").strip().upper(),
                timestamp_ist=ts or now_ist(),
                price=_to_float(item.get("price") or item.get("ltp")),
                volume=int(_to_float(item.get("volume"), 0)) if item.get("volume") is not None else None,
                day_change_pct=item.get("day_change_pct"),
            )
        if not obs.symbol or obs.price <= 0:
            continue
        ts = obs.timestamp_ist.astimezone(IST)
        key = (obs.symbol, ts.isoformat(timespec="seconds"), obs.price)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(QuoteObservation(obs.symbol, ts, obs.price, obs.volume, obs.day_change_pct))
    normalized.sort(key=lambda obs: (obs.symbol, obs.timestamp_ist))
    current = (now or now_ist()).astimezone(IST)
    buckets: dict[tuple[str, datetime], list[QuoteObservation]] = {}
    for obs in normalized:
        minute = (obs.timestamp_ist.minute // timeframe_minutes) * timeframe_minutes
        bucket_start = obs.timestamp_ist.replace(minute=minute, second=0, microsecond=0)
        if bucket_start + timedelta(minutes=timeframe_minutes) > current:
            continue
        buckets.setdefault((obs.symbol, bucket_start), []).append(obs)
    candles: list[Candle] = []
    for (symbol, bucket_start), rows in sorted(buckets.items(), key=lambda item: item[0]):
        rows = sorted(rows, key=lambda obs: obs.timestamp_ist)
        volume = None if any(obs.volume is None for obs in rows) else sum(int(obs.volume or 0) for obs in rows)
        prices = [obs.price for obs in rows]
        candles.append(
            Candle(
                symbol=symbol,
                timestamp_ist=bucket_start,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=volume,
                complete=True,
            )
        )
    return candles


def summarize_quote_movement(observations: Iterable[QuoteObservation | dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    """Describe short-term stock movement; this is context, not an order signal."""
    points: list[tuple[datetime, float]] = []
    for item in observations:
        stamp = item.timestamp_ist if isinstance(item, QuoteObservation) else parse_ist_datetime(item.get("timestamp_ist"))
        price = item.price if isinstance(item, QuoteObservation) else _to_float(item.get("price"))
        if stamp and price > 0:
            points.append((stamp.astimezone(IST), price))
    points.sort(key=lambda point: point[0])
    current = (now or now_ist()).astimezone(IST)
    points = [point for point in points if point[0].date() == current.date() and point[0] <= current]
    if not points:
        return {"movement": "WAITING FOR QUOTES", "delta_pct": None, "minute_pct": None, "pullback_pct": None, "sample_count": 0}
    recent = points[-12:]
    last_time, last_price = recent[-1]
    age_seconds = max(0, (current - last_time).total_seconds())
    previous = recent[-2][1] if len(recent) > 1 else None
    minute_anchor = next((price for stamp, price in reversed(recent[:-1]) if stamp <= last_time - timedelta(seconds=50)), None)
    delta_pct = (last_price / previous - 1) * 100 if previous else None
    minute_pct = (last_price / minute_anchor - 1) * 100 if minute_anchor else None
    peak = max(price for _, price in recent)
    pullback_pct = (peak - last_price) / peak * 100 if peak else None
    movement = "BUILDING HISTORY"
    if age_seconds > 30:
        movement = "STALE QUOTE"
    elif len(recent) >= 4:
        last_three = [price for _, price in recent[-3:]]
        falling = last_three[0] > last_three[1] > last_three[2]
        if falling and pullback_pct >= 0.15:
            movement = "DECLINE STARTING"
        elif falling and pullback_pct >= 0.05:
            movement = "TOPPING WATCH"
        elif last_three[0] < last_three[1] < last_three[2]:
            movement = "STILL RISING"
        else:
            movement = "SIDEWAYS / MIXED"
    return {
        "movement": movement,
        "delta_pct": round(delta_pct, 3) if delta_pct is not None else None,
        "minute_pct": round(minute_pct, 3) if minute_pct is not None else None,
        "pullback_pct": round(pullback_pct, 3) if pullback_pct is not None else None,
        "sample_count": len(recent),
    }


def _resistance_zone(candles: list[Candle], config: SellOnRiseMonitorConfig, evaluation: dict[str, Any] | None) -> dict[str, Any]:
    latest = candles[-1]
    refs: list[tuple[str, float]] = []
    evaluation = evaluation or {}
    for label, key in (
        ("previous_close", "previous_close"),
        ("previous_day_low", "previous_day_low"),
        ("previous_day_close", "previous_day_close"),
        ("vwap", "vwap"),
        ("20_dma", "ema20"),
        ("50_dma", "ema50"),
        ("prior_breakdown", "previous_52w_high"),
    ):
        value = _to_float(evaluation.get(key))
        if value > 0:
            refs.append((label, value))
    opening = candles[: min(15, len(candles))]
    if opening:
        refs.append(("opening_range_low", min(c.low for c in opening)))
        refs.append(("opening_range_high", max(c.high for c in opening)))
    refs.append(("recent_swing_high", max(c.high for c in candles[-5:])))
    tolerance = max(latest.close * config.resistance_tolerance_percent / 100.0, latest.close * 0.001)
    near_refs = [(label, value) for label, value in refs if latest.close - tolerance * 2 <= value <= latest.close + tolerance * 2]
    chosen = near_refs or sorted(refs, key=lambda ref: abs(ref[1] - latest.close))[:2]
    values = [value for _, value in chosen if value > 0]
    if not values:
        return {"resistance_low": 0.0, "resistance_high": 0.0, "references": [], "confidence": "LOW"}
    low = min(values) - tolerance
    high = max(values) + tolerance
    confidence = "HIGH" if len(chosen) >= 3 else "MEDIUM" if len(chosen) >= 2 else "LOW"
    return {
        "resistance_low": round(low, 2),
        "resistance_high": round(high, 2),
        "references": [f"{label}:{value:.2f}" for label, value in chosen],
        "confidence": confidence,
    }


def _is_rejection(candle: Candle, resistance: dict[str, Any], previous: Candle | None) -> tuple[bool, str, list[str]]:
    r_low = _to_float(resistance.get("resistance_low"))
    r_high = _to_float(resistance.get("resistance_high"))
    if r_low <= 0 or r_high <= 0:
        return False, "", ["No valid resistance zone."]
    body = abs(candle.close - candle.open)
    upper_wick = candle.high - max(candle.open, candle.close)
    candle_range = max(candle.high - candle.low, 0.01)
    close_location = (candle.close - candle.low) / candle_range
    touched = candle.high >= r_low
    failed_close = candle.close <= r_high * 1.0015
    bearish_body = candle.close < candle.open
    upper_wick_ok = upper_wick >= max(body, candle_range * 0.20)
    close_weak = close_location <= 0.55
    engulfing = bool(previous and candle.open >= previous.close and candle.close < previous.open)
    ok = touched and failed_close and (upper_wick_ok or bearish_body or engulfing) and close_weak
    pattern = "BEARISH_ENGULFING" if engulfing else "FAILED_BREAKOUT" if candle.high > r_high else "SHOOTING_STAR" if upper_wick_ok else "LOWER_HIGH_REVERSAL"
    reasons = [
        f"touch={touched}",
        f"failed_close={failed_close}",
        f"upper_wick/body={upper_wick:.2f}/{body:.2f}",
        f"close_location={close_location:.2f}",
    ]
    return ok, pattern if ok else "", reasons


def evaluate_pattern(
    symbol: str,
    candles: list[Candle | dict[str, Any]],
    config: SellOnRiseMonitorConfig | dict[str, Any],
    *,
    evaluation: dict[str, Any] | None = None,
    existing_state: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    cfg = config if isinstance(config, SellOnRiseMonitorConfig) else SellOnRiseMonitorConfig.from_dict(config)
    clean_symbol = str(symbol or "").strip().upper()
    normalized: list[Candle] = []
    for candle in candles:
        if isinstance(candle, Candle):
            normalized.append(candle)
        else:
            ts = parse_ist_datetime(candle.get("timestamp_ist"))
            normalized.append(
                Candle(
                    symbol=str(candle.get("symbol") or clean_symbol).strip().upper(),
                    timestamp_ist=ts or now_ist(),
                    open=_to_float(candle.get("open")),
                    high=_to_float(candle.get("high")),
                    low=_to_float(candle.get("low")),
                    close=_to_float(candle.get("close")),
                    volume=int(_to_float(candle.get("volume"), 0)) if candle.get("volume") is not None else None,
                    complete=bool(candle.get("complete", True)),
                )
            )
    normalized = [c for c in normalized if c.symbol == clean_symbol and c.complete and c.open > 0 and c.high > 0 and c.low > 0 and c.close > 0]
    normalized.sort(key=lambda c: c.timestamp_ist)
    stamp = (now or now_ist()).astimezone(IST)
    state = dict(existing_state or {})
    warnings: list[str] = []
    vetoes: list[str] = []
    phase = "OBSERVING"
    decision = "OBSERVE"
    pattern: dict[str, Any] = {
        "initial_high": 0.0,
        "confirmed_low": 0.0,
        "initial_decline_percent": 0.0,
        "rebound_percent": 0.0,
        "resistance_low": 0.0,
        "resistance_high": 0.0,
        "resistance_references": [],
        "rejection_type": "",
        "rejection_timestamp": "",
        "rejection_high": 0.0,
        "rejection_low": 0.0,
        "confirmation_level": 0.0,
        "confirmation_timestamp": "",
        "confidence": "LOW",
        "_candle_count": len(normalized),
    }
    if len(normalized) < cfg.minimum_candles_before_pattern:
        return _pattern_result(clean_symbol, stamp, phase, decision, pattern, warnings + ["Need more completed candles."], vetoes)
    initial_high = max(c.high for c in normalized)
    high_index = next(i for i, c in enumerate(normalized) if c.high == initial_high)
    low_after_high = min(c.low for c in normalized[high_index:])
    pattern["initial_high"] = round(initial_high, 2)
    pattern["confirmed_low"] = round(low_after_high, 2)
    decline_pct = (initial_high - low_after_high) / initial_high * 100.0 if initial_high else 0.0
    pattern["initial_decline_percent"] = round(decline_pct, 2)
    existing_52w_breakdown = str((evaluation or {}).get("state") or "").upper() in {"FAILED_BREAKOUT", "NEAR_HIGH_REJECTION"}
    if decline_pct < cfg.minimum_initial_decline_percent and not existing_52w_breakdown:
        return _pattern_result(clean_symbol, stamp, phase, "WAIT_FOR_REBOUND", pattern, warnings + ["Initial weakness not established."], vetoes)
    phase = "INITIAL_MOVE_IDENTIFIED"
    low_index = next(i for i, c in enumerate(normalized) if c.low == low_after_high)
    after_low = normalized[low_index:]
    if len(after_low) < cfg.minimum_rebound_candles:
        return _pattern_result(clean_symbol, stamp, phase, "WAIT_FOR_REBOUND", pattern, ["Waiting for rebound candles."], vetoes)
    latest = normalized[-1]
    rebound_pct = (latest.close - low_after_high) / low_after_high * 100.0 if low_after_high else 0.0
    pattern["rebound_percent"] = round(rebound_pct, 2)
    if rebound_pct < cfg.minimum_rebound_percent_from_intraday_low:
        return _pattern_result(clean_symbol, stamp, phase, "WAIT_FOR_REBOUND", pattern, ["Controlled rebound not yet present."], vetoes)
    phase = "REBOUND_IN_PROGRESS"
    resistance = _resistance_zone(normalized, cfg, evaluation)
    pattern["resistance_low"] = resistance["resistance_low"]
    pattern["resistance_high"] = resistance["resistance_high"]
    pattern["resistance_references"] = resistance["references"]
    pattern["confidence"] = resistance["confidence"]
    if resistance["resistance_low"] <= 0:
        return _pattern_result(clean_symbol, stamp, "INVALIDATED", "ORDER_BLOCKED", pattern, warnings, ["NO_RESISTANCE_REFERENCE"])
    if latest.high < resistance["resistance_low"]:
        return _pattern_result(clean_symbol, stamp, phase, "NEAR_RESISTANCE", pattern, ["Rebound has not tested resistance yet."], vetoes)
    phase = "RESISTANCE_TEST"
    rejection_index = None
    rejection_type = ""
    rejection_reasons: list[str] = []
    # Rejection must happen after the confirmed low and the configured rebound
    # candles.  Earlier selloff candles cannot be reused as the rejection leg.
    rebound_ready_index = low_index + cfg.minimum_rebound_candles
    start = max(1, rebound_ready_index, len(normalized) - (cfg.confirmation_must_occur_within_candles + 2))
    for idx in range(start, len(normalized)):
        ok, candle_type, reasons = _is_rejection(normalized[idx], resistance, normalized[idx - 1] if idx > 0 else None)
        if ok:
            rejection_index = idx
            rejection_type = candle_type
            rejection_reasons = reasons
            break
    if rejection_index is None:
        return _pattern_result(clean_symbol, stamp, phase, "REJECTION_CANDIDATE", pattern, ["Resistance touched; waiting for rejection candle."], vetoes)
    rejection = normalized[rejection_index]
    phase = "REJECTION_CANDIDATE"
    pattern.update(
        {
            "rejection_type": rejection_type,
            "rejection_timestamp": rejection.timestamp_ist.isoformat(timespec="seconds"),
            "rejection_high": round(rejection.high, 2),
            "rejection_low": round(rejection.low, 2),
        }
    )
    if any(c.close > rejection.high for c in normalized[rejection_index + 1 :]):
        return _pattern_result(clean_symbol, stamp, "INVALIDATED", "INVALIDATED", pattern, rejection_reasons, ["PRICE_BROKE_REJECTION_HIGH"])
    buffer = max(rejection.close * cfg.confirmation_buffer_percent / 100.0, 0.01)
    confirmation_level = rejection.low - buffer
    pattern["confirmation_level"] = round(confirmation_level, 2)
    confirmation_window = normalized[rejection_index + 1 : rejection_index + 1 + cfg.confirmation_must_occur_within_candles]
    for candle in confirmation_window:
        if candle.low <= confirmation_level or candle.close <= confirmation_level:
            pattern["confirmation_timestamp"] = candle.timestamp_ist.isoformat(timespec="seconds")
            signal_key = signal_idempotency_key(
                trading_date=stamp.date().isoformat(),
                monitor_session_id=str(state.get("monitor_session_id") or ""),
                symbol=clean_symbol,
                expiry=cfg.expiry,
                rejection_timestamp=pattern["rejection_timestamp"],
                confirmation_timestamp=pattern["confirmation_timestamp"],
                short_strike=str(state.get("short_strike") or ""),
                hedge_strike=str(state.get("hedge_strike") or ""),
            )
            return _pattern_result(
                clean_symbol,
                stamp,
                "REJECTION_CONFIRMED",
                "SELL_SIGNAL",
                pattern,
                rejection_reasons,
                vetoes,
                signal_key=signal_key,
                order_allowed=False,
            )
    if len(normalized) - rejection_index - 1 >= cfg.confirmation_must_occur_within_candles:
        return _pattern_result(clean_symbol, stamp, "EXPIRED", "INVALIDATED", pattern, rejection_reasons, ["CONFIRMATION_EXPIRED"])
    return _pattern_result(clean_symbol, stamp, phase, "WAIT_FOR_CONFIRMATION", pattern, rejection_reasons, vetoes)


def _pattern_result(
    symbol: str,
    generated_at: datetime,
    phase: str,
    decision: str,
    pattern: dict[str, Any],
    warnings: list[str],
    vetoes: list[str],
    *,
    signal_key: str = "",
    order_allowed: bool = False,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "generated_at_ist": generated_at.astimezone(IST).isoformat(timespec="seconds"),
        "quote_timestamp_ist": generated_at.astimezone(IST).isoformat(timespec="seconds"),
        "pattern_state": phase if phase in MONITOR_PHASES else "OBSERVING",
        "pattern": pattern,
        "candle_count": int(pattern.get("_candle_count") or 0),
        "risk_gates": {},
        "warnings": warnings,
        "hard_vetoes": vetoes,
        "decision": decision,
        "signal_key": signal_key,
        "order_allowed": bool(order_allowed and not vetoes),
    }


def signal_idempotency_key(
    *,
    trading_date: str,
    monitor_session_id: str,
    symbol: str,
    expiry: str,
    rejection_timestamp: str,
    confirmation_timestamp: str,
    short_strike: str,
    hedge_strike: str,
) -> str:
    payload = "|".join(
        [
            trading_date,
            monitor_session_id,
            symbol.upper(),
            expiry,
            rejection_timestamp,
            confirmation_timestamp,
            short_strike,
            hedge_strike,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SellOnRiseMonitorRepository:
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
                CREATE TABLE IF NOT EXISTS sell_on_rise_monitor_config (
                    config_id TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    config_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sell_on_rise_monitor_session (
                    session_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    trading_date TEXT NOT NULL,
                    started_at TEXT,
                    expected_end_at TEXT,
                    next_scan_at TEXT,
                    scans_completed INTEGER NOT NULL DEFAULT 0,
                    api_failures INTEGER NOT NULL DEFAULT 0,
                    signals_generated INTEGER NOT NULL DEFAULT 0,
                    previews_generated INTEGER NOT NULL DEFAULT 0,
                    orders_submitted INTEGER NOT NULL DEFAULT 0,
                    orders_blocked INTEGER NOT NULL DEFAULT 0,
                    config_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sell_on_rise_quote_observation (
                    observation_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timestamp_ist TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume INTEGER,
                    day_change_pct REAL,
                    UNIQUE(session_id, symbol, timestamp_ist, price)
                );
                CREATE TABLE IF NOT EXISTS sell_on_rise_pattern_state (
                    session_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(session_id, symbol)
                );
                CREATE TABLE IF NOT EXISTS sell_on_rise_signal (
                    signal_key TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    signal_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sell_on_rise_audit_event (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    symbol TEXT,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_config(self, config: SellOnRiseMonitorConfig | dict[str, Any]) -> None:
        cfg = config if isinstance(config, SellOnRiseMonitorConfig) else SellOnRiseMonitorConfig.from_dict(config)
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sell_on_rise_monitor_config(config_id, updated_at, config_json) VALUES ('default', ?, ?)",
                (ist_text(), json.dumps(cfg.to_dict(), default=str)),
            )

    def load_config(self) -> SellOnRiseMonitorConfig:
        with self.connect() as conn:
            row = conn.execute("SELECT config_json FROM sell_on_rise_monitor_config WHERE config_id='default'").fetchone()
        return SellOnRiseMonitorConfig.from_dict(json.loads(row["config_json"])) if row else SellOnRiseMonitorConfig()

    def latest_session(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sell_on_rise_monitor_session ORDER BY updated_at DESC LIMIT 1").fetchone()
        return self._session_row(row) if row else None

    def create_or_update_session(self, config: SellOnRiseMonitorConfig, *, start_now: bool, status: str = "MONITORING") -> dict[str, Any]:
        start_reference = now_ist() if start_now else None
        window = monitoring_window(config, trading_day=now_ist().date(), started_now_at=start_reference)
        started_at = window["actual_start_timestamp_ist"]
        end_at = window["expected_end_timestamp_ist"]
        key_payload = json.dumps({"day": now_ist().date().isoformat(), "symbols": config.selected_symbols, "start": started_at}, sort_keys=True)
        session_id = f"SOR-{hashlib.sha256(key_payload.encode('utf-8')).hexdigest()[:16]}"
        next_scan = now_ist() + timedelta(seconds=config.quote_check_interval_seconds)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sell_on_rise_monitor_session(
                    session_id, status, trading_date, started_at, expected_end_at, next_scan_at,
                    config_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    status,
                    now_ist().date().isoformat(),
                    started_at,
                    end_at,
                    next_scan.isoformat(timespec="seconds"),
                    json.dumps(config.to_dict(), default=str),
                    ist_text(),
                ),
            )
        self.audit(session_id, "", "SESSION", f"{status}: {','.join(config.selected_symbols)}", window)
        return self.latest_session() or {}

    def stop_session(self, session_id: str | None = None) -> None:
        session = self.latest_session() if not session_id else {"session_id": session_id}
        if not session:
            return
        with self.connect() as conn:
            conn.execute(
                "UPDATE sell_on_rise_monitor_session SET status='STOPPED_BY_USER', updated_at=? WHERE session_id=?",
                (ist_text(), session["session_id"]),
            )
        self.audit(session["session_id"], "", "STOP", "Monitor stopped by user.", {})

    def reset_today(self) -> int:
        today = now_ist().date().isoformat()
        with self.connect() as conn:
            rows = conn.execute("SELECT session_id FROM sell_on_rise_monitor_session WHERE trading_date=?", (today,)).fetchall()
            session_ids = [row["session_id"] for row in rows]
            deleted = 0
            for session_id in session_ids:
                for table in ("sell_on_rise_quote_observation", "sell_on_rise_pattern_state", "sell_on_rise_signal"):
                    cursor = conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
                    deleted += int(cursor.rowcount or 0)
                conn.execute("UPDATE sell_on_rise_monitor_session SET status='STOPPED_BY_USER', updated_at=? WHERE session_id=?", (ist_text(), session_id))
        return deleted

    def save_observations(self, session_id: str, observations: list[QuoteObservation]) -> int:
        count = 0
        with self.connect() as conn:
            for obs in observations:
                observation_id = hashlib.sha256(
                    f"{session_id}|{obs.symbol}|{obs.timestamp_ist.isoformat()}|{obs.price}".encode("utf-8")
                ).hexdigest()
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO sell_on_rise_quote_observation(
                        observation_id, session_id, symbol, timestamp_ist, price, volume, day_change_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation_id,
                        session_id,
                        obs.symbol,
                        obs.timestamp_ist.astimezone(IST).isoformat(timespec="seconds"),
                        obs.price,
                        obs.volume,
                        obs.day_change_pct,
                    ),
                )
                count += int(cursor.rowcount or 0)
        return count

    def observations(self, session_id: str, symbol: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT symbol, timestamp_ist, price, volume, day_change_pct FROM sell_on_rise_quote_observation WHERE session_id=? AND symbol=? ORDER BY timestamp_ist",
                (session_id, symbol.upper()),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_observations(self, session_id: str) -> dict[str, dict[str, Any]]:
        """Return the latest stored quote observation for each monitored symbol."""

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT q.symbol, q.timestamp_ist, q.price, q.volume, q.day_change_pct
                FROM sell_on_rise_quote_observation q
                INNER JOIN (
                    SELECT symbol, MAX(timestamp_ist) AS timestamp_ist
                    FROM sell_on_rise_quote_observation
                    WHERE session_id=?
                    GROUP BY symbol
                ) latest
                  ON latest.symbol = q.symbol AND latest.timestamp_ist = q.timestamp_ist
                WHERE q.session_id=?
                ORDER BY q.symbol
                """,
                (session_id, session_id),
            ).fetchall()
        return {
            str(row["symbol"] or "").upper(): {
                "ltp": row["price"],
                "day_change_pct": row["day_change_pct"],
                "quote_timestamp_ist": row["timestamp_ist"],
                "volume": row["volume"],
            }
            for row in rows
        }

    def save_pattern_state(self, session_id: str, symbol: str, result: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sell_on_rise_pattern_state(session_id, symbol, state_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, symbol.upper(), json.dumps(result, default=str), ist_text()),
            )

    def latest_pattern_states(self, session_id: str) -> dict[str, dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT symbol, state_json FROM sell_on_rise_pattern_state WHERE session_id=? ORDER BY symbol", (session_id,)).fetchall()
        return {row["symbol"]: json.loads(row["state_json"] or "{}") for row in rows}

    def create_signal_once(self, session_id: str, result: dict[str, Any]) -> bool:
        key = str(result.get("signal_key") or "")
        if not key:
            return False
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO sell_on_rise_signal(signal_key, session_id, symbol, status, signal_json, created_at, updated_at)
                VALUES (?, ?, ?, 'NEW', ?, ?, ?)
                """,
                (key, session_id, str(result.get("symbol") or ""), json.dumps(result, default=str), ist_text(), ist_text()),
            )
            created = int(cursor.rowcount or 0) == 1
            if created:
                conn.execute(
                    "UPDATE sell_on_rise_monitor_session SET signals_generated=signals_generated+1, status='SIGNAL_DETECTED', updated_at=? WHERE session_id=?",
                    (ist_text(), session_id),
                )
        if created:
            self.audit(session_id, str(result.get("symbol") or ""), "SIGNAL", "Confirmed sell-on-rise rejection signal.", result)
        return created

    def audit(self, session_id: str | None, symbol: str | None, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        stamp = ist_text()
        event_id = hashlib.sha256(f"{stamp}|{session_id}|{symbol}|{event_type}|{message}".encode("utf-8")).hexdigest()
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sell_on_rise_audit_event(event_id, session_id, symbol, event_type, message, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, session_id, symbol, event_type, message, json.dumps(payload or {}, default=str), stamp),
            )

    def audit_rows(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sell_on_rise_audit_event ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_audit_rows(self) -> int:
        """Clear only local Sell-on-Rise audit/log rows.

        This does not touch monitor configuration, pattern state, quote
        observations, signals, pair-order monitor rows, or broker orders.
        """

        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM sell_on_rise_audit_event")
        return int(cursor.rowcount or 0)

    def increment_scan(self, session_id: str, *, api_failures: int = 0, interval_seconds: int = 10) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sell_on_rise_monitor_session
                SET scans_completed=scans_completed+1,
                    api_failures=api_failures+?,
                    next_scan_at=?,
                    updated_at=?
                WHERE session_id=?
                """,
                (
                    api_failures,
                    (now_ist() + timedelta(seconds=max(5, int(interval_seconds or 10)))).isoformat(timespec="seconds"),
                    ist_text(),
                    session_id,
                ),
            )

    def increment_preview(self, session_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE sell_on_rise_monitor_session SET previews_generated=previews_generated+1, status='ORDER_PENDING_CONFIRMATION', updated_at=? WHERE session_id=?",
                (ist_text(), session_id),
            )

    def _session_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["config"] = SellOnRiseMonitorConfig.from_dict(json.loads(item.get("config_json") or "{}")).to_dict()
        item.pop("config_json", None)
        return item


def build_monitor_rows(
    config: SellOnRiseMonitorConfig,
    session: dict[str, Any] | None,
    states: dict[str, dict[str, Any]],
    evaluations_by_symbol: dict[str, dict[str, Any]],
    latest_quotes: dict[str, dict[str, Any]] | None = None,
    quote_history: dict[str, list[dict[str, Any]]] | None = None,
    option_symbols: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    latest_quotes = latest_quotes or {}
    quote_history = quote_history or {}
    option_symbols = option_symbols or {}
    for symbol in config.selected_symbols:
        result = states.get(symbol) or {}
        pattern = result.get("pattern") if isinstance(result.get("pattern"), dict) else {}
        quote = latest_quotes.get(symbol) or {}
        movement = summarize_quote_movement(quote_history.get(symbol) or [])
        option_symbol = option_symbols.get(symbol, "")
        option_points = quote_history.get(option_symbol) or []
        option_movement = summarize_quote_movement(option_points)
        evaluation = evaluations_by_symbol.get(symbol) or {}
        latest_price = quote.get("ltp") or evaluation.get("live_cmp") or 0
        latest_quote_time = quote.get("quote_timestamp_ist") or result.get("quote_timestamp_ist") or "-"
        phase = str(result.get("pattern_state") or "OBSERVING")
        decision = str(result.get("decision") or "OBSERVE")
        if str(evaluation.get("decision") or "").upper() in {"BLOCKED", "DATA_ERROR"}:
            decision = "ORDER_BLOCKED"
            result.setdefault("hard_vetoes", []).append("52W_EVALUATION_NOT_APPROVED")
        rows.append(
            {
                "symbol": symbol,
                "spot": latest_price,
                "day_change_pct": quote.get("day_change_pct"),
                "quote_timestamp_ist": latest_quote_time,
                **movement,
                "option_symbol": option_symbol,
                "option_ltp": option_points[-1].get("price") if option_points else None,
                "option_movement": option_movement,
                "pattern_phase": phase,
                "initial_decline": pattern.get("initial_decline_percent", 0),
                "rebound": pattern.get("rebound_percent", 0),
                "resistance": (
                    f"{pattern.get('resistance_low', 0)}-{pattern.get('resistance_high', 0)}"
                    if pattern.get("resistance_low")
                    else "-"
                ),
                "rejection": pattern.get("rejection_type") or "-",
                "confirmation": pattern.get("confirmation_timestamp") or "-",
                "short_ce": f"{config.short_call_otm_percent:.1f}% OTM",
                "hedge_ce": f"{config.protective_call_otm_percent:.1f}% OTM",
                "lots": config.number_of_lots,
                "decision": decision,
                "last_scan": result.get("generated_at_ist") or "-",
                "candle_count": result.get("candle_count") or 0,
                "why": "; ".join([*(result.get("warnings") or []), *(result.get("hard_vetoes") or [])]) or "Waiting for next completed candle.",
                "signal_key": result.get("signal_key") or "",
            }
        )
    return rows
