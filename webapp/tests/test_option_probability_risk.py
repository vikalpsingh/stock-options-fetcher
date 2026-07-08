from datetime import date

import app


def base_risk(**overrides):
    values = {
        "symbol": "ABC26JUL120CE",
        "underlying": "ABC",
        "option_type": "CE",
        "position_side": "SHORT",
        "strike": 120.0,
        "expiry": date(2026, 7, 30),
        "dte": 23,
        "spot": 100.0,
        "avg_price": 1.50,
        "ltp": 1.00,
        "bid": None,
        "ask": None,
        "delta": 0.10,
        "iv": 0.20,
        "distance_to_strike_points": 20.0,
        "distance_to_strike_pct": 20.0,
        "expected_move_points": 5.0,
        "expected_move_pct": 5.0,
        "expected_move_multiple": 4.0,
        "probability_expiry_itm_pct": 10.0,
        "probability_touch_pct": 20.0,
        "premium_multiple": 0.67,
        "dte_bucket": "MONTHLY",
        "probability_risk_state": "SAFE",
        "recommended_action": "PASSIVE_CLOSE_ALLOWED",
        "reason": "",
        "warnings": [],
    }
    values.update(overrides)
    return app.OptionProbabilityRisk(**values)


def test_calculate_distance_to_strike_for_ce_and_pe():
    assert app.calculate_distance_to_strike(100, 120, "CE") == (20, 20)
    assert app.calculate_distance_to_strike(100, 80, "PE") == (20, 20)


def test_delta_probability_is_primary_source():
    assert app.calculate_probability_expiry_itm("CE", 0.12) == 12.0
    assert app.calculate_probability_expiry_itm("PE", -0.18) == 18.0
    assert app.calculate_probability_touch(12.0, 0.12) == 24.0


def test_probability_falls_back_to_black_scholes_when_delta_missing():
    probability = app.calculate_probability_expiry_itm(
        "CE",
        delta=None,
        spot=100,
        strike=110,
        dte=30,
        iv=0.25,
    )
    assert probability is not None
    assert 0 < probability < 100


def test_short_position_premium_double_is_panic():
    risk = app.classify_probability_risk(base_risk(ltp=3.0, premium_multiple=2.0))
    assert risk.probability_risk_state == "PANIC"
    assert risk.recommended_action == "CANCEL_PASSIVE_AND_CLOSE_OR_ROLL"


def test_short_position_strike_touch_is_panic():
    risk = app.classify_probability_risk(
        base_risk(distance_to_strike_points=-1.0, distance_to_strike_pct=-1.0)
    )
    assert risk.probability_risk_state == "PANIC"


def test_expiry_week_forces_exit():
    risk = app.classify_probability_risk(base_risk(dte=5, dte_bucket="EXPIRY_WEEK"))
    assert risk.probability_risk_state == "FORCE_EXIT"


def test_review_state_blocks_passive_buy_close():
    risk = app.classify_probability_risk(
        base_risk(probability_touch_pct=40.0, probability_expiry_itm_pct=20.0)
    )
    assert risk.probability_risk_state == "REVIEW"
    assert not app.passive_buy_close_allowed(risk)


def test_safe_short_allows_passive_buy_close():
    risk = app.classify_probability_risk(base_risk())
    assert risk.probability_risk_state == "SAFE"
    assert app.passive_buy_close_allowed(risk)


def test_passive_buy_close_blocked_when_ltp_above_entry():
    risk = app.classify_probability_risk(base_risk(avg_price=1.5, ltp=1.6, premium_multiple=1.07))
    assert not app.passive_buy_close_allowed(risk)


def test_aggressive_buy_close_uses_ask_or_ltp_plus_buffer():
    with_ask = base_risk(ask=10.0, ltp=9.0)
    without_ask = base_risk(ask=None, ltp=9.0)
    assert app.aggressive_buy_close_price(with_ask) == 10.2
    assert app.aggressive_buy_close_price(without_ask) == 9.45


def test_build_option_probability_risk_marks_missing_inputs_as_warning():
    risk = app.build_option_probability_risk(
        {
            "tradingsymbol": "ABC26JUL120CE",
            "quantity": -100,
            "average_price": 1.5,
            "ltp": 1.0,
        },
        {},
    )
    assert risk.probability_risk_state in {"SAFE", "WATCH", "REVIEW"}
    assert risk.warnings
