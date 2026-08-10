from datetime import date, datetime
from unittest.mock import patch

import app


def test_option_symbol_parts_parses_nifty_weekly_numeric_expiry():
    parts = app.option_symbol_parts("NIFTY2681122600PE")

    assert parts is not None
    assert parts["underlying"] == "NIFTY"
    assert parts["expiry_kind"] == "WEEKLY"
    assert parts["option_type"] == "PE"
    assert parts["strike"] == "22600"
    assert app.expiry_date_for_parts(parts) == date(2026, 8, 11)


def test_missing_close_guard_builds_buy_order_for_nifty_weekly_short_position():
    position = {
        "exchange": "NFO",
        "tradingsymbol": "NIFTY2681122600PE",
        "quantity": -65,
        "product": "NRML",
        "average_price": 16.0,
        "ltp": 15.65,
    }
    with patch.object(app, "open_option_positions", return_value=[position]), patch.object(
        app, "refresh_option_positions_with_live_ltp", return_value=[position]
    ), patch.object(app, "open_option_close_orders_by_symbol_side", return_value={}), patch.object(
        app, "app_now", return_value=datetime(2026, 7, 22, 10, 32, tzinfo=app.INDIA_TIME_ZONE)
    ), patch.object(
        app, "intraday_hard_stop_start_dte_setting", return_value=9
    ):
        orders, evaluations = app.build_missing_option_close_orders(kite=None, discount_percent=20)

    assert evaluations[0]["action"] == "PLACE_BUY_CLOSE"
    assert evaluations[0]["dte"] == 14
    assert evaluations[0]["dte_gate_applied"] is True
    assert orders[0]["tradingsymbol"] == "NIFTY2681122600PE"
    assert orders[0]["transaction_type"] == "BUY"
    assert orders[0]["quantity"] == 65
    assert orders[0]["price"] == 12.5
    assert orders[0]["price_basis"] == "min_ltp_average_price"


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

    assert evaluations[0]["action"] == "MODIFY_OR_PLACE_BUY_CLOSE"
    assert evaluations[0]["probability_risk_state"] == "FORCE_EXIT"
    assert orders[0]["tradingsymbol"] == "NAUKRI26JUL950PE"
    assert orders[0]["transaction_type"] == "BUY"
    assert orders[0]["price"] == 10.35
    assert orders[0]["price"] < position["ltp"]
    assert orders[0]["price_basis"] == "probability_force_exit_passive_ltp"
    assert "Hard stop 24.45 has not crossed" in orders[0]["risk_note"]


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

    assert evaluations[0]["probability_risk_state"] == "FORCE_EXIT"
    assert evaluations[0]["hard_stop_triggered"] is False
    assert orders[0]["tradingsymbol"] == "ETERNAL26JUL315CE"
    assert orders[0]["transaction_type"] == "BUY"
    assert orders[0]["price"] == 2.55
    assert orders[0]["price"] < position["ltp"]
    assert orders[0]["price_basis"] == "probability_force_exit_passive_ltp"
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


def test_missing_close_guard_skips_sell_order_for_long_buy_position_when_stop_enabled():
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

    assert orders == []
    assert evaluations[0]["action"] == "SKIP_OPTION_SELL_STOP_ENABLED"
    assert evaluations[0]["close_side"] == "SELL"


def test_missing_close_guard_builds_sell_order_for_long_buy_position_when_stop_disabled():
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
        orders, evaluations = app.build_missing_option_close_orders(
            kite=None,
            discount_percent=20,
            stop_option_sell=False,
        )

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


def test_execute_position_orders_blocks_sell_when_stop_enabled():
    orders = [
        {
            "tradingsymbol": "NIFTY26JUL22200PE",
            "transaction_type": "SELL",
            "quantity": 65,
        }
    ]

    try:
        app.execute_position_buy_orders(
            orders,
            {0},
            dry_run=True,
            keep_existing_orders=True,
            stop_option_sell=True,
        )
    except PermissionError as exc:
        assert "STOP OPTION SELL is enabled" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("SELL close order should be blocked while STOP OPTION SELL is enabled")


def test_positions_panel_shows_stop_option_sell_enabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SETTINGS_PATH", tmp_path / "app_settings.json")

    html = app.render_positions_panel(app.PageState(active_tab="positions"))

    assert 'name="position_stop_option_sell" value="1" checked' in html
    assert 'name="position_stop_option_sell_present" value="1"' in html
    assert "STOP OPTION SELL: ON" in html
    assert 'formaction="/positions/save-option-sell-flag"' in html
    assert "Save Option Sell Close Flag" in html
    assert "Scheduled Default Close Orders" in html
    assert "Intraday Missing Close-Order Guard" in html
    assert 'formaction="/positions/intraday-guard-run"' in html
    assert 'formaction="/positions/intraday-guard-start"' in html
    assert 'formaction="/positions/intraday-guard-stop"' in html
    assert 'formaction="/positions/intraday-guard-clear"' in html


