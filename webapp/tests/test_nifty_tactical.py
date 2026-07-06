from datetime import date
import unittest

from nifty_tactical import (
    classify_nifty_market_regime,
    evaluate_nifty_tactical_spread_exit,
    select_nifty_tactical_strategy,
    select_spread_strikes_by_delta,
    tactical_orders_from_spreads,
    validate_nifty_income_allocation,
    validate_spread_credit_quality,
)


def chain(expiry=date(2026, 7, 28)):
    rows = []
    for option_type, strikes in {
        "PE": [(23000, 0.18, 62, 60, 65), (22800, 0.14, 58, 56, 59), (22300, 0.05, 10, 9, 11), (22100, 0.03, 6, 5, 7)],
        "CE": [(25000, 0.17, 64, 61, 66), (25200, 0.14, 58, 56, 59), (25700, 0.05, 10, 9, 11), (25900, 0.03, 6, 5, 7)],
    }.items():
        for strike, delta, ltp, bid, ask in strikes:
            rows.append(
                {
                    "expiry": expiry,
                    "option_type": option_type,
                    "strike": strike,
                    "delta": delta if option_type == "CE" else -delta,
                    "ltp": ltp,
                    "bid": bid,
                    "ask": ask,
                    "tradingsymbol": f"NIFTY26JUL{strike}{option_type}",
                }
            )
    return rows


