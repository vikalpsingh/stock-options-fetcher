from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


NIFTY_TACTICAL_DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "mode": "REGIME_BASED_TACTICAL_SPREAD",
    "entry_execution_mode": "SUGGESTION_ONLY",
    "exit_execution_mode": "SUGGESTION_ONLY",
    "dte_min": 21,
    "dte_max": 35,
    "sell_delta_min": 0.12,
    "sell_delta_max": 0.18,
    "hedge_delta_min": 0.03,
    "hedge_delta_max": 0.06,
    "min_credit_pct_of_spread_width": 8.0,
    "preferred_credit_pct_of_spread_width": 10.0,
    "excellent_credit_pct_of_spread_width": 12.0,
    "profit_booking_credit_decay_min_pct": 50.0,
    "profit_booking_credit_decay_max_pct": 60.0,
    "profit_booking_credit_decay_default_pct": 55.0,
    "stop_loss_credit_multiple_min": 1.5,
    "stop_loss_credit_multiple_max": 2.0,
    "default_stop_loss_credit_multiple": 1.75,
    "max_nifty_income_share_pct": 20.0,
    "preferred_nifty_income_share_pct": 10.0,
    "low_vix_threshold": 11.0,
    "high_vix_threshold": 24.0,
    "spread_width_points_allowed": [300, 400, 500, 600, 700],
    "default_spread_width_points": 500,
    "no_trade_on_breakout_day": True,
    "no_trade_on_panic_fall": True,
    "no_trade_if_credit_too_low": True,
    "no_naked_nifty_options": True,
}


@dataclass
class TacticalSpreadLeg:
    side: str
    option_type: str
    strike: float
    delta: float | None = None
    ltp: float | None = None
    bid: float | None = None
    ask: float | None = None
    tradingsymbol: str = ""
    expiry: date | None = None


@dataclass
class TacticalSpread:
    strategy: str
    expiry: date | None
    legs: list[TacticalSpreadLeg] = field(default_factory=list)
    spread_width_points: float = 0.0
    net_credit_points: float = 0.0
    credit_pct_of_spread_width: float = 0.0
    credit_quality: str = "UNKNOWN"
    accepted: bool = False
    reason: str = ""


