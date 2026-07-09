import unittest
from unittest.mock import patch

import app


class NiftyIndividualSellTest(unittest.TestCase):
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
        )
        execute_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
