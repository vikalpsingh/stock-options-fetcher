import unittest

from nifty_options_engine.workflow import (
    build_trade_unlock_panel,
    dynamic_yield_gate,
    scan_nifty_spread_alternatives,
    validate_active_nifty_hedges,
    validate_nifty_data_quality,
)


class NiftyWorkflowTests(unittest.TestCase):
    def test_low_vix_exception_lowers_yield_gate_when_all_safety_checks_pass(self):
        result = dynamic_yield_gate(
            india_vix=10.8,
            credit_pct_of_spread_width=8.5,
            stop_loss_credit_multiple=1.4,
            delta_available=True,
            expected_move_available=True,
            confidence_score=76,
            hard_blocks=[],
        )

        self.assertTrue(result["low_vix_exception_used"])
        self.assertEqual(result["dynamic_min_yield"], 0.65)

    def test_low_vix_exception_not_used_when_credit_is_weak(self):
        result = dynamic_yield_gate(
            india_vix=10.8,
            credit_pct_of_spread_width=6.0,
            stop_loss_credit_multiple=1.4,
            delta_available=True,
            expected_move_available=True,
            confidence_score=76,
            hard_blocks=[],
        )

        self.assertFalse(result["low_vix_exception_used"])
        self.assertEqual(result["dynamic_min_yield"], 0.80)
        self.assertFalse(result["checks"]["credit_ok"])

    def test_trade_unlock_panel_reports_required_credit_gap(self):
        result = build_trade_unlock_panel(
            summary={"net_credit": 20, "premium_yield_on_margin_pct": 0.55, "vix": 14},
            suggestion={"allowed": False, "skip_reason": "CREDIT_BELOW_MINIMUM"},
            candidate_previews=[
                {
                    "spread_width_points": 500,
                    "delta": 0.14,
                    "expected_move_multiple": 1.4,
                }
            ],
            confidence_score={"score": 72, "hard_blocks": []},
            no_trade_decision={},
        )

        self.assertTrue(result["blocked"])
        self.assertEqual(result["required_credit_points"], 40)
        self.assertEqual(result["credit_gap_points"], 20)

    def test_spread_scanner_ranks_allowed_candidate_first(self):
        rows = [
            {"selected_strategy": "BULL_PUT_SPREAD", "spread_width_points": 300, "net_credit": 15, "oi": 20000, "confidence_score": 85},
            {"selected_strategy": "BULL_PUT_SPREAD", "spread_width_points": 500, "net_credit": 50, "oi": 20000, "confidence_score": 80},
        ]

        result = scan_nifty_spread_alternatives({"expiry": "2026-07-28"}, rows)

        self.assertTrue(result[0]["allowed"])
        self.assertEqual(result[0]["width"], 500)
        self.assertGreaterEqual(result[0]["credit_pct_of_width"], 8)

    def test_spread_scanner_rejects_poor_liquidity(self):
        result = scan_nifty_spread_alternatives(
            {"expiry": "2026-07-28"},
            [{"selected_strategy": "BEAR_CALL_SPREAD", "spread_width_points": 500, "net_credit": 50, "oi": 0, "volume": 0}],
        )

        self.assertFalse(result[0]["allowed"])
        self.assertEqual(result[0]["liquidity_status"], "REVIEW")

    def test_data_quality_good_when_required_fields_available(self):
        result = validate_nifty_data_quality(
            {
                "nifty_spot": 24000,
                "india_vix": 14,
                "option_ltp": True,
                "bid_ask": True,
                "sell_delta": True,
                "hedge_delta": True,
                "expected_move": 220,
                "expiry": "2026-07-28",
                "instrument_symbol": True,
                "margin_estimate": 40000,
            }
        )

        self.assertEqual(result["status"], "GOOD")
        self.assertTrue(result["live_order_enabled"])

    def test_data_quality_missing_delta_disables_live_order(self):
        result = validate_nifty_data_quality(
            {
                "nifty_spot": 24000,
                "india_vix": 14,
                "option_ltp": True,
                "bid_ask": True,
                "expected_move": 220,
                "expiry": "2026-07-28",
                "instrument_symbol": True,
                "margin_estimate": 40000,
            }
        )

        self.assertEqual(result["status"], "PARTIAL")
        self.assertFalse(result["live_order_enabled"])
        self.assertIn("sell_delta", result["missing_fields"])

    def test_hedge_integrity_blocks_unhedged_short(self):
        result = validate_active_nifty_hedges(
            [
                {"tradingsymbol": "NIFTY26JUL22500PE", "quantity": -65, "expiry": "2026-07-28"},
            ]
        )

        self.assertEqual(result["status"], "CRITICAL")
        self.assertTrue(result["block_new_entries"])
        self.assertEqual(result["rows"][0]["hedge_status"], "UNHEDGED_SHORT")

    def test_hedge_integrity_allows_matching_long_hedge(self):
        result = validate_active_nifty_hedges(
            [
                {"tradingsymbol": "NIFTY26JUL22500PE", "quantity": -65, "expiry": "2026-07-28"},
                {"tradingsymbol": "NIFTY26JUL22000PE", "quantity": 65, "expiry": "2026-07-28"},
                {"tradingsymbol": "NIFTY26JUL25200CE", "quantity": -65, "expiry": "2026-07-28"},
                {"tradingsymbol": "NIFTY26JUL25700CE", "quantity": 65, "expiry": "2026-07-28"},
            ]
        )

        self.assertEqual(result["status"], "OK")
        self.assertFalse(result["block_new_entries"])
        self.assertTrue(all(row["hedge_status"] == "OK" for row in result["rows"]))

    def test_hedge_integrity_flags_insufficient_quantity(self):
        result = validate_active_nifty_hedges(
            [
                {"tradingsymbol": "NIFTY26JUL25200CE", "quantity": -130, "expiry": "2026-07-28"},
                {"tradingsymbol": "NIFTY26JUL25700CE", "quantity": 65, "expiry": "2026-07-28"},
            ]
        )

        self.assertEqual(result["status"], "HIGH")
        self.assertFalse(result["block_new_entries"])
        self.assertEqual(result["rows"][0]["hedge_status"], "PARTIAL_HEDGE")


if __name__ == "__main__":
    unittest.main()
