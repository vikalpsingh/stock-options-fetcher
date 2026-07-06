import unittest

from nifty_options_engine.market_regime import classify_nifty_market_regime
from nifty_options_engine.order_builder import build_order_intents, order_intents_to_csv_rows
from nifty_options_engine.order_executor import place_nifty_orders
from nifty_options_engine.risk_validator import validate_nifty_strategy


def spread_strategy():
    return {
        "strategy_id": "TEST",
        "selected_strategy": "BULL_PUT_SPREAD",
        "spread_width_points": 500,
        "net_credit_points": 50,
        "legs": [
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTY26JUL22500PE",
                "transaction_type": "SELL",
                "quantity": 65,
                "price": 50,
                "ltp": 50,
                "bid": 49,
                "ask": 52,
                "strike": 22500,
            },
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTY26JUL22000PE",
                "transaction_type": "BUY",
                "quantity": 65,
                "price": 10,
                "ltp": 10,
                "bid": 9,
                "ask": 11,
                "strike": 22000,
            },
        ],
    }


class NiftyOptionsEngineTests(unittest.TestCase):
    def test_regime_above_20ema_selects_bull_put_spread(self):
        result = classify_nifty_market_regime({"nifty_spot": 24000, "ema20": 23800, "ema50": 23600, "rsi": 55, "india_vix": 15})
        self.assertEqual(result["selected_strategy"], "BULL_PUT_SPREAD")

    def test_regime_below_20ema_selects_bear_call_spread(self):
        result = classify_nifty_market_regime({"nifty_spot": 23600, "ema20": 23800, "ema50": 24000, "rsi": 45, "india_vix": 15})
        self.assertEqual(result["selected_strategy"], "BEAR_CALL_SPREAD")

    def test_validator_rejects_naked_short(self):
        strategy = spread_strategy()
        strategy["legs"] = [strategy["legs"][0]]
        result = validate_nifty_strategy(strategy, config={"disallow_naked_short_options": True})
        self.assertFalse(result["allowed"])
        self.assertIn("NAKED_SHORT_OPTION_BLOCKED", result["skip_reason"])

    def test_validator_rejects_credit_below_8pct(self):
        strategy = spread_strategy()
        strategy["net_credit_points"] = 25
        result = validate_nifty_strategy(strategy, config={"min_credit_pct_of_spread_width": 8.0})
        self.assertFalse(result["allowed"])
        self.assertIn("CREDIT_BELOW_MINIMUM", result["skip_reason"])

    def test_order_builder_places_buy_hedge_before_sell_short(self):
        intents = build_order_intents(spread_strategy())
        self.assertEqual([intent.transaction_type for intent in intents], ["BUY", "SELL"])
        self.assertEqual(intents[0].tradingsymbol, "NIFTY26JUL22000PE")

    def test_csv_format_remains_kite_compatible(self):
        rows = order_intents_to_csv_rows(build_order_intents(spread_strategy()))
        self.assertEqual(
            list(rows[0].keys()),
            ["exchange", "tradingsymbol", "quantity", "transaction_type", "product", "order_type", "price", "validity"],
        )

    def test_suggestion_only_does_not_place_live_order(self):
        result = place_nifty_orders(build_order_intents(spread_strategy()), "SUGGESTION_ONLY")
        self.assertFalse(result["placed"])
        self.assertEqual(result["status"], "SUGGESTION_ONLY")

    def test_live_confirmed_requires_manual_confirmation(self):
        result = place_nifty_orders(build_order_intents(spread_strategy()), "LIVE_CONFIRMED", live_order_enabled=True, manual_confirmation=False)
        self.assertFalse(result["placed"])
        self.assertEqual(result["status"], "BLOCKED_CONFIRMATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
