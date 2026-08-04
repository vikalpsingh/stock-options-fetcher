"""Kite option market-depth liquidity analyser for DHAN paired spreads."""

from __future__ import annotations

from typing import Any

import risk_config


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sum_depth(depth_rows: Any, field: str) -> float:
    if not isinstance(depth_rows, list):
        return 0.0
    return sum(_num((row or {}).get(field)) for row in depth_rows[:5] if isinstance(row, dict))


def _best_depth_price(depth_rows: Any) -> float:
    if not isinstance(depth_rows, list) or not depth_rows:
        return 0.0
    return _num((depth_rows[0] or {}).get("price"))


def analyze_option_liquidity(tradingsymbol: str, quote: dict[str, Any] | None) -> dict[str, Any]:
    """Return normalized RED/AMBER/GREEN liquidity for one option contract."""

    clean_quote = quote or {}
    depth = clean_quote.get("depth") if isinstance(clean_quote.get("depth"), dict) else {}
    buy_depth = depth.get("buy") if isinstance(depth, dict) else []
    sell_depth = depth.get("sell") if isinstance(depth, dict) else []
    last_price = _num(clean_quote.get("last_price") or clean_quote.get("ltp") or clean_quote.get("last_traded_price"))
    best_bid = _best_depth_price(buy_depth) or _num(clean_quote.get("best_bid") or clean_quote.get("bid"))
    best_ask = _best_depth_price(sell_depth) or _num(clean_quote.get("best_ask") or clean_quote.get("ask"))
    buy_orders = _sum_depth(buy_depth, "orders")
    sell_orders = _sum_depth(sell_depth, "orders")
    buy_qty = _sum_depth(buy_depth, "quantity") or _num(clean_quote.get("buy_quantity"))
    sell_qty = _sum_depth(sell_depth, "quantity") or _num(clean_quote.get("sell_quantity"))
    volume = _num(clean_quote.get("volume"))
    oi = _num(clean_quote.get("oi"))
    has_actual_trade_count = "number_of_trades" in clean_quote and clean_quote.get("number_of_trades") is not None
    trade_activity = _num(clean_quote.get("number_of_trades")) if has_actual_trade_count else volume
    trade_count_source = "ACTUAL_TRADE_COUNT" if has_actual_trade_count else "VOLUME_PROXY"
    spread = max(best_ask - best_bid, 0.0) if best_bid and best_ask else 0.0
    spread_pct = (spread / last_price * 100) if last_price else 0.0

    red_reasons: list[str] = []
    if buy_orders < risk_config.LIQUIDITY_AMBER_MIN_BUY_ORDERS:
        red_reasons.append(f"top 5 buy order count {buy_orders:.0f} below {risk_config.LIQUIDITY_AMBER_MIN_BUY_ORDERS}")
    if sell_orders < risk_config.LIQUIDITY_AMBER_MIN_SELL_ORDERS:
        red_reasons.append(f"top 5 sell order count {sell_orders:.0f} below {risk_config.LIQUIDITY_AMBER_MIN_SELL_ORDERS}")
    if trade_activity < risk_config.LIQUIDITY_AMBER_MIN_TRADE_ACTIVITY:
        red_reasons.append(f"trade activity {trade_activity:.0f} below {risk_config.LIQUIDITY_AMBER_MIN_TRADE_ACTIVITY}")
    if best_bid <= 0:
        red_reasons.append("best bid unavailable")
    if best_ask <= 0:
        red_reasons.append("best ask unavailable")
    if last_price <= 0:
        red_reasons.append("LTP unavailable")

    if red_reasons:
        condition = "RED"
        reason = "; ".join(red_reasons)
    elif (
        buy_orders >= risk_config.LIQUIDITY_GREEN_MIN_BUY_ORDERS
        and sell_orders >= risk_config.LIQUIDITY_GREEN_MIN_SELL_ORDERS
        and trade_activity >= risk_config.LIQUIDITY_GREEN_MIN_TRADE_ACTIVITY
    ):
        condition = "GREEN"
        reason = "Strong liquidity from top 5 depth orders and trade activity."
    else:
        condition = "AMBER"
        reason = "Acceptable liquidity from top 5 depth orders and trade activity."

    return {
        "tradingsymbol": tradingsymbol,
        "best_bid": round(best_bid, 2),
        "best_ask": round(best_ask, 2),
        "bid_ask_spread": round(spread, 2),
        "bid_ask_spread_pct": round(spread_pct, 2),
        "volume": int(volume),
        "oi": int(oi),
        "top_5_buy_order_count": int(buy_orders),
        "top_5_sell_order_count": int(sell_orders),
        "top_5_buy_quantity": int(buy_qty),
        "top_5_sell_quantity": int(sell_qty),
        "trade_activity_count": int(trade_activity),
        "trade_count_source": trade_count_source,
        "liquidity_condition": condition,
        "liquidity_reason": reason,
        "order_allowed": condition in {"AMBER", "GREEN"},
    }


def fallback_option_liquidity(tradingsymbol: str, reason: str = "Live Kite depth unavailable; use limit order and verify slippage.") -> dict[str, Any]:
    return {
        "tradingsymbol": tradingsymbol,
        "best_bid": 0,
        "best_ask": 0,
        "bid_ask_spread": 0,
        "bid_ask_spread_pct": 0,
        "volume": 0,
        "oi": 0,
        "top_5_buy_order_count": 0,
        "top_5_sell_order_count": 0,
        "top_5_buy_quantity": 0,
        "top_5_sell_quantity": 0,
        "trade_activity_count": 0,
        "trade_count_source": "VOLUME_PROXY",
        "liquidity_condition": "AMBER",
        "liquidity_reason": reason,
        "order_allowed": True,
    }


def analyze_pair_liquidity(
    sell_tradingsymbol: str,
    sell_quote: dict[str, Any] | None,
    buy_tradingsymbol: str,
    buy_quote: dict[str, Any] | None,
    *,
    allow_fallback: bool = False,
) -> dict[str, Any]:
    sell = (
        fallback_option_liquidity(sell_tradingsymbol)
        if allow_fallback and not sell_quote
        else analyze_option_liquidity(sell_tradingsymbol, sell_quote)
    )
    buy = (
        fallback_option_liquidity(buy_tradingsymbol)
        if allow_fallback and not buy_quote
        else analyze_option_liquidity(buy_tradingsymbol, buy_quote)
    )
    conditions = {sell["liquidity_condition"], buy["liquidity_condition"]}
    if "RED" in conditions:
        pair_condition = "RED"
    elif conditions == {"GREEN"}:
        pair_condition = "GREEN"
    else:
        pair_condition = "AMBER"
    order_allowed = pair_condition in {"AMBER", "GREEN"}
    reason = (
        "Poor liquidity — order blocked."
        if pair_condition == "RED"
        else "Strong liquidity — order allowed."
        if pair_condition == "GREEN"
        else "Acceptable liquidity — order allowed with caution."
    )
    if pair_condition == "RED":
        reason = f"{reason} SELL: {sell['liquidity_reason']} BUY: {buy['liquidity_reason']}"
    return {
        "sell_leg_liquidity": sell,
        "hedge_leg_liquidity": buy,
        "pair_liquidity_condition": pair_condition,
        "liquidity_order_allowed": order_allowed,
        "liquidity_reason": reason,
    }
