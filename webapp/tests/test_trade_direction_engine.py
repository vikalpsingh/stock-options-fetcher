from datetime import date, timedelta

from trade_direction_engine import evaluate_technical_direction


def candles(direction: int = 1, count: int = 240):
    rows = []
    for index in range(count):
        close = 100 + direction * index * 0.4
        rows.append({
            "time": (date(2025, 1, 1) + timedelta(days=index)).isoformat(),
            "open": close - direction * 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000 + index * 5,
        })
    rows[-1]["volume"] = 4000
    return rows


def test_bullish_breakout_scores_four_strategies_independently():
    daily = candles(1)
    hourly = candles(1, 260)
    result = evaluate_technical_direction(daily, hourly, {"direction": "BULLISH", "relative_strength_pct": 2.0})
    assert result["data_quality_status"] == "PASS"
    assert result["technical_direction"] == "BULLISH"
    assert set(result["scores"]) == {"CE_BUY", "CE_SELL", "PE_BUY", "PE_SELL"}
    assert result["scores"]["CE_BUY"]["score"] > result["scores"]["CE_SELL"]["score"]
    assert result["hourly_confirmation"]["candle_count"] == 260
    assert result["hourly_confirmation"]["sma200"] is not None


def test_bearish_breakdown_prefers_bearish_strategy():
    result = evaluate_technical_direction(
        candles(-1), candles(-1, 260), {"direction": "BEARISH", "relative_strength_pct": -2.0}
    )
    assert result["technical_direction"] == "BEARISH"
    assert result["scores"]["PE_BUY"]["score"] > result["scores"]["PE_SELL"]["score"]


def test_missing_history_fails_closed():
    result = evaluate_technical_direction(candles(1, 80), [], None)
    assert result["data_quality_status"] == "INSUFFICIENT_DATA"
    assert result["strategy_candidate"] == "NO TRADE"


def test_missing_sector_is_unknown_and_not_rescaled():
    result = evaluate_technical_direction(candles(1), candles(1, 260), None)
    assert result["data_quality_status"] == "PARTIAL"
    assert all(item["components"]["sector"] == 0 for item in result["scores"].values())
    assert max(item["score"] for item in result["scores"].values()) <= 79
