from trade_gpt_payload_builder import build_trade_gpt_payload


def base_preview() -> dict:
    return {
        "symbol": "TCS",
        "tradingsymbol": "TCS26OCT3000CE",
        "expiry": "2026-10-29",
        "strike": 3000,
        "option_type": "CE",
        "side": "BUY",
        "lots": 1,
        "quantity": 175,
        "product": "NRML",
        "stock_cmp": 2950,
        "ltp": 42.5,
        "limit_price": 42.5,
        "bid": 42.4,
        "ask": 42.6,
        "spread_rupees": 0.2,
        "spread_pct": 0.47,
        "volume": 0,
        "oi": 12000,
        "iv_percent": 21.5,
        "delta": 0.44,
        "gamma": 0.001,
        "theta": -2.5,
        "vega": 1.2,
        "dte": 11,
        "lot_size": 175,
        "market_session": "LIVE",
        "quote_fresh": True,
        "quote_at": "2026-10-18T12:00:00+05:30",
        "decision": "ELIGIBLE TO PLACE",
        "decision_score": 90,
        "nearby_strikes": [{"tradingsymbol": "TCS26OCT2950CE", "ltp": 61.0}],
    }


def test_payload_contains_actual_selected_quote_and_zero_volume_is_available() -> None:
    payload = build_trade_gpt_payload(
        instruction="analyse",
        preview=base_preview(),
        market={"ohlc": {"close": 2920}, "positions": []},
        checks=[{"name": "Liquidity", "status": "PASS", "reason": "Fresh depth"}],
        earnings={"next_result_date": "2026-11-10", "result_date_source": "NSE", "verified_at": "now"},
        monthly_risk={"remaining_loss_budget": 25000, "risk_state": "GREEN"},
    )
    assert payload["option"]["premium"] == 42.5
    assert payload["option"]["volume"] == 0
    assert payload["option"]["oi"] == 12000
    assert payload["availability"]["volume_available"] is True
    assert payload["availability"]["oi_available"] is True
    assert payload["availability"]["live_option_chain_available"] is True
    assert payload["option_chain"][0]["tradingsymbol"] == "TCS26OCT2950CE"
    assert payload["metadata"]["gpt_cannot_override_risk_engine"] is True


def test_after_hours_and_crossed_depth_are_not_labelled_live() -> None:
    preview = base_preview()
    preview.update({"market_session": "AFTER_HOURS", "quote_fresh": False, "bid": 43, "ask": 42})
    payload = build_trade_gpt_payload(
        instruction="analyse",
        preview=preview,
        market={},
        checks=[],
    )
    assert payload["availability"]["live_option_chain_available"] is False
    assert payload["availability"]["bid_ask_available"] is False
    assert payload["risk"]["data_quality"] == "STALE"
    assert payload["risk"]["event_risk"] == "UNKNOWN"
    assert any("not a fresh LIVE" in issue for issue in payload["data_issues"])


def test_missing_values_remain_null_and_are_reported() -> None:
    preview = base_preview()
    preview.update({"volume": None, "oi": None, "iv_percent": None, "bid": 0, "ask": 0})
    payload = build_trade_gpt_payload(
        instruction="analyse",
        preview=preview,
        market={},
        checks=[{"name": "Risk engine", "status": "BLOCK", "reason": "Maximum loss exceeded"}],
    )
    assert payload["option"]["volume"] is None
    assert payload["option"]["iv_pct"] is None
    assert payload["availability"]["iv_available"] is False
    assert payload["risk"]["event_risk"] == "UNKNOWN"
    assert any("Risk engine: Maximum loss exceeded" in issue for issue in payload["data_issues"])


def test_payload_includes_independently_calculated_technical_evidence() -> None:
    payload = build_trade_gpt_payload(
        instruction="analyse",
        preview=base_preview(),
        market={
            "intelligence": {"five_pct_direction_choices": [{"label": "5% OTM CE BUY", "status": "PREFERRED"}]},
            "technical_checklist": {
                "rsi_14": 63.5,
                "rsi_direction": "RISING",
                "support": 2850,
                "resistance": 3010,
                "breakout": False,
                "breakdown": False,
                "sector_alignment": "UNKNOWN",
                "supports": "CE BUY / defined-risk PE SELL",
                "opposing_evidence": ["Near resistance"],
                "thesis_invalidation": "Below 2850",
                "source": "ZERODHA_KITE_HISTORICAL_DAILY",
            }
        },
        checks=[],
    )
    assert payload["market"]["rsi_14"] == 63.5
    assert payload["market"]["support"] == 2850
    assert payload["market"]["opposing_technical_evidence"] == ["Near resistance"]
    assert payload["market"]["technical_source"] == "ZERODHA_KITE_HISTORICAL_DAILY"
    assert payload["market"]["five_pct_direction_choices"][0]["status"] == "PREFERRED"
