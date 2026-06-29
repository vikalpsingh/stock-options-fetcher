from datetime import date
import unittest
from unittest.mock import patch

import app


class NiftyPairProtectiveBuyPricingTest(unittest.TestCase):
    def test_nifty_pair_protective_buy_legs_are_discounted_below_ltp(self):
        expiry = date(2026, 7, 28)
        spot = 24098.65
        config = {
            "lot_size": 65,
            "strike_rounding": 100,
            "manual_pair_sell_markup_percent": 20.0,
        }
        quote_map = {
            "NFO:NIFTYTEST22500PE": {"last_price": 29.05, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST22200PE": {"last_price": 20.95, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST25200CE": {"last_price": 39.85, "oi": 20_000, "volume": 100},
            "NFO:NIFTYTEST25500CE": {"last_price": 18.10, "oi": 20_000, "volume": 100},
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
        self.assertEqual(by_symbol["NIFTYTEST22500PE"]["price"], 34.9)
        self.assertEqual(by_symbol["NIFTYTEST25200CE"]["price"], 47.85)
        self.assertEqual(by_symbol["NIFTYTEST22200PE"]["price"], 16.75)
        self.assertEqual(by_symbol["NIFTYTEST25500CE"]["price"], 14.45)
        self.assertEqual(by_symbol["NIFTYTEST22200PE"]["protective_buy_discount_percent"], 20.0)
        self.assertEqual(by_symbol["NIFTYTEST25500CE"]["protective_buy_discount_percent"], 20.0)
        self.assertAlmostEqual(risk["net_credit"], 3350.75)
        self.assertAlmostEqual(risk["margin_required"], 18320.25)
        self.assertAlmostEqual(risk["return_on_margin_pct"], 18.289870225570608, places=5)

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
