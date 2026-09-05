from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
from dhan_it_pair_execution import DhanItPairRepository
from fifty_two_week_ai_call_spread import (
    FiftyTwoWeekState,
    FiftyTwoWeekAiRepository,
    SellOnRiseEvaluator,
    build_52w_ai_call_spread_preview,
    normalize_screener_csv,
    parse_indian_number,
)


class MockKiteAdapter:
    def __init__(self, quotes: dict[str, dict]) -> None:
        self.quotes = quotes

    def get_quote(self, instruments):
        return {item: self.quotes[item] for item in instruments if item in self.quotes}


class MockEvaluationAdapter:
    def __init__(
        self,
        *,
        symbol: str = "TEST",
        live_cmp: float = 990,
        today_high: float = 1000,
        today_low: float = 970,
        live_volume: int = 900,
        option_bid: float = 20,
        option_ask: float = 21,
        option_volume: int = 500,
        option_oi: int = 2000,
        include_fno: bool = True,
        candles: list[dict] | None = None,
    ) -> None:
        self.symbol = symbol
        self.live_cmp = live_cmp
        self.today_high = today_high
        self.today_low = today_low
        self.live_volume = live_volume
        self.option_bid = option_bid
        self.option_ask = option_ask
        self.option_volume = option_volume
        self.option_oi = option_oi
        self.include_fno = include_fno
        self.candles = candles or evaluation_candles()

    def get_instruments(self, exchange):
        if exchange == "NSE":
            return [{"tradingsymbol": self.symbol, "instrument_token": 1001}]
        if exchange == "NFO" and self.include_fno:
            return [
                {
                    "tradingsymbol": f"{self.symbol}26SEP1050CE",
                    "name": self.symbol,
                    "instrument_type": "CE",
                    "strike": 1050,
                    "expiry": "2026-09-29",
                    "lot_size": 100,
                    "instrument_token": 2001,
                }
            ]
        return []

    def get_quote(self, instruments):
        out = {}
        for item in instruments:
            if item == f"NSE:{self.symbol}":
                out[item] = {
                    "last_price": self.live_cmp,
                    "volume": self.live_volume,
                    "ohlc": {"high": self.today_high, "low": self.today_low, "close": 980},
                }
            elif item == f"NFO:{self.symbol}26SEP1050CE":
                out[item] = quote(self.option_ask, self.option_bid, self.option_ask, self.option_volume, self.option_oi)
        return out

    def historical_data(self, instrument_token, from_date, to_date, interval):
        return list(self.candles)


def evaluation_candles(
    *,
    count: int = 260,
    start: float = 850,
    end: float = 985,
    previous_high: float = 1000,
    previous_low: float = 700,
    volume: int = 1000,
) -> list[dict]:
    candles = []
    for idx in range(count):
        close = start + (end - start) * idx / max(count - 1, 1)
        high = min(previous_high - 2, close + 5)
        low = max(previous_low, close - 5)
        candles.append({"date": date(2025, 1, 1), "open": close - 2, "high": high, "low": low, "close": close, "volume": volume})
    candles[-20]["high"] = previous_high
    candles[-60]["low"] = previous_low
    return candles


def contract(symbol: str, strike: float, expiry: str = "2026-09-29", lot_size: int = 100) -> dict:
    return {
        "tradingsymbol": symbol,
        "name": "TEST",
        "instrument_type": "CE",
        "strike": strike,
        "expiry": expiry,
        "lot_size": lot_size,
        "instrument_token": f"TOKEN-{symbol}",
    }


def quote(ltp: float, bid: float, ask: float, volume: int = 250, oi: int = 1000) -> dict:
    return {
        "last_price": ltp,
        "volume": volume,
        "oi": oi,
        "depth": {
            "buy": [{"price": bid, "quantity": 50, "orders": 25}],
            "sell": [{"price": ask, "quantity": 50, "orders": 25}],
        },
    }


def test_parse_indian_number_handles_common_screener_values():
    assert parse_indian_number("1,234.50") == 1234.5
    assert parse_indian_number("12.5%") == 12.5
    assert parse_indian_number("₹1,000 Cr.") == 1000.0
    assert parse_indian_number("N/A") is None


def test_normalize_screener_csv_keeps_required_fields_and_extras():
    rows = normalize_screener_csv(
        "Company,NSE Code,CMP,Market Cap,Profit after tax,3Y Sales Growth,Distance from 52W High,Custom\n"
        "Test Limited,TEST,\"1,000\",5000,250,18%,4%,Alpha\n"
    )
    assert rows[0]["company"] == "Test Limited"
    assert rows[0]["symbol"] == "TEST"
    assert rows[0]["screener_cmp"] == 1000
    assert rows[0]["sales_growth_3y_pct"] == 18
    assert rows[0]["distance_from_52w_high_pct"] == 4
    assert rows[0]["extra_fields"]["custom"] == "Alpha"