def tactical_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(NIFTY_TACTICAL_DEFAULT_CONFIG)
    if config:
        for key, value in config.items():
            if key in merged:
                merged[key] = value
    return merged


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def classify_nifty_market_regime(market_data: dict[str, Any]) -> dict[str, Any]:
    spot = _float(market_data.get("nifty_spot") or market_data.get("spot"))
    ema20 = _float(market_data.get("nifty_20ema") or market_data.get("ema20") or market_data.get("dma_20"))
    ema50 = _float(market_data.get("nifty_50ema") or market_data.get("ema50") or market_data.get("dma_50"))
    rsi = _float(market_data.get("rsi_14") or market_data.get("rsi"), 50.0)
    adx = _float(market_data.get("adx_14") or market_data.get("adx"), 25.0)
    intraday_change = _float(market_data.get("intraday_change_pct"))
    gap = _float(market_data.get("gap_pct"))
    vix_change = _float(market_data.get("vix_intraday_change_pct") or market_data.get("vix_5d_change_pct"))
    prev_high = _float(market_data.get("previous_20day_high") or market_data.get("previous_swing_high"))
    breadth = str(market_data.get("breadth_regime") or market_data.get("market_breadth") or "").upper()

    indicators: dict[str, Any] = {
        "spot": spot,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "adx": adx,
        "intraday_change_pct": intraday_change,
        "gap_pct": gap,
        "breadth": breadth or "UNKNOWN",
    }

    breakout = bool(
        spot > 0
        and prev_high > 0
        and spot > prev_high
        and intraday_change > 1.0
        and breadth in {"STRONG", "BULLISH", "VERY_STRONG"}
    )
    panic = bool(
        intraday_change < -1.25
        and gap < -0.75
        and vix_change > 10.0
        and breadth in {"WEAK", "BEARISH", "VERY_WEAK"}
    )

    if breakout:
        regime = "BREAKOUT_DAY"
        reason = "NIFTY broke above recent high with strong breadth."
    elif panic:
        regime = "PANIC_FALL"
        reason = "NIFTY has a panic-fall signature; avoid immediate put selling."
    elif (
        adx < 20
        and 45 <= rsi <= 60
        and spot > 0
        and ema20 > 0
        and abs(spot - ema20) / spot <= 0.005
        and (ema50 <= 0 or abs(spot - ema50) / spot <= 0.01)
    ):
        regime = "SIDEWAYS"
        reason = "Low ADX with price close to moving averages; iron-condor regime."
    elif spot > ema20 > 0 and spot > ema50 > 0 and 45 <= rsi <= 65:
        regime = "BUY_ON_DIPS"
        reason = "NIFTY is above 20/50 EMA with controlled RSI; bull put spread regime."
    elif spot < ema20 and spot < ema50 and 35 <= rsi <= 55:
        regime = "SELL_ON_RISE"
        reason = "NIFTY is below 20/50 EMA with weak bounce profile; bear call spread regime."
    elif adx < 20 and 45 <= rsi <= 60:
        regime = "SIDEWAYS"
        reason = "ADX and RSI suggest sideways premium-selling conditions."
    else:
        regime = str(market_data.get("trend_regime") or "SIDEWAYS").upper()
        reason = "Fallback regime from available trend data."
        if regime in {"BULLISH", "STRONG_BULLISH"}:
            regime = "BUY_ON_DIPS"
        elif regime in {"BEARISH", "STRONG_BEARISH"}:
            regime = "SELL_ON_RISE"
        elif regime not in {"BUY_ON_DIPS", "SELL_ON_RISE", "SIDEWAYS"}:
            regime = "SIDEWAYS"

    return {
        "regime": regime,
        "breakout_status": breakout,
        "panic_fall_status": panic,
        "reason": reason,
        "indicators_used": indicators,
    }


