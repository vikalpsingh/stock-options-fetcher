"""Build Kite 5%/10% spread previews from live/resolved option data."""

from __future__ import annotations

from datetime import date
from typing import Any

import kite_spread_config as spread_cfg
from kite_spread_income_universe import ce_coverage_reason
from kite_option_resolver import KiteOptionResolver
from kite_option_liquidity import analyze_pair_liquidity
from risk_engine import RiskVetoEngine


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fetch_cmp_from_kite(adapter: Any, symbols: list[str]) -> dict[str, float | None]:
    instruments = [f"NSE:{str(symbol).upper()}" for symbol in symbols]
    try:
        data = adapter.get_ltp(instruments)
    except Exception:
        return {str(symbol).upper(): None for symbol in symbols}
    out = {}
    for symbol in symbols:
        key = f"NSE:{str(symbol).upper()}"
        out[str(symbol).upper()] = _num((data.get(key) or {}).get("last_price") or (data.get(key) or {}).get("ltp")) or None
    return out


def fetch_fresh_equity_quotes_from_kite(adapter: Any, symbols: list[str]) -> dict[str, dict[str, float | None]]:
    """Fetch current NSE LTP/day-change directly from Kite with no app cache."""

    clean_symbols = [str(symbol or "").strip().upper().removeprefix("NSE:") for symbol in symbols if str(symbol or "").strip()]
    instruments = [f"NSE:{symbol}" for symbol in clean_symbols]
    try:
        data = adapter.get_quote(instruments)
    except Exception:
        return {symbol: {"ltp": None, "day_change_pct": None, "previous_close": None, "yearly_high": None, "pct_to_52_high": None} for symbol in clean_symbols}
    out: dict[str, dict[str, float | None]] = {}
    for symbol in clean_symbols:
        key = f"NSE:{symbol}"
        quote = data.get(key) or {}
        ltp = _num(quote.get("last_price") or quote.get("ltp")) or None
        close = _num((quote.get("ohlc") or {}).get("close") or quote.get("close")) or None
        yearly_high = _num(
            quote.get("yearly_high")
            or quote.get("52_week_high")
            or quote.get("fifty_two_week_high")
            or (quote.get("ohlc") or {}).get("yearly_high")
        ) or None
        day_change_pct = round((ltp - close) / close * 100, 2) if ltp and close else None
        pct_to_52_high = round((ltp - yearly_high) / yearly_high * 100, 2) if ltp and yearly_high else None
        out[symbol] = {
            "ltp": ltp,
            "day_change_pct": day_change_pct,
            "previous_close": close,
            "yearly_high": yearly_high,
            "pct_to_52_high": pct_to_52_high,
        }
    return out


def _quote_metrics(quote: dict[str, Any]) -> dict[str, float]:
    depth = quote.get("depth") or {}
    buy = (depth.get("buy") or [{}])[0] if isinstance(depth.get("buy"), list) else {}
    sell = (depth.get("sell") or [{}])[0] if isinstance(depth.get("sell"), list) else {}
    return {
        "ltp": _num(quote.get("last_price") or quote.get("ltp")),
        "bid": _num(buy.get("price") or quote.get("bid")),
        "ask": _num(sell.get("price") or quote.get("ask")),
        "volume": _num(quote.get("volume")),
        "oi": _num(quote.get("oi")),
    }


def _pop_estimate(strategy: str, spot: float, sell_strike: float, vix: float = 15.0, dte: int = 30) -> tuple[float, bool]:
    distance = abs(sell_strike - spot) / spot * 100 if spot > 0 else 0
    vol_penalty = max(vix - 12, 0) * 0.8
    time_penalty = max(30 - dte, 0) * 0.2
    pop = max(45, min(90, 55 + distance * 4 - vol_penalty - time_penalty))
    return round(pop, 1), True


