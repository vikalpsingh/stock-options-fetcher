import unittest
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

    def test_ce_max_profit_and_quantity_use_covered_lots(self):
        result = app.score_ce_sell_candidate(
            {
                "stock": "TEST", "holding_qty": 1200, "active_lot_size": 500,
                "requested_lots": 3, "cmp": 1000, "selected_ce_strike": 1100,
                "premium": 10, "sell_limit_price": 12, "contract_valid": True,
                "event_risk": "GREEN", "breakout_risk": "GREEN", "sell_pop": 90,
            }
        )
        self.assertEqual(result["lots_to_sell"], 2)
        self.assertEqual(result["quantity"], 1000)
        self.assertEqual(result["max_profit"], 12000)
        self.assertLessEqual(result["final_ce_score"], 100)

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
            ce_sell_top=[{"stock": "TOP", "final_ce_score": 90}],
            ce_sell_watch=[{"stock": "WATCH", "final_ce_score": 70}],
            ce_sell_avoid=[{"stock": "AVOID", "final_ce_score": 20}],
        )
        rendered = app.render_ce_sell_dashboard(state)
        self.assertEqual(rendered.count("ce-sell-order-button"), 1)
        self.assertIn('data-underlying="TOP"', rendered)
        self.assertNotIn('data-underlying="WATCH"', rendered)
        self.assertNotIn('data-underlying="AVOID"', rendered)

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

    def test_score_is_capped_at_100(self):
        result = app.score_pe_sell_candidate(candidate())
        self.assertLessEqual(result["final_pe_score"], 100)
        self.assertLessEqual(result["stock_quality_score"], 40)
        self.assertLessEqual(result["pe_trade_score"], 60)

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
        self.assertNotIn("PFC monthly P&amp;L", output)
        self.assertNotIn("Expected Portfolio Behavior", output)


if __name__ == "__main__":
    unittest.main()