def select_nifty_tactical_strategy(market_state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = tactical_config(config)
    regime = str(market_state.get("regime") or market_state.get("trend_regime") or "SIDEWAYS").upper()
    spot = _float(market_state.get("nifty_spot") or market_state.get("spot"))
    ema20 = _float(market_state.get("nifty_20ema") or market_state.get("ema20") or market_state.get("dma_20"))
    vix = _float(market_state.get("india_vix"), 0.0)
    event = str(market_state.get("event_risk_status") or "OK").upper()
    breakout = bool(market_state.get("breakout_status")) or regime == "BREAKOUT_DAY"
    panic = bool(market_state.get("panic_fall_status")) or regime == "PANIC_FALL"

    if event == "HIGH":
        return _strategy_result("NO_TRADE", False, False, "High event risk. No new NIFTY tactical spread.")
    if breakout and cfg.get("no_trade_on_breakout_day", True):
        return _strategy_result("NO_TRADE", False, False, "Breakout day. Do not sell call spread.")
    if panic and cfg.get("no_trade_on_panic_fall", True):
        return _strategy_result("NO_TRADE", False, False, "Panic fall. Do not sell put spread immediately.")
    if vix and vix > _float(cfg.get("high_vix_threshold"), 24.0):
        return _strategy_result("NO_TRADE", False, False, "India VIX is above tactical threshold. Skip fresh NIFTY income.")

    if (spot > ema20 > 0 and regime in {"BULLISH", "STRONG_BULLISH", "BUY_ON_DIPS"}) or regime == "BUY_ON_DIPS":
        return _strategy_result(
            "BULL_PUT_SPREAD",
            True,
            False,
            "NIFTY above 20 EMA / buy-on-dips regime. Use Bull Put Spread only.",
        )
    if (spot < ema20 and ema20 > 0 and regime in {"BEARISH", "STRONG_BEARISH", "SELL_ON_RISE"}) or regime == "SELL_ON_RISE":
        return _strategy_result(
            "BEAR_CALL_SPREAD",
            False,
            True,
            "NIFTY below 20 EMA / sell-on-rise regime. Use Bear Call Spread only.",
        )
    if regime == "SIDEWAYS" and (not vix or vix <= _float(cfg.get("high_vix_threshold"), 24.0)):
        return _strategy_result(
            "IRON_CONDOR",
            True,
            True,
            "Sideways regime. Iron Condor allowed only if credit is meaningful.",
        )
    return _strategy_result("NO_TRADE", False, False, "No clean NIFTY tactical edge.")


def _strategy_result(strategy: str, pe: bool, ce: bool, reason: str) -> dict[str, Any]:
    return {
        "selected_strategy": strategy,
        "allow_pe_spread": pe,
        "allow_ce_spread": ce,
        "allowed": strategy != "NO_TRADE",
        "reason": reason,
        "skip_reason": None if strategy != "NO_TRADE" else reason,
    }


def validate_spread_credit_quality(spread: dict[str, Any] | TacticalSpread, config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = tactical_config(config)
    if isinstance(spread, TacticalSpread):
        width = _float(spread.spread_width_points)
        credit = _float(spread.net_credit_points)
    else:
        width = _float(spread.get("spread_width_points") or spread.get("spread_width"))
        credit = _float(spread.get("net_credit_points") or spread.get("net_credit"))
    pct = (credit / width * 100.0) if width > 0 else 0.0
    minimum = _float(cfg.get("min_credit_pct_of_spread_width"), 8.0)
    preferred = _float(cfg.get("preferred_credit_pct_of_spread_width"), 10.0)
    excellent = _float(cfg.get("excellent_credit_pct_of_spread_width"), 12.0)

    if pct < minimum:
        quality = "REJECT"
        accepted = False
        reason = "Credit too low for risk. Far-OTM hedged spread is structurally low-yield."
    elif pct >= excellent:
        quality = "EXCELLENT"
        accepted = True
        reason = "Credit is excellent for the defined spread width."
    elif pct >= preferred:
        quality = "GOOD"
        accepted = True
        reason = "Credit is good for the defined spread width."
    else:
        quality = "ACCEPTABLE"
        accepted = True
        reason = "Credit is acceptable but not premium-rich."
    return {
        "accepted": accepted,
        "credit_quality": quality,
        "credit_pct_of_spread_width": pct,
        "net_credit_points": credit,
        "spread_width_points": width,
        "reason": reason,
    }


def validate_nifty_income_allocation(
    monthly_income_plan: float | int | None,
    current_nifty_income: float | int | None,
    total_monthly_income_target: float | int | None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = tactical_config(config)
    total_target = _float(total_monthly_income_target or monthly_income_plan)
    nifty_income = _float(current_nifty_income)
    share = (nifty_income / total_target * 100.0) if total_target > 0 else 0.0
    max_share = _float(cfg.get("max_nifty_income_share_pct"), 20.0)
    preferred = _float(cfg.get("preferred_nifty_income_share_pct"), 10.0)
    if share > max_share:
        status = "BLOCK"
        allowed = False
        reason = "NIFTY income allocation is already above 20% of monthly target."
    elif share >= preferred:
        status = "HIGH_CONFIDENCE_ONLY"
        allowed = True
        reason = "NIFTY income allocation is between preferred and max; allow only high-confidence trades."
    else:
        status = "ALLOW"
        allowed = True
        reason = "NIFTY income allocation is below preferred limit."
    return {
        "allowed": allowed,
        "status": status,
        "nifty_income_allocation_pct": share,
        "reason": reason,
    }


def evaluate_nifty_tactical_spread_exit(strategy: dict[str, Any], live_prices: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = tactical_config(config)
    entry_credit = _float(strategy.get("entry_net_credit") or strategy.get("net_credit_points"))
    current_value = _float(live_prices.get("current_spread_value"))
    target_decay = _float(cfg.get("profit_booking_credit_decay_default_pct"), 55.0)
    stop_multiple = _float(cfg.get("default_stop_loss_credit_multiple"), 1.75)
    credit_decay = ((entry_credit - current_value) / entry_credit * 100.0) if entry_credit > 0 else 0.0
    target_hit = entry_credit > 0 and credit_decay >= target_decay
    stop_hit = entry_credit > 0 and current_value >= entry_credit * stop_multiple
    if target_hit:
        signal = "BOOK_PROFIT"
        reason = "Target credit decay reached."
    elif stop_hit:
        signal = "STOP_LOSS"
        reason = "Spread value reached stop-loss multiple."
    else:
        signal = "HOLD"
        reason = "Credit decay and stop-loss thresholds not reached."
    return {
        "exit_signal": signal,
        "exit_reason": reason,
        "current_spread_value": current_value,
        "credit_decay_pct": credit_decay,
        "stop_multiple": (current_value / entry_credit) if entry_credit > 0 else 0.0,
        "target_hit": target_hit,
        "stop_hit": stop_hit,
        "target_buyback_value": entry_credit * (1 - target_decay / 100.0) if entry_credit > 0 else 0.0,
        "stop_loss_value": entry_credit * stop_multiple if entry_credit > 0 else 0.0,
    }


def select_spread_strikes_by_delta(
    option_chain: list[dict[str, Any]],
    selected_strategy: str,
    config: dict[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    cfg = tactical_config(config)
    today = today or date.today()
    dte_min = int(cfg.get("dte_min") or 21)
    dte_max = int(cfg.get("dte_max") or 35)
    sell_min = _float(cfg.get("sell_delta_min"), 0.12)
    sell_max = _float(cfg.get("sell_delta_max"), 0.18)
    hedge_min = _float(cfg.get("hedge_delta_min"), 0.03)
    hedge_max = _float(cfg.get("hedge_delta_max"), 0.06)

    candidates = []
    for row in option_chain:
        expiry = _date(row.get("expiry") or row.get("expiry_date"))
        if not expiry:
            continue
        dte = (expiry - today).days
        if dte_min <= dte <= dte_max:
            candidates.append({**row, "expiry": expiry, "dte": dte})
    if not candidates:
        return {"accepted": False, "reason": "No NIFTY expiry available in 21-35 DTE window.", "spreads": []}
    expiry = min({row["expiry"] for row in candidates}, key=lambda item: abs((item - today).days - 28))
    chain = [row for row in candidates if row["expiry"] == expiry]

    def abs_delta(row: dict[str, Any]) -> float:
        return abs(_float(row.get("delta")))

    def pick_short(option_type: str) -> dict[str, Any] | None:
        rows = [row for row in chain if str(row.get("option_type") or row.get("type") or "").upper() == option_type]
        valid = [row for row in rows if sell_min <= abs_delta(row) <= sell_max]
        if not valid:
            return None
        return min(valid, key=lambda row: abs(abs_delta(row) - ((sell_min + sell_max) / 2)))

    def pick_hedge(option_type: str, short: dict[str, Any]) -> dict[str, Any] | None:
        short_strike = _float(short.get("strike"))
        rows = [row for row in chain if str(row.get("option_type") or row.get("type") or "").upper() == option_type]
        if option_type == "PE":
            rows = [row for row in rows if _float(row.get("strike")) < short_strike]
        else:
            rows = [row for row in rows if _float(row.get("strike")) > short_strike]
        if not rows:
            return None
        valid = [row for row in rows if hedge_min <= abs_delta(row) <= hedge_max]
        source = valid or rows
        return min(source, key=lambda row: (0 if row in valid else 1, abs(abs_delta(row) - ((hedge_min + hedge_max) / 2))))

    spreads: list[dict[str, Any]] = []
    sides = []
    strategy = selected_strategy.upper()
    if strategy in {"BULL_PUT_SPREAD", "IRON_CONDOR"}:
        sides.append("PE")
    if strategy in {"BEAR_CALL_SPREAD", "IRON_CONDOR"}:
        sides.append("CE")
    for option_type in sides:
        short = pick_short(option_type)
        if not short:
            return {"accepted": False, "reason": f"No {option_type} short delta in 0.12-0.18 band.", "spreads": spreads}
        hedge = pick_hedge(option_type, short)
        if not hedge:
            return {"accepted": False, "reason": f"No farther OTM {option_type} hedge found.", "spreads": spreads}
        short_strike = _float(short.get("strike"))
        hedge_strike = _float(hedge.get("strike"))
        width = abs(short_strike - hedge_strike)
        short_price = _float(short.get("bid") or short.get("ltp") or short.get("last_price"))
        hedge_price = _float(hedge.get("ask") or hedge.get("ltp") or hedge.get("last_price"))
        spread = {
            "option_type": option_type,
            "expiry": expiry,
            "dte": (expiry - today).days,
            "short_strike": short_strike,
            "short_delta": abs_delta(short),
            "hedge_strike": hedge_strike,
            "hedge_delta": abs_delta(hedge),
            "spread_width_points": width,
            "net_credit_points": max(0.0, short_price - hedge_price),
            "short_symbol": short.get("tradingsymbol") or short.get("symbol") or "",
            "hedge_symbol": hedge.get("tradingsymbol") or hedge.get("symbol") or "",
            "short_ltp": _float(short.get("ltp") or short.get("last_price")),
            "hedge_ltp": _float(hedge.get("ltp") or hedge.get("last_price")),
            "short_bid": _float(short.get("bid")),
            "hedge_ask": _float(hedge.get("ask")),
        }
        spread.update(validate_spread_credit_quality(spread, cfg))
        spreads.append(spread)
    accepted = bool(spreads) and all(row.get("accepted") for row in spreads)
    return {
        "accepted": accepted,
        "reason": "Selected by delta and credit quality." if accepted else "One or more spreads failed credit quality.",
        "expiry": expiry,
        "selected_strategy": strategy,
        "spreads": spreads,
    }


def tactical_orders_from_spreads(selection: dict[str, Any], lot_size: int = 65, lots: int = 1) -> list[dict[str, Any]]:
    if not selection.get("accepted"):
        return []
    quantity = int(lot_size) * int(lots)
    orders: list[dict[str, Any]] = []
    for spread in selection.get("spreads") or []:
        orders.append(
            {
                "exchange": "NFO",
                "tradingsymbol": spread.get("hedge_symbol"),
                "quantity": quantity,
                "transaction_type": "BUY",
                "product": "NRML",
                "order_type": "LIMIT",
                "price": spread.get("hedge_ltp") or 0,
                "validity": "DAY",
            }
        )
        orders.append(
            {
                "exchange": "NFO",
                "tradingsymbol": spread.get("short_symbol"),
                "quantity": quantity,
                "transaction_type": "SELL",
                "product": "NRML",
                "order_type": "LIMIT",
                "price": spread.get("short_ltp") or 0,
                "validity": "DAY",
            }
        )
    return orders


def tactical_audit_row(
    market_regime: dict[str, Any],
    strategy: dict[str, Any],
    credit: dict[str, Any] | None,
    allocation: dict[str, Any] | None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = tactical_config(config)
    credit = credit or {}
    allocation = allocation or {}
    return {
        "nifty_mode": cfg.get("mode"),
        "market_regime": market_regime.get("regime"),
        "selected_strategy": strategy.get("selected_strategy"),
        "dte": credit.get("dte", ""),
        "short_delta": credit.get("short_delta", ""),
        "hedge_delta": credit.get("hedge_delta", ""),
        "spread_width": credit.get("spread_width_points", ""),
        "net_credit_points": credit.get("net_credit_points", ""),
        "credit_pct_of_spread_width": credit.get("credit_pct_of_spread_width", ""),
        "credit_quality": credit.get("credit_quality", ""),
        "profit_booking_credit_decay_pct": cfg.get("profit_booking_credit_decay_default_pct"),
        "stop_loss_credit_multiple": cfg.get("default_stop_loss_credit_multiple"),
        "nifty_income_allocation_pct": allocation.get("nifty_income_allocation_pct", ""),
        "no_trade_reason": strategy.get("skip_reason") or "",
        "strategy_reason": strategy.get("reason") or "",
    }
