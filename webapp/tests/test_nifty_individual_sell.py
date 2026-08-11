import unittest
import json
from datetime import date
from unittest.mock import patch

import app


class NiftyIndividualSellTest(unittest.TestCase):
    def test_json_safe_default_serializes_date_for_position_action_modal(self):
        payload = json.dumps(
            {"ok": True, "candidate": {"expiry": date(2026, 8, 18)}},
            default=app.json_safe_default,
        )

        self.assertIn('"expiry": "2026-08-18"', payload)

    def test_bounded_nifty_income_sell_strikes_round_inside_four_percent(self):
        result = app.bounded_nifty_income_sell_strikes(
            spot=24500,
            pe_otm_pct=6.5,
            ce_otm_pct=5.5,
            strike_rounding=100,
            max_sell_otm_pct=4.0,
        )

        self.assertEqual(result["pe_sell_strike"], 23600)
        self.assertEqual(result["ce_sell_strike"], 25400)
        self.assertLessEqual(result["pe_otm_pct"], 4.0)
        self.assertLessEqual(result["ce_otm_pct"], 4.0)

    def test_bounded_nifty_income_hedge_width_keeps_total_otm_near_five_point_five_percent(self):
        result = app.bounded_nifty_income_hedge_width(
            spot=12000,
            sell_strike=11500,
            option_type="PE",
            preferred_width_points=300,
            strike_rounding=100,
            max_total_hedge_otm_pct=5.5,
        )

        self.assertEqual(result["hedge_width_points"], 100)
        self.assertLessEqual(result["hedge_otm_pct"], 5.5)
        self.assertTrue(result["hedge_width_capped"])

    def test_short_pe_23000_creates_buy_22700_pe_hedge(self):
        expiry = date(2026, 8, 25)
        instruments = [
            {"name": "NIFTY", "segment": "NFO-OPT", "expiry": expiry, "strike": 22700, "instrument_type": "PE", "tradingsymbol": "NIFTY26AUG22700PE"},
        ]
        candidate = app.build_hedge_repair_candidate(
            {"tradingsymbol": "NIFTY26AUG23000PE", "quantity": -130, "average_price": 18.0, "pnl": 1456.0, "expiry": expiry},
            "SAME_EXPIRY",
            300,
            130,
            instruments,
            {"NFO:NIFTY26AUG22700PE": {"last_price": 6.8, "depth": {"buy": [{"price": 6.75}], "sell": [{"price": 6.85}]}}},
            current_date=date(2026, 8, 11),
        )

        self.assertEqual(candidate["hedge_symbol"], "NIFTY26AUG22700PE")
        self.assertEqual(candidate["hedge_strike"], 22700)
        self.assertEqual(candidate["transaction_type"], "BUY")
        self.assertEqual(candidate["hedge_validity"], "SAME_EXPIRY_FULL_HEDGE")
        self.assertAlmostEqual(candidate["estimated_cost"], 910.0)
        self.assertAlmostEqual(candidate["limit_cash_flow"], -910.0)
        self.assertAlmostEqual(candidate["projected_pnl_after_limit"], 546.0)
        self.assertIn("subtracts the protective BUY hedge LIMIT cost", candidate["pnl_projection_note"])

    def test_sell_against_long_projection_adds_limit_credit_to_current_pnl(self):
        expiry = date(2026, 8, 18)
        instruments = [
            {"name": "NIFTY", "segment": "NFO-OPT", "expiry": expiry, "strike": 24900, "instrument_type": "CE", "tradingsymbol": "NIFTY2681824900CE"},
        ]
        candidate = app.build_sell_against_long_candidate(
            {"tradingsymbol": "NIFTY2681825200CE", "quantity": 195, "average_price": 26.0, "last_price": 3.75, "pnl": -4338.75, "expiry": expiry},
            24900,
            expiry,
            195,
            instruments,
            {"NFO:NIFTY2681824900CE": {"last_price": 34.7, "depth": {"buy": [{"price": 34.1}], "sell": [{"price": 34.8}]}}},
            current_date=date(2026, 8, 11),
        )

        self.assertEqual(candidate["sell_symbol"], "NIFTY2681824900CE")
        self.assertAlmostEqual(candidate["limit_cash_flow"], 6649.5)
        self.assertAlmostEqual(candidate["projected_pnl_after_limit"], 2310.75)

    def test_short_ce_25000_creates_buy_25300_ce_hedge(self):
        expiry = date(2026, 8, 25)
        instruments = [
            {"name": "NIFTY", "segment": "NFO-OPT", "expiry": expiry, "strike": 25300, "instrument_type": "CE", "tradingsymbol": "NIFTY26AUG25300CE"},
        ]
        candidate = app.build_hedge_repair_candidate(
            {"tradingsymbol": "NIFTY26AUG25000CE", "quantity": -65, "average_price": 20.0, "expiry": expiry},
            "SAME_EXPIRY",
            300,
            65,
            instruments,
            {"NFO:NIFTY26AUG25300CE": {"last_price": 7.0, "depth": {"buy": [{"price": 6.95}], "sell": [{"price": 7.05}]}}},
            current_date=date(2026, 8, 11),
        )

        self.assertEqual(candidate["hedge_symbol"], "NIFTY26AUG25300CE")
        self.assertEqual(candidate["hedge_strike"], 25300)
        self.assertEqual(candidate["hedge_validity"], "SAME_EXPIRY_FULL_HEDGE")

    def test_later_expiry_hedge_is_calendar_and_requires_confirmation(self):
        short_expiry = date(2026, 8, 25)
        later_expiry = date(2026, 9, 8)
        instruments = [
            {"name": "NIFTY", "segment": "NFO-OPT", "expiry": later_expiry, "strike": 22700, "instrument_type": "PE", "tradingsymbol": "NIFTY08SEP22700PE"},
        ]
        candidate = app.build_hedge_repair_candidate(
            {"tradingsymbol": "NIFTY26AUG23000PE", "quantity": -130, "average_price": 18.0, "expiry": short_expiry},
            "2W_AWAY",
            300,
            130,
            instruments,
            {"NFO:NIFTY08SEP22700PE": {"last_price": 40.0, "depth": {"buy": [{"price": 39.5}], "sell": [{"price": 40.5}]}}},
            current_date=date(2026, 8, 25),
        )

        self.assertEqual(candidate["hedge_validity"], "CALENDAR_HEDGE_REDUCES_RISK")
        self.assertTrue(candidate["manual_confirmation_required"])
        self.assertIn("calendar hedge", candidate["warning"].lower())

    def test_long_ce_same_expiry_allows_sell_lower_ce(self):
        expiry = date(2026, 8, 18)
        instruments = [
            {"name": "NIFTY", "segment": "NFO-OPT", "expiry": expiry, "strike": 25000, "instrument_type": "CE", "tradingsymbol": "NIFTY18AUG25000CE"},
        ]
        candidate = app.build_sell_against_long_candidate(
            {"tradingsymbol": "NIFTY2681825200CE", "quantity": 195, "average_price": 26.0, "expiry": expiry},
            25000,
            expiry,
            195,
            instruments,
            {"NFO:NIFTY18AUG25000CE": {"last_price": 45.0, "depth": {"buy": [{"price": 44.5}], "sell": [{"price": 45.5}]}}},
            current_date=date(2026, 8, 11),
        )

        self.assertTrue(candidate["allowed"])
        self.assertEqual(candidate["sell_symbol"], "NIFTY18AUG25000CE")
        self.assertEqual(candidate["orders"][0]["transaction_type"], "SELL")

    def test_long_ce_blocks_direct_later_expiry_sell(self):
        long_expiry = date(2026, 8, 18)
        later_expiry = date(2026, 9, 8)
        candidate = app.build_sell_against_long_candidate(
            {"tradingsymbol": "NIFTY2681825200CE", "quantity": 195, "average_price": 26.0, "expiry": long_expiry},
            25000,
            later_expiry,
            195,
            [],
            current_date=date(2026, 8, 11),
        )

        self.assertFalse(candidate["allowed"])
        self.assertEqual(candidate["reason"], "SHORT_EXPIRY_BEYOND_LONG_HEDGE_EXPIRY_USE_ROLL_SELL")

    def test_roll_sell_orders_close_current_then_new_hedged_spread_at_cmp_limit(self):
        target_expiry = date(2026, 9, 8)
        instruments = [
            {"name": "NIFTY", "segment": "NFO-OPT", "expiry": target_expiry, "strike": 25200, "instrument_type": "CE", "tradingsymbol": "NIFTY08SEP25200CE"},
            {"name": "NIFTY", "segment": "NFO-OPT", "expiry": target_expiry, "strike": 24900, "instrument_type": "CE", "tradingsymbol": "NIFTY08SEP24900CE"},
        ]
        candidate = app.build_roll_sell_candidate(
            {"tradingsymbol": "NIFTY2681825200CE", "quantity": 195, "average_price": 26.0, "last_price": 3.75, "pnl": -4338.75, "expiry": date(2026, 8, 18)},
            "4W_AWAY",
            300,
            195,
            instruments,
            {
                "NFO:NIFTY2681825200CE": {"last_price": 3.75, "depth": {"buy": [{"price": 3.70}], "sell": [{"price": 3.80}]}},
                "NFO:NIFTY08SEP25200CE": {"last_price": 20.0, "depth": {"buy": [{"price": 19.5}], "sell": [{"price": 20.5}]}},
                "NFO:NIFTY08SEP24900CE": {"last_price": 52.0, "depth": {"buy": [{"price": 51.5}], "sell": [{"price": 52.5}]}},
            },
            current_date=date(2026, 8, 11),
        )

        self.assertEqual([order["transaction_type"] for order in candidate["orders"]], ["SELL", "BUY", "SELL"])
        self.assertEqual([order["tag"] for order in candidate["orders"]], ["NIFTY_ROLL_CLOSE", "NIFTY_ROLL_HEDGE", "NIFTY_ROLL_SELL"])
        self.assertEqual([order["execution_sequence"] for order in candidate["orders"]], [1, 2, 3])
        self.assertEqual([order["tradingsymbol"] for order in candidate["orders"]], ["NIFTY2681825200CE", "NIFTY08SEP25200CE", "NIFTY08SEP24900CE"])
        self.assertEqual([order["price"] for order in candidate["orders"]], [3.75, 20.0, 52.0])
        self.assertTrue(candidate["orders"][0]["close_existing_position"])
        self.assertAlmostEqual(candidate["close_cash_flow"], 731.25)
        self.assertAlmostEqual(candidate["net_credit"], 6240.0)
        self.assertAlmostEqual(candidate["limit_cash_flow"], 6971.25)
        self.assertAlmostEqual(candidate["projected_pnl_after_limit"], 2632.5)

    def test_nifty_sequence_respects_roll_execution_sequence(self):
        ordered = app.nifty_order_preview_sequence(
            [
                {"transaction_type": "SELL", "option_type": "CE", "tradingsymbol": "NEWSELL", "execution_sequence": 3},
                {"transaction_type": "BUY", "option_type": "CE", "tradingsymbol": "NEWHEDGE", "execution_sequence": 2},
                {"transaction_type": "SELL", "option_type": "CE", "tradingsymbol": "CLOSECURRENT", "execution_sequence": 1},
            ]
        )

        self.assertEqual([row["tradingsymbol"] for row in ordered], ["CLOSECURRENT", "NEWHEDGE", "NEWSELL"])

    def test_roll_close_leg_is_not_treated_as_naked_new_sell(self):
        validation = app.validate_nifty_defined_risk_orders(
            [
                {
                    "transaction_type": "SELL",
                    "tradingsymbol": "NIFTY2681825200CE",
                    "option_type": "CE",
                    "strike": 25200,
                    "expiry_date": "2026-08-18",
                    "close_existing_position": True,
                    "tag": "NIFTY_ROLL_CLOSE",
                },
                {
                    "transaction_type": "BUY",
                    "tradingsymbol": "NIFTY08SEP25200CE",
                    "option_type": "CE",
                    "strike": 25200,
                    "expiry_date": "2026-09-08",
                },
                {
                    "transaction_type": "SELL",
                    "tradingsymbol": "NIFTY08SEP24900CE",
                    "option_type": "CE",
                    "strike": 24900,
                    "expiry_date": "2026-09-08",
                    "hedge_width_points": 300,
                },
            ]
        )

        self.assertTrue(validation["allowed"])

    def test_nifty_300_point_spread_two_lots_gross_risk_is_39000(self):
        risk = app.calculate_nifty_defined_risk(
            "BULL_PUT_SPREAD",
            [
                {"transaction_type": "BUY", "option_type": "PE", "strike": 22700, "price": 4.0},
                {"transaction_type": "SELL", "option_type": "PE", "strike": 23000, "price": 14.0},
            ],
            lot_size=65,
            lots=2,
            max_loss_cap=60000,
        )

        self.assertEqual(risk["gross_risk"], 39000)
        self.assertEqual(risk["net_credit_value"], 1300)
        self.assertEqual(risk["max_loss"], 37700)
        self.assertEqual(risk["cap_status"], "PASS")

    def test_nifty_iron_condor_uses_max_side_width_not_sum(self):
        risk = app.calculate_nifty_defined_risk(
            "IRON_CONDOR",
            [
                {"transaction_type": "BUY", "option_type": "PE", "strike": 22700, "price": 4.0},
                {"transaction_type": "SELL", "option_type": "PE", "strike": 23000, "price": 14.0},
                {"transaction_type": "BUY", "option_type": "CE", "strike": 25800, "price": 5.0},
                {"transaction_type": "SELL", "option_type": "CE", "strike": 25500, "price": 15.0},
            ],
            lot_size=65,
            lots=2,
            max_loss_cap=60000,
        )

        self.assertEqual(risk["gross_risk"], 39000)
        self.assertEqual(risk["net_credit_value"], 2600)
        self.assertEqual(risk["max_loss"], 36400)
        self.assertEqual(risk["cap_status"], "PASS")

    def test_total_projected_nifty_risk_above_cap_fails(self):
        new_risk = app.calculate_nifty_defined_risk(
            "BEAR_CALL_SPREAD",
            [
                {"transaction_type": "BUY", "option_type": "CE", "strike": 25800, "price": 4.0},
                {"transaction_type": "SELL", "option_type": "CE", "strike": 25500, "price": 14.0},
            ],
            lot_size=65,
            lots=2,
            max_loss_cap=60000,
        )
        total = app.calculate_total_nifty_risk_after_order(
            [
                {"tradingsymbol": "NIFTY26AUG23000PE", "quantity": -130, "average_price": 30.0, "strike": 23000, "option_type": "PE"},
                {"tradingsymbol": "NIFTY26AUG22700PE", "quantity": 130, "average_price": 5.0, "strike": 22700, "option_type": "PE"},
            ],
            {"risk": new_risk},
            cap=60000,
        )

        self.assertEqual(total["cap_status"], "FAIL")
        self.assertIn("MAX_LOSS_CAP_BREACH", total["hard_block_reasons"])

    def test_missing_hedge_hard_blocks_new_order(self):
        risk = app.calculate_nifty_defined_risk(
            "BEAR_CALL_SPREAD",
            [{"transaction_type": "SELL", "option_type": "CE", "strike": 25500, "price": 14.0}],
            lot_size=65,
            lots=2,
            max_loss_cap=60000,
        )
        total = app.calculate_total_nifty_risk_after_order([], {"risk": risk}, cap=60000)

        self.assertFalse(risk["defined_risk"])
        self.assertEqual(total["cap_status"], "FAIL")
        self.assertIn("NEW_ORDER_NOT_HEDGED", total["hard_block_reasons"])

    def test_low_credit_and_confidence_are_warnings_with_known_risk_override(self):
        risk = app.calculate_nifty_defined_risk(
            "BULL_PUT_SPREAD",
            [
                {"transaction_type": "BUY", "option_type": "PE", "strike": 22700, "price": 4.0},
                {"transaction_type": "SELL", "option_type": "PE", "strike": 23000, "price": 14.0},
            ],
            lot_size=65,
            lots=2,
            max_loss_cap=60000,
        )
        total = app.calculate_total_nifty_risk_after_order([], {"risk": risk}, cap=60000)
        gates = app.evaluate_nifty_simplified_trade_gates(
            total,
            risk,
            fresh_quote_available=True,
            broker_margin_verified=True,
            manual_confirmation=True,
            known_risk_override=True,
            confidence_score=62,
            credit_pct_of_width=5.5,
            delta_missing=True,
        )

        self.assertEqual(gates["hard_blocks"], [])
        self.assertIn("CONFIDENCE_BELOW_70", gates["warnings"])
        self.assertIn("CREDIT_BELOW_8_PERCENT", gates["warnings"])
        self.assertIn("DELTA_MISSING", gates["warnings"])
        self.assertTrue(gates["place_order_enabled"])

    def test_broker_margin_missing_hard_blocks_live_order_gate(self):
        risk = app.calculate_nifty_defined_risk(
            "BULL_PUT_SPREAD",
            [
                {"transaction_type": "BUY", "option_type": "PE", "strike": 22700, "price": 4.0},
                {"transaction_type": "SELL", "option_type": "PE", "strike": 23000, "price": 14.0},
            ],
            lot_size=65,
            lots=2,
            max_loss_cap=60000,
        )
        total = app.calculate_total_nifty_risk_after_order([], {"risk": risk}, cap=60000)
        gates = app.evaluate_nifty_simplified_trade_gates(
            total,
            risk,
            fresh_quote_available=True,
            broker_margin_verified=False,
            manual_confirmation=True,
            known_risk_override=True,
        )

        self.assertIn("BROKER_MARGIN_NOT_VERIFIED", gates["hard_blocks"])
        self.assertFalse(gates["place_order_enabled"])

    def test_nifty_order_preview_sequence_places_all_buy_hedges_before_sells(self):
        ordered = app.nifty_order_preview_sequence(
            [
                {"transaction_type": "SELL", "option_type": "PE", "tradingsymbol": "NIFTYSELLPE"},
                {"transaction_type": "BUY", "option_type": "CE", "tradingsymbol": "NIFTYBUYCE"},
                {"transaction_type": "SELL", "option_type": "CE", "tradingsymbol": "NIFTYSELLCE"},
                {"transaction_type": "BUY", "option_type": "PE", "tradingsymbol": "NIFTYBUYPE"},
            ]
        )

        self.assertEqual([row["transaction_type"] for row in ordered], ["BUY", "BUY", "SELL", "SELL"])
        self.assertEqual(ordered[0]["tradingsymbol"], "NIFTYBUYPE")

    def test_single_pe_risk_ack_can_override_pair_only_risk_rejection(self):
        decision = app.evaluate_nifty_individual_uncovered_override(
            {"PE"},
            include_cover=False,
            risk_acknowledged=True,
            confidence={
                "action": "PREVIEW_ONLY",
                "hard_blocks": ["POOR_PREMIUM_YIELD"],
            },
        )

        self.assertTrue(decision["requested"])
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["selected_side"], "PE")

    def test_both_sides_do_not_get_individual_risk_override(self):
        decision = app.evaluate_nifty_individual_uncovered_override(
            {"PE", "CE"},
            include_cover=False,
            risk_acknowledged=True,
            confidence={"hard_blocks": []},
        )

        self.assertFalse(decision["requested"])
        self.assertFalse(decision["allowed"])

    def test_hard_market_gate_cannot_be_overridden(self):
        decision = app.evaluate_nifty_individual_uncovered_override(
            {"CE"},
            include_cover=False,
            risk_acknowledged=True,
            confidence={"hard_blocks": ["HIGH_VIX", "POOR_PREMIUM_YIELD"]},
        )

        self.assertTrue(decision["requested"])
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["non_overridable_blocks"], ["HIGH_VIX"])

    @patch.object(app, "execute_nifty_orders")
    @patch.object(app, "nifty_income_manual_pair_snapshot")
    @patch.object(app, "kite_profile_nifty_income_enabled", return_value=True)
    def test_acknowledged_single_ce_reaches_live_execution(
        self,
        _profile_enabled,
        snapshot_mock,
        execute_mock,
    ):
        snapshot_mock.return_value = {
            "missing_ltp": [],
            "dynamic_hedge_allowed": True,
            "uncovered_sides": ["CE"],
            "naked_live_allowed": False,
            "risk_reward_status": "MANUAL_SINGLE_LEG_RISK_ACCEPTED",
            "individual_uncovered_override": {
                "requested": True,
                "allowed": True,
                "selected_side": "CE",
                "non_overridable_blocks": [],
            },
            "orders": [
                {
                    "exchange": "NFO",
                    "tradingsymbol": "NIFTYTEST25000CE",
                    "transaction_type": "SELL",
                    "quantity": 65,
                    "price": 25.0,
                }
            ],
        }
        execute_mock.return_value = [{"status": "LIVE_SENT"}]

        result = app.place_nifty_income_manual_pair(
            5.5,
            5.5,
            lots=1,
            include_pe=False,
            include_ce=True,
            include_cover=False,
            allow_uncovered_override=True,
        )

        self.assertEqual(result, [{"status": "LIVE_SENT"}])
        snapshot_mock.assert_called_once_with(
            5.5,
            5.5,
            1,
            False,
            True,
            False,
            True,
            None,
            None,
            None,
        )
        execute_mock.assert_called_once()

    @patch.object(app, "execute_nifty_orders")
    @patch.object(app, "nifty_income_manual_pair_snapshot")
    @patch.object(app, "kite_profile_nifty_income_enabled", return_value=True)
    def test_defined_risk_acknowledgement_allows_risk_reward_override(
        self,
        _profile_enabled,
        snapshot_mock,
        execute_mock,
    ):
        snapshot_mock.return_value = {
            "missing_ltp": [],
            "dynamic_hedge_allowed": True,
            "uncovered_sides": [],
            "defined_risk": True,
            "max_loss_unlimited": False,
            "risk_reward_status": "REJECT_PREMIUM_YIELD",
            "return_on_margin_pct": 2.83,
            "max_loss_to_credit_ratio": 35.4,
            "confidence_score": {"action": "PREVIEW_ONLY", "label": "Preview"},
            "individual_uncovered_override": {"requested": False, "allowed": False},
            "orders": [
                {
                    "exchange": "NFO",
                    "tradingsymbol": "NIFTYTEST22900PE",
                    "transaction_type": "BUY",
                    "quantity": 65,
                    "price": 1.0,
                },
                {
                    "exchange": "NFO",
                    "tradingsymbol": "NIFTYTEST22900PE",
                    "transaction_type": "SELL",
                    "quantity": 65,
                    "price": 16.5,
                },
            ],
        }
        execute_mock.return_value = [{"status": "LIVE_SENT"}]

        result = app.place_nifty_income_manual_pair(
            5.0,
            5.0,
            lots=1,
            include_pe=True,
            include_ce=True,
            include_cover=True,
            accept_defined_risk_override=True,
        )

        self.assertEqual(result, [{"status": "LIVE_SENT"}])
        execute_mock.assert_called_once()
        self.assertIn("accepted defined-risk override", execute_mock.call_args.args[2])

    @patch.object(app, "execute_nifty_orders")
    @patch.object(app, "nifty_income_manual_pair_snapshot")
    @patch.object(app, "kite_profile_nifty_income_enabled", return_value=True)
    def test_defined_risk_acknowledgement_allows_no_trade_warning_when_defined_risk(
        self,
        _profile_enabled,
        snapshot_mock,
        execute_mock,
    ):
        snapshot_mock.return_value = {
            "missing_ltp": [],
            "dynamic_hedge_allowed": True,
            "uncovered_sides": [],
            "defined_risk": True,
            "max_loss_unlimited": False,
            "risk_reward_status": "REJECT_PREMIUM_YIELD",
            "confidence_score": {"action": "NO_TRADE", "label": "No trade"},
            "individual_uncovered_override": {"requested": False, "allowed": False},
            "orders": [],
        }
        execute_mock.return_value = [{"status": "LIVE_SENT"}]

        result = app.place_nifty_income_manual_pair(
            5.0,
            5.0,
            lots=1,
            include_pe=True,
            include_ce=True,
            include_cover=True,
            accept_defined_risk_override=True,
        )

        self.assertEqual(result, [{"status": "LIVE_SENT"}])
        execute_mock.assert_called_once()

    @patch.object(app, "execute_nifty_orders")
    @patch.object(app, "nifty_option_positions")
    @patch.object(app, "nifty_position_action_candidate_snapshot")
    def test_sell_against_long_acknowledgement_can_override_cap_fail_when_long_hedge_exists(
        self,
        snapshot_mock,
        positions_mock,
        execute_mock,
    ):
        snapshot_mock.return_value = {
            "candidate": {
                "action_type": "SELL_AGAINST_LONG",
                "allowed": True,
                "hedge_validity": "SAME_EXPIRY_FULL_HEDGE",
                "source_position": {"tradingsymbol": "NIFTY2681825200CE"},
                "orders": [
                    {
                        "exchange": "NFO",
                        "tradingsymbol": "NIFTY2681824800CE",
                        "quantity": 195,
                        "transaction_type": "SELL",
                        "product": "NRML",
                        "order_type": "LIMIT",
                        "price": 34.10,
                        "validity": "DAY",
                    }
                ],
            },
            "risk_cap": {"cap_status": "FAIL", "cap_remaining": -11351},
        }
        positions_mock.return_value = [{"tradingsymbol": "NIFTY2681825200CE", "quantity": 195}]
        execute_mock.return_value = [{"status": "LIVE_SENT"}]

        with patch.object(app.kite_orders, "kite_client", return_value=object()):
            result = app.place_nifty_position_action_order(
                "NIFTY2681825200CE",
                "SELL_AGAINST_LONG",
                "SAME_EXPIRY",
                400,
                195,
                "BID",
                True,
            )

        self.assertEqual(result, [{"status": "LIVE_SENT"}])
        execute_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