def test_build_52w_preview_uses_ceiling_strikes_and_credit_spread_math():
    instruments = [
        contract("TEST26SEP1040CE", 1040),
        contract("TEST26SEP1050CE", 1050),
        contract("TEST26SEP1190CE", 1190),
        contract("TEST26SEP1200CE", 1200),
    ]
    adapter = MockKiteAdapter(
        {
            "NFO:TEST26SEP1050CE": quote(30, 29.95, 30.5),
            "NFO:TEST26SEP1200CE": quote(5, 4.8, 5.05),
        }
    )
    preview = build_52w_ai_call_spread_preview(
        symbol="TEST",
        spot=1000,
        lots=2,
        option_chain_data=instruments,
        kite_adapter=adapter,
        today=date(2026, 9, 4),
    )
    assert preview["risk_decision"] == "APPROVED"
    assert preview["sell_leg_tradingsymbol"] == "TEST26SEP1050CE"
    assert preview["buy_leg_tradingsymbol"] == "TEST26SEP1200CE"
    assert preview["quantity"] == 200
    assert preview["buy_reference_price"] == 5.05
    assert preview["buy_limit_price"] == 4.8
    assert preview["sell_limit_price"] == 29.95
    assert preview["sell_initial_limit_price"] == 32.95
    assert preview["net_credit"] == 25.15
    assert preview["max_gain"] == 5030
    assert preview["max_loss"] == 24970
    assert preview["breakeven"] == 1075.15


def test_build_52w_preview_allows_configured_limit_price_offsets():
    instruments = [contract("TEST26SEP1050CE", 1050), contract("TEST26SEP1200CE", 1200)]
    adapter = MockKiteAdapter(
        {
            "NFO:TEST26SEP1050CE": quote(30, 30.0, 30.5),
            "NFO:TEST26SEP1200CE": quote(5, 4.8, 5.0),
        }
    )
    preview = build_52w_ai_call_spread_preview(
        symbol="TEST",
        spot=1000,
        lots=1,
        option_chain_data=instruments,
        kite_adapter=adapter,
        buy_limit_discount_pct=10,
        sell_limit_markup_pct=15,
        today=date(2026, 9, 4),
    )

    assert preview["quantity"] == 100
    assert preview["buy_limit_price"] == 4.5
    assert preview["sell_limit_price"] == 30.0
    assert preview["sell_initial_limit_price"] == 34.5
    assert preview["net_credit"] == 25.5
    assert preview["max_gain"] == 2550
    assert preview["max_loss"] == 12450


def test_build_52w_preview_blocks_when_credit_is_not_positive():
    instruments = [contract("TEST26SEP1050CE", 1050), contract("TEST26SEP1200CE", 1200)]
    adapter = MockKiteAdapter(
        {
            "NFO:TEST26SEP1050CE": quote(4, 4.0, 4.2),
            "NFO:TEST26SEP1200CE": quote(5, 4.8, 5.05),
        }
    )
    preview = build_52w_ai_call_spread_preview(
        symbol="TEST",
        spot=1000,
        lots=1,
        option_chain_data=instruments,
        kite_adapter=adapter,
        today=date(2026, 9, 4),
    )
    assert preview["risk_decision"] == "BLOCKED"
    assert "NET_CREDIT_NON_POSITIVE" in preview["risk_reason"]


def test_build_52w_preview_uses_farthest_listed_hedge_when_20_pct_missing():
    instruments = [
        contract("TEST26SEP9700CE", 9700, lot_size=200),
        contract("TEST26SEP10000CE", 10000, lot_size=200),
    ]
    adapter = MockKiteAdapter(
        {
            "NFO:TEST26SEP9700CE": quote(55, 54.95, 56.0),
            "NFO:TEST26SEP10000CE": quote(9, 8.75, 9.05),
        }
    )
    preview = build_52w_ai_call_spread_preview(
        symbol="TEST",
        spot=9194,
        lots=1,
        option_chain_data=instruments,
        kite_adapter=adapter,
        today=date(2026, 9, 4),
    )
    assert preview["risk_decision"] == "APPROVED"
    assert preview["sell_leg_tradingsymbol"] == "TEST26SEP9700CE"
    assert preview["buy_leg_tradingsymbol"] == "TEST26SEP10000CE"
    assert preview["quantity"] == 200
    assert preview["hedge_fallback_used"] is True
    assert "+20% hedge was unavailable" in preview["risk_reason"]


