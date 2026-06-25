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
    def test_nifty_income_profile_defaults_to_monika_only(self):
        with patch.object(app, "load_app_settings", return_value={}):
            profiles = app.load_kite_profiles()

        self.assertTrue(profiles["Monika"]["NIFTY_INCOME_ENABLED"])
        self.assertFalse(profiles["Vikalp"]["NIFTY_INCOME_ENABLED"])
        self.assertFalse(profiles["Shanti"]["NIFTY_INCOME_ENABLED"])
        self.assertFalse(profiles["Aanya"]["NIFTY_INCOME_ENABLED"])

    def test_nifty_income_profile_flag_is_saved_per_profile(self):
        profiles = {
            name: app.blank_kite_profile(name)
            for name in app.KITE_PROFILE_NAMES
        }
        with (
            patch.object(app, "load_kite_profiles", return_value=profiles),
            patch.object(app, "save_app_settings") as save_settings,
        ):
            saved = app.save_kite_profile(
                "Shanti",
                {"NIFTY_INCOME_ENABLED": True},
            )

        self.assertTrue(saved["NIFTY_INCOME_ENABLED"])
        persisted_profiles = save_settings.call_args.args[0]["kite_profiles"]
        self.assertTrue(persisted_profiles["Shanti"]["NIFTY_INCOME_ENABLED"])
        self.assertTrue(persisted_profiles["Monika"]["NIFTY_INCOME_ENABLED"])

    def test_nifty_income_tab_visibility_follows_profile_permission(self):
        profiles = {
            name: app.blank_kite_profile(name)
            for name in app.KITE_PROFILE_NAMES
        }
        with patch.object(app, "load_kite_profiles", return_value=profiles):
            shanti_html = app.render_page(
                app.PageState(active_tab="kite-setup", kite_profile="Shanti")
            ).decode("utf-8")
            monika_html = app.render_page(
                app.PageState(active_tab="kite-setup", kite_profile="Monika")
            ).decode("utf-8")

        self.assertNotIn('data-tab="nifty-income"', shanti_html)
        self.assertIn('data-tab="nifty-income"', monika_html)
        self.assertIn("Enable Nifty Income tab", monika_html)

    def test_manual_nifty_pair_is_blocked_when_profile_permission_is_disabled(self):
        with (
            patch.object(app, "kite_profile_nifty_income_enabled", return_value=False),
            patch.object(app, "selected_kite_profile_name", return_value="Shanti"),
            patch.object(app, "nifty_income_manual_pair_snapshot") as snapshot,
        ):
            with self.assertRaisesRegex(PermissionError, "disabled for Kite profile Shanti"):
                app.place_nifty_income_manual_pair(5.5, 5.5, 1)

        snapshot.assert_not_called()

    def test_nifty_scheduler_is_skipped_when_profile_permission_is_disabled(self):
        with (
            patch.object(app, "kite_profile_nifty_income_enabled", return_value=False),
            patch.object(app, "nifty_income_config") as config,
        ):
            result = app.run_nifty_income_entry_job(
                app.datetime(2026, 6, 19, 15, 16, tzinfo=app.INDIA_TIME_ZONE)
            )

        self.assertIsNone(result)
        config.assert_not_called()

    def sell_pe_position(self, **overrides):
        position = {
            "tradingsymbol": "NTPC26JUN310PE",
            "exchange": "NFO",
            "quantity": -1500,
            "average_price": 10.0,
            "ltp": 8.0,
            "product": "NRML",
            "assignment_allowed": False,
        }
        position.update(overrides)
        return position

    def test_sell_pe_profit_capture_generates_profit_book_exit(self):
        result = app.evaluate_sell_pe_exit(
            self.sell_pe_position(ltp=5),
            {"stock_cmp": 350, "strike": 310},
            500000,
        )
        self.assertTrue(result["should_exit"])
        self.assertEqual(result["action"], "BUY_TO_CLOSE")
        self.assertEqual(result["exit_status"], "PROFIT_BOOK")

    def test_sell_pe_two_times_premium_generates_hard_loss_exit(self):
        result = app.evaluate_sell_pe_exit(
            self.sell_pe_position(ltp=20),
            {"stock_cmp": 350, "strike": 310},
            500000,
        )
        self.assertTrue(result["should_exit"])
        self.assertEqual(result["exit_status"], "HARD_LOSS_EXIT")

    def test_sell_pe_strike_breach_exits_without_assignment_plan(self):
        result = app.evaluate_sell_pe_exit(
            self.sell_pe_position(),
            {"stock_cmp": 309, "strike": 310},
            500000,
        )
        self.assertTrue(result["should_exit"])
        self.assertEqual(result["exit_status"], "ITM_EXIT")

    def test_sell_pe_near_strike_and_expanding_exits(self):
        result = app.evaluate_sell_pe_exit(
            self.sell_pe_position(ltp=16),
            {"stock_cmp": 315, "strike": 310},
            500000,
        )
        self.assertTrue(result["should_exit"])
        self.assertEqual(result["exit_status"], "NEAR_STRIKE_EXIT")

    def test_sell_pe_insufficient_cash_exits_before_other_rules(self):
        result = app.evaluate_sell_pe_exit(
            self.sell_pe_position(),
            {"stock_cmp": 350, "strike": 310},
            300000,
        )
        self.assertEqual(result["required_cash"], 418500)
        self.assertFalse(result["cash_covered"])
        self.assertTrue(result["should_exit"])
        self.assertEqual(result["exit_status"], "CASH_RISK_EXIT")

    def test_sell_pe_safe_buy_close_uses_best_ask(self):
        evaluation = app.evaluate_sell_pe_exit(
            self.sell_pe_position(ltp=20),
            {"stock_cmp": 350, "strike": 310},
            500000,
        )
        order = app.generate_pe_buy_to_close_order(
            self.sell_pe_position(ltp=20),
            {
                "last_price": 20,
                "depth": {
                    "buy": [{"price": 19.8}],
                    "sell": [{"price": 20.1}],
                },
            },
            evaluation,
        )
        self.assertEqual(order["transaction_type"], "BUY")
        self.assertEqual(order["price"], 20.15)
        self.assertEqual(order["exit_status"], "HARD_LOSS_EXIT")

    def test_index_pe_is_left_to_nifty_pair_exit_monitor(self):
        result = app.evaluate_sell_pe_exit(
            self.sell_pe_position(
                tradingsymbol="NIFTY26JUN23000PE",
                quantity=-65,
                ltp=25,
            ),
            {"stock_cmp": 22900, "strike": 23000},
            100000,
        )
        self.assertFalse(result["should_exit"])
        self.assertEqual(result["exit_status"], "NOT_SELL_PE")
        self.assertIn("NIFTY pair exit monitor", result["reason"])

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
            patch.object(app, "build_intraday_loss_limit_close_orders", return_value=([], [])),
            patch.object(app, "build_intraday_pe_risk_exit_orders", return_value=([], [])),
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

    def test_income_growth_gpt_csv_save_loads_research(self):
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
        research_rows = [{"symbol": "PFC26JUN400PE"}]
        with (
            patch.object(app, "parse_csv_text", return_value=parsed_rows),
            patch.object(app, "validate_kite_order_rows"),
            patch.object(app, "save_today_csv_text", return_value=("16Jun2026.csv", "Saved CSV.")),
            patch.object(app, "activate_today_csv_path") as activate_path,
            patch.object(app, "research_csv_symbols", return_value=research_rows) as research,
        ):
            outcome = app.save_income_growth_gpt_csv_for_research(csv_text)

        self.assertEqual(outcome["csv_path"], "16Jun2026.csv")
        self.assertEqual(outcome["order_count"], 1)
        self.assertEqual(outcome["research_rows"], research_rows)
        self.assertEqual(outcome["research_count"], 1)
        activate_path.assert_called_once_with("16Jun2026.csv")
        research.assert_called_once()

    def test_income_growth_outcome_links_to_gpt_and_research(self):
        state = app.PageState(
            active_tab="income-growth",
            income_growth_saved_csv_path="C:/income/16Jun2026.csv",
            income_growth_outcome_message="Saved CSV. Loaded Research comparison for 1 symbol(s).",
            income_growth_research_count=1,
            income_growth_gpt_response_id="resp_123",
            income_growth_gpt_csv="exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity\n",
            income_growth_gpt_output="exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity\n",
        )

        html = app.render_income_growth_panel(state)

        self.assertIn("Outcome", html)
        self.assertIn("16Jun2026.csv", html)
        self.assertIn("Open GPT response", html)
        self.assertIn('data-tab-target="research"', html)

    def test_best_sell_candidate_csv_combines_top_ce_and_pe(self):
        ce_top = [
            {
                "option_symbol": "PFC26JUN480CE",
                "active_lot_size": 1300,
                "lots_to_sell": 2,
                "sell_limit_price": 3.6,
            },
            {
                "option_symbol": "HAVELLS26JUN1300CE",
                "active_lot_size": 500,
                "lots_to_sell": 1,
                "sell_limit_price": 14.2,
            },
        ]
        pe_top = [
            {
                "option_symbol": "PFC26JUN400PE",
                "lot_size": 1300,
                "sell_limit_price": 2.8,
            },
            {
                "option_symbol": "CAMS26JUN760PE",
                "lot_size": 750,
                "sell_limit_price": 8.3,
            },
        ]
        with (
            patch.object(app, "ce_sell_dashboard", return_value=(ce_top, [], [])),
            patch.object(app, "income_dashboard_snapshot", return_value={"pe_top": pe_top}),
        ):
            csv_text, returned_ce, returned_pe = app.best_sell_candidate_csv(True)

        rows = app.parse_csv_text(csv_text)
        self.assertEqual(returned_ce, ce_top)
        self.assertEqual(returned_pe, pe_top)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["tradingsymbol"], "PFC26JUN480CE")
        self.assertEqual(rows[0]["quantity"], "1300")
        self.assertEqual(rows[2]["tradingsymbol"], "PFC26JUN400PE")
        self.assertEqual(rows[2]["quantity"], "1300")
        self.assertEqual(rows[2]["transaction_type"], "SELL")

    def test_research_panel_has_best_sell_csv_button(self):
        state = app.PageState(active_tab="research")

        html = app.render_research_panel(state)

        self.assertIn("/research/best-sells", html)
        self.assertIn("Generate Best 3 PE + 3 CE SELL CSV", html)
        self.assertIn("/research/gpt-best-sells", html)
        self.assertIn("Generate with GPT + Current Positions", html)

    def test_research_gpt_prompt_contains_current_position_risk_context(self):
        positions = [
            {
                "symbol": "BAJFINANCE26JUN1000CE",
                "quantity": -750,
                "average_price": 8.8,
                "ltp": 12.0,
                "pnl": -2400,
                "return_pct": -2.5,
                "captured_pct": -36.36,
                "remaining_premium": 9000,
                "sell_pop": 72,
                "otm_distance": 4.5,
                "strategy_strength": "RED_AVOID",
                "deployed": 96000,
                "existing_buy_order": {"order_id": "123"},
                "pe_exit_status": "REVIEW",
                "pe_exit_reason": "Premium expanded.",
            }
        ]
        prompt = app.research_gpt_prompt_with_current_positions(
            "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity\n",
            positions,
            {"count": 1, "total_pnl": -2400, "total_deployed": 96000},
            date(2026, 6, 24),
        )

        self.assertIn("These are current positions", prompt)
        self.assertIn("BAJFINANCE26JUN1000CE", prompt)
        self.assertIn("close_buy_order_pending", prompt)
        self.assertIn("YES", prompt)
        self.assertIn("Do not generate an order for an exact option symbol", prompt)
        self.assertIn("Return at most 3 CE SELL and 3 PE SELL", prompt)
        self.assertIn("Mandatory expiry for every new NFO option order: 28 Jul 2026", prompt)
        self.assertIn("Tradingsymbols must use 26JUL", prompt)
        self.assertIn("5 or fewer", prompt)

    def test_research_monthly_expiry_rolls_to_july_when_under_five_trading_days(self):
        policy = app.research_monthly_expiry_policy(date(2026, 6, 24))

        self.assertEqual(policy["front_expiry"], date(2026, 6, 30))
        self.assertEqual(policy["front_trading_days"], 4)
        self.assertTrue(policy["rolled_to_next_month"])
        self.assertEqual(policy["target_expiry"], date(2026, 7, 28))
        self.assertEqual(policy["target_month_code"], "26JUL")

    def test_research_monthly_expiry_rolls_at_five_trading_days(self):
        policy = app.research_monthly_expiry_policy(date(2026, 6, 23))

        self.assertEqual(policy["front_trading_days"], 5)
        self.assertTrue(policy["rolled_to_next_month"])
        self.assertEqual(policy["target_expiry"], date(2026, 7, 28))
        self.assertEqual(policy["target_month_code"], "26JUL")

    def test_monthly_expiry_policy_keeps_front_month_above_five_days(self):
        selected, rolled_from, remaining = app.income_selected_expiry(
            [date(2026, 6, 30), date(2026, 7, 28)],
            date(2026, 6, 22),
        )

        self.assertEqual(selected, date(2026, 6, 30))
        self.assertIsNone(rolled_from)
        self.assertIsNone(remaining)

    def test_monthly_expiry_policy_rolls_to_next_month_at_five_days(self):
        selected, rolled_from, remaining = app.income_selected_expiry(
            [date(2026, 6, 30), date(2026, 7, 28)],
            date(2026, 6, 23),
        )

        self.assertEqual(selected, date(2026, 7, 28))
        self.assertEqual(rolled_from, date(2026, 6, 30))
        self.assertEqual(remaining, 5)

    def test_monthly_expiry_policy_blocks_when_next_month_is_unavailable(self):
        with self.assertRaisesRegex(ValueError, "next monthly contract is not available"):
            app.income_selected_expiry(
                [date(2026, 6, 30)],
                date(2026, 6, 23),
            )

    def test_next_monthly_pe_candidate_uses_july_at_five_trading_days(self):
        kite = object()
        instruments = [
            {
                "name": "PFC",
                "instrument_type": "PE",
                "expiry": date(2026, 6, 30),
                "strike": 900,
                "tradingsymbol": "PFC26JUN900PE",
                "lot_size": 1300,
            },
            {
                "name": "PFC",
                "instrument_type": "PE",
                "expiry": date(2026, 7, 28),
                "strike": 900,
                "tradingsymbol": "PFC26JUL900PE",
                "lot_size": 1300,
            },
        ]
        with (
            patch.object(
                app,
                "cached_kite_quote",
                return_value={"NSE:PFC": {"last_price": 1000}},
            ),
            patch.object(app, "cached_kite_instruments", return_value=instruments),
        ):
            result = app.next_monthly_pe_candidate(
                kite,
                "PFC",
                today=date(2026, 6, 23),
            )

        self.assertEqual(result["symbol"], "PFC26JUL900PE")
        self.assertEqual(result["expiry"], date(2026, 7, 28))
        self.assertEqual(result["rolled_from_expiry"], date(2026, 6, 30))
        self.assertEqual(result["rolled_from_trading_days"], 5)

    def test_next_monthly_ce_candidate_uses_july_at_five_trading_days(self):
        kite = object()
        instruments = [
            {
                "name": "PFC",
                "instrument_type": "CE",
                "expiry": date(2026, 6, 30),
                "strike": 1100,
                "tradingsymbol": "PFC26JUN1100CE",
                "lot_size": 1300,
            },
            {
                "name": "PFC",
                "instrument_type": "CE",
                "expiry": date(2026, 7, 28),
                "strike": 1100,
                "tradingsymbol": "PFC26JUL1100CE",
                "lot_size": 1300,
            },
        ]
        with (
            patch.object(
                app,
                "cached_kite_quote",
                return_value={"NSE:PFC": {"last_price": 1000}},
            ),
            patch.object(app, "cached_kite_instruments", return_value=instruments),
        ):
            result = app.next_monthly_ce_candidate(
                kite,
                "PFC",
                today=date(2026, 6, 23),
            )

        self.assertEqual(result["symbol"], "PFC26JUL1100CE")
        self.assertEqual(result["expiry"], date(2026, 7, 28))
        self.assertEqual(result["rolled_from_expiry"], date(2026, 6, 30))
        self.assertEqual(result["rolled_from_trading_days"], 5)

    def test_trading_ce_scan_replaces_stale_front_month_candidate_at_five_days(self):
        kite = object()
        growth_rows = [
            {
                "symbol": "PFC",
                "candidate_ce": "PFC26JUN110CE",
                "quantity": 1300,
                "cmp": 100,
                "core": "N",
                "input_month": 0,
                "input_1w": 0,
                "input_today": 0,
                "avg_price": 80,
            }
        ]
        instruments = [
            {
                "name": "PFC",
                "instrument_type": "CE",
                "expiry": date(2026, 6, 30),
                "strike": 110,
                "tradingsymbol": "PFC26JUN110CE",
                "lot_size": 1300,
            },
            {
                "name": "PFC",
                "instrument_type": "CE",
                "expiry": date(2026, 7, 28),
                "strike": 110,
                "tradingsymbol": "PFC26JUL110CE",
                "lot_size": 1300,
            },
        ]
        settings = {
            **app.DEFAULT_CE_SELL_SETTINGS,
            "default_otm_percent": 10,
            "core_otm_add_percent": 0,
            "price_markup_percent": 20,
        }
        with (
            patch.object(
                app,
                "kite_orders",
                Namespace(kite_client=lambda: kite),
            ),
            patch.object(app, "app_now", return_value=app.datetime(2026, 6, 23, 10, 0)),
            patch.object(app, "income_growth_candidates", return_value=(growth_rows, {})),
            patch.object(app, "load_ce_sell_settings", return_value=settings),
            patch.object(app, "active_position_underlyings", return_value=set()),
            patch.object(app, "cached_kite_instruments", return_value=instruments),
            patch.object(app, "classify_pe_event_risk", return_value=("GREEN", "No event")),
            patch.object(
                app,
                "ce_corporate_action_from_news",
                return_value={
                    "corporate_action_risk": "GREEN",
                    "corporate_action_type": "NONE",
                    "corporate_action_detail": "",
                },
            ),
            patch.object(
                app,
                "ce_macro_tape_snapshot",
                return_value={"risk": "GREEN", "detail": "Stable"},
            ),
            patch.object(app, "ce_macro_beta_buffer", return_value=0),
            patch.object(
                app,
                "cached_kite_quote",
                return_value={"NFO:PFC26JUL110CE": {"last_price": 5}},
            ),
            patch.object(
                app,
                "option_analytics_for_symbol",
                return_value={"delta": 0.1, "sell_pop": 90, "iv_percent": 25},
            ),
            patch.object(
                app,
                "rank_ce_sell_candidates",
                side_effect=lambda candidates, _settings: (candidates, [], []),
            ),
        ):
            top, _, _ = app.build_live_ce_sell_rankings()

        self.assertEqual(top[0]["option_symbol"], "PFC26JUL110CE")
        self.assertEqual(top[0]["expiry"], "2026-07-28")
        self.assertEqual(top[0]["rolled_from_expiry"], date(2026, 6, 30))
        self.assertEqual(top[0]["rolled_from_trading_days"], 5)

    def test_generate_research_csv_with_current_positions_calls_gpt_with_positions(self):
        positions = [{"symbol": "PFC26JUN400PE", "quantity": -1300, "pnl": 500}]
        summary = {"count": 1, "total_pnl": 500}
        candidate_csv = (
            "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity\n"
            "NFO,HAVELLS26JUN1300CE,500,SELL,NRML,LIMIT,10,DAY\n"
        )
        final_csv = (
            "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity\n"
            "NFO,HAVELLS26JUL1300CE,500,SELL,NRML,LIMIT,10,DAY\n"
        )
        with (
            patch.object(app, "positions_research", return_value=(positions, summary)),
            patch.object(app, "best_sell_candidate_csv", return_value=(candidate_csv, [{"symbol": "HAVELLS"}], [])),
            patch.object(app, "generate_csv_with_openai", return_value=(final_csv, final_csv, "resp_1")) as generate,
        ):
            result = app.generate_research_csv_with_current_positions(
                "gpt-test",
                "system",
                date(2026, 6, 24),
            )

        sent_prompt = generate.call_args.args[0]
        self.assertIn("PFC26JUN400PE", sent_prompt)
        self.assertIn("HAVELLS26JUN1300CE", sent_prompt)
        self.assertIn("26JUL", sent_prompt)
        self.assertEqual(result["csv_text"], final_csv)
        self.assertEqual(result["position_summary"], summary)
        self.assertEqual(result["expiry_policy"]["target_month_name"], "July 2026")

    def test_research_gpt_retries_once_when_front_month_is_returned(self):
        positions = [{"symbol": "PFC26JUN400PE", "quantity": -1300, "pnl": 500}]
        summary = {"count": 1, "total_pnl": 500}
        candidate_csv = (
            "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity\n"
            "NFO,HAVELLS26JUN1300CE,500,SELL,NRML,LIMIT,10,DAY\n"
        )
        invalid_csv = (
            "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity\n"
            "NFO,HAVELLS26JUN1300CE,500,SELL,NRML,LIMIT,10,DAY\n"
        )
        repaired_csv = (
            "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity\n"
            "NFO,HAVELLS26JUL1300CE,500,SELL,NRML,LIMIT,10,DAY\n"
        )
        with (
            patch.object(app, "positions_research", return_value=(positions, summary)),
            patch.object(app, "best_sell_candidate_csv", return_value=(candidate_csv, [{"symbol": "HAVELLS"}], [])),
            patch.object(
                app,
                "generate_csv_with_openai",
                side_effect=[
                    (invalid_csv, invalid_csv, "resp_1"),
                    (repaired_csv, repaired_csv, "resp_2"),
                ],
            ) as generate,
        ):
            result = app.generate_research_csv_with_current_positions(
                "gpt-test",
                "system",
                date(2026, 6, 24),
            )

        self.assertEqual(generate.call_count, 2)
        self.assertIn("EXPIRY CORRECTION REQUIRED", generate.call_args_list[1].args[0])
        self.assertIn("26JUL", generate.call_args_list[1].args[0])
        self.assertEqual(result["csv_text"], repaired_csv)
        self.assertEqual(result["response_id"], "resp_2")

    def test_research_panel_displays_positions_sent_to_gpt_and_response(self):
        state = app.PageState(
            active_tab="research",
            research_positions_rows=[
                {
                    "symbol": "PFC26JUN400PE",
                    "quantity": -1300,
                    "average_price": 3.7,
                    "ltp": 2.1,
                    "pnl": 2080,
                    "captured_pct": 43.2,
                    "sell_pop": 88,
                    "otm_distance": 9,
                    "strategy_strength": "GREEN",
                }
            ],
            research_positions_summary={
                "count": 1,
                "total_pnl": 2080,
                "total_deployed": 80000,
                "return_pct": 2.6,
            },
            research_gpt_output="exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity",
            research_gpt_response_id="resp_1",
        )

        html = app.render_research_panel(state)

        self.assertIn("Current Positions Sent To GPT", html)
        self.assertIn("PFC26JUN400PE", html)
        self.assertIn("GPT Portfolio-Aware Outcome", html)
        self.assertIn("resp_1", html)

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

        def build_orders(_kite, discount):
            built_states.append(discount)
            return [order], []

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
            patch.object(app, "build_intraday_loss_limit_close_orders", return_value=([], [])),
            patch.object(app, "build_intraday_pe_risk_exit_orders", return_value=([], [])),
            patch.object(app, "build_missing_option_close_orders", side_effect=build_orders),
            patch.object(app, "execute_position_buy_orders", return_value=([order], [result])),
        ):
            first = app.run_intraday_position_close_job(run_at)
            second = app.run_intraday_position_close_job(run_at)

        self.assertEqual(first["status"], "PLACED")
        self.assertEqual(first["run_count_today"], 1)
        self.assertEqual(built_states[0], 35.0)
        self.assertIn("35% below LTP", first["message"])
        self.assertIsNone(second)

    def test_missing_close_orders_cover_short_stock_and_long_nifty_options(self):
        positions = [
            {
                "exchange": "NFO",
                "tradingsymbol": "HAVELLS26JUL1300CE",
                "quantity": -500,
                "product": "NRML",
                "average_price": 10.0,
                "ltp": 8.0,
            },
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTY2672122500PE",
                "quantity": 65,
                "product": "NRML",
                "average_price": 18.45,
                "ltp": 18.20,
            },
        ]
        with (
            patch.object(app, "open_option_positions", return_value=positions),
            patch.object(app, "refresh_option_positions_with_live_ltp", return_value=positions),
            patch.object(app, "open_option_close_orders_by_symbol_side", return_value={}),
        ):
            orders, evaluations = app.build_missing_option_close_orders(
                object(),
                20,
            )

        self.assertEqual(len(orders), 2)
        short_close, long_close = orders
        self.assertEqual(short_close["transaction_type"], "BUY")
        self.assertEqual(short_close["price"], 6.4)
        self.assertEqual(short_close["price_basis"], "min_ltp_average_price")
        self.assertEqual(long_close["tradingsymbol"], "NIFTY2672122500PE")
        self.assertEqual(long_close["transaction_type"], "SELL")
        self.assertEqual(long_close["quantity"], 65)
        self.assertEqual(long_close["price"], 22.15)
        self.assertEqual(long_close["price_basis"], "max_ltp_average_price")
        self.assertIn("20% above max", long_close["risk_note"])
        self.assertEqual(
            [row["action"] for row in evaluations],
            ["PLACE_BUY_CLOSE", "PLACE_SELL_CLOSE"],
        )

    def test_missing_close_orders_apply_lower_basis_to_nifty_short_pe_and_ce(self):
        positions = [
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTY2672122600PE",
                "quantity": -65,
                "product": "NRML",
                "average_price": 20.35,
                "ltp": 20.35,
            },
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTY2672125100CE",
                "quantity": -65,
                "product": "NRML",
                "average_price": 49.10,
                "ltp": 44.10,
            },
        ]
        with (
            patch.object(app, "open_option_positions", return_value=positions),
            patch.object(
                app,
                "refresh_option_positions_with_live_ltp",
                return_value=positions,
            ),
            patch.object(app, "open_option_close_orders_by_symbol_side", return_value={}),
        ):
            orders, evaluations = app.build_missing_option_close_orders(object(), 20)

        self.assertEqual(len(orders), 2)
        self.assertEqual([row["transaction_type"] for row in orders], ["BUY", "BUY"])
        self.assertEqual([row["quantity"] for row in orders], [65, 65])
        self.assertEqual(orders[0]["price"], 16.25)
        self.assertEqual(orders[1]["price"], 35.25)
        self.assertEqual(
            [row["price_basis"] for row in orders],
            ["min_ltp_average_price", "min_ltp_average_price"],
        )
        self.assertEqual(
            [row["price_basis"] for row in evaluations],
            [20.35, 44.10],
        )

    def test_open_option_positions_includes_stock_and_weekly_nifty_options(self):
        positions = [
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTY2672122600PE",
                "quantity": -65,
                "product": "NRML",
                "average_price": 20.35,
                "last_price": 20.35,
                "pnl": 0,
            },
            {
                "exchange": "NFO",
                "tradingsymbol": "HAVELLS26JUL1300CE",
                "quantity": -500,
                "product": "NRML",
                "average_price": 10,
                "last_price": 8,
                "pnl": 1000,
            },
            {
                "exchange": "NSE",
                "tradingsymbol": "HAVELLS",
                "quantity": 100,
                "product": "CNC",
                "average_price": 1000,
                "last_price": 1100,
                "pnl": 10000,
            },
        ]
        kite = Namespace(positions=lambda: {"net": positions})
        with patch.object(
            app,
            "kite_orders",
            Namespace(kite_client=lambda: kite),
        ):
            result = app.open_option_positions(use_cache=False)

        self.assertEqual(
            [row["tradingsymbol"] for row in result],
            ["NIFTY2672122600PE", "HAVELLS26JUL1300CE"],
        )

    def test_positions_research_keeps_weekly_nifty_when_analytics_is_unavailable(self):
        position = {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY2672122600PE",
            "quantity": -65,
            "product": "NRML",
            "average_price": 20.35,
            "ltp": 20.35,
            "pnl": 0,
        }
        existing = {
            "order_id": "NIFTY-BUY-1",
            "quantity": 65,
            "price": 16.25,
        }
        with (
            patch.object(app, "open_option_positions", return_value=[position]),
            patch.object(
                app,
                "refresh_option_positions_with_live_ltp",
                return_value=[position],
            ),
            patch.object(app, "kite_available_cash", return_value=1000000),
            patch.object(
                app,
                "open_option_close_orders_by_symbol_side",
                return_value={("NIFTY2672122600PE", "BUY"): existing},
            ),
            patch.object(
                app,
                "option_analytics_for_symbol",
                side_effect=ValueError("Weekly index analytics unavailable"),
            ),
            patch.object(app, "margin_required_for_position", return_value=50000),
            patch.object(
                app,
                "kite_orders",
                Namespace(kite_client=lambda: object()),
            ),
        ):
            rows, summary = app.positions_research(True)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "NIFTY2672122600PE")
        self.assertEqual(rows[0]["close_side"], "BUY")
        self.assertEqual(rows[0]["existing_close_order"], existing)
        self.assertEqual(rows[0]["deployed"], 50000)
        self.assertIn("Weekly index analytics unavailable", rows[0]["error"])
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["total_deployed"], 50000)

    def test_missing_close_order_requires_matching_transaction_side(self):
        position = {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY2672122500PE",
            "quantity": 65,
            "product": "NRML",
            "average_price": 18.45,
            "ltp": 18.20,
        }
        with (
            patch.object(app, "open_option_positions", return_value=[position]),
            patch.object(
                app,
                "refresh_option_positions_with_live_ltp",
                return_value=[position],
            ),
            patch.object(
                app,
                "open_option_close_orders_by_symbol_side",
                return_value={
                    ("NIFTY2672122500PE", "BUY"): {"order_id": "wrong-side"}
                },
            ),
        ):
            orders, evaluations = app.build_missing_option_close_orders(object(), 20)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["transaction_type"], "SELL")
        self.assertEqual(evaluations[0]["action"], "PLACE_SELL_CLOSE")

        with (
            patch.object(app, "open_option_positions", return_value=[position]),
            patch.object(
                app,
                "refresh_option_positions_with_live_ltp",
                return_value=[position],
            ),
            patch.object(
                app,
                "open_option_close_orders_by_symbol_side",
                return_value={
                    ("NIFTY2672122500PE", "SELL"): {
                        "order_id": "correct-side",
                        "price": 22.15,
                    }
                },
            ),
        ):
            orders, evaluations = app.build_missing_option_close_orders(object(), 20)

        self.assertEqual(orders, [])
        self.assertEqual(evaluations[0]["action"], "SKIP_EXISTING_CLOSE_ORDER")

    def test_long_nifty_close_sell_is_submitted_with_clean_kite_payload(self):
        order = {
            "variety": "regular",
            "exchange": "NFO",
            "tradingsymbol": "NIFTY2672122500PE",
            "transaction_type": "SELL",
            "quantity": 65,
            "product": "NRML",
            "order_type": "LIMIT",
            "price": 22.15,
            "validity": "DAY",
            "tag": "AUTO_CLOSE",
            "average_price": 18.45,
            "ltp": 18.20,
            "risk_note": "AUTO CLOSE COVER",
            "skip_if_close_order_exists": True,
        }
        with (
            patch.dict(app.os.environ, {"KITE_CONFIRM_LIVE_ORDER": "YES"}),
            patch.object(app.kite_buy_positions, "kite_client", return_value=object()),
            patch.object(app, "open_option_close_orders_by_symbol_side", return_value={}),
            patch.object(
                app.kite_buy_positions,
                "place_order",
                return_value="NIFTY-CLOSE-1",
            ) as place,
        ):
            submitted, results = app.execute_position_buy_orders(
                [order],
                {0},
                False,
                True,
            )

        payload = place.call_args.args[1]
        self.assertEqual(payload["transaction_type"], "SELL")
        self.assertEqual(payload["quantity"], 65)
        self.assertEqual(payload["price"], 22.15)
        self.assertNotIn("risk_note", payload)
        self.assertNotIn("average_price", payload)
        self.assertEqual(submitted, [order])
        self.assertEqual(results[0]["status"], "LIVE_SENT")
        self.assertEqual(results[0]["order_id"], "NIFTY-CLOSE-1")

    def test_intraday_loss_limit_builds_buy_at_ten_percent_below_fresh_ltp(self):
        positions = [
            {
                "exchange": "NFO",
                "tradingsymbol": "HAVELLS26JUN1300CE",
                "quantity": -500,
                "product": "NRML",
                "average_price": 10.0,
                "ltp": 20.0,
            },
            {
                "exchange": "NFO",
                "tradingsymbol": "PFC26JUN400PE",
                "quantity": -1300,
                "product": "NRML",
                "average_price": 10.0,
                "ltp": 19.95,
            },
        ]
        with (
            patch.object(app, "open_option_positions", return_value=positions),
            patch.object(app, "refresh_option_positions_with_live_ltp", return_value=positions),
        ):
            orders, evaluations = app.build_intraday_loss_limit_close_orders(object())

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["tradingsymbol"], "HAVELLS26JUN1300CE")
        self.assertEqual(orders[0]["transaction_type"], "BUY")
        self.assertEqual(orders[0]["price"], 18.0)
        self.assertEqual(orders[0]["tag"], "LOSS100_EXIT")
        self.assertEqual(orders[0]["price_basis"], "fresh_LTP_loss_limit")
        self.assertIn("LOSS LIMIT", orders[0]["risk_note"])
        self.assertTrue(evaluations[0]["triggered"])
        self.assertFalse(evaluations[1]["triggered"])

    def test_intraday_loss_limit_execution_modifies_existing_buy_and_audits_note(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "HAVELLS26JUN1300CE",
            "transaction_type": "BUY",
            "quantity": 500,
            "product": "NRML",
            "order_type": "LIMIT",
            "price": 18.0,
            "validity": "DAY",
            "risk_note": "LOSS LIMIT: premium loss reached 100%.",
        }
        with (
            patch.dict(app.os.environ, {"KITE_CONFIRM_LIVE_ORDER": "YES"}),
            patch.object(app.kite_buy_positions, "kite_client", return_value=object()),
            patch.object(app.kite_buy_positions, "modify_or_place_order", return_value="OID-1") as modify,
        ):
            _, results = app.execute_position_buy_orders([order], {0}, False, False)

        modify.assert_called_once()
        self.assertEqual(results[0]["status"], "LIVE_SENT")
        self.assertIn("LOSS LIMIT", results[0]["detail"])

    def test_intraday_strict_pe_scan_skips_profitable_next_month_position_with_existing_close(self):
        position = {
            "exchange": "NFO",
            "tradingsymbol": "NAUKRI26JUL940PE",
            "quantity": -550,
            "product": "NRML",
            "average_price": 20.0,
            "ltp": 10.0,
        }
        option_quote = {"last_price": 10.0}
        stock_quote = {"last_price": 1100.0}
        existing_order = {
            "order_id": "260624150668758",
            "tradingsymbol": "NAUKRI26JUL940PE",
            "transaction_type": "BUY",
            "status": "OPEN",
            "price": 11.2,
            "pending_quantity": 550,
            "quantity": 550,
        }
        with (
            patch.object(
                app,
                "cached_kite_quote",
                return_value={
                    "NFO:NAUKRI26JUL940PE": option_quote,
                    "NSE:NAUKRI": stock_quote,
                },
            ),
            patch.object(app, "kite_available_cash", return_value=1000000),
            patch.object(
                app,
                "open_option_buy_orders_by_symbol",
                return_value={"NAUKRI26JUL940PE": existing_order},
            ),
            patch.object(app, "generate_pe_buy_to_close_order") as generate_order,
        ):
            orders, evaluations = app.build_intraday_pe_risk_exit_orders(
                object(),
                [position],
            )

        self.assertEqual(orders, [])
        self.assertEqual(evaluations[0]["exit_status"], "PROFIT_BOOK")
        self.assertEqual(
            evaluations[0]["scheduler_action"],
            "SKIP_EXISTING_CLOSE_ORDER",
        )
        self.assertEqual(
            evaluations[0]["existing_close_order_id"],
            "260624150668758",
        )
        self.assertEqual(evaluations[0]["existing_close_price"], 11.2)
        generate_order.assert_not_called()

    def test_strict_pe_execution_preserves_close_order_created_after_scan(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "NAUKRI26JUL940PE",
            "transaction_type": "BUY",
            "quantity": 550,
            "product": "NRML",
            "order_type": "LIMIT",
            "price": 14.45,
            "validity": "DAY",
            "skip_if_close_order_exists": True,
        }
        existing_order = {
            "order_id": "260624150668758",
            "price": 11.2,
            "pending_quantity": 550,
        }
        with (
            patch.dict(app.os.environ, {"KITE_CONFIRM_LIVE_ORDER": "YES"}),
            patch.object(app.kite_buy_positions, "kite_client", return_value=object()),
            patch.object(
                app,
                "open_option_close_orders_by_symbol_side",
                return_value={("NAUKRI26JUL940PE", "BUY"): existing_order},
            ),
            patch.object(app.kite_buy_positions, "place_order") as place,
            patch.object(app.kite_buy_positions, "modify_or_place_order") as modify,
        ):
            submitted, results = app.execute_position_buy_orders(
                [order],
                {0},
                False,
                True,
            )

        self.assertEqual(submitted, [])
        self.assertEqual(results[0]["status"], "SKIPPED_EXISTING")
        self.assertIn("11.20", results[0]["detail"])
        place.assert_not_called()
        modify.assert_not_called()

    def test_intraday_job_prioritises_loss_limit_override(self):
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

        loss_order = {
            "tradingsymbol": "CAMS26JUN760PE",
            "quantity": 750,
            "price": 27.0,
            "price_basis": "fresh_LTP_loss_limit",
            "discount_percent": 10,
            "risk_note": "LOSS LIMIT: premium loss reached 100%.",
        }
        run_at = app.datetime(2026, 6, 12, 10, 0, tzinfo=app.INDIA_TIME_ZONE)
        execute_calls = []

        def execute(orders, selected, dry_run, keep_existing):
            execute_calls.append((orders, keep_existing))
            return orders, [{"tradingsymbol": orders[0]["tradingsymbol"], "status": "LIVE_SENT"}]

        with (
            patch.object(app, "intraday_position_close_schedule_state", side_effect=read_schedule),
            patch.object(app, "save_intraday_position_close_schedule_state", side_effect=save_schedule),
            patch.object(app, "selected_kite_profile_name", return_value="Shanti"),
            patch.object(app, "load_kite_profiles", return_value={"Shanti": app.blank_kite_profile()}),
            patch.object(app, "apply_kite_profile_to_env"),
            patch.object(app, "kite_setup_issue", return_value=""),
            patch.object(app.kite_buy_positions, "kite_client", return_value=object()),
            patch.object(app, "verify_scheduled_position_market_open", return_value=(True, "Market open.")),
            patch.object(app, "build_intraday_loss_limit_close_orders", return_value=([loss_order], [{"triggered": True}])),
            patch.object(app, "build_intraday_pe_risk_exit_orders", return_value=([], [])),
            patch.object(app, "build_missing_option_close_orders", return_value=([], [])),
            patch.object(app, "execute_position_buy_orders", side_effect=execute),
        ):
            result = app.run_intraday_position_close_job(run_at)

        self.assertEqual(result["status"], "PLACED")
        self.assertEqual(execute_calls[0][1], False)
        self.assertIn("100% loss-limit overrides: 1", result["message"])
        self.assertIn("10% below fresh_LTP_loss_limit", result["message"])
        self.assertEqual(result["loss_limit_evaluations"], [{"triggered": True}])

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
        with (
            patch.object(app, "scheduled_job_definitions", return_value=jobs),
            patch.object(app, "scheduler_master_state", return_value={"enabled": True}),
        ):
            stopped = app.update_scheduled_job_control("test-job", "stop", now)
            started = app.update_scheduled_job_control("test-job", "start", now)
            paused = app.update_scheduled_job_control("test-job", "pause-day", now)

        self.assertFalse(stopped["enabled"])
        self.assertTrue(started["enabled"])
        self.assertEqual(paused["status"], "PAUSED")
        self.assertTrue(app.scheduled_job_is_paused(paused, now))
        self.assertEqual(len(saved_updates), 3)

    def test_scheduler_pause_all_and_start_all_persist_every_job(self):
        states = {
            "job-a": {"enabled": True, "status": "WAITING"},
            "job-b": {"enabled": True, "status": "WAITING"},
        }
        master_updates = []

        def job_definition(key):
            return {
                "name": key,
                "purpose": "Test",
                "schedule": "Weekdays",
                "load": lambda key=key: dict(states[key]),
                "save": lambda key=key, **updates: states[key].update(updates) or dict(states[key]),
            }

        jobs = {key: job_definition(key) for key in states}

        def save_master(**updates):
            master_updates.append(dict(updates))
            return dict(updates)

        now = app.datetime(2026, 6, 18, 10, 0, tzinfo=app.INDIA_TIME_ZONE)
        with (
            patch.object(app, "scheduled_job_definitions", return_value=jobs),
            patch.object(app, "save_scheduler_master_state", side_effect=save_master),
        ):
            paused = app.update_all_scheduled_jobs("pause-all", now)
            started = app.update_all_scheduled_jobs("start-all", now)

        self.assertFalse(paused["enabled"])
        self.assertTrue(started["enabled"])
        self.assertTrue(all(state["enabled"] for state in states.values()))
        self.assertEqual(len(master_updates), 2)
        self.assertEqual(master_updates[0]["status"], "PAUSED")
        self.assertEqual(master_updates[1]["status"], "RUNNING")

    def test_scheduler_master_pause_blocks_manual_run(self):
        with patch.object(app, "scheduler_master_state", return_value={"enabled": False}):
            with self.assertRaisesRegex(RuntimeError, "Click Start All"):
                app.run_scheduled_job_now("position_close_open")

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
        with patch.object(
            app,
            "scheduler_master_state",
            return_value={"enabled": True, "status": "RUNNING", "message": "All jobs enabled."},
        ):
            output = app.render_scheduler_control_panel()

        self.assertIn("Scheduled Jobs Control", output)
        self.assertIn("Default Close Orders", output)
        self.assertIn("Income Growth GPT CSV", output)
        self.assertIn("Intraday Close-Order Guard", output)
        self.assertIn("Pause for 1 day", output)
        self.assertIn("Run now", output)
        self.assertIn("Pause All", output)
        self.assertIn("Start All", output)
        self.assertIn("/scheduler/pause-all", output)
        self.assertIn("/scheduler/start-all", output)

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
        self.assertIn("BUY at 27.5% below the lower of", output)
        self.assertIn("SELL at 27.5% above", output)

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
                return_value={
                    "NFO:PFC26JUN400PE": {
                        "last_price": 2.85,
                        "depth": {"buy": [{"price": 2.80}], "sell": [{"price": 2.90}]},
                    }
                },
            ),
        ):
            orders = app.build_orders([row], True, False)
        self.assertEqual(orders[0]["price"], 2.75)
        self.assertEqual(orders[0]["ltp"], 2.85)
        self.assertEqual(orders[0]["max_gain"], 3575.0)
        self.assertEqual(orders[0]["price_protection_status"], "ADJUSTED")

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
                return_value={
                    "NFO:PFC26JUN400PE": {
                        "last_price": 2.85,
                        "depth": {"buy": [{"price": 2.80}], "sell": [{"price": 2.90}]},
                    }
                },
            ),
        ):
            orders = app.build_orders([row], True, False)
        self.assertEqual(orders[0]["price"], 3.20)
        self.assertEqual(orders[0]["ltp"], 2.85)
        self.assertEqual(orders[0]["max_gain"], 4160.0)
        self.assertEqual(orders[0]["price_protection_status"], "OK")

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
            patch.object(app, "apply_nfo_option_price_protection", return_value=[built]),
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

    def test_sell_zero_price_uses_best_bid_inside_lpp(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY26JUN24000CE",
            "transaction_type": "SELL",
            "order_type": "LIMIT",
            "price": 0,
        }
        quote = {
            "last_price": 12.0,
            "depth": {"buy": [{"price": 11.80}], "sell": [{"price": 11.95}]},
        }
        result = app.validateOrderPriceWithinRange(order, quote)
        self.assertTrue(result["ok"])
        self.assertEqual(result["price"], 11.75)
        self.assertTrue(result["auto_adjusted"])

    def test_buy_zero_price_uses_best_ask_inside_lpp(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY26JUN24000CE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "price": 0,
        }
        quote = {
            "last_price": 12.0,
            "depth": {"buy": [{"price": 11.80}], "sell": [{"price": 11.95}]},
        }
        result = app.validateOrderPriceWithinRange(order, quote)
        self.assertTrue(result["ok"])
        self.assertEqual(result["price"], 12.0)

    def test_lpp_range_below_and_above_50(self):
        self.assertEqual(app.estimateOptionLppRange(12.0), (0.05, 32.0))
        self.assertEqual(app.estimateOptionLppRange(100.0), (60.0, 140.0))

    def test_sell_without_bid_is_blocked(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY26JUN24000CE",
            "transaction_type": "SELL",
            "order_type": "LIMIT",
            "price": 0,
        }
        quote = {"last_price": 12.0, "depth": {"buy": [], "sell": [{"price": 11.95}]}}
        result = app.validateOrderPriceWithinRange(order, quote)
        self.assertFalse(result["ok"])
        self.assertIn("No valid best bid", result["reason"])

    def test_buy_without_ask_is_blocked(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY26JUN24000CE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "price": 0,
        }
        quote = {"last_price": 12.0, "depth": {"buy": [{"price": 11.80}], "sell": []}}
        result = app.validateOrderPriceWithinRange(order, quote)
        self.assertFalse(result["ok"])
        self.assertIn("No valid best ask", result["reason"])

    def test_wide_spread_is_blocked(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY26JUN24000CE",
            "transaction_type": "SELL",
            "order_type": "LIMIT",
            "price": 0,
        }
        quote = {
            "last_price": 10.0,
            "depth": {"buy": [{"price": 7.0}], "sell": [{"price": 11.0}]},
        }
        result = app.validateOrderPriceWithinRange(order, quote)
        self.assertFalse(result["ok"])
        self.assertIn("spread", result["reason"])

    def test_price_rounds_to_five_paise_tick(self):
        self.assertEqual(app.roundToTick(11.773), 11.75)
        self.assertEqual(app.roundToTick(11.778), 11.80)

    def test_lpp_rejection_retries_once_with_recalculated_price(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY26JUN24000CE",
            "transaction_type": "SELL",
            "order_type": "LIMIT",
            "quantity": 65,
            "price": 40.0,
            "_csv_price": 40.0,
        }
        quote = {
            "NFO:NIFTY26JUN24000CE": {
                "last_price": 12.0,
                "depth": {"buy": [{"price": 11.80}], "sell": [{"price": 11.95}]},
            }
        }
        calls = []

        def fake_place(_kite, payload):
            calls.append(payload["price"])
            if len(calls) == 1:
                raise Exception("outside the current allowed limit price protection range")
            return "OID123"

        with (
            patch.object(app, "cached_kite_quote", return_value=quote),
            patch.object(app, "place_order_allowing_autoslice", side_effect=fake_place),
        ):
            order_id, action = app.send_order_with_lpp_retry(object(), order, True)
        self.assertEqual(order_id, "OID123")
        self.assertIn("retried_after_lpp_rejection", action)
        self.assertEqual(calls, [40.0, 11.75])

    def test_kite_error_result_includes_allowed_price_retry_order(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "NIFTY26JUN24000CE",
            "transaction_type": "SELL",
            "order_type": "LIMIT",
            "quantity": 65,
            "product": "NRML",
            "price": 40.0,
            "validity": "DAY",
        }
        quote = {
            "NFO:NIFTY26JUN24000CE": {
                "last_price": 12.0,
                "depth": {"buy": [{"price": 11.80}], "sell": [{"price": 11.95}]},
            }
        }
        with patch.object(app, "cached_kite_quote", return_value=quote):
            result = app.kite_error_result_with_retry(
                object(),
                order,
                Exception("outside the current allowed limit price protection range"),
                "NIFTY order",
            )
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["retry_order"]["price"], 11.75)
        self.assertIn("Allowed-price retry", result["detail"])

    def test_kite_response_modal_shows_retry_action(self):
        state = app.PageState(
            active_tab="place",
            results=[
                {
                    "tradingsymbol": "NIFTY26JUN24000CE",
                    "status": "ERROR",
                    "detail": "Kite rejected price.",
                    "retry_order": {
                        "exchange": "NFO",
                        "tradingsymbol": "NIFTY26JUN24000CE",
                        "transaction_type": "SELL",
                        "quantity": 65,
                        "product": "NRML",
                        "order_type": "LIMIT",
                        "price": 11.75,
                        "validity": "DAY",
                    },
                }
            ],
        )
        html = app.render_kite_response_modal(state)
        self.assertIn("Kite Order Response", html)
        self.assertIn("/nfo/retry-safe-price", html)
        self.assertIn("Submit allowed price", html)
        self.assertIn("11.75", html)

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

    def test_investing_bse_numeric_scrip_resolves_to_kite_tradingsymbol(self):
        item = {
            "code": "BSE:501423",
            "company": "Shaily Engg",
        }
        bse_instruments = [
            {
                "exchange_token": "501423",
                "instrument_token": 12345,
                "tradingsymbol": "SHAILY",
                "name": "Shaily Engineering Plastics",
            }
        ]

        candidates = app.investing_resolved_quote_candidates(item, [], bse_instruments)

        self.assertEqual(candidates[0], "BSE:SHAILY")
        self.assertNotIn("BSE:501423", candidates)

    def test_investing_nse_missing_symbol_falls_back_to_bse_instrument(self):
        item = {
            "code": "NSE:TESTCO",
            "company": "Test Company",
        }
        bse_instruments = [
            {
                "exchange_token": "500001",
                "tradingsymbol": "TESTCO",
                "name": "Test Company",
            }
        ]

        candidates = app.investing_resolved_quote_candidates(item, [], bse_instruments)

        self.assertEqual(candidates[0], "NSE:TESTCO")
        self.assertIn("BSE:TESTCO", candidates)

    def test_investing_rows_use_bse_quote_and_display_resolved_ticker(self):
        holdings = [
            {
                "code": "BSE:501423",
                "company": "Shaily Engg",
                "sector": "Manf",
                "core": "N",
                "quantity": 1206,
                "avg_price": 174.98,
            }
        ]

        def instruments(_kite, exchange):
            if exchange == "BSE":
                return [
                    {
                        "exchange_token": "501423",
                        "tradingsymbol": "SHAILY",
                        "name": "Shaily Engineering Plastics",
                    }
                ]
            return []

        with (
            patch.object(app, "INVESTING_HOLDINGS", holdings),
            patch.object(app.kite_orders, "kite_client", return_value=object()),
            patch.object(app, "cached_kite_instruments", side_effect=instruments),
            patch.object(
                app,
                "cached_kite_quote",
                return_value={
                    "BSE:SHAILY": {
                        "last_price": 200.0,
                        "ohlc": {"close": 190.0},
                    }
                },
            ) as quotes,
            patch.object(app, "investing_52_week_levels", return_value={"high": 220, "low": 150}),
            patch.object(app, "fetch_investing_news", return_value={}),
        ):
            rows, summary = app.investing_holdings_rows()

        self.assertIn("BSE:SHAILY", quotes.call_args.args[1])
        self.assertEqual(rows[0]["quote_key"], "BSE:SHAILY")
        self.assertEqual(rows[0]["symbol"], "SHAILY")
        self.assertEqual(rows[0]["cmp"], 200.0)
        self.assertAlmostEqual(rows[0]["daily_change_pct"], 5.263157, places=5)
        self.assertGreater(summary["total_market"], 0)

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

    def test_commodity_holding_objective_met_shows_full_sell_action(self):
        state = app.PageState(active_tab="commodity")
        state.commodity_holdings = [
            {
                "symbol": "SILVERBEES",
                "label": "Nippon India Silver ETF",
                "quantity": 125,
                "sellable_quantity": 125,
                "average_price": 200.0,
                "ltp": 245.0,
                "source": "holding",
                "investment": 25000.0,
                "market_value": 30625.0,
                "pnl": 5625.0,
                "profit_pct": 22.5,
                "profit_target_pct": 20,
                "book_profit": True,
                "book_profit_reason": "Profit 22.50% reached target 20%",
            }
        ]

        output = app.render_commodity_panel(state)

        self.assertIn("Objective met", output)
        self.assertIn("Profit 22.50% reached target 20%", output)
        self.assertIn("Sell full holding", output)
        self.assertIn("SELL full holding 125 SILVERBEES", output)

    def test_commodity_sell_rejects_duplicate_open_sell_order(self):
        holding = {
            "symbol": "SILVERBEES",
            "quantity": 125,
            "sellable_quantity": 125,
            "average_price": 200.0,
            "ltp": 245.0,
            "profit_pct": 22.5,
            "book_profit": True,
            "book_profit_reason": "Profit 22.50% reached target 20%",
        }
        duplicate = {
            "tradingsymbol": "SILVERBEES",
            "transaction_type": "SELL",
            "status": "OPEN",
            "pending_quantity": 125,
        }
        with (
            patch.dict(app.os.environ, {"KITE_CONFIRM_LIVE_ORDER": "YES"}),
            patch.object(app, "commodity_etf_holdings", return_value=[holding]) as holdings,
            patch.object(app.kite_orders, "kite_client", return_value=object()),
            patch.object(app, "cached_kite_orders", return_value=[duplicate]),
            patch.object(app.kite_orders, "place_order") as place,
        ):
            with self.assertRaisesRegex(ValueError, "open SELL order already exists"):
                app.place_commodity_etf_sell_order("SILVERBEES")

        holdings.assert_called_once_with(force_refresh=True)
        place.assert_not_called()

    def test_commodity_sell_revalidates_objective_before_order(self):
        holding = {
            "symbol": "SILVERBEES",
            "quantity": 125,
            "sellable_quantity": 125,
            "average_price": 238.96,
            "ltp": 215.0,
            "profit_pct": -10.03,
            "book_profit": False,
        }
        with (
            patch.dict(app.os.environ, {"KITE_CONFIRM_LIVE_ORDER": "YES"}),
            patch.object(app, "commodity_etf_holdings", return_value=[holding]) as holdings,
            patch.object(app.kite_orders, "place_order") as place,
        ):
            with self.assertRaisesRegex(ValueError, "below BOOK profit threshold 20%"):
                app.place_commodity_etf_sell_order("SILVERBEES")

        holdings.assert_called_once_with(force_refresh=True)
        place.assert_not_called()

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
                    "symbol": "PGINVIT",
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
                    "symbol": "IRBINVIT",
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
        self.assertIn('data-symbol="PGINVIT"', output)
        self.assertIn('data-symbol="IRBINVIT"', output)
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
                        "exchange": "BSE",
                        "tradingsymbol": "PGINVIT",
                        "quantity": 100,
                        "average_price": 93.825,
                        "last_price": 93.79,
                    },
                    {
                        "exchange": "NSE",
                        "tradingsymbol": "IRBINVIT",
                        "quantity": 150,
                        "average_price": 60.2167,
                        "last_price": 60.58,
                    },
                ]

        with (
            patch.object(app, "cached_kite_quote", return_value={}),
            patch.object(app, "cached_value", side_effect=lambda _key, fn, _ttl: fn()),
            patch.object(app, "selected_kite_profile_name", return_value="Shanti"),
        ):
            rows = app.dividend_income_rows(FakeKite(), {})

        by_symbol = {row["symbol"]: row for row in rows}
        self.assertEqual(by_symbol["PGINVIT"]["quantity"], 100)
        self.assertEqual(by_symbol["PGINVIT"]["exchange"], "BSE")
        self.assertEqual(by_symbol["PGINVIT"]["avg_price"], 93.825)
        self.assertEqual(by_symbol["PGINVIT"]["cmp"], 93.79)
        self.assertEqual(by_symbol["PGINVIT"]["invested_amount"], 9382.5)
        self.assertEqual(by_symbol["PGINVIT"]["market_value"], 9379.0)
        self.assertAlmostEqual(by_symbol["PGINVIT"]["pnl"], -3.5)
        self.assertEqual(by_symbol["PGINVIT"]["holding_source"], "Kite profile: Shanti")
        self.assertEqual(by_symbol["IRBINVIT"]["quantity"], 150)
        self.assertEqual(by_symbol["IRBINVIT"]["exchange"], "NSE")
        self.assertEqual(by_symbol["IRBINVIT"]["avg_price"], 60.2167)

    def test_income_growth_equity_order_uses_requested_limit_price(self):
        snapshot = {
            "symbol": "PGINVIT",
            "exchange": "BSE",
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
            result = app.place_income_growth_equity_order("PGINVIT", "BUY", 10, 100.03)

        self.assertEqual(result["status"], "LIVE_SENT")
        self.assertEqual(placed["tradingsymbol"], "PGINVIT")
        self.assertEqual(placed["exchange"], "BSE")
        self.assertEqual(placed["product"], "CNC")
        self.assertEqual(placed["order_type"], "LIMIT")
        self.assertEqual(placed["price"], 100.05)

    def test_income_growth_page_enables_dividend_table_sorting_and_limit_gap(self):
        page_html = app.render_page(app.PageState(active_tab="income-growth")).decode("utf-8")
        self.assertIn("enableTableSorting(document.getElementById('dividend-income-table'))", page_html)
        self.assertIn("const incomeEquityLimitPrice", page_html)
        self.assertIn("Limit vs CMP", page_html)

    def test_nifty_income_mmi_rules_choose_safer_strikes(self):
        greed = app.calculate_nifty_dynamic_strikes(24000, 65)
        fear = app.calculate_nifty_dynamic_strikes(24000, 35)

        self.assertEqual(greed["mmi_regime"], "GREED_OVERBOUGHT")
        self.assertEqual(greed["pe_sell_strike"], 22400)
        self.assertEqual(greed["ce_sell_strike"], 25100)
        self.assertEqual(fear["mmi_regime"], "FEAR_OVERSOLD")
        self.assertEqual(fear["pe_sell_strike"], 22900)
        self.assertEqual(fear["ce_sell_strike"], 25600)

    def test_nifty_income_vix_filter_rejects_low_and_high_vix(self):
        low = app.apply_vix_filter_and_adjustment(5.5, 5.5, 10.5)
        high = app.apply_vix_filter_and_adjustment(5.5, 5.5, 25)
        elevated = app.apply_vix_filter_and_adjustment(5.5, 5.5, 18)

        self.assertFalse(low["allowed"])
        self.assertEqual(low["skip_reason"], "LOW_VIX_POOR_PREMIUM")
        self.assertFalse(high["allowed"])
        self.assertEqual(high["skip_reason"], "VERY_HIGH_VIX_EVENT_RISK")
        self.assertTrue(elevated["allowed"])
        self.assertEqual(elevated["adjusted_pe_otm_pct"], 6.0)
        self.assertEqual(elevated["position_size_multiplier"], 0.75)

    def test_nifty_delta_filter_uses_strict_entry_limits(self):
        warning = app.validate_short_option_delta(-0.16, 0.10)
        rejected = app.validate_short_option_delta(-0.21, 0.10)

        self.assertTrue(warning["allowed"])
        self.assertEqual(warning["status"], "WARNING")
        self.assertEqual(warning["position_size_multiplier"], 0.5)
        self.assertFalse(rejected["allowed"])
        self.assertEqual(rejected["status"], "REJECT")

    def test_nifty_vix_layer_limits_and_strong_trend_cap(self):
        self.assertEqual(app.get_max_allowed_nifty_layers(10.5), 0)
        self.assertEqual(app.get_max_allowed_nifty_layers(17), 3)
        self.assertEqual(app.get_max_allowed_nifty_layers(19), 2)
        self.assertEqual(app.get_max_allowed_nifty_layers(23), 1)
        self.assertEqual(app.get_max_allowed_nifty_layers(26), 0)
        self.assertEqual(app.get_max_allowed_nifty_layers(17, "STRONG_BULLISH"), 1)
        self.assertFalse(app.validate_nifty_layer_count(2, 2)["allowed"])

    def test_nifty_strong_trends_select_one_sided_defined_risk_spreads(self):
        base = {
            "mmi": 50,
            "india_vix": 16,
            "vix_allowed": True,
            "monthly_risk_allowed": True,
            "margin_heat_allowed": True,
            "current_active_layers": 0,
            "pe_sell_strike": 22600,
            "ce_sell_strike": 25400,
            "hedge_distance_points": 500,
        }
        bullish = app.select_nifty_income_strategy({**base, "trend_regime": "STRONG_BULLISH"})
        bearish = app.select_nifty_income_strategy({**base, "trend_regime": "STRONG_BEARISH"})

        self.assertEqual(bullish["selected_strategy"], "BULL_PUT_SPREAD")
        self.assertIsNone(bullish["final_ce_sell_strike"])
        self.assertEqual(bearish["selected_strategy"], "BEAR_CALL_SPREAD")
        self.assertIsNone(bearish["final_pe_sell_strike"])

    def test_nifty_defined_risk_validator_blocks_naked_live_sell(self):
        naked = [
            {
                "tradingsymbol": "NIFTY26JUN23000PE",
                "transaction_type": "SELL",
                "option_type": "PE",
                "strike": 23000,
                "expiry_date": "2026-06-30",
            }
        ]
        hedged = naked + [
            {
                "tradingsymbol": "NIFTY26JUN22500PE",
                "transaction_type": "BUY",
                "option_type": "PE",
                "strike": 22500,
                "expiry_date": "2026-06-30",
            }
        ]

        self.assertFalse(app.validate_nifty_defined_risk_orders(naked)["allowed"])
        self.assertTrue(app.validate_nifty_defined_risk_orders(hedged)["allowed"])
        with (
            patch.dict(app.os.environ, {"KITE_CONFIRM_LIVE_ORDER": "YES"}),
            patch.object(app, "nifty_income_config", return_value={"allow_live_naked_nifty_sell": False}),
        ):
            with self.assertRaises(PermissionError):
                app.execute_nifty_orders(naked, "LIVE_CONFIRMED", "NIFTY entry")

    def test_nifty_entry_does_not_send_short_legs_after_hedge_failure(self):
        orders = [
            {"tradingsymbol": "NIFTY26JUN22500PE", "transaction_type": "BUY", "option_type": "PE", "strike": 22500, "expiry_date": "2026-06-30"},
            {"tradingsymbol": "NIFTY26JUN25500CE", "transaction_type": "BUY", "option_type": "CE", "strike": 25500, "expiry_date": "2026-06-30"},
            {"tradingsymbol": "NIFTY26JUN23000PE", "transaction_type": "SELL", "option_type": "PE", "strike": 23000, "expiry_date": "2026-06-30"},
            {"tradingsymbol": "NIFTY26JUN25000CE", "transaction_type": "SELL", "option_type": "CE", "strike": 25000, "expiry_date": "2026-06-30"},
        ]
        for order in orders:
            order.update({"exchange": "NFO", "quantity": 65, "product": "NRML", "order_type": "LIMIT", "price": 10, "validity": "DAY"})

        with (
            patch.dict(app.os.environ, {"KITE_CONFIRM_LIVE_ORDER": "YES"}),
            patch.object(app, "nifty_income_config", return_value={"allow_live_naked_nifty_sell": False}),
            patch.object(app.kite_orders, "kite_client", return_value=object()),
            patch.object(app, "apply_nfo_option_price_protection"),
            patch.object(app, "send_order_with_lpp_retry", side_effect=RuntimeError("hedge rejected")) as send_order,
            patch.object(app, "kite_error_result_with_retry", return_value={"status": "ERROR"}),
        ):
            results = app.execute_nifty_orders(orders, "LIVE_CONFIRMED", "NIFTY entry")

        self.assertEqual(send_order.call_count, 2)
        self.assertEqual([row["status"] for row in results[-2:]], ["BLOCKED", "BLOCKED"])

    def nifty_emergency_strategy(self, **updates):
        strategy = {
            "entry_spot": 24000,
            "current_mtm_pnl": -1000,
            "max_loss": 10000,
            "risk_utilisation_pct": 10,
            "legs": [
                {
                    "tradingsymbol": "NIFTY26JUN23000PE",
                    "option_type": "PE",
                    "strike": 23000,
                    "original_transaction_type": "SELL",
                    "entry_price": 100,
                    "current_ltp": 110,
                    "delta": -0.10,
                },
                {
                    "tradingsymbol": "NIFTY26JUN25000CE",
                    "option_type": "CE",
                    "strike": 25000,
                    "original_transaction_type": "SELL",
                    "entry_price": 100,
                    "current_ltp": 110,
                    "delta": 0.10,
                },
            ],
        }
        strategy.update(updates)
        return strategy

    def test_nifty_emergency_exit_triggers_on_premium_delta_strike_and_distance(self):
        premium = self.nifty_emergency_strategy()
        premium["legs"][0]["current_ltp"] = 200
        delta = self.nifty_emergency_strategy()
        delta["legs"][1]["delta"] = 0.25

        self.assertEqual(
            app.evaluate_nifty_emergency_exit(premium, 24000)["exit_reason"],
            "EMERGENCY_SHORT_LEG_2X_PREMIUM",
        )
        self.assertEqual(
            app.evaluate_nifty_emergency_exit(delta, 24000)["exit_reason"],
            "EMERGENCY_SHORT_DELTA_25",
        )
        self.assertEqual(
            app.evaluate_nifty_emergency_exit(self.nifty_emergency_strategy(), 23000)["exit_reason"],
            "EMERGENCY_SHORT_STRIKE_TOUCHED",
        )
        self.assertEqual(
            app.evaluate_nifty_emergency_exit(self.nifty_emergency_strategy(), 23300)["exit_reason"],
            "EMERGENCY_SPOT_DISTANCE_70_PERCENT",
        )

    def test_nifty_emergency_exit_triggers_on_risk_utilisation(self):
        strategy = self.nifty_emergency_strategy(risk_utilisation_pct=75)
        result = app.evaluate_nifty_emergency_exit(strategy, 24000)
        self.assertTrue(result["exit_signal"])
        self.assertEqual(result["exit_reason"], "EMERGENCY_RISK_UTILISATION_75")

    def test_nifty_credit_decay_can_book_week_one_profit(self):
        now = app.datetime(2026, 6, 16, 10, 0, tzinfo=app.INDIA_TIME_ZONE)
        pair = self.nifty_pair(5, 0.5, now=now)
        pair.update({"entry_net_credit": 10000, "current_strategy_value": 7400})

        result = app.evaluate_nifty_weekly_pair_exit(pair, now)

        self.assertTrue(result["exit_signal"])
        self.assertEqual(result["exit_reason"], "WEEK1_CREDIT_DECAY_25_PERCENT")
        self.assertAlmostEqual(result["credit_decay_pct"], 26.0)

    def test_nifty_force_close_uses_earlier_of_day21_and_t_minus_7(self):
        entry = app.datetime(2026, 6, 1, 15, 16, tzinfo=app.INDIA_TIME_ZONE)
        expiry = date(2026, 6, 18)
        close_at = app.calculate_nifty_force_close_datetime(
            entry,
            expiry,
            {**app.NIFTY_INCOME_DEFAULT_CONFIG, "weekly_pair_force_close_time": "14:59"},
        )

        self.assertEqual(close_at.date(), date(2026, 6, 11))
        self.assertEqual(close_at.strftime("%H:%M"), "14:59")

    def test_nifty_income_expected_move_pushes_close_strikes_away(self):
        result = app.validate_short_strikes_against_expected_move(
            spot=24000,
            pe_sell_strike=23800,
            ce_sell_strike=24200,
            expected_move_points=300,
            min_expected_move_multiplier=1.2,
            strike_rounding=100,
        )

        self.assertEqual(result["adjusted_pe_sell_strike"], 23600)
        self.assertEqual(result["adjusted_ce_sell_strike"], 24400)
        self.assertIn("expected move", result["expected_move_adjustment_reason"])

    def test_nifty_income_strategy_selector_prefers_defined_risk_only(self):
        neutral = app.select_nifty_income_strategy(
            {
                "mmi": 50,
                "trend_regime": "SIDEWAYS",
                "vix_allowed": True,
                "monthly_risk_allowed": True,
                "margin_heat_allowed": True,
                "pe_sell_strike": 22600,
                "ce_sell_strike": 25400,
                "hedge_distance_points": 500,
            }
        )
        greed = app.select_nifty_income_strategy(
            {
                "mmi": 70,
                "trend_regime": "MIXED",
                "vix_allowed": True,
                "monthly_risk_allowed": True,
                "margin_heat_allowed": True,
                "pe_sell_strike": 22600,
                "ce_sell_strike": 25400,
                "hedge_distance_points": 500,
            }
        )

        self.assertEqual(neutral["selected_strategy"], "IRON_CONDOR")
        self.assertEqual(neutral["hedge_pe_strike"], 22100)
        self.assertEqual(neutral["hedge_ce_strike"], 25900)
        self.assertEqual(greed["selected_strategy"], "BEAR_CALL_SPREAD")
        self.assertIsNone(greed["final_pe_sell_strike"])

    def test_nifty_time_exit_date_moves_weekend_to_previous_trading_day(self):
        expiry = date(2026, 7, 3)
        self.assertEqual(app.scheduled_nifty_time_exit_date(expiry, 7), date(2026, 6, 26))

        saturday_due = date(2026, 7, 4)
        self.assertEqual(app.scheduled_nifty_time_exit_date(saturday_due, 7), date(2026, 6, 26))

    def test_nifty_time_exit_orders_reverse_open_positions(self):
        positions = [
            {
                "tradingsymbol": "NIFTY26JUN24000CE",
                "quantity": -75,
                "expiry": date(2026, 6, 26),
                "ltp": 100,
            },
            {
                "tradingsymbol": "NIFTY26JUN24500CE",
                "quantity": 75,
                "expiry": date(2026, 6, 26),
                "ltp": 25,
            },
        ]
        now = app.datetime(2026, 6, 19, 14, 59, tzinfo=app.INDIA_TIME_ZONE)
        with patch.object(app, "nifty_income_state", return_value={"time_exit_generated_keys": []}):
            orders = app.nifty_time_exit_orders_for_positions(
                positions,
                {"time_exit_days_before_expiry": 7, "time_exit_time": "14:59", "time_exit_order_type": "MARKET"},
                now,
            )

        self.assertEqual(orders[0]["transaction_type"], "BUY")
        self.assertEqual(orders[1]["transaction_type"], "SELL")
        self.assertEqual(orders[0]["quantity"], 75)
        self.assertEqual(orders[0]["exit_reason"], "TIME_EXIT_T_MINUS_7")

    def test_nifty_income_jobs_are_visible_in_scheduler_and_tab(self):
        jobs = app.scheduled_job_definitions()
        self.assertIn("nifty_income_entry", jobs)
        self.assertIn("nifty_income_time_exit", jobs)

        with patch.object(
            app,
            "nifty_income_snapshot",
            return_value={
                "config": app.nifty_income_config(),
                "state": app.nifty_income_state(),
                "summary": {"active_positions": 0, "pnl": 0, "spot": 24000, "mmi": 50, "vix": 14, "pop": "Defined-risk"},
                "positions": [],
                "suggestion": {"selected_strategy": "IRON_CONDOR", "allowed": True, "pe_otm_pct": 5.5, "ce_otm_pct": 5.5},
                "entry_orders": [],
                "time_exit_orders": [],
                "warnings": [],
            },
        ):
            page_html = app.render_page(app.PageState(active_tab="nifty-income")).decode("utf-8")

        self.assertIn("Nifty Income", page_html)
        self.assertIn("Defined-risk NIFTY income engine", page_html)
        self.assertIn("Run T-7 Exit Now", page_html)
        self.assertIn("'nifty-income': '/nifty-income'", page_html)
        self.assertIn("document.getElementById('nifty-income-panel').style.display", page_html)

    def test_next_nifty_income_entry_date_uses_upcoming_friday(self):
        thursday = app.datetime(2026, 6, 18, 12, 0, tzinfo=app.INDIA_TIME_ZONE)
        friday_before = app.datetime(2026, 6, 19, 14, 0, tzinfo=app.INDIA_TIME_ZONE)
        friday_after = app.datetime(2026, 6, 19, 16, 0, tzinfo=app.INDIA_TIME_ZONE)

        self.assertEqual(app.next_nifty_income_entry_date(thursday, "15:22"), date(2026, 6, 19))
        self.assertEqual(app.next_nifty_income_entry_date(friday_before, "15:22"), date(2026, 6, 19))
        self.assertEqual(app.next_nifty_income_entry_date(friday_after, "15:22"), date(2026, 6, 26))

    def test_nifty_candidate_preview_calculates_ltp_otm_max_gain_and_yield(self):
        entry_orders = [
            {
                "tradingsymbol": "NIFTY26JUN22600PE",
                "transaction_type": "SELL",
                "option_type": "PE",
                "strike": 22600,
                "expiry_date": "2026-06-26",
                "mmi_selected_otm_pct": 5.5,
            },
            {
                "tradingsymbol": "NIFTY26JUN22100PE",
                "transaction_type": "BUY",
                "option_type": "PE",
                "strike": 22100,
                "expiry_date": "2026-06-26",
            },
        ]
        quote_map = {
            "NFO:NIFTY26JUN22600PE": {
                "last_price": 120,
                "oi": 1000,
                "volume": 250,
                "depth": {"buy": [{"price": 119}], "sell": [{"price": 121}]},
            },
            "NFO:NIFTY26JUN22100PE": {"last_price": 40},
        }

        rows = app.nifty_candidate_previews(
            entry_orders,
            quote_map,
            24000,
            {"lot_size": 75},
            300,
        )

        self.assertEqual(rows[0]["side"], "PE")
        self.assertAlmostEqual(rows[0]["otm_pct"], 5.8333, places=3)
        self.assertEqual(rows[0]["option_ltp"], 120)
        self.assertEqual(rows[0]["premium_value_per_lot"], 9000)
        self.assertEqual(rows[0]["max_gain_opportunity"], 6000)
        self.assertEqual(rows[0]["max_loss"], 31500)
        self.assertAlmostEqual(rows[0]["premium_yield_on_margin_pct"], 19.0476, places=3)
        self.assertEqual(rows[0]["risk_status"], "GREEN")

    def test_nifty_preview_liquidity_reduces_ce_otm_by_max_200_points(self):
        quotes = {
            "NIFTY26JUN25500CE": {"oi": 100, "volume": 0},
            "NIFTY26JUN25400CE": {"oi": 9000, "volume": 5},
            "NIFTY26JUN25300CE": {"oi": 0, "volume": 0},
            "NIFTY26JUN25200CE": {"oi": 50000, "volume": 1000},
        }
        order = {
            "tradingsymbol": "NIFTY26JUN25500CE",
            "transaction_type": "SELL",
            "option_type": "CE",
            "strike": 25500,
        }

        adjusted = app.adjust_nifty_preview_sell_order_for_liquidity(
            order,
            lambda symbol: quotes.get(symbol, {}),
            lambda strike, option_type: f"NIFTY26JUN{strike}{option_type}",
        )

        self.assertEqual(adjusted["strike"], 25300)
        self.assertEqual(adjusted["tradingsymbol"], "NIFTY26JUN25300CE")
        self.assertEqual(adjusted["liquidity_shift_points"], 200)
        self.assertIn("Max adjustment allowed is 200 points", adjusted["liquidity_adjustment_note"])

    def test_nifty_preview_liquidity_reduces_pe_otm_towards_spot(self):
        quotes = {
            "NIFTY26JUN22600PE": {"oi": 500, "volume": 1},
            "NIFTY26JUN22700PE": {"oi": 15000, "volume": 0},
        }
        order = {
            "tradingsymbol": "NIFTY26JUN22600PE",
            "transaction_type": "SELL",
            "option_type": "PE",
            "strike": 22600,
        }

        adjusted = app.adjust_nifty_preview_sell_order_for_liquidity(
            order,
            lambda symbol: quotes.get(symbol, {}),
            lambda strike, option_type: f"NIFTY26JUN{strike}{option_type}",
        )

        self.assertEqual(adjusted["strike"], 22700)
        self.assertEqual(adjusted["tradingsymbol"], "NIFTY26JUN22700PE")
        self.assertEqual(adjusted["liquidity_shift_points"], 100)

    def test_nifty_dashboard_renders_market_preview_and_scheduled_jobs(self):
        config = app.nifty_income_config()
        snapshot = {
            "config": config,
            "state": app.nifty_income_state(),
            "summary": {
                "active_positions": 1,
                "pnl": 1250,
                "spot": 24000,
                "mmi": 55,
                "vix": 14,
                "pop": "Defined-risk",
                "margin_required": 31500,
                "max_gain": 6000,
            },
            "market_regime": {
                "nifty_spot": 24000,
                "nifty_futures": 24050,
                "mmi": 55,
                "mmi_regime": "NEUTRAL",
                "india_vix": 14,
                "vix_regime": "NORMAL_LOW",
                "rsi_14": "N/A",
                "adx_14": "N/A",
                "dma_20": "N/A",
                "dma_50": "N/A",
                "trend_regime": "SIDEWAYS",
                "expected_move_points": 300,
                "expected_move_pct": 1.25,
            },
            "positions": [],
            "suggestion": {
                "selected_strategy": "IRON_CONDOR",
                "allowed": True,
                "mmi_regime": "NEUTRAL",
                "vix_regime": "NORMAL_LOW",
                "entry_date": "2026-06-19",
                "final_pe_sell_strike": 22600,
                "final_ce_sell_strike": 25400,
                "pe_otm_pct": 5.5,
                "ce_otm_pct": 5.5,
                "expected_net_credit": 80,
                "estimated_target_profit": 787.5,
                "estimated_stop_loss": 945,
                "time_exit_date": "2026-06-19",
            },
            "entry_orders": [],
            "candidate_previews": [
                {
                    "side": "PE",
                    "action": "SELL",
                    "expiry_date": "2026-06-26",
                    "tradingsymbol": "NIFTY26JUN22600PE",
                    "hedge_symbol": "NIFTY26JUN22100PE",
                    "strike": 22600,
                    "nifty_spot": 24000,
                    "otm_pct": 5.83,
                    "mmi_selected_otm_pct": 5.5,
                    "option_ltp": 120,
                    "bid": 119,
                    "ask": 121,
                    "delta": "N/A",
                    "iv": "N/A",
                    "oi": 1000,
                    "change_oi": "N/A",
                    "volume": 250,
                    "premium_value_per_lot": 9000,
                    "max_gain_opportunity": 6000,
                    "margin_required": 31500,
                    "premium_yield_on_margin_pct": 19.04,
                    "risk_status": "GREEN",
                    "selection_reason": "test",
                },
                {
                    "side": "CE",
                    "action": "SELL",
                    "expiry_date": "2026-06-26",
                    "tradingsymbol": "NIFTY26JUN25400CE",
                    "hedge_symbol": "N/A",
                    "strike": 25400,
                    "nifty_spot": 24000,
                    "otm_pct": 5.83,
                    "mmi_selected_otm_pct": 5.5,
                    "option_ltp": 110,
                    "bid": 109,
                    "ask": 112,
                    "delta": "N/A",
                    "iv": "N/A",
                    "oi": 900,
                    "change_oi": "N/A",
                    "volume": 200,
                    "premium_value_per_lot": 8250,
                    "max_gain_opportunity": 8250,
                    "margin_required": "Use defined-risk hedge",
                    "premium_yield_on_margin_pct": 0,
                    "risk_status": "GREEN",
                    "selection_reason": "test",
                }
            ],
            "time_exit_orders": [],
            "scheduled_jobs": [
                {
                    "name": "NIFTY Income Entry",
                    "purpose": "Build defined-risk NIFTY income orders",
                    "enabled": True,
                    "schedule": "Fridays at 15:22 IST",
                    "timezone": "Asia/Kolkata",
                    "next_run": "19 Jun 2026 15:22 IST",
                    "last_run": "Not run yet",
                    "last_status": "WAITING",
                    "execution_mode": "SUGGESTION_ONLY",
                    "auto_order": False,
                    "auto_exit": True,
                }
            ],
            "warnings": [],
        }

        html = app.render_nifty_income_panel(
            app.PageState(active_tab="nifty-income", nifty_income_snapshot=snapshot)
        )

        self.assertIn("NIFTY Income Strategy Preview", html)
        self.assertIn("Upcoming Friday Preview", html)
        self.assertIn("nifty-preview-table", html)
        self.assertIn("PE SELL", html)
        self.assertIn("CE SELL", html)
        self.assertIn("NIFTY26JUN22600PE", html)
        self.assertIn("NIFTY26JUN25400CE", html)
        self.assertIn("strike-cell", html)
        self.assertIn("otm-cell", html)
        self.assertIn("Scheduled Jobs", html)
        self.assertIn("NIFTY Income Entry", html)
        self.assertIn('id="nifty-pair-include-pe"', html)
        self.assertIn('id="nifty-pair-include-ce"', html)
        self.assertIn('id="nifty-pair-include-cover"', html)
        self.assertIn('id="nifty-pair-max-loss"', html)
        self.assertIn("Protective BUY", html)
        self.assertIn("Protective covers", html)

    def nifty_pair(self, age_days, pnl_pct, margin=100000, now=None):
        now = now or app.datetime(2026, 6, 16, 10, 0, tzinfo=app.INDIA_TIME_ZONE)
        entry = now - app.timedelta(days=age_days)
        return {
            "strategy_id": "NIFTY-WEEKLY-2026-06-30",
            "pair_id": "NIFTY-2026-06-30",
            "expiry_date": "2026-06-30",
            "entry_datetime": entry.isoformat(),
            "margin_required": margin,
            "current_mtm_pnl": margin * pnl_pct / 100,
            "open_legs": [
                {"tradingsymbol": "NIFTY26JUN23000PE", "quantity": -75, "option_type": "PE", "closure_transaction_type": "BUY"},
                {"tradingsymbol": "NIFTY26JUN25000CE", "quantity": -75, "option_type": "CE", "closure_transaction_type": "BUY"},
            ],
            "pe_symbol": "NIFTY26JUN23000PE",
            "ce_symbol": "NIFTY26JUN25000CE",
            "warnings": [],
        }

    def test_nifty_weekly_pair_exit_age_based_rules(self):
        now = app.datetime(2026, 6, 16, 10, 0, tzinfo=app.INDIA_TIME_ZONE)
        cases = [
            (5, 2.1, True, "WEEK1_PROFIT_TARGET_2_PERCENT"),
            (5, -6.0, False, ""),
            (10, 2.6, True, "WEEK2_PROFIT_TARGET_2_5_PERCENT"),
            (10, -5.1, True, "WEEK2_STOP_LOSS_5_PERCENT"),
            (16, 3.1, True, "WEEK3_PROFIT_TARGET_3_PERCENT"),
            (16, -5.1, True, "WEEK3_STOP_LOSS_5_PERCENT"),
        ]
        for age, pnl_pct, should_exit, reason in cases:
            result = app.evaluate_nifty_weekly_pair_exit(self.nifty_pair(age, pnl_pct, now=now), now)
            self.assertEqual(result["exit_signal"], should_exit, (age, pnl_pct))
            self.assertEqual(result["exit_reason"], reason)

    def test_nifty_weekly_pair_force_close_only_after_time(self):
        before = app.datetime(2026, 6, 22, 14, 58, tzinfo=app.INDIA_TIME_ZONE)
        after = app.datetime(2026, 6, 22, 15, 0, tzinfo=app.INDIA_TIME_ZONE)
        pair = self.nifty_pair(21, 0.0, now=before)

        before_result = app.evaluate_nifty_weekly_pair_exit(pair, before)
        after_result = app.evaluate_nifty_weekly_pair_exit(pair, after)

        self.assertFalse(before_result["exit_signal"])
        self.assertTrue(after_result["exit_signal"])
        self.assertEqual(after_result["exit_reason"], "FORCE_CLOSE_DAY21_OR_T_MINUS_7")

    def test_nifty_weekly_pair_exit_orders_reverse_sell_and_buy_hedges(self):
        now = app.datetime(2026, 6, 16, 10, 0, tzinfo=app.INDIA_TIME_ZONE)
        positions = [
            {"tradingsymbol": "NIFTY26JUN23000PE", "quantity": -75, "pnl": 1500, "margin_required": 25000, "entry_datetime": (now - app.timedelta(days=5)).isoformat()},
            {"tradingsymbol": "NIFTY26JUN25000CE", "quantity": -75, "pnl": 700, "margin_required": 25000, "entry_datetime": (now - app.timedelta(days=5)).isoformat()},
            {"tradingsymbol": "NIFTY26JUN22500PE", "quantity": 75, "pnl": -50, "margin_required": 0, "entry_datetime": (now - app.timedelta(days=5)).isoformat()},
            {"tradingsymbol": "NIFTY26JUN25500CE", "quantity": 75, "pnl": -50, "margin_required": 0, "entry_datetime": (now - app.timedelta(days=5)).isoformat()},
        ]
        with patch.object(app, "nifty_income_state", return_value={"weekly_pair_exit_generated_keys": []}):
            rows, orders = app.nifty_weekly_pair_exit_orders_for_positions(positions, now=now)

        self.assertTrue(rows[0]["exit_signal"])
        sides = {order["tradingsymbol"]: order["transaction_type"] for order in orders}
        self.assertEqual(sides["NIFTY26JUN23000PE"], "BUY")
        self.assertEqual(sides["NIFTY26JUN25000CE"], "BUY")
        self.assertEqual(sides["NIFTY26JUN22500PE"], "SELL")
        self.assertEqual(sides["NIFTY26JUN25500CE"], "SELL")

    def test_nifty_weekly_pair_duplicate_exit_is_not_generated(self):
        now = app.datetime(2026, 6, 16, 10, 0, tzinfo=app.INDIA_TIME_ZONE)
        positions = [
            {"tradingsymbol": "NIFTY26JUN23000PE", "quantity": -75, "pnl": 1500, "margin_required": 25000, "entry_datetime": (now - app.timedelta(days=5)).isoformat()},
            {"tradingsymbol": "NIFTY26JUN25000CE", "quantity": -75, "pnl": 700, "margin_required": 25000, "entry_datetime": (now - app.timedelta(days=5)).isoformat()},
        ]
        duplicate_key = "NIFTY-2026-06-30:WEEK1_PROFIT_TARGET_2_PERCENT"
        with patch.object(app, "nifty_income_state", return_value={"weekly_pair_exit_generated_keys": [duplicate_key]}):
            rows, orders = app.nifty_weekly_pair_exit_orders_for_positions(positions, now=now)

        self.assertEqual(orders, [])
        self.assertEqual(rows[0]["last_monitor_status"], "DUPLICATE_SKIPPED")

    def test_nifty_weekly_pair_suggestion_and_auto_modes(self):
        orders = [{"tradingsymbol": "NIFTY26JUN23000PE", "exchange": "NFO", "transaction_type": "BUY", "quantity": 75, "product": "NRML", "order_type": "MARKET", "price": 0, "validity": "DAY"}]
        suggestion = app.execute_nifty_orders(orders, "SUGGESTION_ONLY", "test")
        self.assertEqual(suggestion[0]["status"], "SUGGESTION_ONLY")

        with patch.dict(app.os.environ, {"KITE_CONFIRM_LIVE_ORDER": "YES"}), patch.object(app.kite_orders, "kite_client") as kite_client, patch.object(app, "place_order_allowing_autoslice", return_value="OID"):
            kite_client.return_value = object()
            live = app.execute_nifty_orders(orders, "AUTO_EXIT_ONLY", "test")
        self.assertEqual(live[0]["status"], "LIVE_SENT")

    def test_nifty_manual_pair_orders_use_entered_otm_and_defined_risk_legs(self):
        expiry = date(2026, 7, 14)
        instruments = [
            {
                "name": "NIFTY",
                "segment": "NFO-OPT",
                "expiry": expiry,
                "strike": strike,
                "instrument_type": option_type,
                "tradingsymbol": f"NIFTY{strike}{option_type}",
            }
            for strike, option_type in (
                (22300, "PE"),
                (22600, "PE"),
                (25400, "CE"),
                (25700, "CE"),
            )
        ]
        quote_map = {
            "NFO:NIFTY22300PE": {"last_price": 12.0, "oi": 20000, "volume": 100},
            "NFO:NIFTY22600PE": {"last_price": 31.25, "oi": 20000, "volume": 100},
            "NFO:NIFTY25400CE": {"last_price": 33.4, "oi": 20000, "volume": 100},
            "NFO:NIFTY25700CE": {"last_price": 15.0, "oi": 20000, "volume": 100},
        }
        config = {
            "lot_size": 65,
            "strike_rounding": 100,
            "hedge_distance_points": 500,
            "manual_pair_sell_markup_percent": 20,
        }

        orders, previews = app.nifty_income_pair_orders_from_otm(
            instruments,
            expiry,
            23989.15,
            5.5,
            5.5,
            config,
            quote_map,
            lots=2,
        )

        self.assertEqual([row["transaction_type"] for row in orders], ["BUY", "SELL", "BUY", "SELL"])
        self.assertEqual([row["quantity"] for row in orders], [130, 130, 130, 130])
        self.assertEqual([row["lot_size"] for row in orders], [65, 65, 65, 65])
        self.assertEqual([row["lots"] for row in orders], [2, 2, 2, 2])
        self.assertEqual(
            [row["tradingsymbol"] for row in orders],
            ["NIFTY22300PE", "NIFTY22600PE", "NIFTY25700CE", "NIFTY25400CE"],
        )
        self.assertEqual([row["price"] for row in orders], [12.0, 37.5, 15.0, 40.1])
        self.assertEqual([row["hedge_width_points"] for row in orders], [300, 300, 300, 300])
        sell_gain = sum(
            row["max_gain_opportunity"]
            for row in previews
            if row["transaction_type"] == "SELL"
        )
        self.assertEqual(sell_gain, 8404.5)

    def test_nifty_manual_pair_orders_use_liquidity_adjusted_strikes_for_submission(self):
        expiry = date(2026, 7, 14)
        instruments = [
            {
                "name": "NIFTY",
                "segment": "NFO-OPT",
                "expiry": expiry,
                "strike": strike,
                "instrument_type": option_type,
                "tradingsymbol": f"NIFTY{strike}{option_type}",
            }
            for strike, option_type in (
                (22400, "PE"),
                (22600, "PE"),
                (22700, "PE"),
                (25400, "CE"),
                (25300, "CE"),
                (25600, "CE"),
            )
        ]
        quote_map = {
            "NFO:NIFTY22400PE": {"last_price": 14.0, "oi": 20000, "volume": 100},
            "NFO:NIFTY22600PE": {"last_price": 31.25, "oi": 100, "volume": 0},
            "NFO:NIFTY22700PE": {"last_price": 40.0, "oi": 20000, "volume": 100},
            "NFO:NIFTY25400CE": {"last_price": 33.4, "oi": 9000, "volume": 5},
            "NFO:NIFTY25300CE": {"last_price": 45.0, "oi": 25000, "volume": 50},
            "NFO:NIFTY25600CE": {"last_price": 18.0, "oi": 20000, "volume": 100},
        }
        config = {
            "lot_size": 65,
            "strike_rounding": 100,
            "manual_pair_sell_markup_percent": 20,
        }

        orders, previews = app.nifty_income_pair_orders_from_otm(
            instruments,
            expiry,
            23989.15,
            5.5,
            5.5,
            config,
            quote_map,
            lots=1,
        )

        self.assertEqual(
            [row["tradingsymbol"] for row in orders],
            ["NIFTY22400PE", "NIFTY22700PE", "NIFTY25600CE", "NIFTY25300CE"],
        )
        self.assertEqual([row["strike"] for row in orders], [22400, 22700, 25600, 25300])
        self.assertEqual([row["liquidity_shift_points"] for row in previews], [0, 100, 0, 100])
        self.assertEqual([row["price"] for row in orders], [14.0, 48.0, 18.0, 54.0])
        self.assertEqual(abs(orders[1]["strike"] - orders[0]["strike"]), 300)
        self.assertEqual(abs(orders[3]["strike"] - orders[2]["strike"]), 300)

    def test_nifty_manual_pair_can_submit_only_pe_spread(self):
        expiry = date(2026, 7, 14)
        instruments = [
            {
                "name": "NIFTY",
                "segment": "NFO-OPT",
                "expiry": expiry,
                "strike": strike,
                "instrument_type": "PE",
                "tradingsymbol": f"NIFTY{strike}PE",
            }
            for strike in (22300, 22600)
        ]
        quote_map = {
            "NFO:NIFTY22300PE": {"last_price": 12.0, "oi": 20000, "volume": 100},
            "NFO:NIFTY22600PE": {"last_price": 31.25, "oi": 20000, "volume": 100},
        }

        orders, _ = app.nifty_income_pair_orders_from_otm(
            instruments,
            expiry,
            23989.15,
            5.5,
            5.5,
            {"lot_size": 65, "strike_rounding": 100, "manual_pair_sell_markup_percent": 20},
            quote_map,
            lots=1,
            include_pe=True,
            include_ce=False,
        )

        self.assertEqual(len(orders), 2)
        self.assertEqual([row["option_type"] for row in orders], ["PE", "PE"])
        self.assertEqual([row["transaction_type"] for row in orders], ["BUY", "SELL"])
        self.assertEqual([row["strike"] for row in orders], [22300, 22600])
        self.assertTrue(app.validate_nifty_defined_risk_orders(orders)["allowed"])

    def test_nifty_manual_pair_can_submit_only_ce_spread(self):
        expiry = date(2026, 7, 14)
        instruments = [
            {
                "name": "NIFTY",
                "segment": "NFO-OPT",
                "expiry": expiry,
                "strike": strike,
                "instrument_type": "CE",
                "tradingsymbol": f"NIFTY{strike}CE",
            }
            for strike in (25400, 25700)
        ]
        quote_map = {
            "NFO:NIFTY25400CE": {"last_price": 33.4, "oi": 20000, "volume": 100},
            "NFO:NIFTY25700CE": {"last_price": 15.0, "oi": 20000, "volume": 100},
        }

        orders, _ = app.nifty_income_pair_orders_from_otm(
            instruments,
            expiry,
            23989.15,
            5.5,
            5.5,
            {"lot_size": 65, "strike_rounding": 100, "manual_pair_sell_markup_percent": 20},
            quote_map,
            lots=1,
            include_pe=False,
            include_ce=True,
        )

        self.assertEqual(len(orders), 2)
        self.assertEqual([row["option_type"] for row in orders], ["CE", "CE"])
        self.assertEqual([row["transaction_type"] for row in orders], ["BUY", "SELL"])
        self.assertEqual([row["strike"] for row in orders], [25700, 25400])
        self.assertTrue(app.validate_nifty_defined_risk_orders(orders)["allowed"])

    def test_nifty_manual_pair_can_preview_sell_legs_without_covers(self):
        expiry = date(2026, 7, 14)
        instruments = [
            {
                "name": "NIFTY",
                "segment": "NFO-OPT",
                "expiry": expiry,
                "strike": strike,
                "instrument_type": option_type,
                "tradingsymbol": f"NIFTY{strike}{option_type}",
            }
            for strike, option_type in ((22600, "PE"), (25400, "CE"))
        ]
        quote_map = {
            "NFO:NIFTY22600PE": {"last_price": 31.25, "oi": 20000, "volume": 100},
            "NFO:NIFTY25400CE": {"last_price": 33.4, "oi": 20000, "volume": 100},
        }

        orders, previews = app.nifty_income_pair_orders_from_otm(
            instruments,
            expiry,
            23989.15,
            5.5,
            5.5,
            {"lot_size": 65, "strike_rounding": 100, "manual_pair_sell_markup_percent": 20},
            quote_map,
            include_cover=False,
        )

        self.assertEqual(len(orders), 2)
        self.assertEqual([row["transaction_type"] for row in orders], ["SELL", "SELL"])
        self.assertFalse(any(row["is_hedge"] for row in previews))
        self.assertFalse(app.validate_nifty_defined_risk_orders(orders)["allowed"])

    def test_nifty_manual_pair_risk_calculates_defined_risk_max_gain_and_loss(self):
        previews = [
            {"transaction_type": "BUY", "option_type": "PE", "strike": 22300, "price": 12, "quantity": 65},
            {"transaction_type": "SELL", "option_type": "PE", "strike": 22600, "price": 37.5, "quantity": 65},
            {"transaction_type": "BUY", "option_type": "CE", "strike": 25700, "price": 15, "quantity": 65},
            {"transaction_type": "SELL", "option_type": "CE", "strike": 25400, "price": 40.1, "quantity": 65},
        ]

        risk = app.calculate_nifty_manual_pair_risk(previews)

        self.assertTrue(risk["defined_risk"])
        self.assertFalse(risk["max_loss_unlimited"])
        self.assertAlmostEqual(risk["max_gain"], 3289.0)
        self.assertAlmostEqual(risk["max_loss"], 17868.5)

    def test_nifty_manual_pair_risk_marks_uncovered_ce_loss_unlimited(self):
        previews = [
            {"transaction_type": "SELL", "option_type": "PE", "strike": 22600, "price": 37.5, "quantity": 65},
            {"transaction_type": "SELL", "option_type": "CE", "strike": 25400, "price": 40.1, "quantity": 65},
        ]

        risk = app.calculate_nifty_manual_pair_risk(previews)

        self.assertFalse(risk["defined_risk"])
        self.assertTrue(risk["max_loss_unlimited"])
        self.assertIsNone(risk["max_loss"])
        self.assertEqual(risk["max_loss_display"], "UNLIMITED")

    def test_nifty_manual_pair_rejects_wrong_hedge_width(self):
        orders = [
            {
                "tradingsymbol": "NIFTY26JUL22300PE",
                "transaction_type": "BUY",
                "option_type": "PE",
                "strike": 22300,
                "expiry_date": "2026-07-28",
            },
            {
                "tradingsymbol": "NIFTY26JUL22700PE",
                "transaction_type": "SELL",
                "option_type": "PE",
                "strike": 22700,
                "expiry_date": "2026-07-28",
                "hedge_width_points": 300,
            },
        ]

        result = app.validate_nifty_defined_risk_orders(orders)

        self.assertFalse(result["allowed"])
        self.assertIn("exactly 300 points away", result["warnings"][0])

    def test_place_nifty_manual_pair_forwards_selected_side(self):
        orders = [
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTY26JUL25700CE",
                "quantity": 65,
                "transaction_type": "BUY",
            },
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTY26JUL25400CE",
                "quantity": 65,
                "transaction_type": "SELL",
            },
        ]
        with (
            patch.object(app, "kite_profile_nifty_income_enabled", return_value=True),
            patch.object(
                app,
                "nifty_income_manual_pair_snapshot",
                return_value={"orders": orders, "missing_ltp": []},
            ) as snapshot,
            patch.object(app, "execute_nifty_orders", return_value=[{"status": "LIVE_SENT"}]) as execute,
        ):
            result = app.place_nifty_income_manual_pair(
                5.5,
                5.5,
                1,
                include_pe=False,
                include_ce=True,
            )

        snapshot.assert_called_once_with(5.5, 5.5, 1, False, True, True)
        execute.assert_called_once_with(orders, "LIVE_CONFIRMED", "Manual NIFTY PE/CE income pair")
        self.assertEqual(result, [{"status": "LIVE_SENT"}])

    def test_nifty_entry_scheduler_runs_friday_defined_risk_at_1516(self):
        now = app.datetime(2026, 6, 19, 15, 16, tzinfo=app.INDIA_TIME_ZONE)
        saved_states = []
        config = {
            **app.NIFTY_INCOME_DEFAULT_CONFIG,
            "enabled": True,
            "entry_time": "15:16",
            "execution_mode": "SUGGESTION_ONLY",
        }
        pair_orders = [
            {"tradingsymbol": "NIFTY22200PE", "transaction_type": "BUY", "quantity": 65},
            {"tradingsymbol": "NIFTY22700PE", "transaction_type": "SELL", "quantity": 65},
            {"tradingsymbol": "NIFTY25300CE", "transaction_type": "SELL", "quantity": 65},
            {"tradingsymbol": "NIFTY25800CE", "transaction_type": "BUY", "quantity": 65},
        ]

        def save_state(**updates):
            saved_states.append(updates)
            return updates

        with (
            patch.object(app, "kite_profile_nifty_income_enabled", return_value=True),
            patch.object(app, "nifty_income_config", return_value=config),
            patch.object(app, "nifty_income_state", return_value={}),
            patch.object(app, "nifty_income_entry_schedule_state", return_value={"enabled": True, "schedule_time": "15:16"}),
            patch.object(app, "save_nifty_income_state", side_effect=save_state),
            patch.object(
                app,
                "nifty_income_snapshot",
                return_value={
                    "suggestion": {"allowed": True, "selected_strategy": "IRON_CONDOR"},
                    "entry_orders": pair_orders,
                },
            ),
            patch.object(app, "execute_nifty_orders", return_value=[{"status": "SUGGESTION_ONLY"}]) as execute_orders,
        ):
            result = app.run_nifty_income_entry_job(now)

        self.assertIsNotNone(result)
        execute_orders.assert_called_once_with(pair_orders, "SUGGESTION_ONLY", "NIFTY Friday defined-risk income entry")
        self.assertIn("NIFTY defined-risk entry generated 4 leg(s)", result["message"])


if __name__ == "__main__":
    unittest.main()
