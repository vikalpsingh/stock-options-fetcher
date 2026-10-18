"""Deterministic technical direction scoring for the manual TRADE terminal.

Scores measure technical quality only. They never authorize broker execution.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


STRATEGIES = ("CE_BUY", "CE_SELL", "PE_BUY", "PE_SELL")


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _ema(values: list[float], length: int) -> float | None:
    if len(values) < length:
        return None
    value = sum(values[:length]) / length
    multiplier = 2 / (length + 1)
    for item in values[length:]:
        value = item * multiplier + value * (1 - multiplier)
    return value


def _sma(values: list[float], length: int, offset: int = 0) -> float | None:
    end = len(values) - offset
    start = end - length
    return sum(values[start:end]) / length if start >= 0 else None


def _rsi(values: list[float], length: int = 14) -> float | None:
    if len(values) <= length:
        return None
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    window = changes[-length:]
    gain = sum(max(item, 0) for item in window) / length
    loss = sum(max(-item, 0) for item in window) / length
    return 100.0 if loss == 0 else 100 - (100 / (1 + gain / loss))


def _clean(candles: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    rows = []
    for row in candles or []:
        close, high, low = _number(row.get("close")), _number(row.get("high")), _number(row.get("low"))
        if close <= 0 or high < close or low > close:
            continue
        rows.append({
            "time": str(row.get("time") or row.get("date") or ""),
            "open": _number(row.get("open")) or close,
            "high": high,
            "low": low,
            "close": close,
            "volume": _number(row.get("volume")),
        })
    return rows


def _label(score: float) -> str:
    if score >= 80:
        return "STRONG"
    if score >= 70:
        return "CONFIRM"
    if score >= 55:
        return "WATCH"
    return "AVOID"


def _direction(strategy: str) -> int:
    return 1 if strategy in {"CE_BUY", "PE_SELL"} else -1


def _strategy_name(strategy: str) -> str:
    return strategy.replace("_", " ")


def evaluate_technical_direction(
    daily_candles: list[dict[str, Any]],
    hourly_candles: list[dict[str, Any]] | None = None,
    sector_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return four independent 0-100 technical scores and component evidence."""
    daily = _clean(daily_candles)
    hourly = _clean(hourly_candles or [])
    if len(daily) < 200:
        return {
            "data_quality_status": "INSUFFICIENT_DATA",
            "reason": f"At least 200 completed daily candles are required; received {len(daily)}.",
            "scores": {},
            "strategy_candidate": "NO TRADE",
            "technical_direction": "UNCERTAIN",
        }
    closes = [float(row["close"]) for row in daily]
    highs = [float(row["high"]) for row in daily]
    lows = [float(row["low"]) for row in daily]
    volumes = [float(row["volume"]) for row in daily]
    price = closes[-1]
    ema20 = _ema(closes, 20)
    ema20_prior = _ema(closes[:-5], 20)
    sma50 = _sma(closes, 50)
    sma50_prior = _sma(closes, 50, 5)
    sma200 = _sma(closes, 200)
    sma200_prior = _sma(closes, 200, 5)
    rsi = _rsi(closes)
    prior_rsi = _rsi(closes[:-3])
    roc5 = (price / closes[-6] - 1) * 100 if closes[-6] else 0
    roc10_prior = (closes[-6] / closes[-11] - 1) * 100 if closes[-11] else 0
    support = min(lows[-21:-1])
    resistance = max(highs[-21:-1])
    breakout = price > resistance
    breakdown = price < support
    higher_lows = lows[-1] > lows[-6] > lows[-11]
    lower_highs = highs[-1] < highs[-6] < highs[-11]
    support_hold = lows[-1] <= support * 1.015 and price > support and price > float(daily[-1]["open"])
    resistance_rejection = highs[-1] >= resistance * 0.985 and price < resistance and price < float(daily[-1]["open"])
    avg_volume = sum(volumes[-21:-1]) / 20 if all(value > 0 for value in volumes[-21:-1]) else None
    rvol = volumes[-1] / avg_volume if avg_volume and volumes[-1] > 0 else None
    hourly_closes = [float(row["close"]) for row in hourly]
    hourly_confirmation = {
        "available": len(hourly_closes) >= 200,
        "ema20": _ema(hourly_closes, 20),
        "sma50": _sma(hourly_closes, 50),
        "sma200": _sma(hourly_closes, 200),
        "rsi_14": _rsi(hourly_closes),
        "candle_count": len(hourly_closes),
    }
    sector = sector_context or {}
    sector_direction = str(sector.get("direction") or "UNKNOWN").upper()
    sector_relative = _number(sector.get("relative_strength_pct")) if sector.get("relative_strength_pct") is not None else None
    scores: dict[str, Any] = {}
    for strategy in STRATEGIES:
        bullish = _direction(strategy) > 0
        is_buy = strategy.endswith("BUY")
        components = {"trend": 0.0, "momentum": 0.0, "structure": 0.0, "volume": 0.0, "sector": 0.0}
        evidence: list[str] = []
        contradictory: list[str] = []

        above_count = sum(price > value for value in (ema20, sma50, sma200) if value is not None)
        below_count = 3 - above_count
        components["trend"] += min(10, (above_count if bullish else below_count) * (10 / 3))
        aligned = bool(ema20 and sma50 and sma200 and (ema20 > sma50 > sma200 if bullish else ema20 < sma50 < sma200))
        slopes = [
            (ema20 or 0) - (ema20_prior or 0),
            (sma50 or 0) - (sma50_prior or 0),
            (sma200 or 0) - (sma200_prior or 0),
        ]
        slope_count = sum(value > 0 if bullish else value < 0 for value in slopes)
        components["trend"] += 5 if aligned else 0
        components["trend"] += min(5, slope_count * (5 / 3))
        persistence = sum(closes[index] > (ema20 or price) if bullish else closes[index] < (ema20 or price) for index in range(-10, 0))
        components["trend"] += persistence
        evidence.append(f"Price {price:.2f}; EMA20 {ema20:.2f}; SMA50 {sma50:.2f}; SMA200 {sma200:.2f}.")

        if rsi is not None:
            if is_buy:
                rsi_ok = rsi >= 55 if bullish else rsi <= 45
            else:
                rsi_ok = (50 <= rsi <= 68) if bullish else (32 <= rsi <= 50)
            components["momentum"] += 10 if rsi_ok else 4 if 45 <= rsi <= 55 else 0
            strengthening = (rsi > (prior_rsi or rsi) and roc5 > roc10_prior) if bullish else (rsi < (prior_rsi or rsi) and roc5 < roc10_prior)
            components["momentum"] += 10 if strengthening else 5 if (roc5 > 0 if bullish else roc5 < 0) else 0
            evidence.append(f"RSI {rsi:.2f}; 5-candle ROC {roc5:+.2f}%.")

        if bullish:
            components["structure"] += 10 if higher_lows else 4
            confirmation = breakout if strategy == "CE_BUY" else support_hold or higher_lows
            adverse = resistance_rejection or breakdown
            invalidation = f"Daily close below support {support:.2f}"
        else:
            components["structure"] += 10 if lower_highs else 4
            confirmation = breakdown if strategy == "PE_BUY" else resistance_rejection or lower_highs
            adverse = support_hold or breakout
            invalidation = f"Daily close above resistance {resistance:.2f}"
        components["structure"] += 10 if confirmation else 3
        if adverse:
            components["structure"] = max(0, components["structure"] - 5)
            contradictory.append("Recent price structure opposes this strategy.")
        evidence.append(f"Support {support:.2f}; resistance {resistance:.2f}; confirmation {'yes' if confirmation else 'not confirmed'}.")

        if rvol is not None:
            components["volume"] += 8 if rvol >= 1.2 else 5 if rvol >= 0.8 else 1
            directional_candle = price > float(daily[-1]["open"]) if bullish else price < float(daily[-1]["open"])
            components["volume"] += 7 if directional_candle and (confirmation or rvol >= 1.2) else 3 if directional_candle else 0
            evidence.append(f"Relative volume {rvol:.2f}x.")
        else:
            contradictory.append("Volume confirmation unavailable.")

        if sector_direction != "UNKNOWN":
            aligned_sector = sector_direction == ("BULLISH" if bullish else "BEARISH")
            relative_ok = sector_relative is not None and (sector_relative > 0 if bullish else sector_relative < 0)
            components["sector"] = (10 if relative_ok else 3) + (5 if aligned_sector else 0)
            if not aligned_sector:
                contradictory.append("Sector trend does not confirm the strategy direction.")
        else:
            contradictory.append("Sector alignment is UNKNOWN and earns no points.")

        total = round(sum(components.values()), 1)
        if sector_direction == "UNKNOWN" and total >= 80:
            total = 79.0
        signal = (
            "Bullish breakout" if strategy == "CE_BUY" else
            "Resistance rejection" if strategy == "CE_SELL" else
            "Bearish breakdown" if strategy == "PE_BUY" else
            "Bullish support hold"
        )
        scores[strategy] = {
            "strategy": _strategy_name(strategy),
            "score": total,
            "classification": _label(total),
            "signal": signal,
            "components": {key: round(value, 1) for key, value in components.items()},
            "evidence": evidence,
            "contradictory_evidence": contradictory,
            "invalidation": invalidation,
        }

    ranked = sorted(scores.values(), key=lambda item: float(item["score"]), reverse=True)
    best = ranked[0]
    candidate = best["strategy"] if float(best["score"]) >= 55 else "NO TRADE"
    bullish_best = max(scores["CE_BUY"]["score"], scores["PE_SELL"]["score"])
    bearish_best = max(scores["PE_BUY"]["score"], scores["CE_SELL"]["score"])
    direction = "BULLISH" if bullish_best >= bearish_best + 8 else "BEARISH" if bearish_best >= bullish_best + 8 else "SIDEWAYS"
    return {
        "data_quality_status": "PASS" if rvol is not None and sector_direction != "UNKNOWN" else "PARTIAL",
        "analysis_timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "primary_timeframe": "1D",
        "entry_timeframe": "1H_3M",
        "technical_direction": direction,
        "strategy_candidate": candidate,
        "technical_score": best["score"] if candidate != "NO TRADE" else 0.0,
        "scores": scores,
        "indicators": {
            "price": round(price, 2), "ema20": round(ema20 or 0, 2), "sma50": round(sma50 or 0, 2),
            "sma200": round(sma200 or 0, 2), "rsi_14": round(rsi or 0, 2), "rvol": round(rvol, 2) if rvol is not None else None,
            "support": round(support, 2), "resistance": round(resistance, 2), "sector_direction": sector_direction,
        },
        "hourly_confirmation": hourly_confirmation,
        "reason": f"Highest deterministic technical score is {best['strategy']} at {best['score']}/100.",
    }