def test_ai52_repository_and_pair_repository_persist_screen_name(tmp_path):
    db_path = tmp_path / "app.db"
    ai_repo = FiftyTwoWeekAiRepository(db_path)
    snapshot_id = ai_repo.save_candidate_snapshot([{"symbol": "TEST"}], "CSV_UPLOAD:test.csv")
    assert snapshot_id.startswith("AI52-")
    assert ai_repo.latest_candidate_snapshot()["rows"][0]["symbol"] == "TEST"
    ai_repo.save_preview(
        {
            "symbol": "TEST",
            "expiry": "2026-09-29",
            "sell_strike": 1050,
            "buy_strike": 1200,
            "selected_lots": 1,
            "lots": 1,
        }
    )
    assert len(ai_repo.latest_previews()) == 1
    assert ai_repo.clear_previews() == 1
    assert ai_repo.latest_previews() == []
    assert ai_repo.latest_candidate_snapshot()["rows"][0]["symbol"] == "TEST"

    pair_repo = DhanItPairRepository(db_path)
    pair_id = pair_repo.create_pair(
        {
            "screen_name": "52W AI Call Spread",
            "strategy_type": "BEAR_CALL_SPREAD",
            "symbol": "TEST",
            "expiry": "2026-09-29",
            "selected_lots": 1,
            "lot_size": 100,
            "quantity": 100,
            "sell_leg_tradingsymbol": "TEST26SEP1050CE",
            "buy_leg_tradingsymbol": "TEST26SEP1200CE",
            "net_credit": 10,
            "max_gain": 1000,
            "max_loss": 14000,
            "breakeven": 1060,
            "pop_estimate": 70,
            "risk_decision": "APPROVED",
        },
        mode="PAPER",
        user_confirmed=True,
    )
    row = pair_repo.get_pair(pair_id)
    assert row["screen_name"] == "52W AI Call Spread"


def test_ai52_pair_monitor_clear_only_removes_52w_ai_rows(tmp_path):
    db_path = tmp_path / "app.db"
    pair_repo = DhanItPairRepository(db_path)
    base_preview = {
        "strategy_type": "BEAR_CALL_SPREAD",
        "symbol": "TEST",
        "expiry": "2026-09-29",
        "selected_lots": 1,
        "lot_size": 100,
        "quantity": 100,
        "sell_leg_tradingsymbol": "TEST26SEP1050CE",
        "buy_leg_tradingsymbol": "TEST26SEP1200CE",
        "net_credit": 10,
        "max_gain": 1000,
        "max_loss": 14000,
        "breakeven": 1060,
        "pop_estimate": 70,
        "risk_decision": "APPROVED",
    }
    ai52_pair_id = pair_repo.create_pair({**base_preview, "screen_name": "52W AI Call Spread"}, mode="PAPER", user_confirmed=True)
    dhan_it_pair_id = pair_repo.create_pair({**base_preview, "screen_name": "DHAN-IT", "symbol": "INFY"}, mode="PAPER", user_confirmed=True)

    deleted = pair_repo.clear_pair_monitor(screen_name="52W AI Call Spread")
    remaining = pair_repo.list_pairs()

    assert deleted["pair_orders_deleted"] == 1
    assert pair_repo.get_pair(ai52_pair_id) is None
    assert pair_repo.get_pair(dhan_it_pair_id) is not None
    assert [row["screen_name"] for row in remaining] == ["DHAN-IT"]


def test_ai52_candidate_symbol_opens_order_ticket_without_actions_column():
    state = app.PageState(
        active_tab="52w-ai-call-spread",
        ai52_candidates=[
            {
                "symbol": "DIVISLAB",
                "company": "Divi's Laboratories",
                "screener_cmp": 9194,
                "market_cap": 100000,
                "pat": 2500,
                "sales_growth_3y_pct": 18,
                "distance_from_52w_high_pct": 4,
                "extra_fields": {"promoter_holding": "51%", "debt_to_equity": "0.1"},
            }
        ],
    )
    page = app.render_ai52_call_spread_panel(state)
    assert 'id="ai52-detail-modal"' in page
    assert "Actions</th>" not in page
    assert "ai52-actions-cell" not in page
    assert "ai52-detail-button" not in page
    assert "Create Call Spread</button>" not in page
    assert 'class="mini-link button-link ai52-symbol-ticket-link"' in page
    assert 'formaction="/52w-ai-call-spread/preview"' in page
    assert "Open order ticket" in page
    assert "/52w-ai-call-spread/clear-previews" in page
    assert "Clean Saved 52W AI Previews" in page
    assert "/52w-ai-call-spread/clear-pair-monitor" in page
    assert "Clear Pair Order Monitor" in page
    assert 'name="ai52_buy_limit_discount_pct"' in page
    assert 'name="ai52_sell_limit_markup_pct"' in page
    assert "BUY limit discount %" in page
    assert "SELL parked markup %" in page
    assert "All option LIMIT prices are rounded to ₹0.05" in page
    assert "<details>" not in page


