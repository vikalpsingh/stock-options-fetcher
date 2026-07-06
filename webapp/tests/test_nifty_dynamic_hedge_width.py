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

    def test_nifty_pair_uses_dynamic_width_for_pe_and_ce_hedges(self):
        expiry = date(2026, 7, 28)
        spot = 24098.65
        config = {
            "lot_size": 65,
            "strike_rounding": 100,
            "manual_pair_sell_markup_percent": 20.0,
        }
        quote_map = {
            "NFO:NIFTYTEST22500PE": {"last_price": 29.05, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST22000PE": {"last_price": 12.00, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST25200CE": {"last_price": 39.85, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST25700CE": {"last_price": 10.00, "oi": 20_000, "volume": 100},
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
        self.assertIn("NIFTYTEST22000PE", by_symbol)
        self.assertIn("NIFTYTEST25700CE", by_symbol)
        self.assertEqual(by_symbol["NIFTYTEST22000PE"]["transaction_type"], "BUY")
        self.assertEqual(by_symbol["NIFTYTEST25700CE"]["transaction_type"], "BUY")
        self.assertEqual(by_symbol["NIFTYTEST22000PE"]["hedge_width_points"], 500)
        self.assertEqual(by_symbol["NIFTYTEST25700CE"]["hedge_width_points"], 500)
        self.assertEqual(by_symbol["NIFTYTEST22500PE"]["vix_hedge_regime"], "HIGH_VIX")

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
