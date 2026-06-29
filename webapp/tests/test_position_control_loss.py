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
