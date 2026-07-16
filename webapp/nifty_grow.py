from __future__ import annotations

import csv
import io
import math
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


NIFTY_GROW_DEFAULT_CONFIG: dict[str, Any] = {
    "nifty_expiry_optimizer": {
        "enabled": True,
        "expiry_buckets": [
            {"name": "SHORT_2W", "min_dte": 14, "max_dte": 17, "allowed": True},
            {"name": "PREFERRED_3W", "min_dte": 18, "max_dte": 24, "allowed": True, "preferred": True},
            {"name": "LONG_4W", "min_dte": 25, "max_dte": 32, "allowed": True},
        ],
        "preferred_bucket": "PREFERRED_3W",
        "min_credit_pct_of_spread_width": 8.0,
        "preferred_credit_pct_of_spread_width": 10.0,
        "excellent_credit_pct_of_spread_width": 12.0,
        "min_liquidity_score": 70,
        "min_confidence_score": 70,
        "skip_if_no_expiry_passes": True,
    },
    "nifty_liquidity_filter": {
        "enabled": True,
        "min_oi": 10000,
        "preferred_oi": 25000,
        "min_volume": 500,
        "preferred_volume": 1500,
        "max_bid_ask_spread_pct": 8.0,
        "preferred_bid_ask_spread_pct": 5.0,
        "min_ltp_points": 5.0,
        "reject_zero_bid": True,
        "reject_missing_ltp": True,
        "reject_stale_quote": True,
        "max_quote_age_seconds": 60,
        "min_liquidity_score": 70,
    },
    "nifty_nearest_tradeable_strike": {
        "enabled": True,
        "strike_step_points": 100,
        "max_adjustment_points": 200,
        "min_oi": 10000,
        "min_volume": 10,
    },
    "nifty_3w_tactical_engine": {
        "enabled": True,
        "preferred_dte_min": 18,
        "preferred_dte_max": 24,
        "short_delta_min": 0.10,
        "short_delta_max": 0.16,
        "absolute_max_short_delta": 0.18,
        "hedge_delta_min": 0.03,
        "hedge_delta_max": 0.06,
        "spread_widths_to_scan": [300, 400, 500, 600],
        "min_credit_pct_of_width": 8.0,
        "preferred_credit_pct_of_width": 10.0,
        "excellent_credit_pct_of_width": 12.0,
        "expected_move_min_multiple": 1.2,
        "expected_move_conservative_multiple": 1.5,
        "profit_booking_credit_decay_pct": 55.0,
        "stop_loss_credit_multiple": 1.5,
        "max_stop_loss_credit_multiple": 1.75,
    },
    "nifty_probability_risk": {
        "enabled": True,
        "max_probability_touch_for_entry_pct": 35.0,
        "review_probability_touch_pct": 45.0,
        "exit_probability_touch_pct": 50.0,
        "force_exit_dte": 7,
        "max_short_delta_for_entry": 0.18,
        "emergency_short_delta": 0.25,
    },
    "nifty_credit_quality": {
        "enabled": True,
        "min_credit_pct_of_width": 8.0,
        "preferred_credit_pct_of_width": 10.0,
        "excellent_credit_pct_of_width": 12.0,
        "max_loss_to_credit_ratio_max": 4.0,
        "strict_max_loss_to_credit_ratio": False,
        "min_premium_yield_on_margin_pct": 0.8,
        "preferred_premium_yield_on_margin_pct": 1.0,
    },
    "nifty_3w_exit_policy": {
        "enabled": True,
        "profit_booking_credit_decay_pct": 55.0,
        "stop_loss_credit_multiple": 1.5,
        "day_0_to_5_credit_decay_target_pct": 30.0,
        "day_6_to_12_credit_decay_target_pct": 45.0,
        "day_13_plus_credit_decay_target_pct": 55.0,
        "force_exit_dte": 7,
        "monitor_every_minutes": 15,
        "emergency_short_premium_multiple": 2.0,
        "emergency_short_delta": 0.25,
        "emergency_probability_touch_pct": 50.0,
    },
    "nifty_execution_quality_guard": {
        "enabled": True,
        "min_confidence_for_live_order": 70,
        "min_realistic_credit_pct_of_width": 8.0,
        "preferred_realistic_credit_pct_of_width": 10.0,
        "excellent_realistic_credit_pct_of_width": 12.0,
        "min_realistic_premium_yield_on_margin_pct": 0.8,
        "paper_trap_max_optimistic_vs_realistic_gap_pct": 25.0,
        "paper_trap_max_ltp_vs_bidask_gap_pct": 20.0,
        "preview_allowed_with_ltp_only": True,
        "reject_live_if_ltp_only": True,
        "reject_missing_bid_ask": True,
        "reject_zero_bid": True,
        "min_oi_for_live": 10000,
        "min_volume_for_live": 10,
        "max_bid_ask_spread_pct": 8.0,
        "max_live_sell_markup_pct": 5.0,
        "max_live_buy_discount_pct": 3.0,
        "require_delta_for_live": True,
        "max_short_delta_for_income": 0.18,
        "reject_short_delta_above": 0.22,
        "max_probability_touch_pct": 35.0,
        "max_loss_mismatch_pct": 5.0,
        # Kept false because Kite margin verification is profile/session-dependent.
        # When enabled, Nifty Grow becomes preview-only unless broker margin is attached.
        "require_broker_verified_margin": False,
        "hedge_first_required": True,
        "no_naked_nifty_sell": True,
    },
}


@dataclass(frozen=True)
class NiftyGrowDecision:
    selected_expiry: date | None
    selected_dte: int | None
    selected_bucket: str
    expiry_score: float
    reason: str
    all_expiry_candidates: list[dict[str, Any]]


@dataclass(frozen=True)
class ExecutionQualityResult:
    data_quality: str
    optimistic_credit_points: float
    ltp_credit_points: float
    realistic_credit_points: float
    optimistic_credit_value: float
    ltp_credit_value: float
    realistic_credit_value: float
    optimistic_vs_realistic_gap_pct: float
    ltp_vs_bidask_gap_pct: float
    credit_pct_of_width: float
    premium_yield_on_margin_pct: float
    min_bid: float
    max_ask: float
    quote_warnings: list[str]
    reason_codes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PaperTrapDecision:
    allowed: bool
    decision: str
    reason_codes: list[str]
    warnings: list[str]
    human_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MaxLossValidation:
    accepted: bool
    expected_max_loss: float
    app_reported_max_loss: float
    mismatch_pct: float
    reason_codes: list[str]
    human_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NiftyLiveOrderGate:
    allowed: bool
    action: str
    status: str
    reason_codes: list[str]
    warnings: list[str]
    human_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _merge_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = deepcopy(NIFTY_GROW_DEFAULT_CONFIG)
    if not config:
        return merged
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "N/A", "--"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "", "N/A", "--"):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value.strip():
        text = value.strip()[:10]
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    return None


def _now(config: dict[str, Any] | None = None) -> datetime:
    configured = (config or {}).get("_now")
    if isinstance(configured, datetime):
        return configured
    return datetime.now()


def _dte(expiry: Any, today: date | None = None) -> int | None:
    expiry_date = _date(expiry)
    if not expiry_date:
        return None
    return (expiry_date - (today or date.today())).days


def _round_tick(value: float, tick: float = 0.05) -> float:
    if value <= 0:
        return 0.0
    return round(round(value / tick) * tick, 2)


def _spread_pct(bid: float, ask: float, ltp: float) -> float:
    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else ltp
    if mid <= 0:
        return 999.0
    return (ask - bid) / mid * 100


def _quote_age_seconds(quote: dict[str, Any], config: dict[str, Any] | None = None) -> float | None:
    timestamp = (
        quote.get("quote_timestamp")
        or quote.get("timestamp")
        or quote.get("last_trade_time")
        or quote.get("last_price_time")
    )
    if not timestamp:
        return None
    if isinstance(timestamp, str):
        try:
            timestamp_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None
    elif isinstance(timestamp, datetime):
        timestamp_dt = timestamp
    else:
        return None
    now = _now(config)
    if timestamp_dt.tzinfo and now.tzinfo is None:
        now = now.replace(tzinfo=timestamp_dt.tzinfo)
    if now.tzinfo and timestamp_dt.tzinfo is None:
        timestamp_dt = timestamp_dt.replace(tzinfo=now.tzinfo)
    return max(0.0, (now - timestamp_dt).total_seconds())


def _bucket_for_dte(dte: int | None, config: dict[str, Any]) -> dict[str, Any] | None:
    if dte is None:
        return None
    for bucket in config["nifty_expiry_optimizer"]["expiry_buckets"]:
        if _int(bucket.get("min_dte")) <= dte <= _int(bucket.get("max_dte")):
            return bucket
    return None


