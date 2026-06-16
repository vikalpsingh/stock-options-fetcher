import unittest
from argparse import Namespace
from datetime import date
from unittest.mock import patch

import app


def candidate(**overrides):
    base = {
        "symbol": "TEST",
        "cmp": 1000,
        "target_strike": 900,
        "strike": 900,
        "lot_size": 500,
        "premium": 8,
        "sell_limit_price": 10,
        "delta": 0.15,
        "sell_pop": 90,
        "iv": 30,
        "oi": 10000,
        "volume": 1000,
        "bid_ask_spread_percent": 5,
        "pcr": 0.9,
        "event_risk": "GREEN",
        "contract_valid": True,
        "fno_ban": False,
        "severe_breakdown": False,
        "has_active_pe_position": False,
        "core": "Y",
        "sector": "Financials",
        "holding": 500,
        "stock_pe": 20,
        "pct_to_52w_high": -20,
        "one_year_return": 15,
        "month_return": 1,
        "week_return": 1,
        "today_return": 0,
        "dte": 20,
    }
    base.update(overrides)
    return base


class PeSellStrategyTests(unittest.TestCase):
    def test_scheduled_position_close_job_places_default_buy_orders_once(self):
        schedule = {
            "enabled": True,
            "schedule_time": "09:20",
            "status": "WAITING",
            "results": [],
        }

        def read_schedule():
            return dict(schedule)

        def save_schedule(**updates):
            schedule.update(updates)
            return dict(schedule)

        order = {"tradingsymbol": "PFC26JUN400PE", "quantity": 1300}
        result = {"tradingsymbol": "PFC26JUN400PE", "status": "LIVE_SENT", "order_id": "123"}
        run_at = app.datetime(2026, 6, 12, 9, 20, tzinfo=app.INDIA_TIME_ZONE)
        built_states = []

        def build_orders(state):
            built_states.append(state)
            return [order]

        with (
            patch.object(app, "position_close_schedule_state", side_effect=read_schedule),
            patch.object(app, "save_position_close_schedule_state", side_effect=save_schedule),
            patch.object(app, "position_close_discount_percent_setting", return_value=32.5),
            patch.object(app, "selected_kite_profile_name", return_value="Shanti"),
            patch.object(app, "load_kite_profiles", return_value={"Shanti": app.blank_kite_profile()}),
            patch.object(app, "apply_kite_profile_to_env"),
            patch.object(app, "kite_setup_issue", return_value=""),
            patch.object(app.kite_buy_positions, "kite_client", return_value=object()),
            patch.object(app, "verify_scheduled_position_market_open", return_value=(True, "Market open.")),
            patch.object(app, "build_position_buy_orders", side_effect=build_orders),
            patch.object(app, "execute_position_buy_orders", return_value=([order], [result])),
        ):
            first = app.run_scheduled_position_close_job(run_at)
            second = app.run_scheduled_position_close_job(run_at)

        self.assertEqual(first["status"], "PLACED")
        self.assertEqual(first["results"], [result])
        self.assertEqual(built_states[0].position_discount_percent, 32.5)
        self.assertIsNone(second)

    def test_scheduled_position_close_job_does_not_run_on_weekend(self):
        run_at = app.datetime(2026, 6, 13, 9, 20, tzinfo=app.INDIA_TIME_ZONE)
        with patch.object(app, "position_close_schedule_state") as schedule_state:
            result = app.run_scheduled_position_close_job(run_at)

        self.assertIsNone(result)
        schedule_state.assert_called_once()

    def test_scheduled_income_growth_gpt_job_saves_valid_today_csv_once(self):
        schedule = {
            "enabled": True,
            "schedule_time": "09:30",
            "status": "WAITING",
        }

        def read_schedule():
            return dict(schedule)

        def save_schedule(**updates):
            schedule.update(updates)
            return dict(schedule)

        csv_text = (
            "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity\n"
            "NFO,PFC26JUN400PE,1300,SELL,NRML,LIMIT,0,DAY\n"
        )
        parsed_rows = [{
            "exchange": "NFO",
            "tradingsymbol": "PFC26JUN400PE",
            "quantity": "1300",
            "transaction_type": "SELL",
            "product": "NRML",
            "order_type": "LIMIT",
            "price": "0",
            "validity": "DAY",
        }]
        run_at = app.datetime(2026, 6, 12, 9, 30, tzinfo=app.INDIA_TIME_ZONE)
        with (
            patch.object(app, "income_growth_gpt_schedule_state", side_effect=read_schedule),
            patch.object(app, "save_income_growth_gpt_schedule_state", side_effect=save_schedule),
            patch.object(app, "selected_kite_profile_name", return_value="Shanti"),
            patch.object(app, "load_kite_profiles", return_value={"Shanti": app.blank_kite_profile()}),
            patch.object(app, "apply_kite_profile_to_env"),
            patch.object(app, "kite_setup_issue", return_value=""),
            patch.object(app.kite_orders, "kite_client", return_value=object()),
            patch.object(app, "verify_scheduled_position_market_open", return_value=(True, "Market open.")),
            patch.object(app, "income_growth_candidates", return_value=([{"symbol": "PFC"}], {"count": 1})),
            patch.object(app, "validate_income_growth_with_openai", return_value=(csv_text, csv_text, "resp_123", False)),
            patch.object(app, "parse_csv_text", return_value=parsed_rows),
            patch.object(app, "validate_kite_order_rows"),
            patch.object(app, "save_today_csv_text", return_value=("12Jun2026.csv", "Saved CSV.")),
            patch.object(app, "activate_today_csv_path") as activate_path,
        ):
            first = app.run_scheduled_income_growth_gpt_job(run_at)
            second = app.run_scheduled_income_growth_gpt_job(run_at)

        self.assertEqual(first["status"], "SAVED")
        self.assertEqual(first["order_count"], 1)
        self.assertIsNone(second)
        activate_path.assert_called_once_with("12Jun2026.csv")

    def test_scheduled_income_growth_gpt_job_does_not_run_on_weekend(self):
        run_at = app.datetime(2026, 6, 13, 9, 30, tzinfo=app.INDIA_TIME_ZONE)
        with patch.object(app, "income_growth_gpt_schedule_state") as schedule_state:
            result = app.run_scheduled_income_growth_gpt_job(run_at)

        self.assertIsNone(result)
        schedule_state.assert_called_once()

    def test_position_buy_prices_follow_requested_twenty_percent_rule(self):
        orders = [
            {
                "exchange": "NFO",
                "tradingsymbol": "PFC26JUN400PE",
                "transaction_type": "BUY",
                "quantity": 1300,
                "average_price": 12.0,
            },
            {
                "exchange": "NFO",
                "tradingsymbol": "CAMS26JUN760PE",
                "transaction_type": "BUY",
                "quantity": 750,
                "average_price": 8.0,
            },
        ]
        args = Namespace(discount_percent=20.0, tick_size=0.05)
        with patch.object(
            app,
            "fresh_kite_ltp_map",
            return_value={
                "NFO:PFC26JUN400PE": 10.0,
                "NFO:CAMS26JUN760PE": 10.0,
            },
        ):
            refreshed = app.refresh_position_buy_order_prices(orders, object(), args)

        self.assertEqual(refreshed[0]["price_basis"], "LTP")
        self.assertEqual(refreshed[0]["price"], 8.0)
        self.assertEqual(refreshed[1]["price_basis"], "average_price")
        self.assertEqual(refreshed[1]["price"], 6.4)

    def test_intraday_position_close_job_runs_once_per_fifteen_minute_slot(self):
        schedule = {
            "enabled": True,
            "start_time": "09:30",
            "end_time": "15:15",
            "interval_minutes": 15,
            "status": "WAITING",
            "results": [],
        }

        def read_schedule():
            return dict(schedule)

        def save_schedule(**updates):
            schedule.update(updates)
            return dict(schedule)

        order = {
            "tradingsymbol": "PFC26JUN400PE",
            "quantity": 1300,
            "price": 2.4,
            "price_basis": "LTP",
        }
        result = {"tradingsymbol": "PFC26JUN400PE", "status": "LIVE_SENT", "order_id": "456"}
        run_at = app.datetime(2026, 6, 12, 9, 45, 10, tzinfo=app.INDIA_TIME_ZONE)
        built_states = []

        def build_orders(state):
            built_states.append(state)
            return [order]

        with (
            patch.object(app, "intraday_position_close_schedule_state", side_effect=read_schedule),
            patch.object(app, "save_intraday_position_close_schedule_state", side_effect=save_schedule),
            patch.object(app, "position_close_discount_percent_setting", return_value=35.0),
            patch.object(app, "selected_kite_profile_name", return_value="Shanti"),
            patch.object(app, "load_kite_profiles", return_value={"Shanti": app.blank_kite_profile()}),
            patch.object(app, "apply_kite_profile_to_env"),
            patch.object(app, "kite_setup_issue", return_value=""),
            patch.object(app.kite_buy_positions, "kite_client", return_value=object()),
            patch.object(app, "verify_scheduled_position_market_open", return_value=(True, "Market open.")),
            patch.object(app, "build_position_buy_orders", side_effect=build_orders),
            patch.object(app, "execute_position_buy_orders", return_value=([order], [result])),
        ):
            first = app.run_intraday_position_close_job(run_at)
            second = app.run_intraday_position_close_job(run_at)

        self.assertEqual(first["status"], "PLACED")
        self.assertEqual(first["run_count_today"], 1)
        self.assertEqual(built_states[0].position_discount_percent, 35.0)
        self.assertIn("35% below LTP", first["message"])
        self.assertIsNone(second)

    def test_intraday_position_close_job_does_not_run_outside_market_window(self):
        run_at = app.datetime(2026, 6, 12, 15, 16, tzinfo=app.INDIA_TIME_ZONE)
        with patch.object(
            app,
            "intraday_position_close_schedule_state",
            return_value={
                "enabled": True,
                "start_time": "09:30",
                "end_time": "15:15",
                "interval_minutes": 15,
            },
        ):
            result = app.run_intraday_position_close_job(run_at)

        self.assertIsNone(result)

    def test_paused_scheduler_job_is_skipped(self):
        run_at = app.datetime(2026, 6, 12, 9, 20, tzinfo=app.INDIA_TIME_ZONE)
        schedule = {
            "enabled": True,
            "schedule_time": "09:20",
            "paused_until": app.datetime(
                2026, 6, 13, 9, 20, tzinfo=app.INDIA_TIME_ZONE
            ).isoformat(),
        }
        with (
            patch.object(app, "position_close_schedule_state", return_value=schedule),
            patch.object(app, "build_position_buy_orders") as build_orders,
        ):
            result = app.run_scheduled_position_close_job(run_at)

        self.assertIsNone(result)
        build_orders.assert_not_called()

    def test_scheduler_controls_persist_stop_start_and_pause(self):
        state = {"enabled": True, "status": "WAITING"}
        saved_updates = []

        def load_state():
            return dict(state)

        def save_state(**updates):
            state.update(updates)
            saved_updates.append(dict(updates))
            return dict(state)

        jobs = {
            "test-job": {
                "name": "Test Job",
                "purpose": "Test",
                "schedule": "Weekdays",
                "load": load_state,
                "save": save_state,
            }
        }
        now = app.datetime(2026, 6, 12, 10, 0, tzinfo=app.INDIA_TIME_ZONE)
        with patch.object(app, "scheduled_job_definitions", return_value=jobs):
            stopped = app.update_scheduled_job_control("test-job", "stop", now)
            started = app.update_scheduled_job_control("test-job", "start", now)
            paused = app.update_scheduled_job_control("test-job", "pause-day", now)

        self.assertFalse(stopped["enabled"])
        self.assertTrue(started["enabled"])
        self.assertEqual(paused["status"], "PAUSED")
        self.assertTrue(app.scheduled_job_is_paused(paused, now))
        self.assertEqual(len(saved_updates), 3)

    def test_next_intraday_schedule_skips_weekend(self):
        friday_after_close = app.datetime(
            2026, 6, 12, 16, 0, tzinfo=app.INDIA_TIME_ZONE
        )
        state = {
            "enabled": True,
            "start_time": "09:30",
            "end_time": "15:15",
            "interval_minutes": 15,
        }

        next_run = app.next_scheduled_job_run(
            "intraday_position_close",
            state,
            friday_after_close,
        )

        self.assertEqual(next_run.strftime("%Y-%m-%d %H:%M"), "2026-06-15 09:30")

    def test_kite_setup_scheduler_control_panel_lists_all_jobs(self):
        output = app.render_scheduler_control_panel()

        self.assertIn("Scheduled Jobs Control", output)
        self.assertIn("Default Close Orders", output)
        self.assertIn("Income Growth GPT CSV", output)
        self.assertIn("Intraday Close-Order Guard", output)
        self.assertIn("Pause for 1 day", output)
        self.assertIn("Run now", output)

    def test_manual_scheduler_run_dispatches_with_force(self):
        expected = {"status": "PLACED", "message": "Manual run ok."}
        with patch.object(
            app,
            "run_scheduled_position_close_job",
            return_value=expected,
        ) as run_close:
            result = app.run_scheduled_job_now("position_close_open")

        self.assertEqual(result, expected)
        run_close.assert_called_once_with(force=True)

    def test_position_analytics_render_before_scheduled_close_orders(self):
        state = app.PageState(active_tab="positions")
        state.positions_rows = [{"symbol": "PFC26JUN400PE", "quantity": -1300}]
        state.positions_summary = {}
        with patch.object(
            app,
            "render_position_close_schedule_panel",
            return_value="<section>SCHEDULE PANEL</section>",
        ):
            output = app.render_positions_panel(state)

        self.assertLess(
            output.index("Active Position Analytics"),
            output.index("SCHEDULE PANEL"),
        )

    def test_schedule_panel_shows_saved_buy_preview_discount(self):
        with patch.object(
            app,
            "position_close_discount_percent_setting",
            return_value=27.5,
        ):
            output = app.render_position_close_schedule_panel()

        self.assertIn("saved BUY Preview discount of 27.5%", output)
        self.assertIn("BUY at 27.5% below fresh LTP", output)

    def test_kite_runtime_error_redirects_to_kite_setup(self):
        state = app.PageState(
            active_tab="positions",
            error="Kite positions authentication failed: open Kite Setup.",
        )

        redirected = app.redirect_state_to_kite_setup_on_error(state)

        self.assertTrue(redirected)
        self.assertEqual(state.active_tab, "kite-setup")
        self.assertIn("Kite needs attention", state.message)

    def test_non_kite_error_stays_on_current_tab(self):
        state = app.PageState(
            active_tab="research",
            error="Could not find a valid Kite order CSV.",
        )

        with patch.object(
            app,
            "kite_setup_issue",
            return_value="Missing Kite setup value(s): KITE_ACCESS_TOKEN",
        ):
            redirected = app.redirect_state_to_kite_setup_on_error(state)

        self.assertFalse(redirected)
        self.assertEqual(state.active_tab, "research")

    def test_missing_setup_without_setup_exception_does_not_hijack_current_tab(self):
        state = app.PageState(active_tab="income")

        with patch.object(
            app,
            "kite_setup_issue",
            return_value="Missing Kite setup value(s): KITE_ACCESS_TOKEN",
        ):
            redirected = app.redirect_state_to_kite_setup_on_error(state)

        self.assertFalse(redirected)
        self.assertEqual(state.active_tab, "income")

    def test_kite_network_error_stays_on_current_tab(self):
        state = app.PageState(
            active_tab="order-management",
            order_book_error="Kite API is unreachable from this machine.",
        )

        with patch.object(app, "kite_setup_issue", return_value=""):
            redirected = app.redirect_state_to_kite_setup_on_error(state)

        self.assertFalse(redirected)
        self.assertEqual(state.active_tab, "order-management")

    def test_kite_business_error_stays_on_current_tab(self):
        state = app.PageState(
            active_tab="income",
            income_error="Kite order rejected: insufficient margin.",
        )

        with patch.object(app, "kite_setup_issue", return_value=""):
            redirected = app.redirect_state_to_kite_setup_on_error(state)

        self.assertFalse(redirected)
        self.assertEqual(state.active_tab, "income")

    def test_generic_permission_and_token_errors_stay_on_current_tab(self):
        for error in (
            "Order permission denied for this instrument.",
            "OpenAI response token limit exceeded.",
            "Traceback in kite_place_order.py while validating quantity.",
        ):
            with self.subTest(error=error):
                state = app.PageState(active_tab="place", error=error)

                redirected = app.redirect_state_to_kite_setup_on_error(state)

                self.assertFalse(redirected)
                self.assertEqual(state.active_tab, "place")

    def test_allowed_ip_error_redirects_to_kite_setup(self):
        state = app.PageState(
            active_tab="place",
            error="IP address is not allowed to place orders for this app.",
        )

        redirected = app.redirect_state_to_kite_setup_on_error(state)

        self.assertTrue(redirected)
        self.assertEqual(state.active_tab, "kite-setup")

    def test_client_error_router_uses_only_explicit_setup_markers(self):
        output = app.render_page(app.PageState(active_tab="place")).decode("utf-8")

        self.assertNotIn("text.includes('token')", output)
        self.assertNotIn("text.includes('permission')", output)
        self.assertIn("'access token is invalid'", output)
        self.assertIn("'ip address is not allowed'", output)

    def test_daily_kite_login_prompt_is_claimed_once_per_day(self):
        original_day = app.DAILY_KITE_LOGIN_PROMPT_DATE
        try:
            app.DAILY_KITE_LOGIN_PROMPT_DATE = None
            prompt_day = date(2026, 6, 15)

            self.assertTrue(app.claim_daily_kite_login_prompt(prompt_day))
            self.assertFalse(app.claim_daily_kite_login_prompt(prompt_day))
            self.assertTrue(app.claim_daily_kite_login_prompt(date(2026, 6, 16)))
        finally:
            app.DAILY_KITE_LOGIN_PROMPT_DATE = original_day

    def test_daily_kite_login_prompt_only_applies_to_full_app_pages(self):
        self.assertTrue(app.is_app_page_request("/"))
        self.assertTrue(app.is_app_page_request("/positions"))
        self.assertTrue(app.is_app_page_request("/kite-setup"))
        self.assertFalse(app.is_app_page_request("/market-quotes"))
        self.assertFalse(app.is_app_page_request("/global-quotes"))
        self.assertFalse(app.is_app_page_request("/trade-news"))

    def test_daily_kite_login_setup_page_opens_login_url_with_fallback(self):
        output = app.render_page(
            app.PageState(active_tab="kite-setup", auto_open_kite_login=True)
        ).decode("utf-8")

        self.assertIn("Start-of-day Kite login opened", output)
        self.assertIn("Open Kite Login manually", output)
        self.assertIn("window.open(dailyKiteLoginUrl", output)

    def test_order_book_separates_terminal_orders_from_actionable_orders(self):
        state = app.PageState(
            active_tab="order-management",
            order_book=[
                {
                    "order_id": "open-1",
                    "variety": "regular",
                    "tradingsymbol": "PFC26JUN400PE",
                    "transaction_type": "SELL",
                    "quantity": 1300,
                    "pending_quantity": 1300,
                    "price": 2.5,
                    "ltp": 2.2,
                    "status": "OPEN",
                    "is_cancellable": True,
                },
                {
                    "order_id": "done-1",
                    "variety": "regular",
                    "tradingsymbol": "CAMS26JUN760PE",
                    "transaction_type": "BUY",
                    "quantity": 750,
                    "pending_quantity": 0,
                    "price": 8.3,
                    "ltp": 8.1,
                    "status": "COMPLETE",
                    "is_cancellable": False,
                },
            ],
        )

        output = app.render_order_book(state)
        actionable_section, completed_section = output.split(
            '<div class="completed-orders-section">', 1
        )

        self.assertIn("PFC26JUN400PE", actionable_section)
        self.assertNotIn("CAMS26JUN760PE", actionable_section)
        self.assertIn("Completed Orders", completed_section)
        self.assertIn("CAMS26JUN760PE", completed_section)
        self.assertNotIn('name="order_key"', completed_section)
        self.assertNotIn("price-step-button", completed_section)

    def test_active_tab_uses_dark_high_contrast_style(self):
        output = app.render_page(app.PageState(active_tab="place")).decode("utf-8")

        self.assertIn("background: linear-gradient(135deg, #0f4c5c 0%, #0f766e 100%)", output)
        self.assertIn("color: #ffffff", output)
        self.assertIn("border-color: #083f49", output)

    def test_zero_price_trading_sell_uses_fresh_option_ltp_plus_markup_and_max_gain(self):
        row = {
            "exchange": "NFO",
            "tradingsymbol": "PFC26JUN400PE",
            "quantity": "1300",
            "transaction_type": "SELL",
            "product": "NRML",
            "order_type": "LIMIT",
            "price": "0",
            "validity": "DAY",
        }
        args = Namespace(
            symbol=row["tradingsymbol"],
            exchange="NFO",
            no_ltp_price=True,
            tick_size=0.05,
        )
        built = {
            "exchange": "NFO",
            "tradingsymbol": row["tradingsymbol"],
            "transaction_type": "SELL",
            "quantity": 1300,
            "price": 18.5,
        }
        with (
            patch.object(app, "cap_trading_option_rows_by_otm", return_value=([row], {})),
            patch.object(app.kite_orders, "args_for_csv_row", return_value=args),
            patch.object(app.kite_orders, "build_order", return_value=built),
            patch.object(app.kite_orders, "kite_client", return_value=object()),
            patch.object(app, "option_sell_markup_percent_setting", return_value=20.0),
            patch.object(
                app,
                "cached_kite_quote",
                return_value={"NFO:PFC26JUN400PE": {"last_price": 2.85}},
            ),
        ):
            orders = app.build_orders([row], True, False)
        self.assertEqual(orders[0]["price"], 3.45)
        self.assertEqual(orders[0]["ltp"], 2.85)
        self.assertEqual(orders[0]["max_gain"], 4485.0)
        self.assertEqual(orders[0]["price_basis"], "fresh_ltp_plus_markup")
        self.assertEqual(orders[0]["price_markup_percent"], 20.0)

    def test_explicit_trading_sell_price_is_replaced_by_fresh_ltp_plus_markup(self):
        row = {
            "exchange": "NFO",
            "tradingsymbol": "PFC26JUN400PE",
            "quantity": "1300",
            "transaction_type": "SELL",
            "price": "3.20",
        }
        args = Namespace(
            symbol=row["tradingsymbol"],
            exchange="NFO",
            no_ltp_price=True,
            tick_size=0.05,
        )
        built = {
            "exchange": "NFO",
            "tradingsymbol": row["tradingsymbol"],
            "transaction_type": "SELL",
            "quantity": 1300,
            "price": 3.20,
        }
        with (
            patch.object(app, "cap_trading_option_rows_by_otm", return_value=([row], {})),
            patch.object(app.kite_orders, "args_for_csv_row", return_value=args),
            patch.object(app.kite_orders, "build_order", return_value=built),
            patch.object(app.kite_orders, "kite_client", return_value=object()),
            patch.object(app, "option_sell_markup_percent_setting", return_value=20.0),
            patch.object(
                app,
                "cached_kite_quote",
                return_value={"NFO:PFC26JUN400PE": {"last_price": 2.85}},
            ),
        ):
            orders = app.build_orders([row], True, False)
        self.assertEqual(orders[0]["price"], 3.45)
        self.assertEqual(orders[0]["ltp"], 2.85)
        self.assertEqual(orders[0]["max_gain"], 4485.0)

    def test_trading_orders_table_shows_option_ltp_and_maximum_gain(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "PFC26JUN400PE",
            "transaction_type": "SELL",
            "quantity": 1300,
            "product": "NRML",
            "order_type": "LIMIT",
            "price": 2.85,
            "ltp": 2.85,
            "price_markup_percent": 20.0,
            "max_gain": 3705.0,
            "validity": "DAY",
            "tag": "GPT_CSP",
        }
        with (
            patch.object(app, "active_position_option_block_keys", return_value=set()),
            patch.object(app, "active_open_order_option_block_keys", return_value=set()),
        ):
            output = app.render_orders_table([order], selected={0})
        self.assertIn("<th>option LTP</th>", output)
        self.assertIn("<th>markup %</th>", output)
        self.assertIn("<th>max gain opportunity</th>", output)
        self.assertIn("<td>3705.00</td>", output)

    def test_trading_open_order_duplicate_blocks_same_symbol_and_side_only(self):
        sell_order = {
            "tradingsymbol": "BAJFINANCE26JUN1000CE",
            "transaction_type": "SELL",
        }
        buy_order = {
            "tradingsymbol": "BAJFINANCE26JUN1000CE",
            "transaction_type": "BUY",
        }
        active = {"BAJFINANCE26JUN1000CE:SELL"}
        self.assertTrue(app.order_has_open_duplicate(sell_order, active))
        self.assertFalse(app.order_has_open_duplicate(buy_order, active))

    def test_trading_table_disables_existing_open_order(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "BAJFINANCE26JUN1000CE",
            "transaction_type": "SELL",
            "quantity": 750,
            "product": "NRML",
            "order_type": "LIMIT",
            "price": 8.0,
            "validity": "DAY",
        }
        with (
            patch.object(app, "active_position_option_block_keys", return_value=set()),
            patch.object(
                app,
                "active_open_order_option_block_keys",
                return_value={"BAJFINANCE26JUN1000CE:SELL"},
            ),
        ):
            output = app.render_orders_table([order], selected={0})
        self.assertIn("Existing open Kite SELL order found", output)
        self.assertIn('value="0" disabled', output)

    def test_live_trading_execution_rechecks_and_blocks_existing_open_order(self):
        row = {
            "exchange": "NFO",
            "tradingsymbol": "BAJFINANCE26JUN1000CE",
            "transaction_type": "SELL",
            "quantity": "750",
            "price": "8",
        }
        built = {
            "exchange": "NFO",
            "tradingsymbol": "BAJFINANCE26JUN1000CE",
            "transaction_type": "SELL",
            "quantity": 750,
            "price": 8.0,
        }
        with (
            patch.dict(app.os.environ, {"KITE_CONFIRM_LIVE_ORDER": "YES"}),
            patch.object(app, "build_orders", return_value=[built]),
            patch.object(app.kite_orders, "kite_client", return_value=object()),
            patch.object(app, "active_position_option_block_keys", return_value=set()),
            patch.object(
                app,
                "active_open_order_option_block_keys",
                return_value={"BAJFINANCE26JUN1000CE:SELL"},
            ),
            patch.object(app.kite_orders, "place_order") as place_order,
        ):
            with self.assertRaisesRegex(ValueError, "same open/pending Kite order already exists"):
                app.execute_orders([row], {0}, False, True, True)
        place_order.assert_not_called()

    def test_far_otm_ce_is_adjusted_to_highest_active_strike_within_cap(self):
        row = {
            "exchange": "NFO",
            "tradingsymbol": "TEST26JUN130CE",
            "quantity": "500",
            "transaction_type": "SELL",
            "price": "0",
        }
        instruments = [
            {
                "name": "TEST",
                "instrument_type": "CE",
                "expiry": date(2026, 6, 30),
                "strike": 110,
                "tradingsymbol": "TEST26JUN110CE",
            },
            {
                "name": "TEST",
                "instrument_type": "CE",
                "expiry": date(2026, 6, 30),
                "strike": 112,
                "tradingsymbol": "TEST26JUN112CE",
            },
            {
                "name": "TEST",
                "instrument_type": "CE",
                "expiry": date(2026, 6, 30),
                "strike": 115,
                "tradingsymbol": "TEST26JUN115CE",
            },
        ]
        with (
            patch.object(app, "cached_kite_quote", return_value={"NSE:TEST": {"last_price": 100}}),
            patch.object(app, "cached_kite_instruments", return_value=instruments),
        ):
            rows, adjustments = app.cap_trading_option_rows_by_otm([row], object())
        self.assertEqual(rows[0]["tradingsymbol"], "TEST26JUN112CE")
        self.assertTrue(adjustments[0]["adjusted"])
        self.assertEqual(adjustments[0]["original_symbol"], "TEST26JUN130CE")
        self.assertEqual(adjustments[0]["otm_percent"], 12.0)

    def test_far_otm_pe_is_adjusted_to_lowest_active_strike_within_cap(self):
        row = {
            "exchange": "NFO",
            "tradingsymbol": "TEST26JUN70PE",
            "quantity": "500",
            "transaction_type": "SELL",
            "price": "0",
        }
        instruments = [
            {
                "name": "TEST",
                "instrument_type": "PE",
                "expiry": date(2026, 6, 30),
                "strike": 85,
                "tradingsymbol": "TEST26JUN85PE",
            },
            {
                "name": "TEST",
                "instrument_type": "PE",
                "expiry": date(2026, 6, 30),
                "strike": 88,
                "tradingsymbol": "TEST26JUN88PE",
            },
            {
                "name": "TEST",
                "instrument_type": "PE",
                "expiry": date(2026, 6, 30),
                "strike": 90,
                "tradingsymbol": "TEST26JUN90PE",
            },
        ]
        with (
            patch.object(app, "cached_kite_quote", return_value={"NSE:TEST": {"last_price": 100}}),
            patch.object(app, "cached_kite_instruments", return_value=instruments),
        ):
            rows, adjustments = app.cap_trading_option_rows_by_otm([row], object())
        self.assertEqual(rows[0]["tradingsymbol"], "TEST26JUN88PE")
        self.assertTrue(adjustments[0]["adjusted"])
        self.assertEqual(adjustments[0]["otm_percent"], 12.0)

    def test_current_fno_lot_sizes_and_coverage_are_applied(self):
        expected = {
            "ETERNAL": 2425, "CAMS": 750, "PGEL": 950, "PFC": 1300,
            "TITAN": 175, "HAVELLS": 500, "CDSL": 475, "MAZDOCK": 200,
            "WAAREEENER": 175, "UNITDSPR": 400, "BAJFINANCE": 750,
            "TATACONSUM": 550, "NAUKRI": 375, "NTPC": 1500,
        }
        self.assertEqual(app.CURRENT_FNO_LOT_SIZES, expected)
        self.assertEqual(app.current_lot_metrics("CAMS", 410, 1)["lots_can_sell"], 0)
        self.assertEqual(app.current_lot_metrics("MAZDOCK", 475, 1)["lots_can_sell"], 1)
        self.assertEqual(app.current_lot_metrics("PGEL", 7350, 3)["times_lot"], 7.74)

    def test_e2e_investing_holding_uses_corrected_split_values(self):
        e2e = next(item for item in app.INVESTING_HOLDINGS if item["code"] == "NSE:E2E")
        self.assertEqual(e2e["quantity"], 4630)
        self.assertEqual(e2e["avg_price"], 213.00)

    def test_option_sell_markup_setting_feeds_pe_and_ce_settings(self):
        with patch.object(app, "load_app_settings", return_value={"option_sell_markup_percent": 25}):
            self.assertEqual(app.load_pe_sell_settings()["price_markup_percent"], 25)
            self.assertEqual(app.load_ce_sell_settings()["price_markup_percent"], 25)

    def test_autoslice_order_retries_without_autoslice_for_old_sdk(self):
        calls = []

        class Kite:
            pass

        def fake_place_order(_kite, order):
            calls.append(dict(order))
            if "autoslice" in order:
                raise TypeError("got an unexpected keyword argument 'autoslice'")
            return "ORDER123"

        with patch.object(app.kite_orders, "place_order", side_effect=fake_place_order):
            order_id = app.place_order_allowing_autoslice(
                Kite(),
                {"variety": "regular", "tradingsymbol": "TEST", "autoslice": True},
            )
        self.assertEqual(order_id, "ORDER123")
        self.assertIn("autoslice", calls[0])
        self.assertNotIn("autoslice", calls[1])

    def test_income_pe_live_order_retries_without_autoslice_for_old_sdk(self):
        calls = []
        snapshot = {
            "symbol": "PGEL26JUN420PE",
            "quantity": 950,
            "ltp": 5.0,
            "limit_price": 6.0,
            "assignment_value": 399000,
            "markup_percent": 20.0,
        }

        def fake_place_order(_kite, order):
            calls.append(dict(order))
            if "autoslice" in order:
                raise TypeError("KiteConnect.place_order() got an unexpected keyword argument 'autoslice'")
            return "PE_ORDER_123"

        with (
            patch.dict(app.os.environ, {"KITE_CONFIRM_LIVE_ORDER": "YES"}),
            patch.object(app.kite_orders, "kite_client", return_value=object()),
            patch.object(app.kite_orders, "place_order", side_effect=fake_place_order),
            patch.object(app, "income_pe_order_snapshot", return_value=snapshot),
            patch.object(app, "invalidate_kite_trade_cache"),
        ):
            result = app.place_income_cash_secured_put_order("PGEL", 420)

        self.assertEqual(result["status"], "LIVE_SENT")
        self.assertEqual(result["order_id"], "PE_ORDER_123")
        self.assertEqual(result["tradingsymbol"], "PGEL26JUN420PE")
        self.assertIn("autoslice", calls[0])
        self.assertNotIn("autoslice", calls[1])

    def test_kiteconnect_payload_error_is_not_reported_as_network_failure(self):
        error = TypeError("KiteConnect.place_order() got an unexpected keyword argument 'autoslice'")
        message = app.friendly_external_error(error, "PGEL26JUN420PE PE SELL")
        self.assertIn("unexpected keyword argument", message)
        self.assertNotIn("unreachable", message)

    def test_open_option_buy_orders_detects_only_pending_buy_orders(self):
        orders = [
            {
                "order_id": "BUY1",
                "tradingsymbol": "PFC26JUN400PE",
                "transaction_type": "BUY",
                "status": "OPEN",
                "pending_quantity": 1300,
                "price": 2.60,
            },
            {
                "order_id": "SELL1",
                "tradingsymbol": "PFC26JUN400PE",
                "transaction_type": "SELL",
                "status": "OPEN",
                "pending_quantity": 1300,
                "price": 4.00,
            },
            {
                "order_id": "DONE1",
                "tradingsymbol": "CAMS26JUN760PE",
                "transaction_type": "BUY",
                "status": "COMPLETE",
                "pending_quantity": 0,
                "price": 8.30,
            },
        ]
        with patch.object(app, "cached_kite_orders", return_value=orders):
            result = app.open_option_buy_orders_by_symbol(object())
        self.assertEqual(list(result), ["PFC26JUN400PE"])
        self.assertEqual(result["PFC26JUN400PE"]["quantity"], 1300)
        self.assertEqual(result["PFC26JUN400PE"]["price"], 2.60)

    def test_position_close_buy_refuses_duplicate_open_buy_order(self):
        position = {
            "tradingsymbol": "PFC26JUN400PE",
            "exchange": "NFO",
            "quantity": -1300,
            "product": "NRML",
            "ltp": 2.85,
        }
        with (
            patch.object(app.kite_orders, "kite_client", return_value=object()),
            patch.object(app, "open_option_positions", return_value=[position]),
            patch.object(
                app,
                "open_option_buy_orders_by_symbol",
                return_value={
                    "PFC26JUN400PE": {
                        "quantity": 1300,
                        "price": 2.60,
                        "status": "OPEN",
                    }
                },
            ),
        ):
            with self.assertRaisesRegex(ValueError, "BUY close order already placed"):
                app.build_position_close_buy_order("PFC26JUN400PE")

    def test_positions_table_marks_existing_buy_close_order(self):
        state = app.PageState(active_tab="positions")
        state.positions_rows = [
            {
                "symbol": "PFC26JUN400PE",
                "product": "NRML",
                "quantity": -1300,
                "existing_buy_order": {
                    "quantity": 1300,
                    "price": 2.60,
                    "status": "OPEN",
                },
            }
        ]
        state.positions_summary = {"count": 1}
        output = app.render_positions_panel(state)
        self.assertIn("BUY ORDER PLACED", output)
        self.assertIn("BUY Qty 1300 | Limit 2.60", output)
        self.assertIn("Close BUY pending", output)
        self.assertNotIn(">BUY -10%</button>", output)

    def test_ce_selected_strike_is_valid_and_above_target(self):
        instruments = [
            {"instrument_type": "CE", "strike": 1240, "tradingsymbol": "TEST1240CE"},
            {"instrument_type": "CE", "strike": 1260, "tradingsymbol": "TEST1260CE"},
        ]
        selected = app.select_valid_ce_contract(instruments, 1244.27)
        self.assertEqual(selected["strike"], 1260)
        self.assertGreaterEqual(selected["strike"], 1244.27)

    def test_ce_holding_below_lot_size_is_rejected(self):
        result = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 499, "active_lot_size": 500,
                "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1100,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "breakout_risk": "GREEN", "sell_pop": 90,
            }
        )
        self.assertEqual(result["status"], "AVOID_TODAY")
        self.assertIn("Insufficient holding", result["reject_reason"])

    def test_ce_existing_position_is_rejected(self):
        result = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 1000, "active_lot_size": 500,
                "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1100,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "breakout_risk": "GREEN", "sell_pop": 90,
                "has_active_position": True,
            }
        )
        self.assertEqual(result["status"], "AVOID_TODAY")
        self.assertIn("Existing active option position", result["reject_reason"])

    def test_ce_max_profit_and_quantity_are_capped_at_one_lot(self):
        result = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 1200, "active_lot_size": 500,
                "requested_lots": 3, "cmp": 1000, "selected_ce_strike": 1100,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "breakout_risk": "GREEN", "sell_pop": 90,
            }
        )
        self.assertEqual(result["covered_lots_available"], 2)
        self.assertEqual(result["lots_to_sell"], 1)
        self.assertEqual(result["quantity"], 500)
        self.assertEqual(result["max_profit"], 6000)
        self.assertLessEqual(result["final_ce_score"], 100)

    def test_ce_corporate_action_inside_cycle_is_rejected(self):
        result = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 1000, "active_lot_size": 500,
                "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1150,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "corporate_action_risk": "RED",
                "breakout_risk": "GREEN", "sell_pop": 90,
            }
        )
        self.assertEqual(result["status"], "AVOID_TODAY")
        self.assertIn("Corporate action", result["reject_reason"])

    def test_ce_low_iv_percentile_reduces_score_without_becoming_hard_filter(self):
        low_iv = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 1000, "active_lot_size": 500,
                "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1150,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "breakout_risk": "GREEN", "sell_pop": 90,
                "iv_percentile": 20,
            }
        )
        high_iv = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 1000, "active_lot_size": 500,
                "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1150,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "breakout_risk": "GREEN", "sell_pop": 90,
                "iv_percentile": 70,
            }
        )
        self.assertNotEqual(low_iv["status"], "AVOID_TODAY")
        self.assertLess(low_iv["ce_trade_score"], high_iv["ce_trade_score"])

    def test_ce_macro_beta_buffer_rejects_strike_that_is_too_close(self):
        result = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 1000, "active_lot_size": 500,
                "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1100,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "breakout_risk": "GREEN", "sell_pop": 90,
                "macro_risk": "RED", "beta": 1.4,
            }
        )
        self.assertEqual(result["required_otm_percent"], 15)
        self.assertNotEqual(result["status"], "AVOID_TODAY")
        self.assertLess(result["ce_trade_components"]["otm_buffer_score"], 4)

    def test_ce_score_exposes_new_pipeline_checks(self):
        result = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 1000, "active_lot_size": 500,
                "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1150,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "corporate_action_risk": "CHECK",
                "breakout_risk": "GREEN", "sell_pop": 90, "iv_percentile": 65,
                "macro_risk": "GREEN", "next_leg_put_strike": 900,
                "next_leg_put_premium": 6, "dte": 30,
            }
        )
        self.assertEqual(result["iv_percentile_risk"], "GREEN")
        self.assertEqual(result["redeployment_risk"], "GREEN")
        self.assertGreater(result["annualized_premium_yield_percent"], 0)
        self.assertEqual(result["coverage_ratio_percent"], 50)
        self.assertLessEqual(result["holding_coverage_score"], 25)
        self.assertLessEqual(result["call_away_comfort_score"], 25)
        self.assertLessEqual(result["ce_trade_score"], 35)
        self.assertLessEqual(result["reinvestment_score"], 15)

    def test_ce_corporate_action_classifier_handles_dividend_and_major_actions(self):
        trade_day = date(2026, 6, 1)
        expiry = date(2026, 6, 30)
        no_action = app.classify_ce_corporate_action({}, 100, trade_day, expiry)
        small_dividend = app.classify_ce_corporate_action(
            {"type": "dividend", "ex_date": "2026-06-15", "dividend_amount": 1},
            100, trade_day, expiry,
        )
        large_dividend = app.classify_ce_corporate_action(
            {"type": "dividend", "ex_date": "2026-06-15", "dividend_amount": 2},
            100, trade_day, expiry,
        )
        split = app.classify_ce_corporate_action(
            {"type": "split", "record_date": "2026-06-20"}, 100, trade_day, expiry
        )
        self.assertEqual(no_action["corporate_action_risk"], "GREEN")
        self.assertEqual(small_dividend["corporate_action_risk"], "AMBER")
        self.assertEqual(large_dividend["corporate_action_risk"], "RED")
        self.assertEqual(split["corporate_action_risk"], "RED")
        for action_type in ("bonus", "rights", "merger", "demerger", "buyback"):
            with self.subTest(action_type=action_type):
                action = app.classify_ce_corporate_action(
                    {"type": action_type, "record_date": "2026-06-20"},
                    100, trade_day, expiry,
                )
                self.assertEqual(action["corporate_action_risk"], "RED")

    def test_ce_red_event_risk_is_hard_reject(self):
        result = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 1000, "active_lot_size": 500,
                "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1150,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "RED", "breakout_risk": "GREEN", "sell_pop": 90,
            }
        )
        self.assertEqual(result["status"], "AVOID_TODAY")
        self.assertIn("RED company event risk", result["reject_reason"])

    def test_ce_iv_metrics_unknown_does_not_crash(self):
        metrics = app.classify_ce_iv_metrics(None, None, 30, 0.4, 0.2)
        self.assertEqual(metrics["iv_status"], "UNKNOWN")
        self.assertEqual(metrics["iv_score"], 2.5)

    def test_ce_tax_and_reinvestment_change_final_score(self):
        base = {
            "stock": "TEST", "holding_qty": 1000, "active_lot_size": 500,
            "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1150,
            "premium": 10, "sell_limit_price": 12, "contract_valid": True,
            "event_risk": "GREEN", "breakout_risk": "GREEN", "sell_pop": 90,
            "average_buy_price": 600, "holding_period_days": 500,
        }
        strong = app.score_ce_sell_candidate({
            **base, "next_leg_put_strike": 900, "next_leg_put_premium": 8,
            "best_alternate_csp_score": 90, "best_alternate_csp_yield_percent": 0.8,
        })
        weak = app.score_ce_sell_candidate({**base, "holding_period_days": 100})
        self.assertGreater(strong["reinvestment_score"], weak["reinvestment_score"])
        self.assertGreater(strong["final_ce_score"], weak["final_ce_score"])
        self.assertEqual(strong["tax_type"], "LTCG")
        self.assertEqual(weak["tax_type"], "STCG")

    def test_ce_do_not_call_away_is_hard_reject(self):
        result = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 1000, "active_lot_size": 500,
                "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1150,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "breakout_risk": "GREEN", "sell_pop": 90,
                "do_not_call_away": True,
            }
        )
        self.assertEqual(result["status"], "AVOID_TODAY")
        self.assertIn("do not call away", result["reject_reason"])

    def test_high_momentum_full_coverage_is_penalized(self):
        partial = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 1000, "active_lot_size": 500,
                "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1150,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "breakout_risk": "RED", "sell_pop": 90,
                "week_return": 8,
            }
        )
        full = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 500, "active_lot_size": 500,
                "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1150,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "breakout_risk": "RED", "sell_pop": 90,
                "week_return": 8,
            }
        )
        self.assertGreater(partial["holding_coverage_score"], full["holding_coverage_score"])

    def test_naked_ce_never_appears_in_top_three(self):
        naked = {
            "stock": "NAKED", "holding_qty": 0, "active_lot_size": 500,
            "requested_lots": 1, "cmp": 1000, "selected_ce_strike": 1100,
            "premium": 10, "sell_limit_price": 12, "contract_valid": True,
            "event_risk": "GREEN", "breakout_risk": "GREEN", "sell_pop": 90,
        }
        covered = {**naked, "stock": "COVERED", "holding_qty": 1000}
        top, _, avoid = app.rank_ce_sell_candidates([naked, covered])
        self.assertNotIn("NAKED", [item["stock"] for item in top])
        self.assertIn("NAKED", [item["stock"] for item in avoid])

    def test_only_top_ce_cards_are_actionable(self):
        state = app.PageState(
            ce_sell_top=[{
                "stock": "TOP", "final_ce_score": 90,
                "corporate_action_risk": "CHECK", "iv_percentile_risk": "GREEN",
                "macro_risk": "AMBER", "redeployment_risk": "GREEN",
            }],
            ce_sell_watch=[{"stock": "WATCH", "final_ce_score": 70}],
            ce_sell_avoid=[{"stock": "AVOID", "final_ce_score": 20}],
        )
        rendered = app.render_ce_sell_dashboard(state)
        self.assertEqual(rendered.count("ce-sell-order-button"), 1)
        self.assertIn('data-underlying="TOP"', rendered)
        self.assertNotIn('data-underlying="WATCH"', rendered)
        self.assertNotIn('data-underlying="AVOID"', rendered)
        self.assertIn("Corporate action", rendered)
        self.assertIn("IV percentile", rendered)
        self.assertIn("Macro / beta buffer", rendered)
        self.assertIn("Next-leg yield", rendered)

    @patch("app.ce_sell_dashboard", return_value=([], [], []))
    def test_ce_snapshot_blocks_candidate_that_is_not_top_three(self, _dashboard):
        with self.assertRaises(PermissionError):
            app.ce_sell_order_snapshot("TEST")

    def test_ce_holding_source_falls_back_to_income_growth_without_adding_accounts(self):
        class Kite:
            @staticmethod
            def holdings():
                return [{"tradingsymbol": "NAUKRI", "quantity": 0, "average_price": 0}]

        with (
            patch.object(
                app,
                "load_income_growth_holding_map",
                return_value={"NAUKRI": {"holding": 615}},
            ),
            patch.object(app, "selected_kite_profile_name", return_value="Shanti"),
        ):
            result = app.covered_ce_holding_source(Kite(), "NAUKRI")
        self.assertEqual(result["holding_qty"], 615)
        self.assertEqual(result["kite_holding_qty"], 0)
        self.assertEqual(result["income_growth_holding_qty"], 615)
        self.assertEqual(result["holding_source"], "Income Growth holding record")

    def test_ce_holding_source_uses_larger_kite_holding_without_summing(self):
        class Kite:
            @staticmethod
            def holdings():
                return [{"tradingsymbol": "NAUKRI", "quantity": 750, "average_price": 900}]

        with (
            patch.object(
                app,
                "load_income_growth_holding_map",
                return_value={"NAUKRI": {"holding": 615}},
            ),
            patch.object(app, "selected_kite_profile_name", return_value="Shanti"),
        ):
            result = app.covered_ce_holding_source(Kite(), "NAUKRI")
        self.assertEqual(result["holding_qty"], 750)
        self.assertEqual(result["holding_source"], "Kite profile: Shanti")

    def test_commodity_card_is_green_only_below_valid_200_dma(self):
        self.assertTrue(app.commodity_below_200_dma(95, 100))
        self.assertFalse(app.commodity_below_200_dma(100, 100))
        self.assertFalse(app.commodity_below_200_dma(105, 100))
        self.assertFalse(app.commodity_below_200_dma(95, None))

    def test_commodity_holdings_table_shows_average_buy_price(self):
        state = app.PageState(active_tab="commodity")
        state.commodity_holdings = [
            {
                "symbol": "SILVERBEES",
                "label": "Nippon India Silver ETF",
                "quantity": 125,
                "average_price": 238.96,
                "source": "holding",
                "investment": 29870.0,
                "market_value": 27500.0,
                "pnl": -2370.0,
                "profit_pct": -7.93,
                "profit_target_pct": 20,
                "book_profit": False,
            }
        ]
        output = app.render_commodity_panel(state)
        self.assertIn("<th>Avg Buy Price</th>", output)
        self.assertIn("<td>238.96</td>", output)

    def test_score_is_capped_at_100(self):
        result = app.score_pe_sell_candidate(candidate())
        self.assertLessEqual(result["final_pe_score"], 100)
        self.assertLessEqual(result["stock_quality_score"], 35)
        self.assertLessEqual(result["pe_trade_score"], 45)
        self.assertLessEqual(result["assignment_recovery_score"], 20)

    def test_hard_reject_never_appears_in_top_three(self):
        rejected = candidate(symbol="BLOCKED", event_risk="RED")
        top, _, avoid = app.rank_pe_sell_candidates([rejected, candidate(symbol="GOOD")])
        self.assertNotIn("BLOCKED", [item["symbol"] for item in top])
        self.assertIn("BLOCKED", [item["symbol"] for item in avoid])

    def test_max_profit_uses_sell_limit_price(self):
        result = app.score_pe_sell_candidate(candidate(sell_limit_price=12, lot_size=500))
        self.assertEqual(result["max_profit"], 6000)
        self.assertAlmostEqual(result["premium_yield_percent"], 6000 / 450000 * 100)

    def test_invalid_strike_is_rejected(self):
        result = app.score_pe_sell_candidate(candidate(contract_valid=False))
        self.assertEqual(result["status"], "AVOID_TODAY")
        self.assertIn("active Kite instrument", result["reject_reason"])

    def test_assignment_cash_above_limit_is_rejected(self):
        result = app.score_pe_sell_candidate(candidate(strike=2000, cmp=2200, lot_size=500))
        self.assertEqual(result["status"], "AVOID_TODAY")
        self.assertIn("Assignment cash", result["reject_reason"])

    def test_existing_pe_position_is_rejected(self):
        result = app.score_pe_sell_candidate(candidate(has_active_pe_position=True))
        self.assertEqual(result["status"], "AVOID_TODAY")
        self.assertIn("Existing active PE position", result["reject_reason"])

    def test_red_corporate_action_is_rejected(self):
        result = app.score_pe_sell_candidate(candidate(corporate_action_risk="RED"))
        self.assertEqual(result["status"], "AVOID_TODAY")
        self.assertIn("RED corporate action", result["reject_reason"])

    def test_falling_knife_below_200_dma_is_rejected(self):
        result = app.score_pe_sell_candidate(
            candidate(dma_200=1100, high_52w=1500, trend_falling=True)
        )
        self.assertEqual(result["falling_knife_risk"], "RED")
        self.assertEqual(result["status"], "AVOID_TODAY")

    def test_corrected_not_broken_above_dma_scores_high(self):
        result = app.calculate_corrected_not_broken_score(800, 700, 1000, False)
        self.assertEqual(result["corrected_not_broken_score"], 6)
        self.assertEqual(result["falling_knife_risk"], "GREEN")

    def test_more_than_45_percent_correction_scores_low(self):
        result = app.calculate_corrected_not_broken_score(500, 450, 1000, False)
        self.assertLessEqual(result["corrected_not_broken_score"], 1)

    def test_good_ce_recovery_data_improves_assignment_score(self):
        weak = app.score_pe_sell_candidate(candidate())
        strong = app.score_pe_sell_candidate(
            candidate(
                same_stock_ce_available=True,
                same_stock_ce_oi=5000,
                same_stock_ce_volume=500,
                same_stock_ce_spread_percent=5,
                post_assignment_ce_yield_percent=0.7,
            )
        )
        self.assertGreater(strong["assignment_recovery_score"], weak["assignment_recovery_score"])
        self.assertGreater(strong["final_pe_score"], weak["final_pe_score"])

    def test_no_ce_liquidity_caps_assignment_recovery_score(self):
        result = app.score_pe_sell_candidate(candidate(same_stock_ce_available=False))
        self.assertLessEqual(result["assignment_recovery_score"], 10)

    def test_high_concentration_reduces_assignment_recovery_score(self):
        low = app.score_pe_sell_candidate(
            candidate(same_stock_ce_available=True, portfolio_after_assignment_percent=10)
        )
        high = app.score_pe_sell_candidate(
            candidate(same_stock_ce_available=True, portfolio_after_assignment_percent=30)
        )
        self.assertGreater(low["portfolio_concentration_score"], high["portfolio_concentration_score"])

    def test_high_iv_in_severe_breakdown_is_rejected(self):
        result = app.score_pe_sell_candidate(
            candidate(iv_percentile=80, severe_breakdown=True)
        )
        self.assertEqual(result["status"], "AVOID_TODAY")
        self.assertEqual(result["iv_status"], "RED")

    def test_unknown_iv_history_is_safe(self):
        result = app.score_pe_sell_candidate(candidate(iv_percentile=None, iv_rank=None))
        self.assertEqual(result["iv_status"], "UNKNOWN")
        self.assertNotEqual(result["status"], "AVOID_TODAY")

    def test_macro_red_below_200_dma_is_rejected(self):
        result = app.score_pe_sell_candidate(
            candidate(macro_risk="RED", dma_200=1100, high_52w=1300)
        )
        self.assertEqual(result["status"], "AVOID_TODAY")
        self.assertIn("Macro risk is RED", result["reject_reason"])

    def test_stock_below_200_dma_cannot_rank_top_three(self):
        top, watch, avoid = app.rank_pe_sell_candidates(
            [candidate(dma_200=1100, high_52w=1200, trend_falling=False)]
        )
        self.assertEqual(top, [])
        self.assertEqual(len(watch), 1)
        self.assertEqual(avoid, [])

    def test_amber_corporate_action_stays_in_watch_review(self):
        top, watch, _ = app.rank_pe_sell_candidates(
            [candidate(corporate_action_risk="AMBER")]
        )
        self.assertEqual(top, [])
        self.assertEqual(watch[0]["status"], "WATCH_REVIEW")

    def test_pe_macro_beta_buffer_widens_high_beta_more(self):
        self.assertGreater(
            app.pe_macro_beta_buffer("RED", 1.5),
            app.pe_macro_beta_buffer("RED", 0.7),
        )

    def test_selected_strike_is_active_and_below_target(self):
        instruments = [
            {"instrument_type": "PE", "strike": 890, "tradingsymbol": "TEST890PE"},
            {"instrument_type": "PE", "strike": 900, "tradingsymbol": "TEST900PE"},
            {"instrument_type": "PE", "strike": 910, "tradingsymbol": "TEST910PE"},
        ]
        selected = app.select_valid_pe_contract(instruments, 905)
        self.assertEqual(selected["strike"], 900)
        self.assertLessEqual(selected["strike"], 905)
        self.assertIn(selected, instruments)

    def test_no_invalid_symbol_is_generated_when_no_strike_exists(self):
        with self.assertRaisesRegex(ValueError, "No valid PE strike"):
            app.select_valid_pe_contract(
                [{"instrument_type": "PE", "strike": 910, "tradingsymbol": "TEST910PE"}],
                905,
            )

    def test_config_changes_filter_result(self):
        base = candidate()
        accepted = app.score_pe_sell_candidate(base, {"max_assignment_cash_per_stock": 600000})
        rejected = app.score_pe_sell_candidate(base, {"max_assignment_cash_per_stock": 400000})
        self.assertNotEqual(accepted["status"], "AVOID_TODAY")
        self.assertEqual(rejected["status"], "AVOID_TODAY")

    def test_broad_article_is_not_red_event_risk(self):
        status, _ = app.classify_pe_event_risk(
            "TEST",
            {"TEST": [{"title": "Ten stocks investors are watching this week"}]},
        )
        self.assertNotEqual(status, "RED")

    def test_upcoming_result_is_red_event_risk(self):
        status, _ = app.classify_pe_event_risk(
            "TEST",
            {"TEST": [{"title": "TEST quarterly result due this week"}]},
        )
        self.assertEqual(status, "RED")

    def test_dividend_article_is_amber(self):
        status, _ = app.classify_pe_event_risk(
            "TEST",
            {"TEST": [{"title": "TEST dividend outlook discussed by analysts"}]},
        )
        self.assertEqual(status, "AMBER")

    def test_income_dashboard_reuses_cache_until_forced(self):
        app.clear_app_cache(("income-dashboard:test-profile",))
        calls = {"growth": 0}

        def growth():
            calls["growth"] += 1
            return ([{"symbol": "TEST", "cmp": 1000}], {})

        with (
            patch.object(app, "selected_kite_profile_name", return_value="test-profile"),
            patch.object(app, "income_growth_candidates", side_effect=growth),
            patch.object(app, "build_live_pe_sell_rankings", return_value=([], [], [])),
            patch.object(app, "open_option_positions", return_value=[]),
        ):
            app.income_dashboard_snapshot()
            app.income_dashboard_snapshot()
            self.assertEqual(calls["growth"], 1)
            app.income_dashboard_snapshot(True)
            self.assertEqual(calls["growth"], 2)

    def test_income_panel_is_compact_and_collapses_review_sections(self):
        state = app.PageState(active_tab="income")
        state.income_summary = {
            "overall_pnl": 1250,
            "active_short_positions": 2,
            "active_pe_positions": 1,
            "active_ce_positions": 1,
            "profitable_positions": 1,
            "review_positions": 1,
        }
        state.income_positions = [
            {
                "tradingsymbol": "TEST26JUN900PE",
                "quantity": -500,
                "average_price": 10,
                "ltp": 8,
                "pnl": 1000,
            }
        ]
        state.console_log = "test console"
        output = app.render_income_panel(state)
        self.assertIn("Income Decision Summary", output)
        self.assertIn("Current Income Positions &amp; P&amp;L", output)
        self.assertIn("<summary>Watch / Review", output)
        self.assertIn("<summary>Avoid Today", output)
        self.assertIn("<summary>View Kite Console", output)
        self.assertIn("20 points for assignment recovery", output)
        self.assertNotIn("PFC monthly P&amp;L", output)
        self.assertNotIn("Expected Portfolio Behavior", output)

    def test_ce_and_pe_review_modals_show_backend_loading_spinners(self):
        state = app.PageState(active_tab="income")
        income_html = app.render_income_panel(state)
        self.assertIn('id="income-pe-loading"', income_html)
        self.assertIn("backend-spinner", income_html)
        page_html = app.render_page(app.PageState(active_tab="trading")).decode("utf-8")
        self.assertIn('id="ce-sell-loading"', page_html)
        self.assertIn("Revalidating coverage, position risk, quote, analytics, and news", page_html)

    def test_ce_and_pe_go_buttons_submit_to_their_explicit_order_routes(self):
        page_html = app.render_page(app.PageState(active_tab="trading")).decode("utf-8")
        self.assertIn("function submitOrderModal(event, modal, reviewButton, goButton)", page_html)
        self.assertIn("const submitAction = goButton.formAction;", page_html)
        self.assertIn("HTMLFormElement.prototype.submit.call(form);", page_html)
        self.assertIn("submitOrderModal(event, ceSellModal, ceSellReview, ceSellGo);", page_html)

    def test_ce_sell_review_modal_keeps_go_actions_visible(self):
        page_html = app.render_page(app.PageState(active_tab="trading")).decode("utf-8")
        self.assertIn("max-height: calc(100vh - 32px);", page_html)
        self.assertIn(".income-pe-order-modal-card .modal-actions", page_html)
        self.assertIn("position: sticky;", page_html)
        self.assertIn("bottom: -20px;", page_html)
        self.assertIn('id="ce-sell-go"', page_html)
        self.assertIn("submitOrderModal(event, incomePeModal, incomePeReview, incomePeGo);", page_html)

    def test_heavy_actions_use_global_blocking_work_overlay(self):
        page_html = app.render_page(app.PageState(active_tab="trading")).decode("utf-8")
        self.assertIn('id="global-work-overlay"', page_html)
        self.assertIn("function beginGlobalWork(title, detail)", page_html)
        self.assertIn("const heavyActionLabels", page_html)
        self.assertIn("'/positions-research/load': 'Calculating position analytics...'", page_html)
        self.assertIn("beginGlobalWork('Submitting order to Kite...'", page_html)
        self.assertIn("setQuoteLoading(ceSellModal, ceSellLoading, true, 'Revalidating covered CE SELL candidate...')", page_html)
        self.assertIn("setQuoteLoading(incomePeModal, incomePeLoading, true, 'Recalculating PE SELL candidate...')", page_html)

    def test_income_growth_renders_dividend_income_invits_with_equity_actions(self):
        state = app.PageState(active_tab="income-growth")
        state.income_growth_summary = {
            "dividend_income_rows": [
                {
                    "symbol": "PGINVIT-IV",
                    "company": "PGINVIT",
                    "quantity": 0,
                    "avg_price": 0,
                    "cmp": 102.5,
                    "holding_source": "Kite profile: Monika",
                    "invested_amount": 0,
                    "market_value": 0,
                    "pnl": 0,
                    "covered_lots": 0,
                    "decision": "DIVIDEND_INCOME_ACCUMULATION",
                },
                {
                    "symbol": "IRBINVIT-IV",
                    "company": "IRBINVIT",
                    "quantity": 0,
                    "avg_price": 0,
                    "cmp": 65.25,
                    "market_value": 0,
                    "pnl": 0,
                    "covered_lots": 0,
                    "decision": "DIVIDEND_INCOME_ACCUMULATION",
                },
            ]
        }

        output = app.render_income_growth_panel(state)

        self.assertIn("Dividend Income", output)
        self.assertIn('id="dividend-income-table"', output)
        self.assertIn('data-symbol="PGINVIT-IV"', output)
        self.assertIn('data-symbol="IRBINVIT-IV"', output)
        self.assertIn('id="income-equity-limit-price"', output)
        self.assertIn("CNC LIMIT BUY or SELL", output)
        self.assertIn("Source: Kite profile: Monika", output)
        self.assertIn("Avg 0", output)
        self.assertIn("P&L 0", output)

    def test_dividend_income_rows_match_zerodha_holdings_by_invit_alias(self):
        class FakeKite:
            def holdings(self):
                return [
                    {
                        "exchange": "NSE",
                        "tradingsymbol": "PGINVIT",
                        "quantity": 125,
                        "average_price": 92.0,
                        "last_price": 95.5,
                    },
                    {
                        "exchange": "NSE",
                        "tradingsymbol": "IRBINVIT",
                        "quantity": 50,
                        "average_price": 60.0,
                        "last_price": 63.0,
                    },
                ]

        with (
            patch.object(app, "cached_kite_quote", return_value={}),
            patch.object(app, "cached_value", side_effect=lambda _key, fn, _ttl: fn()),
            patch.object(app, "selected_kite_profile_name", return_value="Shanti"),
        ):
            rows = app.dividend_income_rows(FakeKite(), {})

        by_symbol = {row["symbol"]: row for row in rows}
        self.assertEqual(by_symbol["PGINVIT-IV"]["quantity"], 125)
        self.assertEqual(by_symbol["PGINVIT-IV"]["avg_price"], 92.0)
        self.assertEqual(by_symbol["PGINVIT-IV"]["cmp"], 95.5)
        self.assertEqual(by_symbol["PGINVIT-IV"]["invested_amount"], 11500.0)
        self.assertEqual(by_symbol["PGINVIT-IV"]["market_value"], 11937.5)
        self.assertEqual(by_symbol["PGINVIT-IV"]["pnl"], 437.5)
        self.assertEqual(by_symbol["PGINVIT-IV"]["holding_source"], "Kite profile: Shanti")
        self.assertEqual(by_symbol["IRBINVIT-IV"]["quantity"], 50)
        self.assertEqual(by_symbol["IRBINVIT-IV"]["avg_price"], 60.0)

    def test_income_growth_equity_order_uses_requested_limit_price(self):
        snapshot = {
            "symbol": "PGINVIT-IV",
            "quantity": 0,
            "average_price": 0,
            "ltp": 101.2,
            "pnl": None,
        }
        fake_kite = object()
        placed = {}

        def place_order(_kite, order):
            placed.update(order)
            return "order-123"

        with (
            patch.dict(app.os.environ, {"KITE_CONFIRM_LIVE_ORDER": "YES"}),
            patch.object(app, "income_growth_equity_snapshot", return_value=snapshot),
            patch.object(app.kite_orders, "kite_client", return_value=fake_kite),
            patch.object(app.kite_orders, "place_order", side_effect=place_order),
            patch.object(app, "invalidate_kite_trade_cache"),
        ):
            result = app.place_income_growth_equity_order("PGINVIT-IV", "BUY", 10, 100.03)

        self.assertEqual(result["status"], "LIVE_SENT")
        self.assertEqual(placed["tradingsymbol"], "PGINVIT-IV")
        self.assertEqual(placed["product"], "CNC")
        self.assertEqual(placed["order_type"], "LIMIT")
        self.assertEqual(placed["price"], 100.05)

    def test_income_growth_page_enables_dividend_table_sorting_and_limit_gap(self):
        page_html = app.render_page(app.PageState(active_tab="income-growth")).decode("utf-8")
        self.assertIn("enableTableSorting(document.getElementById('dividend-income-table'))", page_html)
        self.assertIn("const incomeEquityLimitPrice", page_html)
        self.assertIn("Limit vs CMP", page_html)


if __name__ == "__main__":
    unittest.main()
