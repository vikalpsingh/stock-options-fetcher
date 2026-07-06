from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Any

from .config import engine_config


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "N/A", "NA", "--"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "", "N/A", "NA", "--"):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_nifty_symbol(symbol: Any) -> dict[str, Any]:
    text = str(symbol or "").upper().replace(" ", "")
    if not text.startswith("NIFTY"):
        return {}
    option_match = re.search(r"(\d{4,6})(CE|PE)$", text)
    if not option_match:
        return {}
    return {
        "symbol": text,
        "strike": float(option_match.group(1)),
        "option_type": option_match.group(2),
    }


def dynamic_yield_gate(
    *,
    india_vix: Any,
    credit_pct_of_spread_width: Any,
    stop_loss_credit_multiple: Any,
    delta_available: bool,
    expected_move_available: bool,
    confidence_score: Any,
    hard_blocks: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = engine_config(config)
    base_yield = _float(cfg.get("base_min_premium_yield_on_margin_pct"), 0.80)
    low_vix_yield = _float(cfg.get("low_vix_exception_min_yield_pct"), 0.65)
    vix = _float(india_vix)
    hard_blocks = [str(item) for item in (hard_blocks or []) if str(item).strip()]
    checks = {
        "low_vix": 0 < vix < _float(cfg.get("low_vix_exception_vix_below"), 12.0),
        "credit_ok": _float(credit_pct_of_spread_width) >= _float(cfg.get("min_credit_pct_of_spread_width"), 8.0),
        "stop_loss_ok": _float(stop_loss_credit_multiple, 99.0)
        <= _float(cfg.get("low_vix_exception_max_stop_loss_credit_multiple"), 1.5),
        "delta_available": bool(delta_available),
        "expected_move_available": bool(expected_move_available),
        "confidence_ok": _float(confidence_score) >= 70,
        "no_hard_block": not hard_blocks,
    }
    if checks["low_vix"] and all(checks.values()):
        return {
            "dynamic_min_yield": low_vix_yield,
            "yield_gate_reason": "Low-VIX exception used: premium threshold reduced because credit, stop, data, and confidence are all safe.",
            "low_vix_exception_used": True,
            "checks": checks,
        }
    reason = "Base yield gate used."
    if checks["low_vix"]:
        failed = [name for name, ok in checks.items() if not ok]
        reason = f"Low-VIX exception not used; failed checks: {', '.join(failed)}."
    return {
        "dynamic_min_yield": base_yield,
        "yield_gate_reason": reason,
        "low_vix_exception_used": False,
        "checks": checks,
    }


def build_trade_unlock_panel(
    *,
    summary: dict[str, Any] | None = None,
    suggestion: dict[str, Any] | None = None,
    candidate_previews: list[dict[str, Any]] | None = None,
    confidence_score: dict[str, Any] | None = None,
    no_trade_decision: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = engine_config(config)
    summary = summary or {}
    suggestion = suggestion or {}
    confidence_score = confidence_score or {}
    no_trade_decision = no_trade_decision or {}
    candidates = candidate_previews or []
    min_credit_pct = _float(cfg.get("min_credit_pct_of_spread_width"), 8.0)
    width = max((_float(row.get("spread_width_points")) for row in candidates), default=_float(summary.get("spread_width_points")))
    current_credit = _float(summary.get("net_credit"))
    if current_credit <= 0 and candidates:
        current_credit = min((_float(row.get("net_credit")) for row in candidates if _float(row.get("net_credit")) > 0), default=0.0)
    required_credit = width * min_credit_pct / 100 if width > 0 else 0.0
    current_yield = _float(summary.get("premium_yield_on_margin_pct"))
    confidence_value = _float(confidence_score.get("score"))
    hard_blocks = [str(item) for item in (confidence_score.get("hard_blocks") or no_trade_decision.get("reasons") or [])]
    delta_available = any(row.get("delta") not in (None, "", "N/A") for row in candidates)
    expected_move_available = any(_float(row.get("expected_move_multiple")) > 0 for row in candidates)
    gate = dynamic_yield_gate(
        india_vix=summary.get("vix"),
        credit_pct_of_spread_width=(current_credit / width * 100 if width > 0 else 0),
        stop_loss_credit_multiple=cfg.get("stop_loss_credit_multiple"),
        delta_available=delta_available,
        expected_move_available=expected_move_available,
        confidence_score=confidence_value,
        hard_blocks=hard_blocks,
        config=cfg,
    )
    missing = []
    if not delta_available:
        missing.append("sell_delta")
    if not expected_move_available:
        missing.append("expected_move")
    if not candidates:
        missing.append("option_candidates")
    blocked = not bool(suggestion.get("allowed")) or bool(no_trade_decision.get("no_trade")) or confidence_score.get("action") in {"NO_TRADE", "PREVIEW_ONLY"}
    unlock_parts = []
    if current_yield < _float(gate["dynamic_min_yield"]):
        unlock_parts.append(
            f"Improve premium yield from {current_yield:.2f}% to at least {_float(gate['dynamic_min_yield']):.2f}%."
        )
    if required_credit > 0 and current_credit < required_credit:
        unlock_parts.append(f"Need net credit around {required_credit:.2f} points; current is {current_credit:.2f}.")
    if missing:
        unlock_parts.append(f"Refresh data to load: {', '.join(missing)}.")
    if hard_blocks:
        unlock_parts.append(f"Resolve hard blocks: {', '.join(hard_blocks)}.")
    if not unlock_parts and blocked:
        unlock_parts.append(str(suggestion.get("strategy_selection_reason") or no_trade_decision.get("blocking_reason") or "Wait for a cleaner regime."))
    if not blocked:
        unlock_parts.append("Trade gate is open; still use manual confirmation and defined-risk spreads only.")
    return {
        "blocked": blocked,
        "blocking_reason": str(suggestion.get("skip_reason") or no_trade_decision.get("blocking_reason") or ("Clear" if not blocked else "NIFTY_ENTRY_BLOCKED")),
        "current_premium_yield_on_margin_pct": current_yield,
        "required_premium_yield_on_margin_pct": gate["dynamic_min_yield"],
        "current_credit_points": current_credit,
        "required_credit_points": required_credit,
        "credit_gap_points": max(0.0, required_credit - current_credit),
        "missing_data_fields": missing,
        "unlock_message": " ".join(unlock_parts),
        **gate,
    }


def scan_nifty_spread_alternatives(
    market_state: dict[str, Any] | None,
    option_chain: list[dict[str, Any]] | None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cfg = engine_config(config)
    market_state = market_state or {}
    candidates = option_chain or []
    widths = [300, 400, 500, 600, 700]
    alternatives: list[dict[str, Any]] = []
    if candidates:
        for row in candidates:
            width = _float(row.get("spread_width_points") or row.get("width"), _float(cfg.get("default_spread_width_points"), 500))
            credit = _float(row.get("net_credit") or row.get("option_ltp") or row.get("ltp"))
            max_gain = _float(row.get("max_gain_opportunity") or row.get("max_gain") or credit * _int(row.get("quantity"), 65))
            max_loss = _float(row.get("margin_required") or row.get("max_loss") or max(0, width - credit) * _int(row.get("quantity"), 65))
            credit_pct = _float(row.get("credit_pct_of_spread_width"), credit / width * 100 if width else 0)
            confidence = _int(row.get("confidence_score") or market_state.get("confidence_score"), 50)
            allowed = credit_pct >= _float(cfg.get("min_credit_pct_of_spread_width"), 8.0)
            liquidity_ok = _int(row.get("oi")) >= 1000 or _int(row.get("volume")) >= 10
            alternatives.append(
                {
                    "strategy": str(row.get("selected_strategy") or market_state.get("selected_strategy") or "IRON_CONDOR"),
                    "expiry": row.get("expiry_date") or market_state.get("expiry"),
                    "dte": row.get("dte") or market_state.get("dte") or "N/A",
                    "side": row.get("side") or row.get("option_type") or "PAIR",
                    "short_strike": row.get("strike"),
                    "hedge_strike": row.get("hedge_strike"),
                    "width": width,
                    "short_delta": row.get("delta"),
                    "hedge_delta": row.get("hedge_delta"),
                    "net_credit_points": credit,
                    "credit_pct_of_width": credit_pct,
                    "premium_yield_on_margin_pct": _float(row.get("premium_yield_on_margin_pct"), max_gain / max_loss * 100 if max_loss else 0),
                    "max_gain": max_gain,
                    "max_loss": max_loss,
                    "max_loss_to_credit_ratio": max_loss / max_gain if max_gain else 999.0,
                    "liquidity_status": "GOOD" if liquidity_ok else "REVIEW",
                    "confidence_score": confidence,
                    "allowed": allowed and liquidity_ok,
                    "rejection_reason": "" if allowed and liquidity_ok else ("Credit below 8% width" if not allowed else "OI/volume needs review"),
                }
            )
    if not alternatives:
        for strategy in ("BULL_PUT_SPREAD", "BEAR_CALL_SPREAD", "IRON_CONDOR"):
            for width in widths:
                alternatives.append(
                    {
                        "strategy": strategy,
                        "expiry": market_state.get("expiry") or "Next monthly",
                        "dte": market_state.get("dte") or "21-35",
                        "side": "PAIR" if strategy == "IRON_CONDOR" else ("PE" if strategy == "BULL_PUT_SPREAD" else "CE"),
                        "short_strike": "Scan required",
                        "hedge_strike": "Scan required",
                        "width": width,
                        "short_delta": "0.12-0.18",
                        "hedge_delta": "0.03-0.06",
                        "net_credit_points": 0.0,
                        "credit_pct_of_width": 0.0,
                        "premium_yield_on_margin_pct": 0.0,
                        "max_gain": 0.0,
                        "max_loss": 0.0,
                        "max_loss_to_credit_ratio": 999.0,
                        "liquidity_status": "DATA_MISSING",
                        "confidence_score": 0,
                        "allowed": False,
                        "rejection_reason": "Option chain scan needs fresh Kite data",
                    }
                )
    alternatives.sort(
        key=lambda row: (
            0 if row.get("allowed") else 1,
            -_float(row.get("confidence_score")),
            -_float(row.get("credit_pct_of_width")),
            -_float(row.get("premium_yield_on_margin_pct")),
            _float(row.get("max_loss_to_credit_ratio"), 999.0),
            0 if row.get("liquidity_status") == "GOOD" else 1,
        )
    )
    return alternatives[:5]


def validate_active_nifty_hedges(active_positions: list[dict[str, Any]] | None) -> dict[str, Any]:
    positions = active_positions or []
    parsed = []
    for position in positions:
        parsed_symbol = _parse_nifty_symbol(position.get("tradingsymbol"))
        if not parsed_symbol:
            continue
        parsed.append({**position, **parsed_symbol, "quantity": _int(position.get("quantity"))})
    shorts = [row for row in parsed if row["quantity"] < 0]
    longs = [row for row in parsed if row["quantity"] > 0]
    rows: list[dict[str, Any]] = []
    critical = False
    for short in shorts:
        side = short["option_type"]
        short_qty = abs(_int(short.get("quantity")))
        expiry = short.get("expiry")
        if side == "PE":
            hedge_candidates = [row for row in longs if row["option_type"] == "PE" and row.get("expiry") == expiry and _float(row.get("strike")) < _float(short.get("strike"))]
        else:
            hedge_candidates = [row for row in longs if row["option_type"] == "CE" and row.get("expiry") == expiry and _float(row.get("strike")) > _float(short.get("strike"))]
        hedge = max(hedge_candidates, key=lambda row: _int(row.get("quantity")), default=None)
        if not hedge:
            status, severity, action = "UNHEDGED_SHORT", "CRITICAL", "ADD_HEDGE_OR_EXIT"
            critical = True
        elif _int(hedge.get("quantity")) < short_qty:
            status, severity, action = "PARTIAL_HEDGE", "HIGH", "ADD_QUANTITY_OR_REDUCE_SHORT"
        else:
            status, severity, action = "OK", "LOW", "MONITOR"
        rows.append(
            {
                "short_symbol": short.get("tradingsymbol") or short.get("symbol"),
                "hedge_symbol": hedge.get("tradingsymbol") if hedge else "",
                "hedge_status": status,
                "severity": severity,
                "short_quantity": short_qty,
                "hedge_quantity": _int(hedge.get("quantity")) if hedge else 0,
                "quantity_match": bool(hedge and _int(hedge.get("quantity")) >= short_qty),
                "expiry_match": bool(hedge and hedge.get("expiry") == expiry),
                "action_required": action,
            }
        )
    return {
        "status": "CRITICAL" if critical else "OK" if not any(row["severity"] == "HIGH" for row in rows) else "HIGH",
        "block_new_entries": critical,
        "allow_exit_orders": True,
        "allow_hedge_repair_orders": critical,
        "rows": rows,
    }


def validate_nifty_data_quality(inputs: dict[str, Any] | None) -> dict[str, Any]:
    inputs = inputs or {}
    required = [
        "nifty_spot",
        "india_vix",
        "option_ltp",
        "bid_ask",
        "sell_delta",
        "hedge_delta",
        "expected_move",
        "expiry",
        "instrument_symbol",
        "margin_estimate",
    ]
    missing = [field for field in required if not inputs.get(field)]
    if not missing:
        status = "GOOD"
    elif len(missing) <= 3:
        status = "PARTIAL"
    else:
        status = "BLOCKED"
    return {
        "status": status,
        "live_order_enabled": status == "GOOD",
        "preview_allowed": True,
        "missing_fields": missing,
        "last_refreshed_at": inputs.get("last_refreshed_at") or datetime.now().isoformat(timespec="seconds"),
        "staleness_warning": inputs.get("staleness_warning") or "",
    }


def build_strategy_recommendation(
    *,
    unlock_panel: dict[str, Any],
    alternatives: list[dict[str, Any]],
    confidence_score: dict[str, Any] | None = None,
    hedge_integrity: dict[str, Any] | None = None,
    data_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    confidence_score = confidence_score or {}
    hedge_integrity = hedge_integrity or {}
    data_quality = data_quality or {}
    best = next((row for row in alternatives if row.get("allowed")), alternatives[0] if alternatives else {})
    if hedge_integrity.get("status") == "CRITICAL":
        action = "NO_TRADE"
        reason = "Active NIFTY hedge integrity is critical. Repair hedge or exit before new entries."
    elif data_quality.get("status") != "GOOD":
        action = "NO_TRADE"
        reason = "Data quality is not good enough for live order. Preview only."
    elif unlock_panel.get("blocked"):
        action = "SCAN_WHEEL" if alternatives else "KEEP_CASH"
        reason = unlock_panel.get("unlock_message") or "NIFTY trade blocked."
    elif best.get("allowed"):
        action = "TRADE_ALLOWED"
        reason = f"{best.get('strategy')} allowed with {best.get('credit_pct_of_width', 0):.2f}% credit of width."
    else:
        action = "KEEP_CASH"
        reason = "No high-quality NIFTY candidate found."
    return {
        "recommended_action": action,
        "recommended_strategy": best.get("strategy") or "NO_TRADE",
        "confidence_score": confidence_score.get("score") or best.get("confidence_score") or 0,
        "reason": reason,
        "best_candidate": best,
        "risk_summary": f"Data {data_quality.get('status', 'N/A')} | Hedge {hedge_integrity.get('status', 'N/A')} | Yield gate {unlock_panel.get('required_premium_yield_on_margin_pct', 0):.2f}%",
        "next_step": "Build Tactical Spread Order" if action == "TRADE_ALLOWED" else ("Review Wheel/Covered Call" if action == "SCAN_WHEEL" else "Keep cash / repair risk"),
    }


def build_capital_router(nifty_no_trade: bool, fallback_candidates: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if not nifty_no_trade:
        return [
            {
                "module": "NIFTY",
                "candidate": "Current tactical spread",
                "expected_premium_yield": "See NIFTY candidates",
                "margin_required": "See margin card",
                "max_risk": "Defined by spread width",
                "confidence_score": "N/A",
                "action": "Proceed only if gates are green",
            }
        ]
    candidates = fallback_candidates or []
    if candidates:
        return candidates[:3]
    return [
        {
            "module": "Wheel Income",
            "candidate": "Scan CSP candidates",
            "expected_premium_yield": "Use PE Sell tab",
            "margin_required": "Cash secured",
            "max_risk": "Assignment value",
            "confidence_score": "Review",
            "action": "Route to Wheel",
        },
        {
            "module": "Covered Call",
            "candidate": "Scan held stocks",
            "expected_premium_yield": "Use CE Sell cards",
            "margin_required": "Shares held",
            "max_risk": "Upside capped",
            "confidence_score": "Review",
            "action": "Route to Covered Calls",
        },
        {
            "module": "Cash",
            "candidate": "Keep cash",
            "expected_premium_yield": "0",
            "margin_required": "0",
            "max_risk": "0",
            "confidence_score": "High safety",
            "action": "Wait",
        },
    ]
