from datetime import date
import unittest
from unittest.mock import patch

import app


def confidence_inputs(**overrides):
    values = {
        "selected_strategy": "BULL_PUT_SPREAD",
        "mmi": 65,
        "india_vix": 15,
        "trend_regime": "BULLISH",
        "pe_delta": 0.10,
        "ce_delta": None,
        "expected_move_multiple_pe": 1.6,
        "expected_move_multiple_ce": None,
        "premium_yield_on_margin_pct": 1.6,
        "oi_validation_status": "GOOD",
        "breadth_regime": "BULLISH",
        "event_risk_status": "OK",
        "hard_block_reasons": [],
    }
    values.update(overrides)
    return values


class NiftyConfidenceScoreTests(unittest.TestCase):
    def test_perfect_bull_put_setup_full_size(self):
        decision = app.calculate_nifty_confidence_score(confidence_inputs())

        self.assertGreaterEqual(decision.score, 85)
        self.assertEqual(decision.label, "EXCELLENT")
        self.assertEqual(decision.action, "FULL_SIZE")
        self.assertEqual(decision.position_size_multiplier, 1.0)

    def test_perfect_iron_condor_neutral_setup_full_size(self):
        decision = app.calculate_nifty_confidence_score(
            confidence_inputs(
                selected_strategy="IRON_CONDOR",
                mmi=50,
                trend_regime="SIDEWAYS",
                pe_delta=0.10,
                ce_delta=0.11,
                expected_move_multiple_pe=1.6,
                expected_move_multiple_ce=1.7,
                breadth_regime="NEUTRAL",
            )
        )

        self.assertGreaterEqual(decision.score, 85)
        self.assertEqual(decision.action, "FULL_SIZE")

    def test_good_setup_returns_half_size(self):
        decision = app.calculate_nifty_confidence_score(
            confidence_inputs(
                mmi=50,
                trend_regime="MIXED",
                pe_delta=0.14,
                expected_move_multiple_pe=1.3,
                premium_yield_on_margin_pct=1.1,
                oi_validation_status="NEUTRAL",
                breadth_regime="NEUTRAL",
            )
        )

        self.assertGreaterEqual(decision.score, 70)
        self.assertLess(decision.score, 85)
        self.assertEqual(decision.action, "HALF_SIZE")
        self.assertEqual(decision.position_size_multiplier, 0.5)

    def test_cautious_setup_is_preview_only(self):
        decision = app.calculate_nifty_confidence_score(
            confidence_inputs(
                mmi=50,
                india_vix=19,
                trend_regime="MIXED",
                pe_delta=0.14,
                expected_move_multiple_pe=1.3,
                premium_yield_on_margin_pct=0.9,
                oi_validation_status="NEUTRAL",
                breadth_regime="NEUTRAL",
            )
        )

        self.assertGreaterEqual(decision.score, 60)
        self.assertLess(decision.score, 70)
        self.assertEqual(decision.action, "PREVIEW_ONLY")
        self.assertEqual(decision.position_size_multiplier, 0.0)

    def test_low_score_no_trade_without_hard_block(self):
        decision = app.calculate_nifty_confidence_score(
            confidence_inputs(
                mmi=50,
                india_vix=23,
                trend_regime="MIXED",
                pe_delta=0.18,
                expected_move_multiple_pe=1.1,
                premium_yield_on_margin_pct=0.9,
                oi_validation_status="RED",
                breadth_regime="BEARISH",
            )
        )

        self.assertLess(decision.score, 60)
        self.assertEqual(decision.action, "NO_TRADE")

    def test_low_vix_hard_block(self):
        decision = app.calculate_nifty_confidence_score(confidence_inputs(india_vix=10.9))

        self.assertIn("LOW_VIX", decision.hard_blocks)
        self.assertEqual(decision.action, "NO_TRADE")

    def test_high_vix_hard_block(self):
        decision = app.calculate_nifty_confidence_score(confidence_inputs(india_vix=24.1))

        self.assertIn("HIGH_VIX", decision.hard_blocks)
        self.assertEqual(decision.action, "NO_TRADE")

    def test_delta_above_twenty_hard_block(self):
        decision = app.calculate_nifty_confidence_score(confidence_inputs(pe_delta=0.21))

        self.assertIn("DELTA_TOO_HIGH", decision.hard_blocks)
        self.assertEqual(decision.action, "NO_TRADE")

    def test_expected_move_too_close_hard_block(self):
        decision = app.calculate_nifty_confidence_score(confidence_inputs(expected_move_multiple_pe=0.99))

        self.assertIn("EXPECTED_MOVE_TOO_CLOSE", decision.hard_blocks)
        self.assertEqual(decision.action, "NO_TRADE")

    def test_poor_premium_yield_hard_block(self):
        decision = app.calculate_nifty_confidence_score(confidence_inputs(premium_yield_on_margin_pct=0.79))

        self.assertIn("POOR_PREMIUM_YIELD", decision.hard_blocks)
        self.assertEqual(decision.action, "NO_TRADE")

    def test_major_event_hard_block(self):
        decision = app.calculate_nifty_confidence_score(confidence_inputs(event_risk_status="MAJOR_WITHIN_3_DAYS"))

        self.assertIn("EVENT_RISK", decision.hard_blocks)
        self.assertEqual(decision.action, "NO_TRADE")

    def test_strategy_against_strong_trend_hard_block(self):
        decision = app.calculate_nifty_confidence_score(
            confidence_inputs(selected_strategy="BEAR_CALL_SPREAD", mmi=35, trend_regime="STRONG_BULLISH", ce_delta=0.10)
        )

        self.assertIn("TREND_AGAINST_STRATEGY", decision.hard_blocks)
        self.assertEqual(decision.action, "NO_TRADE")

    def test_hard_block_overrides_high_numeric_score(self):
        decision = app.calculate_nifty_confidence_score(
            confidence_inputs(hard_block_reasons=["MONTHLY_LOSS_LIMIT"])
        )

        self.assertGreaterEqual(decision.score, 85)
        self.assertEqual(decision.label, "NO_TRADE")
        self.assertEqual(decision.action, "NO_TRADE")

    def test_missing_inputs_create_warnings_and_partial_scores(self):
        decision = app.calculate_nifty_confidence_score(
            confidence_inputs(mmi=None, india_vix=None, oi_validation_status=None)
        )

        self.assertIn("MMI missing.", decision.warnings)
        self.assertIn("India VIX missing.", decision.warnings)
        self.assertIn("Open interest validation missing.", decision.warnings)
        self.assertGreater(decision.score, 0)

    def test_half_size_multiplier_reduces_nifty_pair_lots(self):
        expiry = date(2026, 7, 28)
        with patch.object(
            app,
            "nifty_symbol_for_leg",
            side_effect=lambda _instruments, _expiry, strike, option_type: f"NIFTYTEST{int(strike)}{option_type}",
        ):
            orders, _ = app.nifty_income_pair_orders_from_otm(
                [],
                expiry,
                24000,
                pe_otm_pct=5.5,
                ce_otm_pct=5.5,
                config={"lot_size": 65, "strike_rounding": 100, "manual_pair_sell_markup_percent": 20},
                quote_map={},
                lots=3,
                include_pe=True,
                include_ce=True,
                include_cover=True,
                india_vix=15,
                confidence_size_multiplier=0.5,
            )

        self.assertTrue(orders)
        self.assertTrue(all(row["lots"] == 1 for row in orders))
        self.assertTrue(all(row["quantity"] == 65 for row in orders))


if __name__ == "__main__":
    unittest.main()