class NiftyTacticalEngineTests(unittest.TestCase):
    def test_above_20ema_buy_on_dips_selects_bull_put_only(self):
        regime = classify_nifty_market_regime({"nifty_spot": 24000, "ema20": 23800, "ema50": 23500, "rsi": 55})
        decision = select_nifty_tactical_strategy({**regime, "nifty_spot": 24000, "nifty_20ema": 23800, "india_vix": 15})

        self.assertEqual(decision["selected_strategy"], "BULL_PUT_SPREAD")
        self.assertTrue(decision["allow_pe_spread"])
        self.assertFalse(decision["allow_ce_spread"])

    def test_below_20ema_sell_on_rise_selects_bear_call_only(self):
        regime = classify_nifty_market_regime({"nifty_spot": 23600, "ema20": 23800, "ema50": 24000, "rsi": 45})
        decision = select_nifty_tactical_strategy({**regime, "nifty_spot": 23600, "nifty_20ema": 23800, "india_vix": 15})

        self.assertEqual(decision["selected_strategy"], "BEAR_CALL_SPREAD")
        self.assertFalse(decision["allow_pe_spread"])
        self.assertTrue(decision["allow_ce_spread"])

    def test_sideways_selects_iron_condor(self):
        regime = classify_nifty_market_regime({"nifty_spot": 24000, "ema20": 23980, "ema50": 23950, "rsi": 52, "adx": 15})
        decision = select_nifty_tactical_strategy({**regime, "india_vix": 14})

        self.assertEqual(decision["selected_strategy"], "IRON_CONDOR")
        self.assertTrue(decision["allow_pe_spread"])
        self.assertTrue(decision["allow_ce_spread"])

    def test_breakout_day_returns_no_trade(self):
        regime = classify_nifty_market_regime(
            {"nifty_spot": 24550, "previous_20day_high": 24400, "intraday_change_pct": 1.2, "breadth_regime": "STRONG"}
        )
        decision = select_nifty_tactical_strategy({**regime, "india_vix": 15})

        self.assertEqual(decision["selected_strategy"], "NO_TRADE")

    def test_panic_fall_returns_no_trade(self):
        regime = classify_nifty_market_regime(
            {"intraday_change_pct": -1.4, "gap_pct": -0.8, "vix_intraday_change_pct": 12, "breadth_regime": "WEAK"}
        )
        decision = select_nifty_tactical_strategy({**regime, "india_vix": 18})

        self.assertEqual(decision["selected_strategy"], "NO_TRADE")

    def test_dte_outside_window_skips_trade(self):
        result = select_spread_strikes_by_delta(chain(date(2026, 7, 10)), "BULL_PUT_SPREAD", today=date(2026, 7, 1))

        self.assertFalse(result["accepted"])
        self.assertIn("21-35 DTE", result["reason"])

    def test_sell_delta_outside_band_rejected(self):
        bad_chain = [{**row, "delta": 0.25 if row["option_type"] == "CE" else -0.25} for row in chain()]
        result = select_spread_strikes_by_delta(bad_chain, "BULL_PUT_SPREAD", today=date(2026, 7, 1))

        self.assertFalse(result["accepted"])
        self.assertIn("short delta", result["reason"])

    def test_hedge_delta_nearest_farther_otm_selected(self):
        result = select_spread_strikes_by_delta(chain(), "BULL_PUT_SPREAD", today=date(2026, 7, 1))

        self.assertTrue(result["accepted"])
        spread = result["spreads"][0]
        self.assertEqual(spread["option_type"], "PE")
        self.assertLess(spread["hedge_strike"], spread["short_strike"])
        self.assertLessEqual(spread["hedge_delta"], 0.06)

    def test_credit_below_8pct_rejected(self):
        result = validate_spread_credit_quality({"spread_width_points": 500, "net_credit_points": 25})

        self.assertFalse(result["accepted"])
        self.assertEqual(result["credit_quality"], "REJECT")

    def test_500_point_40_credit_accepted(self):
        result = validate_spread_credit_quality({"spread_width_points": 500, "net_credit_points": 40})

        self.assertTrue(result["accepted"])
        self.assertEqual(result["credit_quality"], "ACCEPTABLE")

    def test_profit_booking_triggers_at_55pct_decay(self):
        result = evaluate_nifty_tactical_spread_exit({"entry_net_credit": 50}, {"current_spread_value": 22})

        self.assertTrue(result["target_hit"])
        self.assertEqual(result["exit_signal"], "BOOK_PROFIT")

    def test_stop_loss_triggers_at_175x_credit(self):
        result = evaluate_nifty_tactical_spread_exit({"entry_net_credit": 50}, {"current_spread_value": 88})

        self.assertTrue(result["stop_hit"])
        self.assertEqual(result["exit_signal"], "STOP_LOSS")

    def test_allocation_above_20_blocks_new_entries(self):
        result = validate_nifty_income_allocation(100000, 25000, 100000)

        self.assertFalse(result["allowed"])
        self.assertEqual(result["status"], "BLOCK")

    def test_bull_put_spread_generates_two_csv_rows(self):
        result = select_spread_strikes_by_delta(chain(), "BULL_PUT_SPREAD", today=date(2026, 7, 1))
        orders = tactical_orders_from_spreads(result)

        self.assertEqual(len(orders), 2)
        self.assertEqual([order["transaction_type"] for order in orders], ["BUY", "SELL"])
        self.assertEqual(list(orders[0].keys())[:8], ["exchange", "tradingsymbol", "quantity", "transaction_type", "product", "order_type", "price", "validity"])

    def test_bear_call_spread_generates_two_csv_rows(self):
        result = select_spread_strikes_by_delta(chain(), "BEAR_CALL_SPREAD", today=date(2026, 7, 1))
        orders = tactical_orders_from_spreads(result)

        self.assertEqual(len(orders), 2)

    def test_iron_condor_generates_four_csv_rows(self):
        result = select_spread_strikes_by_delta(chain(), "IRON_CONDOR", today=date(2026, 7, 1))
        orders = tactical_orders_from_spreads(result)

        self.assertEqual(len(orders), 4)

    def test_no_trade_blocks_entry_csv_generation(self):
        decision = select_nifty_tactical_strategy({"breakout_status": True, "india_vix": 15})
        orders = tactical_orders_from_spreads({"accepted": decision["allowed"], "spreads": []})

        self.assertEqual(decision["selected_strategy"], "NO_TRADE")
        self.assertEqual(orders, [])


if __name__ == "__main__":
    unittest.main()
