"""50/200 DMA decision gate for DHAN-IT call-spread candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import risk_config
from dhan_it_universe import IT_FNO_SYMBOLS


NIFTY_IT_SYMBOL = "NIFTY IT"
DHAN_IT_WATCH_SYMBOLS = [NIFTY_IT_SYMBOL, *IT_FNO_SYMBOLS]
DHAN_IT_STRATEGIES = {"BEAR_CALL_SPREAD", "WATCH", "NO_TRADE"}


@dataclass(frozen=True)
class DhanItCallSpreadSignal:
    symbol: str
    company_name: str = ""
    spot: float | None = None
    day_change_pct: float | None = None
    nifty_it_regime: str = "DATA_UNAVAILABLE"
    stock_regime: str = "DATA_UNAVAILABLE"
    price_vs_50dma: str = "DATA_UNAVAILABLE"
    price_vs_200dma: str = "DATA_UNAVAILABLE"
    distance_from_50dma_pct: float | None = None
    distance_from_200dma_pct: float | None = None
    ema20: float | None = None
    ema50: float | None = None
    rsi: float | None = None
    rsi_direction: str = "UNKNOWN"
    atr: float | None = None
    atr_pct: float | None = None
    vwap: float | None = None
    price_vs_vwap: str = "UNKNOWN"
    resistance_20d: float | None = None
    swing_high: float | None = None
    distance_to_resistance_pct: float | None = None
    rejection_confirmed: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    event_risk: str = "NO"
    liquidity_condition: str = "UNKNOWN"
    signal_status: str = "DATA_UNAVAILABLE"
    strategy_type: str = "NO_TRADE"
    confidence: int = 0
    decision: str = "BLOCKED"
    decision_reason: str = "Technical data unavailable."
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def calculate_moving_averages(
    closes: Iterable[Any],
    min_sessions: int | None = None,
) -> dict[str, Any]:
    """Calculate 50/200 DMA from completed daily closes."""
    prices = [float(item) for item in closes if _float_or_none(item) is not None]
    required = min_sessions or getattr(risk_config, "DHAN_IT_MIN_DMA_HISTORY_SESSIONS", 200)
    return {
        "dma_50": round(sum(prices[-50:]) / 50, 2) if len(prices) >= 50 else None,
        "dma_200": round(sum(prices[-200:]) / 200, 2) if len(prices) >= 200 else None,
        "history_count": len(prices),
        "data_available": len(prices) >= required,
    }


def calculate_dma_distance(price: Any, dma: Any) -> float | None:
    spot = _float_or_none(price)
    average = _float_or_none(dma)
    if spot is None or average is None:
        return None
    return round((spot - average) / average * 100, 2)


def classify_trend(price: Any, dma_50: Any, dma_200: Any) -> str:
    spot = _float_or_none(price)
    fifty = _float_or_none(dma_50)
    two_hundred = _float_or_none(dma_200)
    if spot is None or fifty is None or two_hundred is None:
        return "DATA_UNAVAILABLE"
    if spot > fifty and fifty > two_hundred:
        return "BULLISH"
    if spot < fifty and fifty < two_hundred:
        return "BEARISH"
    return "MIXED"


def classify_nifty_it_regime(price: Any, dma_50: Any, dma_200: Any) -> str:
    return classify_trend(price, dma_50, dma_200)


def classify_dhan_it_regime(price: Any, dma_50: Any, dma_200: Any) -> str:
    spot = _float_or_none(price)
    fifty = _float_or_none(dma_50)
    two_hundred = _float_or_none(dma_200)
    if spot is None or fifty is None or two_hundred is None:
        return "DATA_UNAVAILABLE"
    if spot < fifty and spot < two_hundred:
        return "BEARISH"
    if spot >= fifty and spot < two_hundred:
        return "BEARISH_RALLY"
    if spot < fifty and spot >= two_hundred:
        return "BULLISH_PULLBACK"
    return "BULLISH"


def _relation(price: Any, reference: Any) -> str:
    spot = _float_or_none(price)
    ref = _float_or_none(reference)
    if spot is None or ref is None:
        return "DATA_UNAVAILABLE"
    return "ABOVE" if spot >= ref else "BELOW"


def evaluate_rejection_confirmation(market_data: dict[str, Any], technical_data: dict[str, Any]) -> tuple[bool, list[str], float | None]:
    spot = _float_or_none(market_data.get("cmp") or market_data.get("spot") or market_data.get("close"))
    close = _float_or_none(market_data.get("close") or spot)
    high = _float_or_none(market_data.get("high"))
    low = _float_or_none(market_data.get("low"))
    vwap = _float_or_none(technical_data.get("vwap"))
    rsi = _float_or_none(technical_data.get("rsi"))
    previous_rsi = _float_or_none(technical_data.get("previous_rsi"))
    dma_200 = _float_or_none(technical_data.get("dma_200"))
    resistance_20d = _float_or_none(technical_data.get("resistance_20d") or technical_data.get("high_20d"))
    swing_high = _float_or_none(technical_data.get("swing_high") or technical_data.get("recent_swing_high"))
    resistance_candidates = [value for value in (dma_200, resistance_20d, swing_high) if value is not None]
    nearest_resistance = min(resistance_candidates, key=lambda value: abs(value - (spot or value))) if resistance_candidates else None
    reasons: list[str] = []
    proximity = float(getattr(risk_config, "DHAN_IT_RESISTANCE_PROXIMITY_PCT", 1.0))
    if spot is not None and nearest_resistance is not None and abs(spot - nearest_resistance) / nearest_resistance * 100 <= proximity:
        reasons.append("price within configured resistance proximity")
    if close is not None and nearest_resistance is not None and close < nearest_resistance:
        reasons.append("close below nearest resistance")
    if high is not None and low is not None and close is not None and high > low:
        upper_wick_pct = max(high - close, 0) / (high - low) * 100
        if upper_wick_pct >= float(getattr(risk_config, "DHAN_IT_UPPER_WICK_MIN_PCT", 40.0)):
            reasons.append("upper wick rejection")
    if spot is not None and vwap is not None and high is not None and high > vwap and close is not None and close < vwap:
        reasons.append("failed above VWAP and closed below VWAP")
    if rsi is not None and previous_rsi is not None and previous_rsi >= 60 and rsi < previous_rsi:
        reasons.append("RSI elevated and turning down")
    if high is not None and swing_high is not None and high >= swing_high and close is not None and close < swing_high:
        reasons.append("failed to hold swing high")
    confirmed = len(reasons) >= int(getattr(risk_config, "DHAN_IT_MIN_REJECTION_CONDITIONS", 2))
    distance_to_resistance = calculate_dma_distance(spot, nearest_resistance) if nearest_resistance else None
    return confirmed, reasons, distance_to_resistance


def build_dhan_it_call_spread_signal(
    symbol: str,
    company_name: str = "",
    *,
    market_data: dict[str, Any] | None = None,
    technical_data: dict[str, Any] | None = None,
    sector_regime: str = "DATA_UNAVAILABLE",
    event_data: dict[str, Any] | None = None,
    liquidity_condition: str = "UNKNOWN",
) -> DhanItCallSpreadSignal:
    market = market_data or {}
    technical = technical_data or {}
    event = event_data or {}
    spot = _float_or_none(market.get("cmp") or market.get("spot") or market.get("close"))
    day_change = _float_or_none(market.get("day_change_pct"))
    dma_50 = _float_or_none(technical.get("dma_50"))
    dma_200 = _float_or_none(technical.get("dma_200"))
    stock_regime = classify_dhan_it_regime(spot, dma_50, dma_200)
    dist_50 = calculate_dma_distance(spot, dma_50)
    dist_200 = calculate_dma_distance(spot, dma_200)
    rejection_confirmed, rejection_reasons, resistance_distance = evaluate_rejection_confirmation(market, technical)
    event_risk = "YES" if event.get("event_risk") or event.get("event_risk_flag") or str(event.get("event_risk") or "").upper() == "YES" else "NO"
    normalized_sector = str(sector_regime or "DATA_UNAVAILABLE").upper()
    rsi = _float_or_none(technical.get("rsi"))
    previous_rsi = _float_or_none(technical.get("previous_rsi"))
    rsi_direction = "UNKNOWN" if rsi is None or previous_rsi is None else "DOWN" if rsi < previous_rsi else "UP" if rsi > previous_rsi else "FLAT"
    atr = _float_or_none(technical.get("atr"))
    atr_pct = round(atr / spot * 100, 2) if atr and spot else None
    vwap = _float_or_none(technical.get("vwap"))
    price_vs_vwap = _relation(spot, vwap)
    watch_rise = day_change is not None and day_change >= float(getattr(risk_config, "DHAN_IT_WATCH_RISE_PCT", 3.0))
    hard_blocks: list[str] = []
    if stock_regime == "DATA_UNAVAILABLE" or normalized_sector == "DATA_UNAVAILABLE":
        hard_blocks.append("DMA data unavailable")
    if event_risk == "YES":
        hard_blocks.append("event/result risk")
    if str(liquidity_condition or "").upper() == "RED":
        hard_blocks.append("RED liquidity")
    if stock_regime == "BULLISH":
        hard_blocks.append("stock above both DMAs; bullish breakout risk")
    if normalized_sector == "BULLISH" and not rejection_confirmed:
        hard_blocks.append("NIFTY IT bullish without confirmed rejection")

    score = 0
    if normalized_sector in {"BEARISH", "BEARISH_RALLY"}:
        score += 20
    elif normalized_sector == "BULLISH_PULLBACK":
        score += 8
    if stock_regime in {"BEARISH", "BEARISH_RALLY"}:
        score += 20
    elif stock_regime == "BULLISH_PULLBACK":
        score += 6
    if rejection_confirmed:
        score += 20
    if resistance_distance is not None and abs(resistance_distance) <= float(getattr(risk_config, "DHAN_IT_RESISTANCE_PROXIMITY_PCT", 1.0)):
        score += 10
    if str(liquidity_condition or "").upper() in {"AMBER", "GREEN", "UNKNOWN"}:
        score += 5 if str(liquidity_condition or "").upper() != "GREEN" else 10
    if event_risk == "NO":
        score += 5

    if hard_blocks:
        status = "BLOCKED" if stock_regime != "DATA_UNAVAILABLE" and normalized_sector != "DATA_UNAVAILABLE" else "DATA_UNAVAILABLE"
        strategy = "NO_TRADE"
        decision = "BLOCKED"
        reason = "; ".join(hard_blocks)
    elif not rejection_confirmed and watch_rise:
        status = "WATCH_RISE"
        strategy = "WATCH"
        decision = "WATCH"
        reason = "Daily rise detected; wait for rejection confirmation before CE spread."
    elif not rejection_confirmed:
        status = "WAIT_REJECTION"
        strategy = "WATCH"
        decision = "WATCH"
        reason = "Approach resistance / trend setup requires rejection confirmation."
    elif normalized_sector == "BEARISH" and stock_regime in {"BEARISH", "BEARISH_RALLY"}:
        status = "REVIEW_CE_PAIR" if score >= 80 else "CONFIRM_REQUIRED"
        strategy = "BEAR_CALL_SPREAD"
        decision = "GREEN" if status == "REVIEW_CE_PAIR" else "AMBER"
        reason = "Bearish IT alignment with confirmed stock rejection."
    elif normalized_sector in {"BEARISH_RALLY", "BULLISH_PULLBACK"} and stock_regime in {"BEARISH", "BEARISH_RALLY"}:
        status = "CONFIRM_REQUIRED"
        strategy = "BEAR_CALL_SPREAD"
        decision = "AMBER"
        reason = "Confirmed rejection but sector alignment is not fully bearish."
    else:
        status = "BLOCKED"
        strategy = "NO_TRADE"
        decision = "BLOCKED"
        reason = "Sector/stock alignment is not suitable for CE spread."

    return DhanItCallSpreadSignal(
        symbol=str(symbol or "").strip().upper(),
        company_name=company_name,
        spot=spot,
        day_change_pct=day_change,
        nifty_it_regime=normalized_sector,
        stock_regime=stock_regime,
        price_vs_50dma=_relation(spot, dma_50),
        price_vs_200dma=_relation(spot, dma_200),
        distance_from_50dma_pct=dist_50,
        distance_from_200dma_pct=dist_200,
        ema20=_float_or_none(technical.get("ema20")),
        ema50=_float_or_none(technical.get("ema50")),
        rsi=rsi,
        rsi_direction=rsi_direction,
        atr=atr,
        atr_pct=atr_pct,
        vwap=vwap,
        price_vs_vwap=price_vs_vwap,
        resistance_20d=_float_or_none(technical.get("resistance_20d") or technical.get("high_20d")),
        swing_high=_float_or_none(technical.get("swing_high") or technical.get("recent_swing_high")),
        distance_to_resistance_pct=resistance_distance,
        rejection_confirmed=rejection_confirmed,
        rejection_reasons=rejection_reasons,
        event_risk=event_risk,
        liquidity_condition=str(liquidity_condition or "UNKNOWN").upper(),
        signal_status=status,
        strategy_type=strategy,
        confidence=min(max(int(score), 0), 100),
        decision=decision,
        decision_reason=reason,
    )


def _has_pair_legs(pair_preview: dict[str, Any]) -> bool:
    return bool(pair_preview.get("sell_leg_tradingsymbol")) and bool(pair_preview.get("buy_leg_tradingsymbol"))


def evaluate_call_spread_dma_gate(
    *,
    symbol: str,
    price: Any,
    dma_50: Any,
    dma_200: Any,
    nifty_it_regime: str,
    data_timestamp: str = "",
    data_stale: bool = False,
    event_risk: bool = False,
    pair_preview: dict[str, Any] | None = None,
    is_sector: bool = False,
    source: str = "Kite/Yahoo",
) -> dict[str, Any]:
    """Return GREEN/AMBER/RED permission for DHAN-IT call-spread review.

    GREEN means the DMA setup supports a bearish/neutral call-credit spread.
    AMBER means the popup can be opened, but explicit acknowledgement is needed.
    RED means no live order path should be enabled from this gate.
    """
    normalized_symbol = str(symbol or "").strip().upper() or symbol
    trend = classify_dhan_it_regime(price, dma_50, dma_200)
    dist_50 = calculate_dma_distance(price, dma_50)
    dist_200 = calculate_dma_distance(price, dma_200)
    regime = str(nifty_it_regime or "DATA_UNAVAILABLE").upper()
    reasons: list[str] = []
    warnings: list[str] = []
    status = "RED"
    decision = "BLOCKED"
    order_allowed = False

    if is_sector:
        if trend == "DATA_UNAVAILABLE" or data_stale:
            reasons.append("NIFTY IT DMA data unavailable or stale.")
            status = "RED"
        elif trend == "BEARISH":
            reasons.append("NIFTY IT is below both 50 DMA and 200 DMA.")
            status = "GREEN"
        elif trend in {"BEARISH_RALLY", "BULLISH_PULLBACK"}:
            reasons.append("NIFTY IT regime is not fully bearish; use stock-level confirmation.")
            status = "AMBER"
        else:
            reasons.append("NIFTY IT trend is bullish; call selling needs extra caution.")
            status = "RED"
        return {
            "symbol": normalized_symbol,
            "status": status,
            "decision": "REGIME_ONLY",
            "order_allowed": False,
            "trend": trend,
            "nifty_it_regime": trend,
            "price": _float_or_none(price),
            "dma_50": _float_or_none(dma_50),
            "dma_200": _float_or_none(dma_200),
            "distance_50_pct": dist_50,
            "distance_200_pct": dist_200,
            "reasons": reasons,
            "warnings": warnings,
            "data_timestamp": data_timestamp,
            "source": source,
            "button_label": "Refresh Sector Signal",
        }

    if trend == "DATA_UNAVAILABLE":
        reasons.append("Stock DMA data unavailable.")
    if regime == "DATA_UNAVAILABLE":
        reasons.append("NIFTY IT regime data unavailable.")
    if data_stale:
        reasons.append("DMA data is stale.")
    if event_risk:
        reasons.append("Event risk is active.")

    if pair_preview is not None:
        pair_liquidity = str(pair_preview.get("pair_liquidity_condition") or "").upper()
        if not _has_pair_legs(pair_preview):
            reasons.append("Both SELL and BUY hedge legs could not be constructed.")
        if pair_liquidity == "RED" or pair_preview.get("liquidity_order_allowed") is False:
            reasons.append("Liquidity condition is RED.")
        if str(pair_preview.get("risk_decision") or "").upper() not in {"", "APPROVED"}:
            reasons.append(str(pair_preview.get("risk_reason") or pair_preview.get("reason") or "Risk engine did not approve."))

    if reasons:
        status = "RED"
        decision = "BLOCKED"
    elif trend in {"BEARISH", "BEARISH_RALLY"} and regime in {"BEARISH", "BEARISH_RALLY", "BULLISH_PULLBACK"}:
        status = "GREEN"
        decision = "ALLOWED"
        order_allowed = True
        reasons.append("Stock is bearish/bearish-rally and IT regime is not bullish.")
        if dist_50 is not None and dist_50 <= -float(getattr(risk_config, "DHAN_IT_REBOUND_RISK_BELOW_50DMA_PCT", 8.0)):
            status = "AMBER"
            decision = "CONFIRM_REQUIRED"
            warnings.append("Stock is deeply below 50 DMA; rebound risk is elevated.")
    elif trend == "BULLISH_PULLBACK" or (trend in {"BEARISH", "BEARISH_RALLY"} and regime == "BULLISH"):
        status = "AMBER"
        decision = "CONFIRM_REQUIRED"
        order_allowed = True
        reasons.append("DMA setup is mixed; open popup only with manual confirmation.")
        if regime == "BULLISH":
            warnings.append("NIFTY IT regime is bullish against a bearish call-spread setup.")
    else:
        status = "RED"
        decision = "BLOCKED"
        reasons.append("Stock trend is bullish; bearish call-spread setup is blocked.")

    return {
        "symbol": normalized_symbol,
        "status": status,
        "decision": decision,
        "order_allowed": order_allowed,
        "trend": trend,
        "nifty_it_regime": regime,
        "price": _float_or_none(price),
        "dma_50": _float_or_none(dma_50),
        "dma_200": _float_or_none(dma_200),
        "distance_50_pct": dist_50,
        "distance_200_pct": dist_200,
        "reasons": reasons,
        "warnings": warnings,
        "data_timestamp": data_timestamp,
        "source": source,
        "button_label": "Build CE Pair" if status == "GREEN" else "Review CE Pair" if status == "AMBER" else "Blocked",
    }


def build_dhan_it_card_view_model(
    *,
    symbol: str,
    label: str,
    market_data: dict[str, Any],
    nifty_it_regime: str,
    pair_preview: dict[str, Any] | None = None,
    is_sector: bool = False,
) -> dict[str, Any]:
    signal = build_dhan_it_call_spread_signal(
        symbol=symbol,
        company_name=label,
        market_data=market_data,
        technical_data=market_data,
        sector_regime=nifty_it_regime,
        event_data=market_data,
        liquidity_condition=str((pair_preview or {}).get("pair_liquidity_condition") or market_data.get("liquidity_condition") or "UNKNOWN"),
    )
    gate = evaluate_call_spread_dma_gate(
        symbol=symbol,
        price=market_data.get("cmp") or market_data.get("price"),
        dma_50=market_data.get("dma_50"),
        dma_200=market_data.get("dma_200"),
        nifty_it_regime=nifty_it_regime,
        data_timestamp=str(market_data.get("data_timestamp") or ""),
        data_stale=bool(market_data.get("data_stale")),
        event_risk=str(market_data.get("event_risk") or "").upper() == "YES",
        pair_preview=pair_preview,
        is_sector=is_sector,
        source=str(market_data.get("source") or "Kite/Yahoo"),
    )
    gate.update(
        {
            "label": label,
            "day_change_pct": _float_or_none(market_data.get("day_change_pct")),
            "event_risk": market_data.get("event_risk"),
            "signal": signal.to_dict(),
            "signal_status": "DATA_UNAVAILABLE" if is_sector and gate.get("status") == "RED" else signal.signal_status if not is_sector else "SECTOR_FILTER",
            "strategy_type": "NO_TRADE" if is_sector else signal.strategy_type,
            "confidence": signal.confidence,
            "decision_reason": gate.get("reasons", [""])[0] if is_sector else signal.decision_reason,
            "stock_regime": signal.stock_regime if not is_sector else gate.get("trend"),
            "rsi": signal.rsi,
            "rsi_direction": signal.rsi_direction,
            "atr_pct": signal.atr_pct,
            "price_vs_vwap": signal.price_vs_vwap,
            "distance_to_resistance_pct": signal.distance_to_resistance_pct,
            "rejection_confirmed": signal.rejection_confirmed,
            "rejection_reasons": signal.rejection_reasons,
        }
    )
    return gate
