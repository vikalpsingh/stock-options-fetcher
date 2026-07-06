import unittest
from datetime import date

from nifty_no_trade import evaluate_nifty_no_trade_regime


def base_inputs(**overrides):
    values = {
        "india_vix": 15.0,
        "premium_yield_on_margin_pct": 1.1,
        "event_calendar": [],
        "current_date": date(2026, 6, 30).isoformat(),
        "trend_regime": "SIDEWAYS",
        "breakout_status": False,
        "breakdown_status": False,
        "consecutive_stop_losses_this_month": 0,
        "monthly_nifty_pnl": 0,
        "nifty_strategy_margin": 100000,
        "monthly_loss_pct_of_nifty_margin": 0,
    }
    values.update(overrides)
    return values


class NiftyNoTradeRegimeTests(unittest.TestCase):
    def test_allows_clean_setup(self):
        decision = evaluate_nifty_no_trade_regime(base_inputs())

        self.assertTrue(decision.allowed)
        self.assertFalse(decision.no_trade)
        self.assertEqual(decision.blocking_reason, None)

    def test_blocks_low_vix_poor_premium_environment(self):
        decision = evaluate_nifty_no_trade_regime(base_inputs(india_vix=10.9))

        self.assertFalse(decision.allowed)
        self.assertIn("NO_TRADE_LOW_VIX_POOR_PREMIUM", decision.reasons)

    def test_blocks_high_vix_uncertainty(self):
        decision = evaluate_nifty_no_trade_regime(base_inputs(india_vix=24.1))

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.blocking_reason, "NO_TRADE_HIGH_VIX_UNCERTAINTY")

    def test_blocks_low_premium_yield_on_margin(self):
        decision = evaluate_nifty_no_trade_regime(base_inputs(premium_yield_on_margin_pct=0.79))

        self.assertFalse(decision.allowed)
        self.assertIn("NO_TRADE_POOR_PREMIUM_YIELD", decision.reasons)

    def test_blocks_major_event_within_three_trading_days(self):
        decision = evaluate_nifty_no_trade_regime(
            base_inputs(
                event_calendar=[
                    {"event_type": "RBI_POLICY", "trading_days_to_event": 2},
                ]
            )
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.blocking_reason, "NO_TRADE_MAJOR_EVENT_WITHIN_3_DAYS")
        self.assertEqual(decision.inputs_snapshot["next_major_event"]["event_type"], "RBI_POLICY")

    def test_blocks_strong_breakout(self):
        decision = evaluate_nifty_no_trade_regime(
            base_inputs(trend_regime="STRONG_BULLISH", breakout_status=True)
        )

        self.assertFalse(decision.allowed)
        self.assertIn("NO_TRADE_STRONG_BREAKOUT", decision.reasons)

    def test_blocks_strong_breakdown(self):
        decision = evaluate_nifty_no_trade_regime(
            base_inputs(trend_regime="STRONG_BEARISH", breakdown_status=True)
        )

        self.assertFalse(decision.allowed)
        self.assertIn("NO_TRADE_STRONG_BREAKDOWN", decision.reasons)

    def test_blocks_two_consecutive_stop_losses(self):
        decision = evaluate_nifty_no_trade_regime(
            base_inputs(consecutive_stop_losses_this_month=2)
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.blocking_reason, "NO_TRADE_TWO_CONSECUTIVE_STOP_LOSSES")
        self.assertFalse(decision.can_manual_override)

    def test_blocks_monthly_loss_limit(self):
        decision = evaluate_nifty_no_trade_regime(
            base_inputs(monthly_nifty_pnl=-5100, monthly_loss_pct_of_nifty_margin=-5.1)
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.blocking_reason, "NO_TRADE_MONTHLY_LOSS_LIMIT_REACHED")

    def test_missing_noncritical_data_warns_without_crash(self):
        decision = evaluate_nifty_no_trade_regime(
            base_inputs(india_vix=None, premium_yield_on_margin_pct=None)
        )

        self.assertTrue(decision.allowed)
        self.assertGreaterEqual(len(decision.warnings), 2)


if __name__ == "__main__":
    unittest.main()