def build_kite_spread_preview(symbol: str, cmp: float | None, strategy: str, expiry: str, lots: int, resolver: KiteOptionResolver, adapter: Any | None = None, risk_engine: Any | None = None, event_risk: bool = False, as_of_date: date | None = None) -> dict[str, Any]:
    reasons: list[str] = []
    if not cmp:
        reasons.append("CMP_UNAVAILABLE")
        cmp = 0.0
    resolved = resolver.resolve_spread_legs(symbol, cmp, expiry, strategy) if cmp else {"error": "CONTRACT_UNRESOLVED"}
    if resolved.get("error"):
        reasons.append("CONTRACT_UNRESOLVED")
        sell = buy = {}
        lot_size = 0
        expiry_text = expiry
        strike_step = sell_target_strike = hedge_target_strike = raw_sell_target_strike = raw_hedge_target_strike = 0.0
    else:
        sell, buy = resolved["sell_leg"], resolved["buy_leg"]
        lot_size = int(resolved.get("lot_size") or 0)
        expiry_text = resolved["expiry"]
        strike_step = _num(resolved.get("strike_step"))
        sell_target_strike = _num(resolved.get("sell_target_strike"))
        hedge_target_strike = _num(resolved.get("hedge_target_strike"))
        raw_sell_target_strike = _num(resolved.get("raw_sell_target_strike"))
        raw_hedge_target_strike = _num(resolved.get("raw_hedge_target_strike"))
    sell_ts = str(sell.get("tradingsymbol") or "")
    buy_ts = str(buy.get("tradingsymbol") or "")
    quotes = {}
    quote_fetch_attempted = False
    if adapter and sell_ts and buy_ts:
        try:
            quote_fetch_attempted = True
            quotes = adapter.get_quote([f"NFO:{sell_ts}", f"NFO:{buy_ts}"])
        except Exception:
            quotes = {}
    sell_quote = quotes.get(f"NFO:{sell_ts}") or {}
    buy_quote = quotes.get(f"NFO:{buy_ts}") or {}
    sell_q = _quote_metrics(sell_quote or sell)
    buy_q = _quote_metrics(buy_quote or buy)
    pair_liquidity = analyze_pair_liquidity(
        sell_ts,
        sell_quote,
        buy_ts,
        buy_quote,
        allow_fallback=not quote_fetch_attempted,
    )
    sell_premium, buy_premium = sell_q["ltp"], buy_q["ltp"]
    if sell_premium <= 0 or buy_premium <= 0:
        reasons.append("OPTION_PREMIUM_UNAVAILABLE")
    for side, q in (("SELL", sell_q), ("BUY", buy_q)):
        if q["volume"] == 0:
            reasons.append("LOW_LIQUIDITY")
        if q["oi"] == 0:
            reasons.append("MISSING_OI")
        if q["bid"] and q["ask"]:
            mid = (q["bid"] + q["ask"]) / 2
            if mid and (q["ask"] - q["bid"]) / mid * 100 > spread_cfg.MAX_BID_ASK_SPREAD_PCT:
                reasons.append("WIDE_BID_ASK")
    quantity = lot_size * max(int(lots or 1), 1)
    net_credit = sell_premium - buy_premium
    if net_credit <= 0:
        reasons.append("NET_CREDIT_NON_POSITIVE")
    sell_strike = _num(sell.get("strike"))
    buy_strike = _num(buy.get("strike"))
    spread_width = abs(buy_strike - sell_strike)
    max_gain = max(net_credit * quantity, 0)
    max_loss = max((spread_width - net_credit) * quantity, 0)
    if max_loss <= 0:
        reasons.append("MAX_LOSS_INVALID")
    if max_loss > spread_cfg.MAX_PAIR_LOSS:
        reasons.append("MAX_LOSS_TOO_HIGH")
    ror = max_gain / max_loss * 100 if max_loss else 0
    if ror < spread_cfg.MIN_RETURN_ON_RISK_PCT:
        reasons.append("RETURN_ON_RISK_TOO_LOW")
    if event_risk:
        reasons.append("EVENT_RISK")
    if not pair_liquidity.get("liquidity_order_allowed", True):
        reasons.append("LIQUIDITY_RED_ORDER_BLOCKED")
    option_type = "CE" if strategy == "BEAR_CALL_SPREAD" else "PE"
    coverage_reason = ce_coverage_reason(symbol, lots, lot_size) if option_type == "CE" else ""
    if coverage_reason:
        reasons.append(coverage_reason)
    risk_trade = {
        "symbol": symbol, "tradingsymbol": sell_ts, "option_type": option_type, "transaction_type": "SELL",
        "quantity": quantity, "lot_size": lot_size or quantity or 1, "premium": sell_premium,
        "price": sell_premium, "strike": sell_strike, "expiry": expiry_text, "underlying_spot": cmp,
        "as_of_date": (as_of_date or date.today()).isoformat(),
        "event_data": {"event_type": "results", "next_event_date": (as_of_date or date.today()).isoformat()} if event_risk else {},
    }
    risk = (risk_engine or RiskVetoEngine()).evaluate(risk_trade)
    defined_risk_pair = bool(sell_ts and buy_ts and max_loss > 0)
    risk_veto_advisory = ""
    if risk.get("decision") == "BLOCKED" and not defined_risk_pair:
        reasons.append("RISK_VETO_ENGINE_BLOCKED")
    elif risk.get("decision") == "BLOCKED":
        risk_veto_advisory = "Single-leg risk veto treated as advisory because both hedge legs are resolved and max loss is defined."
    reasons = list(dict.fromkeys(reasons))
    pop, approx = _pop_estimate(strategy, cmp, sell_strike)
    breakeven = sell_strike + net_credit if strategy == "BEAR_CALL_SPREAD" else sell_strike - net_credit
    return {
        "symbol": symbol, "cmp": cmp, "strategy_type": strategy, "expiry": expiry_text, "lot_size": lot_size,
        "selected_lots": lots, "quantity": quantity, "sell_leg_tradingsymbol": sell_ts,
        "buy_leg_tradingsymbol": buy_ts, "sell_leg_premium": round(sell_premium, 2),
        "buy_leg_premium": round(buy_premium, 2), "sell_limit_price": round(sell_premium, 2),
        "buy_limit_price": round(buy_premium, 2), "net_credit": round(net_credit, 2),
        "spread_width": spread_width, "max_gain": round(max_gain, 2), "max_loss": round(max_loss, 2),
        "breakeven": round(breakeven, 2), "return_on_risk_pct": round(ror, 2), "pop_estimate": pop,
        "pop_is_approx": approx, "margin_required": 0, "liquidity_view": "OK" if pair_liquidity.get("pair_liquidity_condition") in {"AMBER", "GREEN"} and not any(r in reasons for r in ("LOW_LIQUIDITY", "WIDE_BID_ASK", "MISSING_OI")) else "WEAK",
        "event_risk": "YES" if event_risk else "NO", "risk_decision": "BLOCKED" if reasons else "APPROVED",
        "risk_reason": "; ".join(reasons) if reasons else "Spread risk checks passed.", "risk_engine": risk,
        "risk_veto_advisory": risk_veto_advisory,
        "spot": cmp, "sell_strike": sell_strike, "hedge_strike": buy_strike,
        "strike_step": strike_step, "sell_target_strike": sell_target_strike,
        "hedge_target_strike": hedge_target_strike,
        "raw_sell_target_strike": round(raw_sell_target_strike, 2),
        "raw_hedge_target_strike": round(raw_hedge_target_strike, 2),
        "reason": "; ".join(reasons) if reasons else "Spread risk checks passed.",
        "sell_leg": sell, "buy_leg": buy,
        "sell_leg_liquidity": pair_liquidity.get("sell_leg_liquidity") or {},
        "hedge_leg_liquidity": pair_liquidity.get("hedge_leg_liquidity") or {},
        "pair_liquidity_condition": pair_liquidity.get("pair_liquidity_condition"),
        "liquidity_order_allowed": pair_liquidity.get("liquidity_order_allowed"),
        "liquidity_reason": pair_liquidity.get("liquidity_reason"),
        "sell_leg_buy_orders": (pair_liquidity.get("sell_leg_liquidity") or {}).get("top_5_buy_order_count"),
        "sell_leg_sell_orders": (pair_liquidity.get("sell_leg_liquidity") or {}).get("top_5_sell_order_count"),
        "sell_leg_trade_activity": (pair_liquidity.get("sell_leg_liquidity") or {}).get("trade_activity_count"),
        "sell_leg_trade_count_source": (pair_liquidity.get("sell_leg_liquidity") or {}).get("trade_count_source"),
        "sell_leg_liquidity_condition": (pair_liquidity.get("sell_leg_liquidity") or {}).get("liquidity_condition"),
        "hedge_leg_buy_orders": (pair_liquidity.get("hedge_leg_liquidity") or {}).get("top_5_buy_order_count"),
        "hedge_leg_sell_orders": (pair_liquidity.get("hedge_leg_liquidity") or {}).get("top_5_sell_order_count"),
        "hedge_leg_trade_activity": (pair_liquidity.get("hedge_leg_liquidity") or {}).get("trade_activity_count"),
        "hedge_leg_trade_count_source": (pair_liquidity.get("hedge_leg_liquidity") or {}).get("trade_count_source"),
        "hedge_leg_liquidity_condition": (pair_liquidity.get("hedge_leg_liquidity") or {}).get("liquidity_condition"),
        "order_payload": {
            "mode": "PAPER_DEFAULT",
            "sequence": "BUY hedge first, then SELL after hedge completion",
            "sell_leg": {"tradingsymbol": sell_ts, "transaction_type": "SELL", "quantity": quantity, "limit_price": round(sell_premium, 2)},
            "buy_leg": {"tradingsymbol": buy_ts, "transaction_type": "BUY", "quantity": quantity, "limit_price": round(buy_premium, 2)},
        },
    }
