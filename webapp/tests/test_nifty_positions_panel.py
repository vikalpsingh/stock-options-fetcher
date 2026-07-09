import unittest

import app


class NiftyPositionsPanelTest(unittest.TestCase):
    def test_best_positions_panel_follows_decision_gate_and_uses_existing_review_flow(self):
        candidate = {
            "side": "PE",
            "expiry_date": "2026-08-04",
            "tradingsymbol": "NIFTY2680422700PE",
            "hedge_symbol": "NIFTY2680422400PE",
            "strike": 22700,
            "nifty_spot": 24022.70,
            "otm_pct": 5.51,
            "mmi_selected_otm_pct": 5.50,
            "option_ltp": 34.65,
            "bid": 34.65,
            "ask": 35.70,
            "oi": 32175,
            "change_oi": 32175,
            "volume": 38675,
            "premium_value_per_lot": 2252.25,
            "max_gain_opportunity": 630.50,
            "margin_required": 36000,
            "credit_pct_of_spread_width": 10.0,
            "spread_width_points": 300,
            "credit_quality": "GOOD",
            "premium_yield_on_margin_pct": 1.75,
            "risk_status": "GREEN",
        }
        snapshot = {
            "config": {
                "manual_pair_sell_markup_percent": 20.0,
                "entry_time": "15:16",
                "time_exit_time": "14:59",
                "execution_mode": "SUGGESTION_ONLY",
            },
            "state": {},
            "summary": {},
            "positions": [],
            "suggestion": {
                "allowed": True,
                "pe_otm_pct": 5.5,
                "ce_otm_pct": 5.5,
            },
            "candidate_previews": [candidate],
            "warnings": [],
        }

        rendered = app.render_nifty_income_panel(
            app.PageState(active_tab="nifty-income", nifty_income_snapshot=snapshot)
        )

        command_index = rendered.index("Tactical Spread Command Center")
        gate_index = rendered.index("Decision Gate")
        positions_index = rendered.index("Best NIFTY PE + CE SELL Positions")
        self.assertLess(command_index, gate_index)
        self.assertLess(gate_index, positions_index)
        self.assertEqual(rendered.count('id="nifty-pair-open"'), 1)
        self.assertIn(">Place nifty positions</button>", rendered)
        self.assertIn("SELL limits default to 20.00% above fresh Kite LTP", rendered)
        self.assertIn("NIFTY PE + CE SELL Position Review", rendered)
        self.assertIn("Individual PE or CE SELL", rendered)
        self.assertIn("Review &amp; Start 10s will unlock", rendered)
        self.assertNotIn("Build Tactical Spread Order", rendered)


if __name__ == "__main__":
    unittest.main()