def test_ai52_sell_on_rise_near_high_without_rejection_is_watch():
    evaluator = SellOnRiseEvaluator(
        MockEvaluationAdapter(live_cmp=990, today_high=998, today_low=985, live_volume=900),
        today=date(2026, 9, 4),
    )

    result = evaluator.evaluate("TEST", {"symbol": "TEST", "company": "Test Ltd"})

    assert result.state == FiftyTwoWeekState.NEAR_HIGH
    assert result.decision in {"WATCH FOR REJECTION", "WAIT", "AVOID"}
    assert "STRONG_BREAKOUT" not in result.block_reasons


def test_ai52_sell_on_rise_failed_breakout_scores_as_sell_candidate():
    candles = evaluation_candles(end=995)
    evaluator = SellOnRiseEvaluator(
        MockEvaluationAdapter(live_cmp=990, today_high=1025, today_low=980, live_volume=800, candles=candles),
        today=date(2026, 9, 4),
    )

    result = evaluator.evaluate("TEST", {"symbol": "TEST", "company": "Test Ltd"})

    assert result.state == FiftyTwoWeekState.FAILED_BREAKOUT
    assert result.rejection_score >= 60
    assert result.decision in {"A+ SELL", "A SELL", "WATCH FOR REJECTION"}


def test_ai52_sell_on_rise_strong_breakout_is_hard_blocked():
    candles = evaluation_candles(end=995, volume=1000)
    evaluator = SellOnRiseEvaluator(
        MockEvaluationAdapter(live_cmp=1045, today_high=1050, today_low=1010, live_volume=2500, candles=candles),
        today=date(2026, 9, 4),
    )

    result = evaluator.evaluate("TEST", {"symbol": "TEST", "company": "Test Ltd"})

    assert result.state == FiftyTwoWeekState.STRONG_BREAKOUT
    assert result.decision == "BLOCKED"
    assert "STRONG_BREAKOUT" in result.block_reasons
    assert any("DO NOT SELL CE" in warning for warning in result.warnings)


def test_ai52_sell_on_rise_blocks_non_fno_candidate():
    evaluator = SellOnRiseEvaluator(MockEvaluationAdapter(include_fno=False), today=date(2026, 9, 4))

    result = evaluator.evaluate("TEST", {"symbol": "TEST"})

    assert result.decision == "BLOCKED"
    assert result.fno_eligible is False
    assert result.block_reasons == ["NOT_FNO"]


def test_ai52_sell_on_rise_blocks_wide_option_spread():
    evaluator = SellOnRiseEvaluator(
        MockEvaluationAdapter(option_bid=10, option_ask=20, option_volume=0, option_oi=0),
        today=date(2026, 9, 4),
    )

    result = evaluator.evaluate("TEST", {"symbol": "TEST"})

    assert result.decision == "BLOCKED"
    assert "OPTION_SPREAD_TOO_WIDE" in result.block_reasons


def test_ai52_evaluate_many_ranks_non_blocked_before_blocked():
    class MultiAdapter(MockEvaluationAdapter):
        def get_instruments(self, exchange):
            if exchange == "NSE":
                return [{"tradingsymbol": "GOOD", "instrument_token": 1}, {"tradingsymbol": "BLOCK", "instrument_token": 2}]
            return [
                {"tradingsymbol": "GOOD26SEP1050CE", "name": "GOOD", "instrument_type": "CE", "strike": 1050, "expiry": "2026-09-29", "lot_size": 100},
                {"tradingsymbol": "BLOCK26SEP1050CE", "name": "BLOCK", "instrument_type": "CE", "strike": 1050, "expiry": "2026-09-29", "lot_size": 100},
            ]

        def get_quote(self, instruments):
            out = {}
            for item in instruments:
                if item == "NSE:GOOD":
                    out[item] = {"last_price": 990, "volume": 800, "ohlc": {"high": 1025, "low": 980, "close": 980}}
                elif item == "NSE:BLOCK":
                    out[item] = {"last_price": 1045, "volume": 2500, "ohlc": {"high": 1050, "low": 1010, "close": 980}}
                elif item.startswith("NFO:"):
                    out[item] = quote(20, 19, 20, 500, 2000)
            return out

    ranked = SellOnRiseEvaluator(MultiAdapter(), today=date(2026, 9, 4)).evaluate_many(
        [{"symbol": "BLOCK"}, {"symbol": "GOOD"}]
    )

    assert ranked[0].symbol == "GOOD"
    assert ranked[0].sell_rank == 1
    assert ranked[-1].symbol == "BLOCK"
    assert ranked[-1].sell_rank is None