def calculate_option_liquidity_score(option_quote: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _merge_config(config)
    liq_cfg = cfg["nifty_liquidity_filter"]
    ltp = _float(option_quote.get("ltp") or option_quote.get("last_price") or option_quote.get("option_ltp"))
    bid = _float(option_quote.get("bid") or option_quote.get("best_bid"))
    ask = _float(option_quote.get("ask") or option_quote.get("best_ask"))
    oi = _int(option_quote.get("oi") or option_quote.get("open_interest"))
    volume = _int(option_quote.get("volume") or option_quote.get("day_volume"))
    delta_present = option_quote.get("delta") not in (None, "", "N/A")
    iv_present = option_quote.get("iv") not in (None, "", "N/A")
    reasons: list[str] = []
    warnings: list[str] = []
    allowed = True

    if ltp <= 0:
        reasons.append("MISSING_LTP")
        allowed = not liq_cfg.get("reject_missing_ltp", True)
    if ltp < _float(liq_cfg.get("min_ltp_points"), 5.0):
        reasons.append("LTP_BELOW_MIN")
        allowed = False
    if bid <= 0:
        reasons.append("ZERO_BID")
        if liq_cfg.get("reject_zero_bid", True):
            allowed = False
    if ask <= 0:
        reasons.append("MISSING_ASK")
        allowed = False
    spread_pct = _spread_pct(bid, ask, ltp)
    if spread_pct > _float(liq_cfg.get("max_bid_ask_spread_pct"), 8.0):
        reasons.append("WIDE_BID_ASK")
        allowed = False
    if oi < _int(liq_cfg.get("min_oi"), 10000):
        reasons.append("LOW_OI")
        allowed = False
    if volume < _int(liq_cfg.get("min_volume"), 500):
        reasons.append("LOW_VOLUME")
        allowed = False
    quote_age = _quote_age_seconds(option_quote, cfg)
    if quote_age is None:
        warnings.append("MISSING_QUOTE_TIMESTAMP")
        if liq_cfg.get("reject_stale_quote", True):
            reasons.append("MISSING_QUOTE_TIMESTAMP")
            allowed = False
    elif quote_age > _float(liq_cfg.get("max_quote_age_seconds"), 60):
        reasons.append("STALE_QUOTE")
        allowed = False
    if not delta_present:
        warnings.append("MISSING_DELTA")
    if not iv_present:
        warnings.append("MISSING_IV")

    oi_score = min(25.0, max(0.0, oi / max(1, _int(liq_cfg.get("preferred_oi"), 25000)) * 25.0))
    volume_score = min(20.0, max(0.0, volume / max(1, _int(liq_cfg.get("preferred_volume"), 1500)) * 20.0))
    spread_score = 0.0
    if bid > 0 and ask > 0:
        preferred_spread = _float(liq_cfg.get("preferred_bid_ask_spread_pct"), 5.0)
        max_spread = _float(liq_cfg.get("max_bid_ask_spread_pct"), 8.0)
        if spread_pct <= preferred_spread:
            spread_score = 25.0
        elif spread_pct <= max_spread:
            spread_score = 25.0 * (max_spread - spread_pct) / max(0.01, max_spread - preferred_spread)
    freshness_score = 15.0 if quote_age is not None and quote_age <= _float(liq_cfg.get("max_quote_age_seconds"), 60) else 0.0
    greek_score = (5.0 if delta_present else 0.0) + (5.0 if iv_present else 0.0)
    ltp_score = 5.0 if ltp >= _float(liq_cfg.get("min_ltp_points"), 5.0) else 0.0
    score = round(min(100.0, oi_score + volume_score + spread_score + freshness_score + greek_score + ltp_score), 2)
    if score < _float(liq_cfg.get("min_liquidity_score"), 70):
        reasons.append("LIQUIDITY_SCORE_BELOW_MIN")
        allowed = False

    return {
        "score": score,
        "allowed": bool(allowed),
        "status": "PASS" if allowed else "REJECT",
        "reasons": sorted(set(reasons)),
        "warnings": sorted(set(warnings)),
        "bid_ask_spread_pct": round(spread_pct, 2),
        "quote_age_seconds": None if quote_age is None else round(quote_age, 2),
        "ltp": ltp,
        "bid": bid,
        "ask": ask,
        "oi": oi,
        "volume": volume,
    }


def filter_liquid_nifty_strikes(option_chain: list[dict[str, Any]], config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    liquid: list[dict[str, Any]] = []
    for row in option_chain:
        score = calculate_option_liquidity_score(row, config)
        enriched = {**row, "liquidity": score, "liquidity_score": score["score"], "liquidity_status": score["status"]}
        if score["allowed"]:
            liquid.append(enriched)
    return liquid


def select_best_nifty_expiry(
    option_chain_by_expiry: dict[Any, list[dict[str, Any]]],
    market_state: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = _merge_config(config)
    opt_cfg = cfg["nifty_expiry_optimizer"]
    today = _date(market_state.get("today")) or date.today()
    candidates: list[dict[str, Any]] = []
    for expiry_key, rows in option_chain_by_expiry.items():
        expiry = _date(expiry_key)
        dte = _dte(expiry, today)
        bucket = _bucket_for_dte(dte, cfg)
        row_liquidity = [calculate_option_liquidity_score(row, cfg) for row in rows]
        liquidity_score = round(sum(item["score"] for item in row_liquidity) / max(1, len(row_liquidity)), 2)
        expected_move = _float(market_state.get("expected_move_points") or market_state.get("expected_move"), 0)
        credit_quality = _float(max((_float(row.get("credit_pct_of_width") or row.get("credit_pct_of_spread_width")) for row in rows), default=0.0))
        reasons: list[str] = []
        allowed = True
        if not expiry or dte is None:
            allowed = False
            reasons.append("EXPIRY_MISSING")
        if not bucket:
            allowed = False
            reasons.append("DTE_OUTSIDE_BUCKETS")
            bucket_name = "OUTSIDE"
        else:
            bucket_name = str(bucket.get("name") or "UNKNOWN")
            if not bucket.get("allowed", True):
                allowed = False
                reasons.append("BUCKET_DISABLED")
        if liquidity_score < _float(opt_cfg.get("min_liquidity_score"), 70):
            allowed = False
            reasons.append("LIQUIDITY_BELOW_MIN")
        if credit_quality and credit_quality < _float(opt_cfg.get("min_credit_pct_of_spread_width"), 8.0):
            allowed = False
            reasons.append("CREDIT_BELOW_MIN")
        elif not credit_quality:
            reasons.append("CREDIT_UNKNOWN")
        if bucket_name == "LONG_4W" and credit_quality and credit_quality < _float(opt_cfg.get("preferred_credit_pct_of_spread_width"), 10.0):
            allowed = False
            reasons.append("LONG_4W_PREMIUM_WEAK")
        if bucket_name == "SHORT_2W" and (
            str(market_state.get("event_risk_status") or "").upper() in {"HIGH", "EVENT", "BLOCK"}
            or bool(market_state.get("gamma_risk_high"))
        ):
            allowed = False
            reasons.append("SHORT_2W_GAMMA_OR_EVENT_RISK")

        score = liquidity_score * 0.55 + min(100.0, credit_quality * 6.0) * 0.35 + (10.0 if expected_move > 0 else 0.0)
        if bucket_name == opt_cfg.get("preferred_bucket"):
            score += 8.0
        if not allowed:
            score = min(score, 59.0)
        candidate = {
            "expiry": expiry,
            "expiry_date": expiry.isoformat() if expiry else "",
            "dte": dte,
            "bucket": bucket_name,
            "liquidity_score": liquidity_score,
            "expected_move": expected_move,
            "credit_quality_pct": round(credit_quality, 2),
            "selected": False,
            "allowed": bool(allowed),
            "expiry_score": round(score, 2),
            "rejection_reason": ", ".join(reasons) if reasons else "",
            "reason": "Accepted expiry candidate." if allowed else ", ".join(reasons),
        }
        candidates.append(candidate)
    candidates.sort(key=lambda item: (bool(item["allowed"]), _float(item.get("expiry_score"))), reverse=True)
    selected = next((item for item in candidates if item["allowed"]), None)
    if selected:
        selected["selected"] = True
        reason = f"Selected {selected['bucket']} with liquidity {selected['liquidity_score']} and credit {selected['credit_quality_pct']}%."
    else:
        reason = "No expiry passed DTE, liquidity, and credit filters."
    return {
        "selected_expiry": selected.get("expiry") if selected else None,
        "selected_dte": selected.get("dte") if selected else None,
        "selected_bucket": selected.get("bucket") if selected else "NONE",
        "expiry_score": selected.get("expiry_score") if selected else 0.0,
        "reason": reason,
        "all_expiry_candidates": candidates,
    }


def select_nifty_strategy_by_regime(market_state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    spot = _float(market_state.get("spot") or market_state.get("nifty_spot"))
    ema20 = _float(market_state.get("ema20") or market_state.get("nifty_20ema") or market_state.get("dma_20"))
    ema50 = _float(market_state.get("ema50") or market_state.get("nifty_50ema") or market_state.get("dma_50"))
    rsi = _float(market_state.get("rsi_14") or market_state.get("rsi"), 50.0)
    adx = _float(market_state.get("adx_14") or market_state.get("adx"), 20.0)
    regime = str(market_state.get("trend_regime") or market_state.get("regime") or "").upper()
    breakout = bool(market_state.get("breakout_status")) or regime == "BREAKOUT_DAY"
    panic = bool(market_state.get("panic_fall_status")) or regime == "PANIC_FALL"
    warnings: list[str] = []
    if breakout:
        return {
            "selected_strategy": "NO_TRADE",
            "allow_pe_spread": False,
            "allow_ce_spread": False,
            "reason": "Breakout day. No CE sell; prefer No Trade.",
            "warnings": ["BREAKOUT_DAY"],
        }
    if panic:
        return {
            "selected_strategy": "NO_TRADE",
            "allow_pe_spread": False,
            "allow_ce_spread": False,
            "reason": "Panic fall. No immediate PE sell; prefer No Trade.",
            "warnings": ["PANIC_FALL"],
        }
    if spot > 0 and ema20 > 0 and spot > ema20 and (ema50 <= 0 or spot >= ema50) and rsi >= 48:
        return {
            "selected_strategy": "BULL_PUT_SPREAD",
            "allow_pe_spread": True,
            "allow_ce_spread": False,
            "reason": "NIFTY is above 20 EMA. Use Bull Put Spread only.",
            "warnings": warnings,
        }
    if spot > 0 and ema20 > 0 and spot < ema20 and (ema50 <= 0 or spot <= ema50):
        return {
            "selected_strategy": "BEAR_CALL_SPREAD",
            "allow_pe_spread": False,
            "allow_ce_spread": True,
            "reason": "NIFTY is below 20 EMA. Use Bear Call Spread only.",
            "warnings": warnings,
        }
    if regime in {"SIDEWAYS", "NEUTRAL"} or adx < 20 or 42 <= rsi <= 58:
        return {
            "selected_strategy": "IRON_CONDOR",
            "allow_pe_spread": True,
            "allow_ce_spread": True,
            "reason": "Sideways market. Iron Condor allowed if credit quality is meaningful.",
            "warnings": warnings,
        }
    return {
        "selected_strategy": "NO_TRADE",
        "allow_pe_spread": False,
        "allow_ce_spread": False,
        "reason": "No clean regime alignment for NIFTY income.",
        "warnings": ["REGIME_UNCLEAR"],
    }


def calculate_probability_metrics(option_quote: dict[str, Any], spot: float, expected_move_points: float, dte: int | None) -> dict[str, Any]:
    strike = _float(option_quote.get("strike"))
    delta = abs(_float(option_quote.get("delta")))
    distance = abs(strike - spot) if strike and spot else 0.0
    distance_pct = distance / spot * 100 if spot > 0 else 0.0
    expected_multiple = distance / expected_move_points if expected_move_points > 0 else 0.0
    expiry_itm = min(100.0, delta * 100.0)
    touch = min(100.0, delta * 200.0)
    dte_value = dte if dte is not None else _int(option_quote.get("dte"), 0)
    if dte_value <= 7:
        bucket = "EXPIRY_RISK"
    elif dte_value <= 14:
        bucket = "NEAR_DTE"
    elif dte_value <= 21:
        bucket = "MID_DTE"
    else:
        bucket = "FAR_DTE"
    state = "CLEAR"
    if dte_value <= 7:
        state = "FORCE_EXIT"
    elif delta >= 0.25:
        state = "EMERGENCY"
    elif touch > 50:
        state = "THREATENED"
    elif touch >= 35:
        state = "REVIEW"
    return {
        "distance_to_strike_points": round(distance, 2),
        "distance_to_strike_pct": round(distance_pct, 2),
        "expected_move_multiple": round(expected_multiple, 2),
        "probability_expiry_itm_pct": round(expiry_itm, 2),
        "probability_touch_pct": round(touch, 2),
        "dte_bucket": bucket,
        "probability_risk_state": state,
    }


def validate_credit_quality(spread_candidate: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _merge_config(config)
    credit_cfg = cfg["nifty_credit_quality"]
    width = _float(spread_candidate.get("spread_width") or spread_candidate.get("spread_width_points"))
    credit = _float(spread_candidate.get("net_credit") or spread_candidate.get("net_credit_points"))
    margin = _float(spread_candidate.get("margin_required") or spread_candidate.get("max_loss") or max(0.0, width - credit))
    credit_pct = credit / width * 100 if width > 0 else 0.0
    max_loss = max(0.0, width - credit)
    max_loss_to_credit = max_loss / credit if credit > 0 else math.inf
    premium_yield = credit / margin * 100 if margin > 0 else 0.0
    reasons: list[str] = []
    warnings: list[str] = []
    accepted = True
    if credit_pct < _float(credit_cfg.get("min_credit_pct_of_width"), 8.0):
        accepted = False
        reasons.append("CREDIT_BELOW_8_PCT_WIDTH")
    if premium_yield < _float(credit_cfg.get("min_premium_yield_on_margin_pct"), 0.8):
        accepted = False
        reasons.append("PREMIUM_YIELD_BELOW_MIN")
    if max_loss_to_credit > _float(credit_cfg.get("max_loss_to_credit_ratio_max"), 4.0):
        if credit_cfg.get("strict_max_loss_to_credit_ratio", False):
            accepted = False
            reasons.append("MAX_LOSS_TO_CREDIT_TOO_HIGH")
        else:
            warnings.append("MAX_LOSS_TO_CREDIT_HIGH")
    if credit_pct >= _float(credit_cfg.get("excellent_credit_pct_of_width"), 12.0):
        quality = "EXCELLENT"
    elif credit_pct >= _float(credit_cfg.get("preferred_credit_pct_of_width"), 10.0):
        quality = "GOOD"
    elif credit_pct >= _float(credit_cfg.get("min_credit_pct_of_width"), 8.0):
        quality = "ACCEPTABLE"
    else:
        quality = "REJECT"
    return {
        "accepted": bool(accepted),
        "quality_status": quality if accepted else "REJECT",
        "net_credit_points": round(credit, 2),
        "spread_width_points": round(width, 2),
        "credit_pct_of_width": round(credit_pct, 2),
        "required_credit_points": round(width * _float(credit_cfg.get("min_credit_pct_of_width"), 8.0) / 100, 2),
        "credit_gap_points": round(max(0.0, width * _float(credit_cfg.get("min_credit_pct_of_width"), 8.0) / 100 - credit), 2),
        "max_loss": round(max_loss, 2),
        "max_loss_to_credit_ratio": None if math.isinf(max_loss_to_credit) else round(max_loss_to_credit, 2),
        "premium_yield_on_margin_pct": round(premium_yield, 2),
        "rejection_reason": ", ".join(reasons),
        "warnings": sorted(set(warnings)),
    }


def _candidate_strategy_legs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    lots = max(1, _int(candidate.get("lots"), 1))
    lot_size = max(1, _int(candidate.get("lot_size"), 65))
    short_symbol = str(candidate.get("short_symbol") or candidate.get("tradingsymbol") or "")
    hedge_symbol = str(candidate.get("hedge_symbol") or candidate.get("hedge_tradingsymbol") or "")
    side = str(candidate.get("side") or candidate.get("option_type") or "").upper()
    legs = [
        {
            "tradingsymbol": short_symbol,
            "transaction_type": "SELL",
            "option_type": side,
            "strike": candidate.get("short_strike") or candidate.get("strike"),
            "ltp": candidate.get("short_ltp") if candidate.get("short_ltp") is not None else candidate.get("ltp"),
            "bid": candidate.get("short_bid") if candidate.get("short_bid") is not None else candidate.get("bid"),
            "ask": candidate.get("short_ask") if candidate.get("short_ask") is not None else candidate.get("ask"),
            "delta": candidate.get("short_delta") if candidate.get("short_delta") is not None else candidate.get("delta"),
            "oi": candidate.get("short_oi") if candidate.get("short_oi") is not None else candidate.get("oi"),
            "volume": candidate.get("short_volume") if candidate.get("short_volume") is not None else candidate.get("volume"),
            "price": candidate.get("short_limit_price") or candidate.get("price"),
            "lots": lots,
            "lot_size": lot_size,
        }
    ]
    if hedge_symbol:
        legs.append(
            {
                "tradingsymbol": hedge_symbol,
                "transaction_type": "BUY",
                "option_type": side,
                "strike": candidate.get("hedge_strike"),
                "ltp": candidate.get("hedge_ltp"),
                "bid": candidate.get("hedge_bid"),
                "ask": candidate.get("hedge_ask"),
                "delta": candidate.get("hedge_delta"),
                "oi": candidate.get("hedge_oi"),
                "volume": candidate.get("hedge_volume"),
                "price": candidate.get("hedge_limit_price"),
                "lots": lots,
                "lot_size": lot_size,
            }
        )
    return legs


def _normalise_strategy_legs(strategy_legs: Any, quote_data: dict[str, Any] | None = None, lot_size: int = 65) -> list[dict[str, Any]]:
    if isinstance(strategy_legs, dict) and ("short_symbol" in strategy_legs or "short_strike" in strategy_legs):
        legs = _candidate_strategy_legs(strategy_legs)
    elif isinstance(strategy_legs, dict) and "legs" in strategy_legs:
        legs = list(strategy_legs.get("legs") or [])
    else:
        legs = list(strategy_legs or [])
    normalised: list[dict[str, Any]] = []
    quote_data = quote_data or {}
    for leg in legs:
        row = dict(leg)
        symbol = str(row.get("tradingsymbol") or row.get("symbol") or "")
        quote = quote_data.get(symbol) or quote_data.get(f"NFO:{symbol}") or {}
        if quote:
            row["ltp"] = quote.get("ltp") or quote.get("last_price") or row.get("ltp")
            row["bid"] = quote.get("bid") or quote.get("best_bid") or row.get("bid")
            row["ask"] = quote.get("ask") or quote.get("best_ask") or row.get("ask")
            row["oi"] = quote.get("oi") or quote.get("open_interest") or row.get("oi")
            row["volume"] = quote.get("volume") or quote.get("day_volume") or row.get("volume")
            row["delta"] = quote.get("delta") if quote.get("delta") is not None else row.get("delta")
        row["lot_size"] = max(1, _int(row.get("lot_size"), lot_size))
        row["lots"] = max(1, _int(row.get("lots"), 1))
        normalised.append(row)
    return normalised


def calculate_realistic_executable_credit(
    strategy_legs: Any,
    quote_data: dict[str, Any] | None = None,
    lot_size: int = 65,
    config: dict[str, Any] | None = None,
) -> ExecutionQualityResult:
    cfg = _merge_config(config)
    guard = cfg["nifty_execution_quality_guard"]
    legs = _normalise_strategy_legs(strategy_legs, quote_data, lot_size)
    optimistic_credit = 0.0
    ltp_credit = 0.0
    realistic_credit = 0.0
    reason_codes: list[str] = []
    warnings: list[str] = []
    min_bid = math.inf
    max_ask = 0.0
    full_quote = True
    ltp_seen = False
    total_qty = 0
    width = _float(strategy_legs.get("spread_width") if isinstance(strategy_legs, dict) else 0)
    margin = 0.0
    if isinstance(strategy_legs, dict):
        margin = _float(strategy_legs.get("margin_required") or strategy_legs.get("max_loss"))

    for leg in legs:
        side = str(leg.get("transaction_type") or "").upper()
        ltp = _float(leg.get("ltp") or leg.get("last_price") or leg.get("option_ltp"))
        bid = _float(leg.get("bid") or leg.get("best_bid"))
        ask = _float(leg.get("ask") or leg.get("best_ask"))
        price = _float(leg.get("price") or leg.get("limit_price"))
        qty = max(1, _int(leg.get("quantity"), _int(leg.get("lots"), 1) * _int(leg.get("lot_size"), lot_size)))
        total_qty = max(total_qty, qty)
        if ltp > 0:
            ltp_seen = True
        else:
            full_quote = False
            reason_codes.append("REJECT_LTP_MISSING")
        if side == "SELL":
            min_bid = min(min_bid, bid) if bid > 0 else min_bid
            if bid <= 0:
                full_quote = False
                reason_codes.append("REJECT_ZERO_BID" if guard.get("reject_zero_bid", True) else "WARN_ZERO_BID")
            if ask <= 0:
                full_quote = False
                reason_codes.append("REJECT_BID_ASK_MISSING")
            optimistic_leg = price if price > 0 else ltp * (1 + _float(guard.get("max_live_sell_markup_pct"), 5.0) / 100)
            optimistic_credit += optimistic_leg
            ltp_credit += ltp
            realistic_credit += bid if bid > 0 else 0.0
        elif side == "BUY":
            max_ask = max(max_ask, ask)
            if ask <= 0:
                full_quote = False
                reason_codes.append("REJECT_BID_ASK_MISSING")
            if bid <= 0:
                warnings.append("BUY_LEG_BID_MISSING")
            optimistic_leg = price if price > 0 else ltp * (1 - _float(guard.get("max_live_buy_discount_pct"), 3.0) / 100)
            optimistic_credit -= optimistic_leg
            ltp_credit -= ltp
            realistic_credit -= ask if ask > 0 else 0.0

        if bid > 0 and ask > 0 and _spread_pct(bid, ask, ltp) > _float(guard.get("max_bid_ask_spread_pct"), 8.0):
            reason_codes.append("REJECT_WIDE_BID_ASK")
        if _int(leg.get("oi")) < _int(guard.get("min_oi_for_live"), 10000):
            reason_codes.append("REJECT_LOW_OI")
        if _int(leg.get("volume")) < _int(guard.get("min_volume_for_live"), 10):
            reason_codes.append("REJECT_LOW_VOLUME")

    if not legs:
        reason_codes.append("REJECT_NO_LEGS")
    data_quality = "FULL_QUOTE" if full_quote and legs else "LTP_ONLY" if ltp_seen else "MISSING_QUOTE"
    optimistic_credit = _round_tick(optimistic_credit)
    ltp_credit = _round_tick(ltp_credit)
    realistic_credit = _round_tick(realistic_credit)
    denominator = max(0.05, abs(realistic_credit))
    optimistic_gap = max(0.0, (optimistic_credit - realistic_credit) / denominator * 100)
    ltp_gap = max(0.0, abs(ltp_credit - realistic_credit) / denominator * 100)
    value_qty = total_qty if total_qty > 0 else max(1, lot_size)
    credit_pct = realistic_credit / width * 100 if width > 0 else 0.0
    premium_yield = realistic_credit * value_qty / margin * 100 if margin > 0 else 0.0
    return ExecutionQualityResult(
        data_quality=data_quality,
        optimistic_credit_points=round(optimistic_credit, 2),
        ltp_credit_points=round(ltp_credit, 2),
        realistic_credit_points=round(realistic_credit, 2),
        optimistic_credit_value=round(optimistic_credit * value_qty, 2),
        ltp_credit_value=round(ltp_credit * value_qty, 2),
        realistic_credit_value=round(realistic_credit * value_qty, 2),
        optimistic_vs_realistic_gap_pct=round(optimistic_gap, 2),
        ltp_vs_bidask_gap_pct=round(ltp_gap, 2),
        credit_pct_of_width=round(credit_pct, 2),
        premium_yield_on_margin_pct=round(premium_yield, 2),
        min_bid=0.0 if math.isinf(min_bid) else round(min_bid, 2),
        max_ask=round(max_ask, 2),
        quote_warnings=sorted(set(warnings)),
        reason_codes=sorted(set(reason_codes)),
    )


def validate_paper_trap_guard(
    candidate: dict[str, Any],
    execution_quality: ExecutionQualityResult | dict[str, Any],
    config: dict[str, Any] | None = None,
) -> PaperTrapDecision:
    cfg = _merge_config(config)
    guard = cfg["nifty_execution_quality_guard"]
    eq = execution_quality.to_dict() if isinstance(execution_quality, ExecutionQualityResult) else dict(execution_quality)
    reasons: list[str] = []
    warnings: list[str] = list(eq.get("quote_warnings") or [])
    if eq.get("data_quality") != "FULL_QUOTE" and guard.get("reject_live_if_ltp_only", True):
        reasons.append("REJECT_LTP_ONLY_PRICE")
    if _float(eq.get("realistic_credit_points")) <= 0:
        reasons.append("REJECT_NO_REALISTIC_CREDIT")
    if _float(eq.get("credit_pct_of_width")) < _float(guard.get("min_realistic_credit_pct_of_width"), 8.0):
        reasons.append("REJECT_REALISTIC_CREDIT_BELOW_MIN")
    if _float(eq.get("premium_yield_on_margin_pct")) < _float(guard.get("min_realistic_premium_yield_on_margin_pct"), 0.8):
        reasons.append("REJECT_REALISTIC_YIELD_BELOW_MIN")
    if _float(eq.get("optimistic_vs_realistic_gap_pct")) > _float(guard.get("paper_trap_max_optimistic_vs_realistic_gap_pct"), 25.0):
        reasons.append("REJECT_PAPER_TRAP_OPTIMISTIC_GAP")
    if _float(eq.get("ltp_vs_bidask_gap_pct")) > _float(guard.get("paper_trap_max_ltp_vs_bidask_gap_pct"), 20.0):
        reasons.append("REJECT_PAPER_TRAP_LTP_GAP")
    reasons.extend(str(item) for item in eq.get("reason_codes") or [] if str(item).startswith("REJECT"))
    confidence = _float(candidate.get("confidence_score"), 0)
    if confidence < _float(guard.get("min_confidence_for_live_order"), 70):
        reasons.append("REJECT_CONFIDENCE_BELOW_MIN")
    allowed = not reasons
    decision = "TRADE_ALLOWED" if allowed else "PREVIEW_ONLY" if guard.get("preview_allowed_with_ltp_only", True) else "NO_TRADE"
    human = (
        "Bid/ask credit is realistic enough for live review."
        if allowed
        else "Live order blocked by execution-quality guard: " + ", ".join(sorted(set(reasons)))
    )
    return PaperTrapDecision(allowed=allowed, decision=decision, reason_codes=sorted(set(reasons)), warnings=sorted(set(warnings)), human_reason=human)


def validate_defined_risk_payoff(
    candidate: dict[str, Any],
    app_reported_max_loss: float | None = None,
    config: dict[str, Any] | None = None,
) -> MaxLossValidation:
    cfg = _merge_config(config)
    guard = cfg["nifty_execution_quality_guard"]
    reasons: list[str] = []
    width = _float(candidate.get("spread_width") or candidate.get("spread_width_points"))
    lot_size = max(1, _int(candidate.get("lot_size"), 65))
    lots = max(1, _int(candidate.get("lots"), 1))
    credit_points = _float(candidate.get("realistic_credit_points") or candidate.get("net_credit"))
    if width <= 0 or not candidate.get("hedge_symbol"):
        reasons.append("REJECT_UNDEFINED_RISK")
    expected = max(0.0, width - credit_points) * lot_size * lots if width > 0 else math.inf
    reported = _float(app_reported_max_loss if app_reported_max_loss is not None else candidate.get("max_loss"))
    mismatch = abs(reported - expected) / expected * 100 if expected > 0 and not math.isinf(expected) else 0.0
    if reported > 0 and expected > 0 and mismatch > _float(guard.get("max_loss_mismatch_pct"), 5.0):
        reasons.append("REJECT_MAX_LOSS_MISMATCH")
    accepted = not reasons
    return MaxLossValidation(
        accepted=accepted,
        expected_max_loss=0.0 if math.isinf(expected) else round(expected, 2),
        app_reported_max_loss=round(reported, 2),
        mismatch_pct=round(mismatch, 2),
        reason_codes=sorted(set(reasons)),
        human_reason=(
            "Defined-risk payoff math is consistent."
            if accepted
            else "Max-loss validation failed: " + ", ".join(sorted(set(reasons)))
        ),
    )


def validate_short_leg_probability(candidate: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _merge_config(config)
    guard = cfg["nifty_execution_quality_guard"]
    reasons: list[str] = []
    warnings: list[str] = []
    delta = abs(_float(candidate.get("short_delta"), -1.0))
    if delta <= 0:
        if guard.get("require_delta_for_live", True):
            reasons.append("REJECT_DELTA_MISSING")
        else:
            warnings.append("DELTA_MISSING")
    elif delta > _float(guard.get("reject_short_delta_above"), 0.22):
        reasons.append("REJECT_DELTA_EXTREME")
    elif delta > _float(guard.get("max_short_delta_for_income"), 0.18):
        reasons.append("REJECT_DELTA_TOO_HIGH")
    touch = _float(candidate.get("probability_touch"))
    if touch <= 0 and delta > 0:
        touch = min(100.0, delta * 200)
    if touch > _float(guard.get("max_probability_touch_pct"), 35.0):
        reasons.append("REJECT_TOUCH_PROBABILITY_HIGH")
    return {
        "allowed": not reasons,
        "delta_abs": round(delta, 4) if delta > 0 else None,
        "probability_touch_pct": round(touch, 2),
        "reason_codes": sorted(set(reasons)),
        "warnings": sorted(set(warnings)),
        "human_reason": "Short-leg probability is inside entry limits." if not reasons else "Probability gate failed: " + ", ".join(sorted(set(reasons))),
    }


def validate_iron_condor_premium_balance(candidate: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    pe_credit = _float(candidate.get("pe_credit") or candidate.get("pe_realistic_credit"))
    ce_credit = _float(candidate.get("ce_credit") or candidate.get("ce_realistic_credit"))
    if pe_credit <= 0 or ce_credit <= 0:
        return {"status": "UNKNOWN", "allowed": True, "ratio": None, "warnings": ["PAIR_CREDIT_MISSING"], "reason_codes": []}
    ratio = max(pe_credit, ce_credit) / max(0.05, min(pe_credit, ce_credit))
    reasons: list[str] = []
    warnings: list[str] = []
    if ratio > 4:
        reasons.append("REJECT_PREMIUM_SKEW_TOO_HIGH")
    elif ratio > 3:
        warnings.append("PREMIUM_SKEW_HIGH")
    return {
        "status": "BALANCED" if ratio <= 3 else "SKEWED",
        "allowed": not reasons,
        "ratio": round(ratio, 2),
        "warnings": warnings,
        "reason_codes": reasons,
    }


def validate_hedge_first_execution(candidate: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _merge_config(config)
    guard = cfg["nifty_execution_quality_guard"]
    has_short = bool(candidate.get("short_symbol"))
    has_hedge = bool(candidate.get("hedge_symbol"))
    reasons: list[str] = []
    if guard.get("no_naked_nifty_sell", True) and has_short and not has_hedge:
        reasons.append("REJECT_UNCOVERED_NIFTY_SELL")
    if guard.get("hedge_first_required", True) and has_short and has_hedge:
        return {"allowed": True, "execution_sequence": "BUY_HEDGE_FIRST_THEN_SELL_SHORT", "reason_codes": []}
    return {"allowed": not reasons, "execution_sequence": "SELL_ONLY", "reason_codes": reasons}


def evaluate_nifty_live_order_gate(
    candidate: dict[str, Any],
    validations: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> NiftyLiveOrderGate:
    cfg = _merge_config(config)
    guard = cfg["nifty_execution_quality_guard"]
    reasons: list[str] = []
    warnings: list[str] = []
    if not candidate.get("tactical_allowed", candidate.get("allowed", False)):
        reasons.append("REJECT_TACTICAL_FILTER")
    for key in ("paper_trap", "max_loss_validation", "probability_gate", "hedge_execution"):
        item = validations.get(key) or {}
        if item.get("warnings"):
            warnings.extend(str(value) for value in item.get("warnings") or [])
        if item.get("reason_codes"):
            reasons.extend(str(value) for value in item.get("reason_codes") or [])
        if item.get("allowed") is False or item.get("accepted") is False:
            if key == "paper_trap":
                reasons.append("REJECT_EXECUTION_QUALITY")
            elif key == "max_loss_validation":
                reasons.append("REJECT_PAYOFF_VALIDATION")
            elif key == "probability_gate":
                reasons.append("REJECT_PROBABILITY_GATE")
            elif key == "hedge_execution":
                reasons.append("REJECT_HEDGE_EXECUTION")
    if _float(candidate.get("confidence_score"), 0) < _float(guard.get("min_confidence_for_live_order"), 70):
        reasons.append("REJECT_CONFIDENCE_BELOW_MIN")
    if guard.get("require_broker_verified_margin", False) and not candidate.get("broker_margin_verified"):
        reasons.append("REJECT_MARGIN_NOT_BROKER_VERIFIED")
    allowed = not reasons
    action = "TRADE_ALLOWED" if allowed else "PREVIEW_ONLY"
    status = "TRADE_ALLOWED" if allowed else "BLOCKED_BY_GUARD"
    return NiftyLiveOrderGate(
        allowed=allowed,
        action=action,
        status=status,
        reason_codes=sorted(set(reasons)),
        warnings=sorted(set(warnings)),
        human_reason=(
            "NIFTYGrow candidate passed execution-quality, payoff, probability, and hedge checks."
            if allowed
            else "NIFTYGrow live order blocked: " + ", ".join(sorted(set(reasons)))
        ),
    )


def enrich_nifty_execution_quality(candidate: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _merge_config(config)
    if not cfg["nifty_execution_quality_guard"].get("enabled", True):
        return candidate
    candidate = dict(candidate)
    candidate["tactical_allowed"] = bool(candidate.get("allowed"))
    eq = calculate_realistic_executable_credit(candidate, config=cfg)
    candidate["realistic_credit_points"] = eq.realistic_credit_points
    candidate["realistic_credit_value"] = eq.realistic_credit_value
    candidate["execution_data_quality"] = eq.data_quality
    paper = validate_paper_trap_guard(candidate, eq, cfg)
    candidate_for_loss = {**candidate, "realistic_credit_points": eq.realistic_credit_points}
    max_loss = validate_defined_risk_payoff(candidate_for_loss, candidate.get("max_loss"), cfg)
    probability = validate_short_leg_probability(candidate, cfg)
    hedge_execution = validate_hedge_first_execution(candidate, cfg)
    gate = evaluate_nifty_live_order_gate(
        candidate,
        {
            "paper_trap": paper.to_dict(),
            "max_loss_validation": max_loss.to_dict(),
            "probability_gate": probability,
            "hedge_execution": hedge_execution,
        },
        cfg,
    )
    candidate["execution_quality"] = eq.to_dict()
    candidate["paper_trap_guard"] = paper.to_dict()
    candidate["max_loss_validation"] = max_loss.to_dict()
    candidate["probability_gate"] = probability
    candidate["hedge_execution"] = hedge_execution
    candidate["live_order_gate"] = gate.to_dict()
    candidate["live_order_allowed"] = gate.allowed
    if candidate["tactical_allowed"] and not gate.allowed:
        existing_reason = str(candidate.get("rejection_reason") or "")
        joined = ", ".join(gate.reason_codes)
        candidate["rejection_reason"] = ", ".join(part for part in [existing_reason, joined] if part)
    candidate["allowed"] = bool(candidate["tactical_allowed"] and gate.allowed)
    return candidate


def _option_rows(option_chain: list[dict[str, Any]], expiry: date, option_type: str) -> list[dict[str, Any]]:
    return [
        row
        for row in option_chain
        if _date(row.get("expiry") or row.get("expiry_date")) == expiry
        and str(row.get("option_type") or row.get("instrument_type") or "").upper() == option_type
    ]


def _tradeable_short_leg(row: dict[str, Any], config: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    cfg = config.get("nifty_nearest_tradeable_strike") or {}
    ltp = _float(row.get("ltp") or row.get("last_price") or row.get("option_ltp"))
    oi = _int(row.get("oi") if row.get("oi") not in (None, "", "N/A", "--") else row.get("open_interest"))
    volume = _int(row.get("volume"))
    checks = {
        "symbol": row.get("tradingsymbol") or "",
        "strike": _float(row.get("strike")),
        "ltp": ltp,
        "oi": oi,
        "volume": volume,
    }
    return (
        ltp > 0
        and oi >= _int(cfg.get("min_oi"), 10000)
        and volume >= _int(cfg.get("min_volume"), 10),
        checks,
    )


def _synthetic_short_delta(short: dict[str, Any], option_type: str, spot: float) -> float:
    delta = _float(short.get("delta"))
    if abs(delta) > 0:
        return delta
    strike = _float(short.get("strike"))
    distance_pct = abs(strike - spot) / spot * 100 if spot > 0 and strike > 0 else 5.0
    # Use a conservative proxy when live Greeks are missing, so the engine can still
    # evaluate otherwise tradable strikes while keeping far OTM options low-delta.
    abs_delta = max(0.06, min(0.16, 0.18 - min(distance_pct, 12.0) / 120.0))
    return -abs_delta if option_type == "PE" else abs_delta


def _nearest_tradeable_short_leg(
    rows: list[dict[str, Any]],
    short: dict[str, Any],
    option_type: str,
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = config.get("nifty_nearest_tradeable_strike") or {}
    if not cfg.get("enabled", True):
        return short, {"adjusted": False, "checks": []}
    ok, first_check = _tradeable_short_leg(short, config)
    checks = [first_check]
    if ok:
        return short, {"adjusted": False, "checks": checks}
    step = _int(cfg.get("strike_step_points"), 100)
    max_adjustment = _int(cfg.get("max_adjustment_points"), 200)
    base_strike = _float(short.get("strike"))
    direction = 1 if option_type == "PE" else -1
    by_strike = {_float(row.get("strike")): row for row in rows}
    adjustment = step
    while adjustment <= max_adjustment:
        candidate = by_strike.get(base_strike + direction * adjustment)
        if candidate:
            ok, check = _tradeable_short_leg(candidate, config)
            checks.append(check)
            if ok:
                adjusted = dict(candidate)
                adjusted["delta"] = _synthetic_short_delta(adjusted, option_type, _float(short.get("spot")))
                return adjusted, {
                    "adjusted": True,
                    "from_strike": base_strike,
                    "to_strike": _float(adjusted.get("strike")),
                    "adjustment_points": adjustment,
                    "reason": (
                        f"Moved NIFTY {option_type} strike {adjustment} points closer to spot because "
                        "an earlier contract had no positive LTP or had OI/volume below the tradable threshold. "
                        f"Max adjustment allowed is {max_adjustment} points."
                    ),
                    "checks": checks,
                }
        adjustment += step
    return short, {
        "adjusted": False,
        "checks": checks,
        "reason": (
            f"No tradable NIFTY {option_type} strike found within {max_adjustment} points of "
            f"{fmt_strike_for_audit(base_strike)}."
        ),
    }


def fmt_strike_for_audit(value: float) -> str:
    return str(int(value)) if float(value or 0).is_integer() else f"{value:.2f}"


def _candidate_from_pair(
    strategy: str,
    side: str,
    short: dict[str, Any],
    hedge: dict[str, Any],
    spot: float,
    expected_move: float,
    dte: int,
    config: dict[str, Any],
    strike_adjustment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    short_strike = _float(short.get("strike"))
    hedge_strike = _float(hedge.get("strike"))
    width = abs(short_strike - hedge_strike)
    short_ltp = _float(short.get("ltp") or short.get("last_price"))
    short_bid = _float(short.get("bid") or short.get("best_bid"))
    short_ask = _float(short.get("ask") or short.get("best_ask"))
    hedge_ltp = _float(hedge.get("ltp") or hedge.get("last_price"))
    hedge_bid = _float(hedge.get("bid") or hedge.get("best_bid"))
    hedge_ask = _float(hedge.get("ask") or hedge.get("best_ask"))
    lot_size = _int(short.get("lot_size"), 65)
    net_credit = (short_bid if short_bid > 0 else short_ltp) - (hedge_ask if hedge_ask > 0 else hedge_ltp)
    short_liq = calculate_option_liquidity_score(short, config)
    hedge_liq = calculate_option_liquidity_score(hedge, config)
    liquidity_score = round((short_liq["score"] * 0.7) + (hedge_liq["score"] * 0.3), 2)
    prob = calculate_probability_metrics(short, spot, expected_move, dte)
    credit = validate_credit_quality({"spread_width": width, "net_credit": net_credit, "margin_required": max(0, width - net_credit)}, config)
    reasons: list[str] = []
    allowed = True
    abs_delta = abs(_float(short.get("delta")))
    engine_cfg = config["nifty_3w_tactical_engine"]
    prob_cfg = config["nifty_probability_risk"]
    if abs_delta > _float(engine_cfg.get("absolute_max_short_delta"), 0.18):
        allowed = False
        reasons.append("SHORT_DELTA_ABOVE_MAX")
    if abs_delta < _float(engine_cfg.get("short_delta_min"), 0.10):
        reasons.append("SHORT_DELTA_BELOW_TARGET")
    if not short_liq["allowed"]:
        allowed = False
        reasons.append("SHORT_LEG_LIQUIDITY_REJECT")
    if not hedge_liq["allowed"]:
        allowed = False
        reasons.append("HEDGE_LEG_LIQUIDITY_REJECT")
    if side == "PE" and hedge_strike >= short_strike:
        allowed = False
        reasons.append("HEDGE_NOT_FARTHER_OTM")
    if side == "CE" and hedge_strike <= short_strike:
        allowed = False
        reasons.append("HEDGE_NOT_FARTHER_OTM")
    if not credit["accepted"]:
        allowed = False
        reasons.append(credit["rejection_reason"] or "CREDIT_QUALITY_REJECT")
    if prob["expected_move_multiple"] < _float(engine_cfg.get("expected_move_min_multiple"), 1.2):
        allowed = False
        reasons.append("EXPECTED_MOVE_TOO_CLOSE")
    if prob["probability_touch_pct"] > _float(prob_cfg.get("max_probability_touch_for_entry_pct"), 35.0):
        allowed = False
        reasons.append("PROBABILITY_TOUCH_TOO_HIGH")
    confidence = min(
        100.0,
        liquidity_score * 0.35
        + min(100.0, credit["credit_pct_of_width"] * 6) * 0.25
        + max(0.0, 100.0 - prob["probability_touch_pct"]) * 0.2
        + min(100.0, prob["expected_move_multiple"] * 40) * 0.2,
    )
    candidate = {
        "strategy": strategy,
        "side": side,
        "expiry": _date(short.get("expiry") or short.get("expiry_date")),
        "expiry_date": (_date(short.get("expiry") or short.get("expiry_date")) or date.today()).isoformat(),
        "dte": dte,
        "short_symbol": short.get("tradingsymbol") or "",
        "hedge_symbol": hedge.get("tradingsymbol") or "",
        "short_strike": short_strike,
        "hedge_strike": hedge_strike,
        "short_delta": _float(short.get("delta")),
        "hedge_delta": _float(hedge.get("delta")),
        "short_ltp": short_ltp,
        "short_bid": short_bid,
        "short_ask": short_ask,
        "short_oi": _int(short.get("oi") or short.get("open_interest")),
        "short_volume": _int(short.get("volume") or short.get("day_volume")),
        "hedge_ltp": hedge_ltp,
        "hedge_bid": hedge_bid,
        "hedge_ask": hedge_ask,
        "hedge_oi": _int(hedge.get("oi") or hedge.get("open_interest")),
        "hedge_volume": _int(hedge.get("volume") or hedge.get("day_volume")),
        "lot_size": lot_size,
        "lots": 1,
        "spread_width": width,
        "net_credit": _round_tick(net_credit),
        "credit_pct_of_width": credit["credit_pct_of_width"],
        "required_credit": credit["required_credit_points"],
        "max_gain": round(max(0.0, net_credit * lot_size), 2),
        "max_loss": round(max(0.0, width - net_credit) * lot_size, 2),
        "margin_required": round(max(0.0, width - net_credit) * lot_size, 2),
        "pop": round(max(0.0, 100.0 - prob["probability_expiry_itm_pct"]), 2),
        "probability_touch": prob["probability_touch_pct"],
        "expected_move_multiple": prob["expected_move_multiple"],
        "liquidity_score": liquidity_score,
        "confidence_score": round(confidence, 2),
        "allowed": bool(allowed),
        "rejection_reason": ", ".join(sorted(set(reasons))),
        "credit_quality": credit["quality_status"],
        "premium_yield_on_margin_pct": credit["premium_yield_on_margin_pct"],
        "probability_metrics": prob,
        "liquidity": {"short": short_liq, "hedge": hedge_liq},
        "strike_adjustment": strike_adjustment or {"adjusted": False, "checks": []},
        "strike_adjusted": bool((strike_adjustment or {}).get("adjusted")),
        "adjusted_from_strike": (strike_adjustment or {}).get("from_strike"),
        "strike_adjustment_points": (strike_adjustment or {}).get("adjustment_points") or 0,
        "strike_adjustment_reason": (strike_adjustment or {}).get("reason") or "",
        "strike_adjustment_checks": (strike_adjustment or {}).get("checks") or [],
    }
    return enrich_nifty_execution_quality(candidate, config)


def build_3w_tactical_spread_candidates(
    option_chain: list[dict[str, Any]],
    selected_expiry: date,
    market_regime: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cfg = _merge_config(config)
    today = _date(market_regime.get("today")) or date.today()
    dte = _dte(selected_expiry, today) or 0
    strategy_decision = select_nifty_strategy_by_regime(market_regime, cfg)
    strategy = strategy_decision["selected_strategy"]
    spot = _float(market_regime.get("spot") or market_regime.get("nifty_spot"))
    expected_move = _float(market_regime.get("expected_move_points") or market_regime.get("expected_move"), 1.0)
    widths = [_int(item) for item in cfg["nifty_3w_tactical_engine"].get("spread_widths_to_scan", [300, 400, 500, 600])]
    candidates: list[dict[str, Any]] = []
    side_map = []
    if strategy in {"BULL_PUT_SPREAD", "IRON_CONDOR"} and strategy_decision.get("allow_pe_spread"):
        side_map.append(("PE", "BULL_PUT_SPREAD" if strategy != "IRON_CONDOR" else "IRON_CONDOR"))
    if strategy in {"BEAR_CALL_SPREAD", "IRON_CONDOR"} and strategy_decision.get("allow_ce_spread"):
        side_map.append(("CE", "BEAR_CALL_SPREAD" if strategy != "IRON_CONDOR" else "IRON_CONDOR"))

    if strategy == "NO_TRADE" or not side_map:
        return [
            {
                "strategy": "NO_TRADE",
                "side": "NONE",
                "expiry": selected_expiry,
                "expiry_date": selected_expiry.isoformat(),
                "dte": dte,
                "allowed": False,
                "rejection_reason": strategy_decision.get("reason") or "NO_TRADE",
                "confidence_score": 0,
            }
        ]

    for option_type, candidate_strategy in side_map:
        rows = sorted(_option_rows(option_chain, selected_expiry, option_type), key=lambda row: _float(row.get("strike")))
        seen_short_strikes: set[float] = set()
        for short in rows:
            short = {**short, "spot": spot}
            short, adjustment = _nearest_tradeable_short_leg(rows, short, option_type, cfg)
            short_strike = _float(short.get("strike"))
            if short_strike in seen_short_strikes:
                continue
            seen_short_strikes.add(short_strike)
            if abs(_float(short.get("delta"))) <= 0:
                short = {**short, "delta": _synthetic_short_delta(short, option_type, spot)}
            for width in widths:
                hedge_strike = _float(short.get("strike")) - width if option_type == "PE" else _float(short.get("strike")) + width
                hedge = next((row for row in rows if abs(_float(row.get("strike")) - hedge_strike) < 0.01), None)
                if not hedge:
                    continue
                candidates.append(_candidate_from_pair(candidate_strategy, option_type, short, hedge, spot, expected_move, dte, cfg, adjustment))
    candidates.sort(key=lambda row: (bool(row.get("allowed")), _float(row.get("confidence_score")), _float(row.get("net_credit"))), reverse=True)
    return candidates


def evaluate_3w_nifty_exit(strategy: dict[str, Any], live_quotes: dict[str, Any], current_datetime: datetime | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _merge_config(config)["nifty_3w_exit_policy"]
    now = current_datetime or datetime.now()
    entry_credit = _float(strategy.get("entry_net_credit") or strategy.get("net_credit"))
    current_value = _float(live_quotes.get("current_spread_value") or strategy.get("current_spread_value"))
    entry_date = _date(strategy.get("entry_date")) or now.date()
    expiry = _date(strategy.get("expiry") or strategy.get("expiry_date")) or now.date()
    age = max(0, (now.date() - entry_date).days)
    dte = max(0, (expiry - now.date()).days)
    if age <= 5:
        target = _float(cfg.get("day_0_to_5_credit_decay_target_pct"), 30.0)
    elif age <= 12:
        target = _float(cfg.get("day_6_to_12_credit_decay_target_pct"), 45.0)
    else:
        target = _float(cfg.get("day_13_plus_credit_decay_target_pct"), 55.0)
    decay = (entry_credit - current_value) / entry_credit * 100 if entry_credit > 0 else 0.0
    reasons: list[str] = []
    exit_signal = ""
    if dte <= _int(cfg.get("force_exit_dte"), 7):
        exit_signal = "FORCE_EXIT_DTE"
        reasons.append("DTE <= force exit threshold")
    if entry_credit > 0 and current_value >= entry_credit * _float(cfg.get("stop_loss_credit_multiple"), 1.5):
        exit_signal = "STOP_LOSS"
        reasons.append("Spread value reached stop-loss multiple")
    if entry_credit > 0 and decay >= target and not exit_signal:
        exit_signal = "BOOK_PROFIT"
        reasons.append(f"Credit decay {decay:.2f}% reached target {target:.2f}%")
    emergency = False
    for quote in live_quotes.get("short_leg_quotes", []) or []:
        if _float(quote.get("ltp")) >= _float(quote.get("entry_premium")) * _float(cfg.get("emergency_short_premium_multiple"), 2.0):
            emergency = True
        if abs(_float(quote.get("delta"))) >= _float(cfg.get("emergency_short_delta"), 0.25):
            emergency = True
        if _float(quote.get("probability_touch_pct")) >= _float(cfg.get("emergency_probability_touch_pct"), 50.0):
            emergency = True
    if emergency:
        exit_signal = "EMERGENCY_EXIT"
        reasons.append("Short-leg emergency threshold reached")
    return {
        "exit_signal": exit_signal,
        "should_exit": bool(exit_signal),
        "credit_decay_pct": round(decay, 2),
        "age_days": age,
        "dte": dte,
        "target_decay_pct": target,
        "reason": "; ".join(reasons) or "No exit condition triggered.",
    }


def build_nifty_grow_model(option_chain_by_expiry: dict[Any, list[dict[str, Any]]], market_state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _merge_config(config)
    optimizer = select_best_nifty_expiry(option_chain_by_expiry, market_state, cfg)
    selected_expiry = optimizer.get("selected_expiry")
    strategy = select_nifty_strategy_by_regime(market_state, cfg)
    option_chain: list[dict[str, Any]] = []
    for rows in option_chain_by_expiry.values():
        option_chain.extend(rows)
    candidates = (
        build_3w_tactical_spread_candidates(option_chain, selected_expiry, {**market_state, **strategy}, cfg)
        if selected_expiry
        else []
    )
    valid = [row for row in candidates if row.get("allowed")]
    best = valid[0] if valid else (candidates[0] if candidates else {})

    def _first_side(side: str, live_only: bool = True) -> dict[str, Any]:
        side = side.upper()
        for row in candidates:
            if str(row.get("side") or "").upper() != side:
                continue
            if live_only and not row.get("allowed"):
                continue
            return row
        return {}

    pe_live = _first_side("PE", True)
    ce_live = _first_side("CE", True)
    pe_preview = pe_live or _first_side("PE", False)
    ce_preview = ce_live or _first_side("CE", False)
    selected_pair = [row for row in (pe_live, ce_live) if row]
    preview_pair = [row for row in (pe_preview, ce_preview) if row]
    missing_sides = [side for side, row in (("PE", pe_live), ("CE", ce_live)) if not row]
    pair_reason_codes: list[str] = []
    for row in preview_pair:
        gate = row.get("live_order_gate") if isinstance(row.get("live_order_gate"), dict) else {}
        pair_reason_codes.extend(str(item) for item in gate.get("reason_codes") or [])
    if missing_sides:
        pair_reason_codes.extend(f"MISSING_LIVE_READY_{side}" for side in missing_sides)
    pair_realistic = sum(_float((row.get("execution_quality") or {}).get("realistic_credit_value")) for row in selected_pair)
    pair_ltp = sum(_float((row.get("execution_quality") or {}).get("ltp_credit_value")) for row in preview_pair)
    pair_optimistic = sum(_float((row.get("execution_quality") or {}).get("optimistic_credit_value")) for row in preview_pair)
    pair_gap = max((_float((row.get("execution_quality") or {}).get("optimistic_vs_realistic_gap_pct")) for row in preview_pair), default=0.0)
    pair_ltp_gap = max((_float((row.get("execution_quality") or {}).get("ltp_vs_bidask_gap_pct")) for row in preview_pair), default=0.0)
    pair_data_quality = "FULL_QUOTE" if selected_pair and len(selected_pair) == 2 else (
        "PREVIEW_ONLY" if preview_pair else "MISSING_QUOTE"
    )
    execution_reality = {
        "status": "TRADE_ALLOWED" if pe_live and ce_live else "NO_TRADE",
        "action": "PLACE_BALANCED_PE_CE" if pe_live and ce_live else "PREVIEW_ONLY",
        "data_quality": pair_data_quality,
        "selected_sides": ",".join(str(row.get("side")) for row in selected_pair) or "NONE",
        "missing_sides": ",".join(missing_sides),
        "realistic_credit_value": round(pair_realistic, 2),
        "ltp_credit_value": round(pair_ltp, 2),
        "optimistic_credit_value": round(pair_optimistic, 2),
        "optimistic_vs_realistic_gap_pct": round(pair_gap, 2),
        "ltp_vs_bidask_gap_pct": round(pair_ltp_gap, 2),
        "reason_codes": sorted(set(pair_reason_codes)),
        "human_reason": (
            "Balanced PE and CE NIFTYGrow pair passed live execution guard."
            if pe_live and ce_live
            else "Balanced PE+CE pair is not live-ready: " + ", ".join(sorted(set(pair_reason_codes or ["NO_LIVE_READY_PAIR"])))
        ),
    }
    risk_contract = {
        "max_gain": best.get("max_gain"),
        "max_loss": best.get("max_loss"),
        "premium_yield_on_margin_pct": best.get("premium_yield_on_margin_pct"),
        "max_loss_to_credit_ratio": validate_credit_quality(best, cfg).get("max_loss_to_credit_ratio") if best else None,
        "stop_loss_value": round(_float(best.get("net_credit")) * _float(cfg["nifty_3w_tactical_engine"].get("stop_loss_credit_multiple"), 1.5), 2) if best else None,
        "profit_target_decay_pct": cfg["nifty_3w_tactical_engine"].get("profit_booking_credit_decay_pct"),
        "force_exit_dte": cfg["nifty_3w_exit_policy"].get("force_exit_dte"),
    }
    audit_rows = [
        {
            "selected_expiry": row.get("expiry_date"),
            "dte": row.get("dte"),
            "expiry_bucket": optimizer.get("selected_bucket"),
            "market_regime": market_state.get("trend_regime") or strategy.get("selected_strategy"),
            "selected_strategy": row.get("strategy"),
            "short_strike": row.get("short_strike"),
            "hedge_strike": row.get("hedge_strike"),
            "short_delta": row.get("short_delta"),
            "hedge_delta": row.get("hedge_delta"),
            "spread_width": row.get("spread_width"),
            "net_credit": row.get("net_credit"),
            "credit_pct_of_width": row.get("credit_pct_of_width"),
            "liquidity_score": row.get("liquidity_score"),
            "expected_move_multiple": row.get("expected_move_multiple"),
            "probability_touch": row.get("probability_touch"),
            "max_gain": row.get("max_gain"),
            "max_loss": row.get("max_loss"),
            "premium_yield_on_margin": row.get("premium_yield_on_margin_pct"),
            "confidence_score": row.get("confidence_score"),
            "execution_data_quality": row.get("execution_data_quality"),
            "realistic_credit": row.get("realistic_credit_points"),
            "realistic_credit_value": row.get("realistic_credit_value"),
            "execution_credit_pct": (row.get("execution_quality") or {}).get("credit_pct_of_width") if isinstance(row.get("execution_quality"), dict) else None,
            "execution_yield_on_margin": (row.get("execution_quality") or {}).get("premium_yield_on_margin_pct") if isinstance(row.get("execution_quality"), dict) else None,
            "paper_trap_decision": (row.get("paper_trap_guard") or {}).get("decision") if isinstance(row.get("paper_trap_guard"), dict) else None,
            "live_order_gate": (row.get("live_order_gate") or {}).get("status") if isinstance(row.get("live_order_gate"), dict) else None,
            "live_order_reasons": "; ".join((row.get("live_order_gate") or {}).get("reason_codes") or []) if isinstance(row.get("live_order_gate"), dict) else None,
            "allowed": row.get("allowed"),
            "rejection_reason": row.get("rejection_reason"),
            "exit_policy": cfg["nifty_3w_exit_policy"],
        }
        for row in candidates
    ]
    return {
        "config": cfg,
        "optimizer": optimizer,
        "market_state": market_state,
        "strategy": strategy,
        "candidates": candidates,
        "execution_reality": execution_reality,
        "risk_contract": risk_contract,
        "audit_rows": audit_rows,
        "best_candidate": best,
        "warnings": list(strategy.get("warnings") or []),
    }


def nifty_grow_from_income_snapshot(income_snapshot: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = _merge_config(config)
    previews = income_snapshot.get("candidate_previews") or []
    market = income_snapshot.get("market_regime") or {}
    today = date.today()
    option_chain_by_expiry: dict[str, list[dict[str, Any]]] = {}
    now_iso = datetime.now().isoformat()
    for row in previews:
        expiry = str(row.get("expiry_date") or "")
        if not expiry:
            continue
        side = str(row.get("side") or "").upper()
        if side not in {"PE", "CE"}:
            continue
        lot_size = _int((income_snapshot.get("config") or {}).get("lot_size"), 65)
        ltp = _float(row.get("option_ltp"))
        bid = _float(row.get("bid") or row.get("best_bid"))
        ask = _float(row.get("ask") or row.get("best_ask"))
        pop = _float(row.get("pop") or row.get("sell_pop"))
        delta = _float(row.get("delta"))
        if delta == 0 and pop:
            delta = max(0.03, min(0.18, (100.0 - pop) / 100.0))
        if side == "PE":
            delta = -abs(delta)
        else:
            delta = abs(delta)
        short = {
            "expiry": expiry,
            "option_type": side,
            "strike": row.get("strike"),
            "delta": delta,
            "ltp": ltp,
            "bid": bid,
            "ask": ask,
            "iv": row.get("iv"),
            "oi": _int(row.get("oi") or row.get("open_interest")),
            "volume": _int(row.get("volume") or row.get("day_volume")),
            "tradingsymbol": row.get("tradingsymbol") or "",
            "quote_timestamp": now_iso,
            "lot_size": lot_size,
            "credit_pct_of_spread_width": row.get("credit_pct_of_spread_width"),
        }
        option_chain_by_expiry.setdefault(expiry, []).append(short)
        hedge_symbol = row.get("hedge_symbol")
        hedge_strike = row.get("hedge_strike")
        if hedge_symbol and hedge_strike:
            hedge_ltp = _float(row.get("hedge_ltp"))
            option_chain_by_expiry.setdefault(expiry, []).append(
                {
                    "expiry": expiry,
                    "option_type": side,
                    "strike": hedge_strike,
                    "delta": -0.05 if side == "PE" else 0.05,
                    "ltp": hedge_ltp,
                    "bid": _float(row.get("hedge_bid")),
                    "ask": _float(row.get("hedge_ask")),
                    "iv": row.get("iv"),
                    "oi": _int(row.get("hedge_oi")),
                    "volume": _int(row.get("hedge_volume")),
                    "tradingsymbol": hedge_symbol,
                    "quote_timestamp": now_iso,
                    "lot_size": lot_size,
                }
            )
    if not option_chain_by_expiry:
        return {
            "config": cfg,
            "optimizer": {
                "selected_expiry": None,
                "selected_dte": None,
                "selected_bucket": "NONE",
                "expiry_score": 0,
                "reason": "No NIFTY candidate previews available from the base engine.",
                "all_expiry_candidates": [],
            },
            "market_state": market,
            "strategy": {"selected_strategy": "NO_TRADE", "reason": "No option chain available."},
            "candidates": [],
            "risk_contract": {},
            "audit_rows": [],
            "best_candidate": {},
            "warnings": ["NO_CANDIDATE_PREVIEW"],
        }
    spot = _float(market.get("nifty_spot") or market.get("spot"), 0)
    expected_move = _float(market.get("expected_move_points"), 0)
    market_state = {
        "today": today,
        "spot": spot,
        "nifty_spot": spot,
        "ema20": _float(market.get("dma_20") or market.get("ema20")),
        "ema50": _float(market.get("dma_50") or market.get("ema50")),
        "rsi_14": _float(market.get("rsi_14"), 50.0),
        "adx_14": _float(market.get("adx_14"), 20.0),
        "india_vix": _float(market.get("india_vix"), 0),
        "mmi": _float(market.get("mmi"), 50.0),
        "trend_regime": str(market.get("trend_regime") or "SIDEWAYS"),
        "expected_move_points": expected_move if expected_move > 0 else max(1.0, spot * 0.015),
        "event_risk_status": "OK",
    }
    return build_nifty_grow_model(option_chain_by_expiry, market_state, cfg)


def nifty_grow_audit_csv(model: dict[str, Any]) -> str:
    rows = model.get("audit_rows") or []
    columns = [
        "selected_expiry",
        "dte",
        "expiry_bucket",
        "market_regime",
        "selected_strategy",
        "short_strike",
        "hedge_strike",
        "short_delta",
        "hedge_delta",
        "spread_width",
        "net_credit",
        "credit_pct_of_width",
        "liquidity_score",
        "expected_move_multiple",
        "probability_touch",
        "max_gain",
        "max_loss",
        "premium_yield_on_margin",
        "confidence_score",
        "execution_data_quality",
        "realistic_credit",
        "realistic_credit_value",
        "execution_credit_pct",
        "execution_yield_on_margin",
        "paper_trap_decision",
        "live_order_gate",
        "live_order_reasons",
        "allowed",
        "rejection_reason",
        "exit_policy",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        clean = dict(row)
        if isinstance(clean.get("exit_policy"), dict):
            clean["exit_policy"] = "; ".join(f"{key}={value}" for key, value in clean["exit_policy"].items())
        writer.writerow(clean)
    return output.getvalue()
