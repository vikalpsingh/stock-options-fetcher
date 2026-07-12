from datetime import date, datetime, timedelta
import unittest

from nifty_grow import (
    build_3w_tactical_spread_candidates,
    build_nifty_grow_model,
    calculate_option_liquidity_score,
    calculate_probability_metrics,
    evaluate_3w_nifty_exit,
    filter_liquid_nifty_strikes,
    nifty_grow_audit_csv,
    select_best_nifty_expiry,
    select_nifty_strategy_by_regime,
    validate_credit_quality,
)


NOW = datetime(2026, 7, 1, 10, 0, 0)
BASE_CONFIG = {"_now": NOW}


def quote(
    strike,
    option_type,
    expiry=date(2026, 7, 21),
    delta=0.12,
    bid=50,
    ask=52,
    ltp=51,
    oi=30000,
    volume=2000,
):
    signed_delta = abs(delta) if option_type == "CE" else -abs(delta)
    return {
        "expiry": expiry,
        "option_type": option_type,
        "strike": strike,
        "delta": signed_delta,
        "bid": bid,
        "ask": ask,
        "ltp": ltp,
        "oi": oi,
        "volume": volume,
        "iv": 15,
        "tradingsymbol": f"NIFTY26JUL{strike}{option_type}",
        "quote_timestamp": NOW,
        "lot_size": 65,
    }


def chain(expiry=date(2026, 7, 21)):
    return [
        quote(22600, "PE", expiry, 0.14, 60, 62, 61),
        quote(22200, "PE", expiry, 0.05, 18, 19, 18.5),
        quote(22100, "PE", expiry, 0.04, 14, 15, 14.5),
        quote(25400, "CE", expiry, 0.14, 62, 64, 63),
        quote(25800, "CE", expiry, 0.05, 20, 21, 20.5),
        quote(25900, "CE", expiry, 0.04, 15, 16, 15.5),
    ]


