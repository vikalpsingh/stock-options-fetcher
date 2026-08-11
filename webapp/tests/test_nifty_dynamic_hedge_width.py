from datetime import date
import unittest
from unittest.mock import patch

import app


class NiftyDynamicHedgeWidthTest(unittest.TestCase):
    def test_dynamic_hedge_width_vix_boundaries(self):
        cases = [
            (None, 300, "ALLOW", True),
            (13.99, 300, "ALLOW", True),
            (14.0, 400, "ALLOW", True),
            (17.99, 400, "ALLOW", True),
            (18.0, 500, "ALLOW", True),
            (21.99, 500, "ALLOW", True),
            (22.0, 600, "ALLOW_REDUCED_SIZE", True),
            (24.0, 600, "ALLOW_REDUCED_SIZE", True),
            (24.01, 700, "SKIP_OR_MANUAL_REVIEW", False),
        ]

        for vix, expected_width, expected_action, expected_allowed in cases:
            with self.subTest(vix=vix):
                decision = app.get_dynamic_hedge_width(vix)
                self.assertEqual(decision["hedge_width_points"], expected_width)
                self.assertEqual(decision["action"], expected_action)
                self.assertEqual(decision["allowed"], expected_allowed)

    def test_nifty_pair_caps_high_vix_hedges_inside_credit_zone(self):
        expiry = date(2026, 7, 28)
        spot = 24098.65
        config = {
            "lot_size": 65,
            "strike_rounding": 100,
            "manual_pair_sell_markup_percent": 20.0,
        }
        quote_map = {
            "NFO:NIFTYTEST23200PE": {"last_price": 29.05, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST22800PE": {"last_price": 12.00, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST25000CE": {"last_price": 39.85, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST25400CE": {"last_price": 10.00, "oi": 20_000, "volume": 100},
        }

        with patch.object(
            app,
            "nifty_symbol_for_leg",
            side_effect=lambda _instruments, _expiry, strike, option_type: f"NIFTYTEST{int(strike)}{option_type}",
        ):
            orders, _ = app.nifty_income_pair_orders_from_otm(
                [],
                expiry,
                spot,
                pe_otm_pct=6.5,
                ce_otm_pct=4.5,
                config=config,
                quote_map=quote_map,
                lots=1,
                include_pe=True,
                include_ce=True,
                include_cover=True,
                india_vix=18.0,
            )

        by_symbol = {row["tradingsymbol"]: row for row in orders}
        self.assertIn("NIFTYTEST22800PE", by_symbol)
        self.assertIn("NIFTYTEST25400CE", by_symbol)
        self.assertEqual(by_symbol["NIFTYTEST22800PE"]["transaction_type"], "BUY")
        self.assertEqual(by_symbol["NIFTYTEST25400CE"]["transaction_type"], "BUY")
        self.assertEqual(by_symbol["NIFTYTEST22800PE"]["hedge_width_points"], 500)
        self.assertEqual(by_symbol["NIFTYTEST25400CE"]["hedge_width_points"], 500)
        self.assertEqual(by_symbol["NIFTYTEST22800PE"]["bounded_hedge_width_points"], 400)
        self.assertEqual(by_symbol["NIFTYTEST25400CE"]["bounded_hedge_width_points"], 400)
        self.assertLess(by_symbol["NIFTYTEST22800PE"]["otm_pct"], 5.5)
        self.assertLess(by_symbol["NIFTYTEST25400CE"]["otm_pct"], 5.5)
        self.assertEqual(by_symbol["NIFTYTEST23200PE"]["vix_hedge_regime"], "HIGH_VIX")

    def test_very_high_vix_reduces_lots_for_nifty_pair(self):
        expiry = date(2026, 7, 28)
        with patch.object(
            app,
            "nifty_symbol_for_leg",
            side_effect=lambda _instruments, _expiry, strike, option_type: f"NIFTYTEST{int(strike)}{option_type}",
        ):
            orders, _ = app.nifty_income_pair_orders_from_otm(
                [],
                expiry,
                24098.65,
                pe_otm_pct=6.5,
                ce_otm_pct=4.5,
                config={"lot_size": 65, "strike_rounding": 100},
                quote_map={},
                lots=2,
                include_pe=True,
                include_ce=False,
                include_cover=True,
                india_vix=22.0,
            )

        self.assertTrue(orders)
        self.assertTrue(all(row["quantity"] == 65 for row in orders))
        self.assertTrue(all(row["lots"] == 1 for row in orders))
        self.assertTrue(all(row["original_lots"] == 2 for row in orders))
        self.assertTrue(all(row["hedge_action"] == "ALLOW_REDUCED_SIZE" for row in orders))


if __name__ == "__main__":
    unittest.main()