def test_position_stop_option_sell_setting_persists_off_for_page_state(tmp_path, monkeypatch):
    settings_path = tmp_path / "app_settings.json"
    monkeypatch.setattr(app, "SETTINGS_PATH", settings_path)

    assert app.position_stop_option_sell_setting() is True

    app.save_app_settings({"position_stop_option_sell": False})

    assert app.position_stop_option_sell_setting() is False
    html = app.render_positions_panel(app.PageState(active_tab="positions"))
    assert 'name="position_stop_option_sell" value="1" checked' not in html
    assert "OPTION SELL CLOSE: ENABLED" in html
    assert 'formaction="/positions/save-option-sell-flag"' in html
    assert "<span>STOP OPTION SELL</span><strong>OFF</strong>" in html


def test_intraday_missing_close_guard_uses_saved_stop_option_sell_setting(
    tmp_path,
    monkeypatch,
):
    settings_path = tmp_path / "app_settings.json"
    monkeypatch.setattr(app, "SETTINGS_PATH", settings_path)
    app.save_app_settings({"position_stop_option_sell": False})

    captured: dict[str, bool] = {}
    default_order = {
        "tradingsymbol": "NIFTY26JUL22200PE",
        "transaction_type": "SELL",
        "quantity": 65,
        "price": 22.15,
    }

    def fake_build_missing_option_close_orders(kite, discount_percent, stop_option_sell=True):
        captured["build_stop_option_sell"] = stop_option_sell
        return [default_order], [{"action": "PLACE_SELL_CLOSE"}]

    def fake_execute_position_buy_orders(
        orders,
        selected_indexes,
        dry_run,
        keep_existing_orders,
        stop_option_sell=True,
    ):
        captured["execute_stop_option_sell"] = stop_option_sell
        return orders, [{"status": "LIVE_SENT", "tradingsymbol": orders[0]["tradingsymbol"]}]

    fake_kite = object()
    with patch.object(app, "load_kite_profiles", return_value={}), patch.object(
        app, "apply_kite_profile_to_env"
    ), patch.object(app, "kite_setup_issue", return_value=""), patch.object(
        app.kite_buy_positions, "kite_client", return_value=fake_kite
    ), patch.object(
        app, "verify_scheduled_position_market_open", return_value=(True, "Market open.")
    ), patch.object(
        app, "build_intraday_loss_limit_close_orders", return_value=([], [])
    ), patch.object(
        app, "build_intraday_pe_risk_exit_orders", return_value=([], [])
    ), patch.object(
        app, "build_missing_option_close_orders", side_effect=fake_build_missing_option_close_orders
    ), patch.object(
        app, "execute_position_buy_orders", side_effect=fake_execute_position_buy_orders
    ):
        result = app.run_intraday_position_close_job(
            now=datetime(2026, 8, 10, 10, 0, tzinfo=app.INDIA_TIME_ZONE),
            force=True,
        )

    assert result is not None
    assert result["status"] == "PLACED"
    assert captured["build_stop_option_sell"] is False
    assert captured["execute_stop_option_sell"] is False


def test_positions_panel_renders_large_colored_buy_and_sell_quantities():
    html = app.render_positions_panel(
        app.PageState(
            active_tab="positions",
            positions_rows=[
                {
                    "symbol": "HAVELLS26AUG1300CE",
                    "quantity": 520,
                    "product": "NRML",
                },
                {
                    "symbol": "BAJFINANCE26AUG1200CE",
                    "quantity": -750,
                    "product": "NRML",
                },
            ],
            positions_summary={"count": 2},
        )
    )

    assert "HAVELLS26AUG1300CE" in html
    assert 'position-qty-badge position-qty-buy">BUY Qty 520</span>' in html
    assert 'position-qty-badge position-qty-sell">SELL Qty 750</span>' in html


def test_positions_active_analytics_prioritizes_otm_pop_margin_iv_pcr_after_pnl():
    html = app.render_positions_panel(
        app.PageState(
            active_tab="positions",
            positions_rows=[
                {
                    "symbol": "HAVELLS26AUG1300CE",
                    "quantity": -520,
                    "pnl": -100,
                    "otm_distance": 4.5,
                    "sell_pop": 82,
                    "deployed": 50000,
                    "iv_percent": 24,
                    "pcr": 0.9,
                }
            ],
            positions_summary={"count": 1},
        )
    )

    header = html[html.index("<th>Position</th>") : html.index("</tr></thead>", html.index("<th>Position</th>"))]
    assert header.index("<th>P&L</th>") < header.index("<th>OTM</th>")
    assert header.index("<th>OTM</th>") < header.index("<th>POP</th>")
    assert header.index("<th>POP</th>") < header.index("<th>Margin</th>")
    assert header.index("<th>Margin</th>") < header.index("<th>IV</th>")
    assert header.index("<th>IV</th>") < header.index("<th>PCR</th>")
    assert header.index("<th>PCR</th>") < header.index("<th>Captured</th>")
