"""Expiry-comparison evaluator for DHAN/Kite 5%/10% stock-option spreads."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import risk_config
from kite_option_resolver import KiteOptionResolver
from kite_spread_engine import build_kite_spread_preview


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dte(expiry: Any, today: date | None = None) -> int:
    expiry_date = _parse_date(expiry)
    if not expiry_date:
        return 0
    return max((expiry_date - (today or date.today())).days, 0)


def _empty_month(expiry: Any = "") -> dict[str, Any]:
    expiry_text = _parse_date(expiry).isoformat() if _parse_date(expiry) else str(expiry or "")
    return {
        "expiry": expiry_text,
        "dte": _dte(expiry_text),
        "sell_leg_tradingsymbol": "",
        "buy_leg_tradingsymbol": "",
        "sell_strike": 0,
        "buy_strike": 0,
        "sell_premium": 0,
        "buy_premium": 0,
        "net_credit": 0,
        "max_gain": 0,
        "max_loss": 0,
        "breakeven": 0,
        "pop": 0,
        "pop_is_approx": True,
        "return_on_risk_pct": 0,
        "margin_required": 0,
        "event_risk": "NO",
        "liquidity": "WEAK",
        "risk_decision": "BLOCKED",
        "risk_reason": "NOT_EVALUATED",
    }


def _month_from_preview(preview: dict[str, Any], expiry: Any, today: date | None = None) -> dict[str, Any]:
    return {
        "expiry": str(preview.get("expiry") or (_parse_date(expiry).isoformat() if _parse_date(expiry) else expiry or "")),
        "sell_expiry": str(preview.get("sell_expiry") or preview.get("expiry") or ""),
        "buy_expiry": str(preview.get("buy_expiry") or preview.get("expiry") or ""),
        "structure_type": str(preview.get("structure_type") or "SAME_EXPIRY_VERTICAL"),
        "dte": _dte(preview.get("expiry") or expiry, today=today),
        "sell_leg_tradingsymbol": str(preview.get("sell_leg_tradingsymbol") or ""),
        "buy_leg_tradingsymbol": str(preview.get("buy_leg_tradingsymbol") or ""),
        "sell_strike": _num(preview.get("sell_strike")),
        "buy_strike": _num(preview.get("hedge_strike")),
        "sell_premium": _num(preview.get("sell_leg_premium")),
        "buy_premium": _num(preview.get("buy_leg_premium")),
        "net_credit": _num(preview.get("net_credit")),
        "max_gain": _num(preview.get("max_gain")),
        "max_loss": _num(preview.get("max_loss")),
        "breakeven": _num(preview.get("breakeven")),
        "pop": _num(preview.get("pop_estimate")),
        "pop_is_approx": bool(preview.get("pop_is_approx", True)),
        "return_on_risk_pct": _num(preview.get("return_on_risk_pct")),
        "margin_required": _num(preview.get("margin_required")),
        "event_risk": str(preview.get("event_risk") or "NO"),
        "liquidity": str(preview.get("liquidity_view") or "WEAK"),
        "risk_decision": str(preview.get("risk_decision") or "BLOCKED"),
        "risk_reason": str(preview.get("risk_reason") or preview.get("reason") or ""),
    }


def _expiry_event_risk(event_data: dict[str, Any] | None, expiry_type: str) -> bool:
    data = event_data or {}
    if bool(data.get("event_risk") or data.get("event_risk_flag")):
        return True
    typed = data.get(expiry_type) or data.get(f"{expiry_type}_month") or {}
    if isinstance(typed, dict):
        return bool(typed.get("event_risk") or typed.get("event_risk_flag"))
    return bool(typed)


def _approved(month: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if str(month.get("risk_decision") or "").upper() != "APPROVED":
        reasons.append("risk engine did not approve")
    if _num(month.get("max_gain")) < risk_config.MIN_PAIR_MAX_GAIN_INR:
        reasons.append(f"max gain below ₹{risk_config.MIN_PAIR_MAX_GAIN_INR:,.0f}")
    if _num(month.get("pop")) < risk_config.MIN_POP_FOR_SPREAD:
        reasons.append(f"POP below {risk_config.MIN_POP_FOR_SPREAD}%")
    if _num(month.get("return_on_risk_pct")) < risk_config.MIN_RETURN_ON_RISK_PCT:
        reasons.append(f"return on risk below {risk_config.MIN_RETURN_ON_RISK_PCT}%")
    if _num(month.get("max_loss")) > risk_config.MAX_ACCEPTABLE_PAIR_LOSS_INR:
        reasons.append(f"max loss above ₹{risk_config.MAX_ACCEPTABLE_PAIR_LOSS_INR:,.0f}")
    if str(month.get("event_risk") or "").upper() == "YES":
        reasons.append("event risk")
    if str(month.get("liquidity") or "").upper() != "OK":
        reasons.append("liquidity weak")
    return not reasons, reasons


def _comparison(current_month: dict[str, Any], next_month: dict[str, Any] | None, better_choice: str) -> dict[str, Any]:
    next_clean = next_month or _empty_month()
    return {
        "gain_difference": round(_num(next_clean.get("max_gain")) - _num(current_month.get("max_gain")), 2),
        "pop_difference": round(_num(next_clean.get("pop")) - _num(current_month.get("pop")), 2),
        "risk_difference": round(_num(next_clean.get("max_loss")) - _num(current_month.get("max_loss")), 2),
        "return_on_risk_difference": round(_num(next_clean.get("return_on_risk_pct")) - _num(current_month.get("return_on_risk_pct")), 2),
        "better_choice": better_choice,
    }


def _calendar_hedge_preview(
    current_preview: dict[str, Any],
    next_preview: dict[str, Any] | None,
    today: date | None = None,
) -> dict[str, Any]:
    """Build SELL-next-month + BUY-current-month hedge preview.

    This is intentionally marked blocked for direct order placement because the
    hedge expires before the short option. The UI may show it for evaluation,
    but the execution safety path must not treat it as a standard defined-risk
    vertical spread.
    """

    if not current_preview or not next_preview:
        return {}
    if not current_preview.get("buy_leg_tradingsymbol") or not next_preview.get("sell_leg_tradingsymbol"):
        return {}
    clean = dict(next_preview)
    sell_expiry = str(next_preview.get("expiry") or "")
    buy_expiry = str(current_preview.get("expiry") or "")
    sell_premium = _num(next_preview.get("sell_leg_premium"))
    buy_premium = _num(current_preview.get("buy_leg_premium"))
    quantity = _num(next_preview.get("quantity") or current_preview.get("quantity"))
    sell_strike = _num(next_preview.get("sell_strike"))
    hedge_strike = _num(current_preview.get("hedge_strike"))
    net_credit = sell_premium - buy_premium
    width = abs(hedge_strike - sell_strike)
    max_gain = max(net_credit * quantity, 0)
    estimated_vertical_loss = max((width - net_credit) * quantity, 0)
    risk_reason = (
        "CALENDAR_HEDGE_EXPIRES_BEFORE_SHORT: SELL leg is next-month but BUY hedge is current-month; "
        "risk is not a standard defined-risk vertical after hedge expiry."
    )
    prior_reasons = [
        str(next_preview.get("risk_reason") or next_preview.get("reason") or "").strip(),
        str(current_preview.get("risk_reason") or current_preview.get("reason") or "").strip(),
    ]
    prior_reasons = [item for item in prior_reasons if item and item != "Spread risk checks passed."]
    if prior_reasons:
        risk_reason = risk_reason + " Prior leg checks: " + " | ".join(prior_reasons)
    clean.update(
        {
            "expiry": sell_expiry,
            "sell_expiry": sell_expiry,
            "buy_expiry": buy_expiry,
            "structure_type": "NEXT_SELL_CURRENT_BUY_CALENDAR_HEDGE",
            "recommended_expiry": "NEXT_SELL_CURRENT_BUY",
            "selected_expiry_choice": "NEXT_SELL_CURRENT_BUY",
            "recommendation_reason": "Review-only calendar hedge: next-month 5% OTM SELL with current-month 10% OTM BUY hedge.",
            "buy_leg": current_preview.get("buy_leg") or {},
            "buy_leg_tradingsymbol": str(current_preview.get("buy_leg_tradingsymbol") or ""),
            "buy_leg_premium": round(buy_premium, 2),
            "buy_limit_price": round(_num(current_preview.get("buy_limit_price") or buy_premium), 2),
            "hedge_strike": hedge_strike,
            "hedge_target_strike": _num(current_preview.get("hedge_target_strike")),
            "raw_hedge_target_strike": _num(current_preview.get("raw_hedge_target_strike")),
            "net_credit": round(net_credit, 2),
            "spread_width": width,
            "max_gain": round(max_gain, 2),
            "max_loss": round(estimated_vertical_loss, 2),
            "return_on_risk_pct": round(max_gain / estimated_vertical_loss * 100, 2) if estimated_vertical_loss else 0,
            "risk_decision": "BLOCKED",
            "final_risk_decision": "NO_TRADE",
            "trader_view": "WATCH_ONLY",
            "risk_reason": risk_reason,
            "reason": risk_reason,
            "risk_veto_advisory": "Direct order placement is blocked until the short-leg expiry also has a valid hedge/roll plan.",
            "order_payload": {
                "mode": "PAPER_DEFAULT",
                "sequence": "BUY current-month hedge first, then SELL next-month leg after hedge completion",
                "sell_leg": {
                    "tradingsymbol": str(next_preview.get("sell_leg_tradingsymbol") or ""),
                    "transaction_type": "SELL",
                    "quantity": int(quantity),
                    "limit_price": round(_num(next_preview.get("sell_limit_price") or sell_premium), 2),
                },
                "buy_leg": {
                    "tradingsymbol": str(current_preview.get("buy_leg_tradingsymbol") or ""),
                    "transaction_type": "BUY",
                    "quantity": int(quantity),
                    "limit_price": round(_num(current_preview.get("buy_limit_price") or buy_premium), 2),
                },
            },
        }
    )
    clean["calendar_hedge"] = _month_from_preview(clean, sell_expiry, today=today)
    return clean


def _resolve_expiry_pair(
    symbol: str,
    current_month_expiry: Any,
    next_month_expiry: Any,
    resolver: KiteOptionResolver,
) -> tuple[str, str]:
    current = _parse_date(current_month_expiry)
    next_expiry = _parse_date(next_month_expiry)
    expiries = resolver.monthly_expiries(symbol)
    if current is None:
        current = resolver.selected_expiry(symbol)
    if next_expiry is None and current is not None:
        later = [item for item in expiries if item > current]
        next_expiry = later[0] if later else None
    return (
        current.isoformat() if current else str(current_month_expiry or ""),
        next_expiry.isoformat() if next_expiry else str(next_month_expiry or ""),
    )


def _flatten_recommended_preview(
    result: dict[str, Any],
    current_preview: dict[str, Any],
    next_preview: dict[str, Any] | None,
) -> dict[str, Any]:
    recommended = str(result.get("recommended_expiry") or "NO_TRADE")
    selected_preview = current_preview if recommended == "CURRENT_MONTH" else next_preview if recommended == "NEXT_MONTH" and next_preview else current_preview
    flat = dict(selected_preview)
    flat["recommended_expiry"] = recommended
    flat["recommendation_reason"] = result.get("recommendation_reason")
    flat["current_month"] = result.get("current_month")
    flat["next_month"] = result.get("next_month")
    flat["comparison"] = result.get("comparison")
    flat["current_month_preview"] = current_preview
    flat["next_month_preview"] = next_preview or {}
    calendar_preview = result.get("calendar_hedge_preview") if isinstance(result.get("calendar_hedge_preview"), dict) else {}
    flat["calendar_hedge_preview"] = calendar_preview
    flat["calendar_hedge"] = result.get("calendar_hedge") if calendar_preview else {}
    flat["current_month_expiry"] = (result.get("current_month") or {}).get("expiry")
    flat["current_month_max_gain"] = (result.get("current_month") or {}).get("max_gain")
    flat["current_month_max_loss"] = (result.get("current_month") or {}).get("max_loss")
    flat["current_month_pop"] = (result.get("current_month") or {}).get("pop")
    flat["current_month_return_on_risk_pct"] = (result.get("current_month") or {}).get("return_on_risk_pct")
    flat["next_month_expiry"] = (result.get("next_month") or {}).get("expiry")
    flat["next_month_max_gain"] = (result.get("next_month") or {}).get("max_gain")
    flat["next_month_max_loss"] = (result.get("next_month") or {}).get("max_loss")
    flat["next_month_pop"] = (result.get("next_month") or {}).get("pop")
    flat["next_month_return_on_risk_pct"] = (result.get("next_month") or {}).get("return_on_risk_pct")
    flat["trader_view"] = "TRADE" if recommended in {"CURRENT_MONTH", "NEXT_MONTH"} else "WATCH_ONLY"
    flat["final_risk_decision"] = "APPROVED" if recommended in {"CURRENT_MONTH", "NEXT_MONTH"} else "NO_TRADE"
    if recommended == "NO_TRADE":
        flat["risk_decision"] = "NO_TRADE"
        flat["risk_reason"] = result.get("recommendation_reason")
        flat["reason"] = result.get("recommendation_reason")
    return flat


def evaluate_spread_with_expiry_comparison(
    symbol: str,
    strategy_type: str,
    spot: float | None,
    selected_lots: int,
    current_month_expiry: Any,
    next_month_expiry: Any,
    option_chain_data: list[dict[str, Any]] | dict[str, Any] | None,
    kite_adapter: Any,
    risk_engine: Any,
    market_data: dict[str, Any] | None,
    technical_data: dict[str, Any] | None,
    event_data: dict[str, Any] | None,
) -> dict[str, Any]:
    resolver = KiteOptionResolver(
        instruments=list(option_chain_data or []) if isinstance(option_chain_data, list) else list((option_chain_data or {}).get("instruments") or []),
        today=(market_data or {}).get("today"),
    )
    current_expiry, next_expiry = _resolve_expiry_pair(symbol, current_month_expiry, next_month_expiry, resolver)
    current_event = _expiry_event_risk(event_data, "current")
    next_event = _expiry_event_risk(event_data, "next")
    current_preview = build_kite_spread_preview(
        symbol,
        spot,
        strategy_type,
        current_expiry,
        selected_lots,
        resolver,
        kite_adapter,
        risk_engine,
        event_risk=current_event,
        as_of_date=(market_data or {}).get("today"),
    )
    current_month = _month_from_preview(current_preview, current_expiry, today=(market_data or {}).get("today"))
    current_ok, current_reasons = _approved(current_month)

    next_preview: dict[str, Any] | None = None
    next_month: dict[str, Any] = _empty_month(next_expiry)
    should_check_next = (
        bool(risk_config.ALLOW_NEXT_MONTH_ROLLOVER_ANALYSIS)
        and bool(next_expiry)
    )
    if should_check_next:
        next_preview = build_kite_spread_preview(
            symbol,
            spot,
            strategy_type,
            next_expiry,
            selected_lots,
            resolver,
            kite_adapter,
            risk_engine,
            event_risk=next_event,
            as_of_date=(market_data or {}).get("today"),
        )
        next_month = _month_from_preview(next_preview, next_expiry, today=(market_data or {}).get("today"))
    next_ok, next_reasons = _approved(next_month)

    should_recommend_next = _num(current_month.get("max_gain")) < risk_config.AUTO_CHECK_NEXT_EXPIRY_IF_GAIN_BELOW
    if current_ok and _num(current_month.get("max_gain")) >= risk_config.MIN_PAIR_MAX_GAIN_INR:
        recommended = "CURRENT_MONTH"
        reason = "Current month meets max gain, POP, return-on-risk, liquidity, event, and max-loss checks."
    elif should_check_next and should_recommend_next and next_ok:
        recommended = "NEXT_MONTH"
        reason = "Current month max gain is below threshold; next month meets gain, POP, return-on-risk, liquidity, event, and max-loss checks."
    else:
        recommended = "NO_TRADE"
        reason_parts = []
        if current_reasons:
            reason_parts.append("current: " + ", ".join(current_reasons))
        if should_check_next and next_reasons:
            reason_parts.append("next: " + ", ".join(next_reasons))
        elif not should_check_next:
            reason_parts.append("next month was not evaluated because current gain threshold did not require rollover analysis or next expiry was unavailable")
        reason = "; ".join(reason_parts) or "No expiry meets paired-spread recommendation rules."

    calendar_preview = _calendar_hedge_preview(current_preview, next_preview, today=(market_data or {}).get("today"))
    result = {
        "symbol": str(symbol or "").upper(),
        "strategy_type": str(strategy_type or "").upper(),
        "recommended_expiry": recommended,
        "recommendation_reason": reason,
        "current_month": current_month,
        "next_month": next_month,
        "calendar_hedge": calendar_preview.get("calendar_hedge") if calendar_preview else {},
        "calendar_hedge_preview": calendar_preview,
        "comparison": _comparison(current_month, next_month, recommended),
    }
    result["recommended_preview"] = _flatten_recommended_preview(result, current_preview, next_preview)
    return result
