from unittest.mock import patch

import app


def test_intraday_guard_uses_hard_stop_price_when_crossed():
    position = {
        "exchange": "NFO",
        "tradingsymbol": "PFC26JUL400PE",
        "quantity": -1300,
        "product": "NRML",
        "average_price": 5.0,
        "ltp": 16.0,
    }
    with patch.object(app, "open_option_positions", return_value=[position]), patch.object(
        app, "refresh_option_positions_with_live_ltp", return_value=[position]
    ), patch.object(
        app, "intraday_hard_stop_trading_days_allowed", return_value=(True, 5)
    ):
        orders, evaluations = app.build_intraday_loss_limit_close_orders(
            kite=None,
            loss_trigger_percent=100,
            ltp_discount_percent=20,
        )

    assert evaluations[0]["hard_stop_triggered"] is True
    assert orders[0]["tradingsymbol"] == "PFC26JUL400PE"
    assert orders[0]["transaction_type"] == "BUY"
    assert orders[0]["price"] == 12.0
    assert orders[0]["price_basis"] == "hard_stop_price"
    assert "HARD STOP CONTROL" in orders[0]["risk_note"]


def test_intraday_guard_does_not_chase_spike_above_entry_before_hard_stop():
    position = {
        "exchange": "NFO",
        "tradingsymbol": "NAUKRI26JUL950PE",
        "quantity": -550,
        "product": "NRML",
        "average_price": 8.15,
        "ltp": 12.95,
    }
    with patch.object(app, "open_option_positions", return_value=[position]), patch.object(
        app, "refresh_option_positions_with_live_ltp", return_value=[position]
    ), patch.object(
        app, "intraday_hard_stop_trading_days_allowed", return_value=(True, 5)
    ):
        orders, evaluations = app.build_intraday_loss_limit_close_orders(
            kite=None,
            loss_trigger_percent=50,
            ltp_discount_percent=20,
        )

    assert orders == []
    assert evaluations[0]["action"] == "SKIP_SPIKE_ABOVE_ENTRY"
    assert evaluations[0]["skipped_limit_price"] == 10.35
    assert "above entry premium" in evaluations[0]["skip_reason"]


def test_intraday_probability_risk_close_stays_below_ltp_before_hard_stop():
    position = {
        "exchange": "NFO",
        "tradingsymbol": "ETERNAL26JUL315CE",
        "quantity": -2425,
        "product": "NRML",
        "average_price": 1.10,
        "ltp": 3.20,
    }
    with patch.object(app, "open_option_positions", return_value=[position]), patch.object(
        app, "refresh_option_positions_with_live_ltp", return_value=[position]
    ), patch.object(
        app, "intraday_hard_stop_trading_days_allowed", return_value=(True, 9)
    ):
        orders, evaluations = app.build_intraday_loss_limit_close_orders(
            kite=None,
            loss_trigger_percent=100,
            ltp_discount_percent=20,
        )

    assert evaluations[0]["probability_risk_state"] == "PANIC"
    assert evaluations[0]["hard_stop_triggered"] is False
    assert orders[0]["tradingsymbol"] == "ETERNAL26JUL315CE"
    assert orders[0]["transaction_type"] == "BUY"
    assert orders[0]["price"] == 2.55
    assert orders[0]["price"] < position["ltp"]
    assert orders[0]["price_basis"] == "probability_panic_passive_ltp"
    assert "PROBABILITY RISK PASSIVE CLOSE" in orders[0]["risk_note"]


def test_control_loss_builds_buy_order_at_ten_percent_below_hard_stop():
    rows = [
        {
            "position_id": "PFC26JUL400PE-1300",
            "symbol": "PFC",
            "tradingsymbol": "PFC26JUL400PE",
            "option_type": "PE",
            "quantity": -1300,
            "entry_premium": 5.0,
            "current_premium": 8.0,
            "hard_stop_premium": 15.0,
        }
    ]
    with patch.object(app, "load_position_risk_monitor", return_value=(rows, {})):
        orders, evaluations = app.build_control_loss_orders_from_position_ids(
            ["PFC26JUL400PE-1300"],
            10,
        )

    assert evaluations[0]["status"] == "READY"
    assert orders[0]["tradingsymbol"] == "PFC26JUL400PE"
    assert orders[0]["transaction_type"] == "BUY"
    assert orders[0]["price"] == 13.5
    assert orders[0]["tag"] == "CTRL_LOSS"


def test_missing_close_guard_builds_sell_order_for_long_buy_position():
    position = {
        "exchange": "NFO",
        "tradingsymbol": "NIFTY26JUL22200PE",
        "quantity": 65,
        "product": "NRML",
        "average_price": 18.45,
        "ltp": 18.20,
    }
    with patch.object(app, "open_option_positions", return_value=[position]), patch.object(
        app, "refresh_option_positions_with_live_ltp", return_value=[position]
    ), patch.object(app, "open_option_close_orders_by_symbol_side", return_value={}):
        orders, evaluations = app.build_missing_option_close_orders(kite=None, discount_percent=20)

    assert evaluations[0]["action"] == "PLACE_SELL_CLOSE"
    assert orders[0]["tradingsymbol"] == "NIFTY26JUL22200PE"
    assert orders[0]["transaction_type"] == "SELL"
    assert orders[0]["quantity"] == 65
    assert orders[0]["price"] == 22.15
    assert orders[0]["price_basis"] == "max_ltp_average_price"
    assert "20% above max(LTP, average entry price)" in orders[0]["risk_note"]


def test_missing_close_guard_skips_long_position_with_existing_sell_close_order():
    position = {
        "exchange": "NFO",
        "tradingsymbol": "NIFTY26JUL22200PE",
        "quantity": 65,
        "product": "NRML",
        "average_price": 18.45,
        "ltp": 18.20,
    }
    existing = {
        ("NIFTY26JUL22200PE", "SELL"): {
            "order_id": "123",
            "quantity": 65,
            "price": 22.15,
            "status": "OPEN",
            "transaction_type": "SELL",
        }
    }
    with patch.object(app, "open_option_positions", return_value=[position]), patch.object(
        app, "refresh_option_positions_with_live_ltp", return_value=[position]
    ), patch.object(app, "open_option_close_orders_by_symbol_side", return_value=existing):
        orders, evaluations = app.build_missing_option_close_orders(kite=None, discount_percent=20)

    assert orders == []
    assert evaluations[0]["action"] == "SKIP_EXISTING_CLOSE_ORDER"
    assert evaluations[0]["close_side"] == "SELL"
