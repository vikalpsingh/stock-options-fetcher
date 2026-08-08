from __future__ import annotations

from dhan_it_call_watch import (
    NIFTY_IT_SYMBOL,
    build_dhan_it_card_view_model,
    build_dhan_it_call_spread_signal,
    calculate_dma_distance,
    calculate_moving_averages,
    classify_dhan_it_regime,
    classify_nifty_it_regime,
    classify_trend,
    evaluate_call_spread_dma_gate,
)


def approved_pair(**overrides):
    pair = {
        "sell_leg_tradingsymbol": "TCS26AUG1050CE",
        "buy_leg_tradingsymbol": "TCS26AUG1100CE",
        "risk_decision": "APPROVED",
        "pair_liquidity_condition": "GREEN",
        "liquidity_order_allowed": True,
    }
    pair.update(overrides)
    return pair


def test_calculates_dma_and_distance_from_completed_closes():
    result = calculate_moving_averages(range(1, 221))

    assert result["history_count"] == 220
    assert result["data_available"] is True
    assert result["dma_50"] == 195.5
    assert result["dma_200"] == 120.5
    assert calculate_dma_distance(90, 100) == -10.0


def test_classifies_stock_and_nifty_it_regime():
    assert classify_trend(120, 110, 100) == "BULLISH"
    assert classify_trend(90, 100, 110) == "BEARISH"
    assert classify_trend(95, 100, 90) == "MIXED"
    assert classify_nifty_it_regime(90, 100, 110) == "BEARISH"
    assert classify_trend(None, 100, 110) == "DATA_UNAVAILABLE"
    assert classify_dhan_it_regime(90, 100, 110) == "BEARISH"
    assert classify_dhan_it_regime(105, 100, 110) == "BEARISH_RALLY"
    assert classify_dhan_it_regime(105, 110, 100) == "BULLISH_PULLBACK"
    assert classify_dhan_it_regime(120, 110, 100) == "BULLISH"


def test_green_when_stock_below_50_200_and_it_regime_not_bullish():
    gate = evaluate_call_spread_dma_gate(
        symbol="TCS",
        price=94,
        dma_50=100,
        dma_200=110,
        nifty_it_regime="BEARISH",
        pair_preview=approved_pair(),
    )

    assert gate["status"] == "GREEN"
    assert gate["decision"] == "ALLOWED"
    assert gate["order_allowed"] is True


def test_amber_for_mixed_stock_dma_setup():
    gate = evaluate_call_spread_dma_gate(
        symbol="INFY",
        price=95,
        dma_50=100,
        dma_200=90,
        nifty_it_regime="BULLISH_PULLBACK",
        pair_preview=approved_pair(),
    )

    assert gate["status"] == "AMBER"
    assert gate["decision"] == "CONFIRM_REQUIRED"
    assert gate["order_allowed"] is True


def test_red_for_bullish_stock_trend():
    gate = evaluate_call_spread_dma_gate(
        symbol="HCLTECH",
        price=120,
        dma_50=110,
        dma_200=100,
        nifty_it_regime="BULLISH_PULLBACK",
        pair_preview=approved_pair(),
    )

    assert gate["status"] == "RED"
    assert gate["order_allowed"] is False


def test_bearish_stock_with_bullish_it_regime_is_amber():
    gate = evaluate_call_spread_dma_gate(
        symbol="TECHM",
        price=94,
        dma_50=100,
        dma_200=110,
        nifty_it_regime="BULLISH",
        pair_preview=approved_pair(),
    )

    assert gate["status"] == "AMBER"
    assert "bullish" in " ".join(gate["warnings"]).lower()


def test_deep_below_50_dma_rebound_risk_downgrades_green_to_amber():
    gate = evaluate_call_spread_dma_gate(
        symbol="TCS",
        price=89,
        dma_50=100,
        dma_200=110,
        nifty_it_regime="BEARISH",
        pair_preview=approved_pair(),
    )

    assert gate["status"] == "AMBER"
    assert any("rebound" in warning.lower() for warning in gate["warnings"])


def test_missing_or_stale_dma_blocks():
    missing = evaluate_call_spread_dma_gate(symbol="TCS", price=90, dma_50=100, dma_200=None, nifty_it_regime="BEARISH")
    stale = evaluate_call_spread_dma_gate(symbol="TCS", price=90, dma_50=100, dma_200=110, nifty_it_regime="BEARISH", data_stale=True)

    assert missing["status"] == "RED"
    assert stale["status"] == "RED"


def test_event_liquidity_and_missing_hedge_override_dma_green():
    event = evaluate_call_spread_dma_gate(
        symbol="TCS", price=94, dma_50=100, dma_200=110, nifty_it_regime="BEARISH", event_risk=True, pair_preview=approved_pair()
    )
    liquidity = evaluate_call_spread_dma_gate(
        symbol="TCS",
        price=94,
        dma_50=100,
        dma_200=110,
        nifty_it_regime="BEARISH",
        pair_preview=approved_pair(pair_liquidity_condition="RED", liquidity_order_allowed=False),
    )
    missing_hedge = evaluate_call_spread_dma_gate(
        symbol="TCS",
        price=94,
        dma_50=100,
        dma_200=110,
        nifty_it_regime="BEARISH",
        pair_preview=approved_pair(buy_leg_tradingsymbol=""),
    )

    assert event["status"] == "RED"
    assert liquidity["status"] == "RED"
    assert missing_hedge["status"] == "RED"


def test_nifty_it_card_is_regime_only_and_never_orderable():
    card = build_dhan_it_card_view_model(
        symbol=NIFTY_IT_SYMBOL,
        label="NIFTY IT Sector Index",
        market_data={"cmp": 30200, "dma_50": 31000, "dma_200": 33000},
        nifty_it_regime="BEARISH",
        is_sector=True,
    )

    assert card["decision"] == "REGIME_ONLY"
    assert card["order_allowed"] is False
    assert card["button_label"] == "Refresh Sector Signal"


def test_daily_rise_creates_watch_rise_not_executable_order():
    signal = build_dhan_it_call_spread_signal(
        "TCS",
        market_data={"cmp": 105, "day_change_pct": 3.4},
        technical_data={"dma_50": 100, "dma_200": 110},
        sector_regime="BEARISH",
    )

    assert signal.signal_status == "WATCH_RISE"
    assert signal.strategy_type == "WATCH"
    assert signal.decision == "WATCH"


def test_two_rejection_conditions_allow_ce_review_in_bearish_alignment():
    signal = build_dhan_it_call_spread_signal(
        "INFY",
        market_data={"cmp": 109, "close": 108, "high": 111, "low": 106, "day_change_pct": 2.5},
        technical_data={"dma_50": 100, "dma_200": 110, "resistance_20d": 110, "rsi": 62, "previous_rsi": 67},
        sector_regime="BEARISH",
        liquidity_condition="GREEN",
    )

    assert signal.rejection_confirmed is True
    assert signal.strategy_type == "BEAR_CALL_SPREAD"
    assert signal.signal_status in {"REVIEW_CE_PAIR", "CONFIRM_REQUIRED"}
    assert signal.confidence >= 70


def test_missing_dma_data_blocks_canonical_signal():
    signal = build_dhan_it_call_spread_signal("TECHM", market_data={"cmp": 1200, "day_change_pct": 4.0}, sector_regime="BEARISH")

    assert signal.signal_status == "DATA_UNAVAILABLE"
    assert signal.strategy_type == "NO_TRADE"
    assert signal.decision == "BLOCKED"
