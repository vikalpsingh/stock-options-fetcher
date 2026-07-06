from datetime import date
import unittest
from unittest.mock import patch

import app


class NiftyExistingHedgeReuseTest(unittest.TestCase):
    def setUp(self):
        self.expiry = date(2026, 7, 28)
        self.spot = 24098.65
        self.config = {
            **app.NIFTY_INCOME_DEFAULT_CONFIG,
            "lot_size": 65,
            "strike_rounding": 100,
            "manual_pair_sell_markup_percent": 20.0,
            "use_existing_hedge_positions": True,
        }

    def _coverage(self, pe=True, ce=True, expiry=None, pe_qty=65, ce_qty=65):
        expiry = expiry or self.expiry
        coverage = app._empty_nifty_long_hedge_coverage(65)
        if pe:
            coverage["long_pe"] = {
                "exchange": "NFO",
                "tradingsymbol": "NIFTYTEST22100PE",
                "quantity": pe_qty,
                "average_price": 8.0,
                "ltp": 7.5,
                "expiry": expiry.isoformat(),
                "strike": 22100.0,
                "option_type": "PE",
                "is_existing_hedge": True,
            }
        if ce:
            coverage["long_ce"] = {
                "exchange": "NFO",
                "tradingsymbol": "NIFTYTEST25500CE",
                "quantity": ce_qty,
                "average_price": 9.0,
                "ltp": 8.5,
                "expiry": expiry.isoformat(),
                "strike": 25500.0,
                "option_type": "CE",
                "is_existing_hedge": True,
            }
        coverage["has_long_pe"] = bool(coverage.get("long_pe"))
        coverage["has_long_ce"] = bool(coverage.get("long_ce"))
        coverage["coverage_status"] = app._nifty_hedge_coverage_status(
            coverage["has_long_pe"],
            coverage["has_long_ce"],
        )
        return coverage

    def _build(self, coverage, use_existing=True):
        with patch.object(
            app,
            "nifty_symbol_for_leg",
            side_effect=lambda _instruments, _expiry, strike, option_type: f"NIFTYTEST{int(strike)}{option_type}",
        ):
            return app.nifty_income_pair_orders_from_otm(
                [],
                self.expiry,
                self.spot,
                pe_otm_pct=6.5,
                ce_otm_pct=4.5,
                config=self.config,
                quote_map={},
                lots=1,
                include_pe=True,
                include_ce=True,
                include_cover=True,
                existing_hedge_coverage=coverage,
                use_existing_hedges=use_existing,
            )

    def test_both_existing_long_hedges_generate_only_sell_orders(self):
        orders, previews = self._build(self._coverage(pe=True, ce=True))

        self.assertEqual([row["transaction_type"] for row in orders], ["SELL", "SELL"])
        self.assertEqual(sum(1 for row in previews if row.get("existing_hedge")), 2)
        self.assertTrue(app.calculate_nifty_manual_pair_risk(previews)["defined_risk"])

    def test_existing_long_ce_only_adds_only_pe_buy_hedge(self):
        orders, previews = self._build(self._coverage(pe=False, ce=True))

        buy_orders = [row for row in orders if row["transaction_type"] == "BUY"]
        self.assertEqual(len(buy_orders), 1)
        self.assertEqual(buy_orders[0]["option_type"], "PE")
        self.assertTrue(any(row.get("existing_hedge") and row["option_type"] == "CE" for row in previews))

    def test_existing_long_pe_only_adds_only_ce_buy_hedge(self):
        orders, previews = self._build(self._coverage(pe=True, ce=False))

        buy_orders = [row for row in orders if row["transaction_type"] == "BUY"]
        self.assertEqual(len(buy_orders), 1)
        self.assertEqual(buy_orders[0]["option_type"], "CE")
        self.assertTrue(any(row.get("existing_hedge") and row["option_type"] == "PE" for row in previews))

    def test_no_existing_hedges_generates_both_buy_hedges(self):
        orders, _ = self._build(self._coverage(pe=False, ce=False))

        buy_orders = [row for row in orders if row["transaction_type"] == "BUY"]
        self.assertEqual({row["option_type"] for row in buy_orders}, {"PE", "CE"})

    def test_existing_hedge_wrong_expiry_is_ignored_by_detector(self):
        wrong_expiry = date(2026, 8, 25)
        positions = [
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTYTEST22100PE",
                "quantity": 65,
                "expiry": wrong_expiry,
                "strike": 22100,
                "option_type": "PE",
            }
        ]

        coverage = app.get_existing_nifty_long_hedges(self.expiry, 65, positions=positions)

        self.assertEqual(coverage["coverage_status"], "NONE")
        self.assertFalse(coverage["has_long_pe"])

    def test_existing_hedge_insufficient_quantity_is_ignored(self):
        positions = [
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTYTEST25500CE",
                "quantity": 10,
                "expiry": self.expiry,
                "strike": 25500,
                "option_type": "CE",
            }
        ]

        coverage = app.get_existing_nifty_long_hedges(self.expiry, 65, positions=positions)

        self.assertEqual(coverage["coverage_status"], "NONE")
        self.assertTrue(coverage["warnings"])

    def test_live_mode_blocks_uncovered_sell_when_cover_disabled(self):
        with patch.object(app, "kite_profile_nifty_income_enabled", return_value=True), patch.object(
            app,
            "nifty_income_manual_pair_snapshot",
            return_value={
                "missing_ltp": [],
                "dynamic_hedge_allowed": True,
                "uncovered_sides": ["CE"],
                "naked_live_allowed": False,
                "risk_reward_status": "OK",
                "orders": [],
            },
        ):
            with self.assertRaises(PermissionError):
                app.place_nifty_income_manual_pair(5.5, 5.5, include_cover=False)


if __name__ == "__main__":
    unittest.main()
