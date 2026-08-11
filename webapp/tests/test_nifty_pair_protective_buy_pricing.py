from datetime import date
import unittest
from unittest.mock import patch

import app


class NiftyPairProtectiveBuyPricingTest(unittest.TestCase):
    def test_nifty_pair_uses_bounded_otm_hedges_and_tick_safe_quote_limits(self):
        expiry = date(2026, 7, 28)
        spot = 24098.65
        config = {
            "lot_size": 65,
            "strike_rounding": 100,
            "manual_pair_sell_markup_percent": 20.0,
        }
        quote_map = {
            "NFO:NIFTYTEST23200PE": {"last_price": 29.05, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST22900PE": {"last_price": 20.95, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST25000CE": {"last_price": 39.85, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST25300CE": {"last_price": 18.10, "oi": 20_000, "volume": 100},
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
            )

        by_symbol = {row["tradingsymbol"]: row for row in orders}
        risk = app.calculate_nifty_manual_pair_risk(orders)
        self.assertEqual(by_symbol["NIFTYTEST23200PE"]["price"], 27.55)
        self.assertEqual(by_symbol["NIFTYTEST25000CE"]["price"], 37.85)
        self.assertEqual(by_symbol["NIFTYTEST22900PE"]["price"], 22.0)
        self.assertEqual(by_symbol["NIFTYTEST25300CE"]["price"], 19.05)
        self.assertEqual(by_symbol["NIFTYTEST22900PE"]["execution_price_mode"], "ASK_PLUS_2_PERCENT")
        self.assertEqual(by_symbol["NIFTYTEST25300CE"]["execution_price_mode"], "ASK_PLUS_2_PERCENT")
        self.assertLess(by_symbol["NIFTYTEST23200PE"]["otm_pct"], 4.0)
        self.assertLess(by_symbol["NIFTYTEST25000CE"]["otm_pct"], 4.0)
        self.assertLess(by_symbol["NIFTYTEST22900PE"]["otm_pct"], 5.5)
        self.assertLess(by_symbol["NIFTYTEST25300CE"]["otm_pct"], 5.5)
        self.assertAlmostEqual(risk["net_credit"], 1582.75)
        self.assertAlmostEqual(risk["margin_required"], 19139.25)
        self.assertAlmostEqual(risk["return_on_margin_pct"], 8.26965528952284, places=5)

    def test_nfo_price_protection_keeps_valid_discounted_buy_limit(self):
        order = {
            "exchange": "NFO",
            "tradingsymbol": "NIFTYTEST22200PE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "price": 16.75,
            "_csv_price": 16.75,
        }
        quote = {
            "last_price": 20.95,
            "depth": {
                "buy": [{"price": 20.90}],
                "sell": [{"price": 21.00}],
            },
        }

        validation = app.calculateSafeLimitPrice(order, quote)

        self.assertTrue(validation["ok"])
        self.assertEqual(validation["price"], 16.75)
        self.assertFalse(validation["auto_adjusted"])


if __name__ == "__main__":
    unittest.main()