class NiftyGrowTests(unittest.TestCase):
    def test_liquidity_rejects_zero_bid(self):
        result = calculate_option_liquidity_score(quote(22600, "PE", bid=0), BASE_CONFIG)
        self.assertFalse(result["allowed"])
        self.assertIn("ZERO_BID", result["reasons"])

    def test_liquidity_rejects_wide_spread(self):
        result = calculate_option_liquidity_score(quote(22600, "PE", bid=10, ask=12), BASE_CONFIG)
        self.assertFalse(result["allowed"])
        self.assertIn("WIDE_BID_ASK", result["reasons"])

    def test_liquidity_rejects_low_oi(self):
        result = calculate_option_liquidity_score(quote(22600, "PE", oi=9000), BASE_CONFIG)
        self.assertFalse(result["allowed"])
        self.assertIn("LOW_OI", result["reasons"])

    def test_liquidity_rejects_stale_quote(self):
        stale = quote(22600, "PE")
        stale["quote_timestamp"] = NOW - timedelta(minutes=5)
        result = calculate_option_liquidity_score(stale, BASE_CONFIG)
        self.assertFalse(result["allowed"])
        self.assertIn("STALE_QUOTE", result["reasons"])

    def test_liquidity_accepts_good_quote(self):
        result = calculate_option_liquidity_score(quote(22600, "PE"), BASE_CONFIG)
        self.assertTrue(result["allowed"])
        self.assertGreaterEqual(result["score"], 70)

    def test_filter_liquid_nifty_strikes_removes_bad_rows(self):
        rows = [quote(22600, "PE"), quote(22500, "PE", bid=0)]
        liquid = filter_liquid_nifty_strikes(rows, BASE_CONFIG)
        self.assertEqual(len(liquid), 1)
        self.assertEqual(liquid[0]["strike"], 22600)

    def test_expiry_optimizer_selects_18_to_24_dte(self):
        model = select_best_nifty_expiry(
            {date(2026, 7, 15): chain(date(2026, 7, 15)), date(2026, 7, 21): chain(date(2026, 7, 21))},
            {"today": date(2026, 7, 1), "expected_move_points": 500},
            BASE_CONFIG,
        )
        self.assertEqual(model["selected_bucket"], "PREFERRED_3W")
        self.assertEqual(model["selected_expiry"], date(2026, 7, 21))

    def test_expiry_optimizer_rejects_weak_four_week_premium(self):
        weak = [{**row, "credit_pct_of_spread_width": 6} for row in chain(date(2026, 7, 28))]
        model = select_best_nifty_expiry(
            {date(2026, 7, 28): weak},
            {"today": date(2026, 7, 1), "expected_move_points": 500},
            BASE_CONFIG,
        )
        self.assertIsNone(model["selected_expiry"])
        self.assertIn("No expiry", model["reason"])

    def test_expiry_optimizer_prefers_three_week_when_liquidity_better_than_four_week(self):
        four_week = [quote(row["strike"], row["option_type"], date(2026, 7, 28), bid=20, ask=21, ltp=20.5, oi=12000, volume=550) for row in chain()]
        three_week = chain(date(2026, 7, 21))
        model = select_best_nifty_expiry(
            {date(2026, 7, 28): four_week, date(2026, 7, 21): three_week},
            {"today": date(2026, 7, 1), "expected_move_points": 500},
            BASE_CONFIG,
        )
        self.assertEqual(model["selected_expiry"], date(2026, 7, 21))

    def test_expiry_optimizer_returns_none_when_all_fail(self):
        bad = [quote(22600, "PE", date(2026, 7, 10), oi=100, volume=10)]
        model = select_best_nifty_expiry({date(2026, 7, 10): bad}, {"today": date(2026, 7, 1)}, BASE_CONFIG)
        self.assertIsNone(model["selected_expiry"])

    def test_regime_sideways_selects_iron_condor(self):
        decision = select_nifty_strategy_by_regime({"spot": 24000, "ema20": 24000, "ema50": 23980, "rsi_14": 52, "adx_14": 16})
        self.assertEqual(decision["selected_strategy"], "IRON_CONDOR")

    def test_regime_bullish_selects_bull_put_only(self):
        decision = select_nifty_strategy_by_regime({"spot": 24100, "ema20": 23900, "ema50": 23700, "rsi_14": 55})
        self.assertEqual(decision["selected_strategy"], "BULL_PUT_SPREAD")
        self.assertTrue(decision["allow_pe_spread"])
        self.assertFalse(decision["allow_ce_spread"])

    def test_regime_bearish_selects_bear_call_only(self):
        decision = select_nifty_strategy_by_regime({"spot": 23600, "ema20": 23800, "ema50": 23900, "rsi_14": 45})
        self.assertEqual(decision["selected_strategy"], "BEAR_CALL_SPREAD")
        self.assertFalse(decision["allow_pe_spread"])
        self.assertTrue(decision["allow_ce_spread"])

    def test_regime_breakout_no_trade(self):
        decision = select_nifty_strategy_by_regime({"breakout_status": True})
        self.assertEqual(decision["selected_strategy"], "NO_TRADE")

    def test_regime_panic_no_trade(self):
        decision = select_nifty_strategy_by_regime({"panic_fall_status": True})
        self.assertEqual(decision["selected_strategy"], "NO_TRADE")

    def test_probability_metrics_delta_touch(self):
        metrics = calculate_probability_metrics({"strike": 22600, "delta": -0.10}, 24000, 900, 20)
        self.assertEqual(metrics["probability_touch_pct"], 20.0)

    def test_probability_metrics_delta_018_touch_review(self):
        metrics = calculate_probability_metrics({"strike": 22600, "delta": -0.18}, 24000, 900, 20)
        self.assertEqual(metrics["probability_touch_pct"], 36.0)
        self.assertEqual(metrics["probability_risk_state"], "REVIEW")

    def test_probability_metrics_expected_move_too_close_signal(self):
        metrics = calculate_probability_metrics({"strike": 23500, "delta": -0.10}, 24000, 600, 20)
        self.assertLess(metrics["expected_move_multiple"], 1.2)

    def test_probability_metrics_dte_force_exit(self):
        metrics = calculate_probability_metrics({"strike": 22600, "delta": -0.10}, 24000, 900, 7)
        self.assertEqual(metrics["probability_risk_state"], "FORCE_EXIT")

    def test_credit_quality_examples(self):
        self.assertFalse(validate_credit_quality({"spread_width": 500, "net_credit": 25})["accepted"])
        self.assertTrue(validate_credit_quality({"spread_width": 500, "net_credit": 40})["accepted"])
        self.assertFalse(validate_credit_quality({"spread_width": 300, "net_credit": 20})["accepted"])
        self.assertTrue(validate_credit_quality({"spread_width": 300, "net_credit": 24})["accepted"])

    def test_3w_candidates_reject_short_delta_above_018(self):
        rows = [quote(22600, "PE", delta=0.22), quote(22200, "PE", delta=0.05)]
        result = build_3w_tactical_spread_candidates(
            rows,
            date(2026, 7, 21),
            {"today": date(2026, 7, 1), "spot": 24000, "ema20": 23900, "ema50": 23800, "rsi_14": 55, "expected_move_points": 900},
            BASE_CONFIG,
        )
        self.assertFalse(result[0]["allowed"])
        self.assertIn("SHORT_DELTA_ABOVE_MAX", result[0]["rejection_reason"])

    def test_3w_candidate_list_ranks_valid_first(self):
        result = build_3w_tactical_spread_candidates(
            chain(),
            date(2026, 7, 21),
            {"today": date(2026, 7, 1), "spot": 24000, "ema20": 23900, "ema50": 23800, "rsi_14": 55, "expected_move_points": 900},
            BASE_CONFIG,
        )
        self.assertTrue(result[0]["allowed"])
        self.assertEqual(result[0]["side"], "PE")

    def test_3w_candidates_move_to_nearest_tradeable_short_strike(self):
        rows = [
            quote(22600, "PE", delta=0.12, bid=0, ask=0, ltp=0, oi=0, volume=0),
            quote(22700, "PE", delta=0.12, bid=0, ask=0, ltp=0, oi=0, volume=0),
            quote(22800, "PE", delta=0.12, bid=50, ask=52, ltp=51, oi=30000, volume=2000),
            quote(22500, "PE", delta=0.05, bid=10, ask=11, ltp=10.5, oi=30000, volume=2000),
        ]
        result = build_3w_tactical_spread_candidates(
            rows,
            date(2026, 7, 21),
            {
                "today": date(2026, 7, 1),
                "spot": 24000,
                "ema20": 23900,
                "ema50": 23800,
                "rsi_14": 55,
                "expected_move_points": 900,
            },
            BASE_CONFIG,
        )
        self.assertTrue(result)
        self.assertEqual(result[0]["short_strike"], 22800)
        self.assertTrue(result[0]["strike_adjusted"])
        self.assertEqual(result[0]["adjusted_from_strike"], 22600)
        self.assertEqual(result[0]["strike_adjustment_points"], 200)

    def test_3w_candidate_rejects_hedge_inside_short(self):
        short = quote(22600, "PE", delta=0.14, bid=50, ask=51, ltp=50.5)
        hedge = quote(22700, "PE", delta=0.05, bid=10, ask=11, ltp=10.5)
        result = build_3w_tactical_spread_candidates(
            [short, hedge],
            date(2026, 7, 21),
            {"today": date(2026, 7, 1), "spot": 24000, "ema20": 23900, "ema50": 23800, "rsi_14": 55, "expected_move_points": 900},
            BASE_CONFIG,
        )
        self.assertEqual(result, [])

    def test_exit_policy_age_buckets_and_stop(self):
        self.assertTrue(
            evaluate_3w_nifty_exit(
                {"entry_net_credit": 100, "entry_date": date(2026, 7, 1), "expiry": date(2026, 7, 21)},
                {"current_spread_value": 68},
                datetime(2026, 7, 4),
            )["should_exit"]
        )
        self.assertTrue(
            evaluate_3w_nifty_exit(
                {"entry_net_credit": 100, "entry_date": date(2026, 7, 1), "expiry": date(2026, 7, 21)},
                {"current_spread_value": 150},
                datetime(2026, 7, 8),
            )["should_exit"]
        )
        self.assertTrue(
            evaluate_3w_nifty_exit(
                {"entry_net_credit": 100, "entry_date": date(2026, 7, 1), "expiry": date(2026, 7, 7)},
                {"current_spread_value": 90},
                datetime(2026, 7, 1),
            )["should_exit"]
        )

    def test_model_and_audit_csv(self):
        model = build_nifty_grow_model(
            {date(2026, 7, 21): chain()},
            {"today": date(2026, 7, 1), "spot": 24000, "ema20": 23900, "ema50": 23800, "rsi_14": 55, "expected_move_points": 900},
            BASE_CONFIG,
        )
        self.assertTrue(model["candidates"])
        csv_text = nifty_grow_audit_csv(model)
        self.assertIn("selected_expiry", csv_text)
        self.assertIn("credit_pct_of_width", csv_text)


if __name__ == "__main__":
    unittest.main()
