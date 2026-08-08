from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import app
import risk_config
from kite_broker_adapter import KiteBrokerAdapter
from kite_spread_evaluator import evaluate_spread_with_expiry_comparison
from kite_option_resolver import KiteOptionResolver, next_otm_strike
from kite_pair_execution import submit_kite_pair
from kite_pair_scheduler import run_kite_pair_scheduler_once
from kite_spread_engine import build_kite_spread_preview, fetch_cmp_from_kite, fetch_fresh_equity_quotes_from_kite
from kite_option_liquidity import analyze_pair_liquidity
from kite_spread_income_universe import INCOME_GROWTH_FNO_HOLDINGS
from kite_spread_repository import KiteSpreadRepository
from kite_spread_universe import KiteSpreadUniverse


class AllowRisk:
    def evaluate(self, trade):
        return {"decision": "APPROVED", "reason_codes": []}


class BlockRisk:
    def evaluate(self, trade):
        return {"decision": "BLOCKED", "reason_codes": ["SINGLE_LEG_SELL_BLOCK"]}


class MockKiteAdapter:
    def __init__(self):
        self.placed = []
        self.modified = []
        self.cancelled = []
        self.orders = []

    def get_ltp(self, instruments):
        return {item: {"last_price": 1000 if item == "NSE:RELIANCE" else 0} for item in instruments}

    def get_quote(self, instruments):
        out = {}
        for item in instruments:
            if item == "NSE:RELIANCE":
                out[item] = {
                    "last_price": 1000,
                    "ohlc": {"close": 980},
                    "yearly_high": 1250,
                    "volume": 1000,
                    "oi": 5000,
                    "depth": {"buy": [{"price": 999.9}], "sell": [{"price": 1000.1}]},
                }
                continue
            ltp = 12 if "1050CE" in item or "950PE" in item else 5
            out[item] = {
                "last_price": ltp,
                "volume": 1000,
                "oi": 5000,
                "depth": {
                    "buy": [{"price": ltp - 0.1, "orders": 250, "quantity": 500} for _ in range(5)],
                    "sell": [{"price": ltp + 0.1, "orders": 250, "quantity": 500} for _ in range(5)],
                },
            }
        return out

    def place_order(self, payload):
        self.placed.append(payload)
        return {"order_id": f"KITE-{len(self.placed)}", "status": "OPEN"}

    def get_orders(self):
        return self.orders

    def modify_order(self, variety, order_id, payload):
        self.modified.append((variety, order_id, payload))
        return {"order_id": order_id}

    def cancel_order(self, variety, order_id):
        self.cancelled.append((variety, order_id))
        return {"order_id": order_id}


def inst(strike: int, opt: str, last_price: float = 0.0) -> dict:
    return {
        "tradingsymbol": f"RELIANCE26AUG{strike}{opt}",
        "name": "RELIANCE",
        "expiry": "2026-08-27",
        "instrument_type": opt,
        "strike": strike,
        "last_price": last_price,
        "lot_size": 250,
    }


def instruments() -> list[dict]:
    return [
        inst(1050, "CE", 12), inst(1100, "CE", 12), inst(1200, "CE", 5),
        inst(950, "PE", 12), inst(900, "PE", 12), inst(800, "PE", 5),
    ]


def spread_inst(expiry: str, strike: int, opt: str, price: float, symbol: str = "RELIANCE") -> dict:
    return {
        "tradingsymbol": f"{symbol}{expiry[5:7]}{expiry[8:10]}{strike}{opt}",
        "name": symbol,
        "expiry": expiry,
        "instrument_type": opt,
        "strike": strike,
        "last_price": price,
        "lot_size": 250,
        "volume": 1000,
        "oi": 5000,
        "depth": {"buy": [{"price": max(price - 0.1, 0.05)}], "sell": [{"price": price + 0.1}]},
    }


def comparison_chain(current_sell: float = 12, current_buy: float = 5, next_sell: float = 30, next_buy: float = 5) -> list[dict]:
    return [
        spread_inst("2026-08-27", 1050, "CE", current_sell),
        spread_inst("2026-08-27", 1100, "CE", current_buy),
        spread_inst("2026-09-24", 1050, "CE", next_sell),
        spread_inst("2026-09-24", 1100, "CE", next_buy),
        spread_inst("2026-08-27", 950, "PE", current_sell),
        spread_inst("2026-08-27", 900, "PE", current_buy),
        spread_inst("2026-09-24", 950, "PE", next_sell),
        spread_inst("2026-09-24", 900, "PE", next_buy),
    ]


def expiry_comparison(**kwargs):
    return evaluate_spread_with_expiry_comparison(
        symbol="RELIANCE",
        strategy_type=kwargs.get("strategy", "BEAR_CALL_SPREAD"),
        spot=1000,
        selected_lots=1,
        current_month_expiry="2026-08-27",
        next_month_expiry="2026-09-24",
        option_chain_data=kwargs.get("chain", comparison_chain()),
        kite_adapter=None,
        risk_engine=AllowRisk(),
        market_data={"today": datetime(2026, 8, 4).date()},
        technical_data={},
        event_data=kwargs.get("event_data", {}),
    )


def depth_quote(orders: int, activity: int, *, number_of_trades: int | None = None, ltp: float = 10.0) -> dict:
    quote = {
        "last_price": ltp,
        "volume": activity,
        "oi": 5000,
        "depth": {
            "buy": [{"price": ltp - 0.05, "orders": orders // 5, "quantity": 1000} for _ in range(5)],
            "sell": [{"price": ltp + 0.05, "orders": orders // 5, "quantity": 1000} for _ in range(5)],
        },
    }
    if number_of_trades is not None:
        quote["number_of_trades"] = number_of_trades
    return quote


def test_pair_liquidity_green_when_both_legs_have_strong_depth():
    result = analyze_pair_liquidity("SELL", depth_quote(1500, 1500), "BUY", depth_quote(1200, 1200))

    assert result["pair_liquidity_condition"] == "GREEN"
    assert result["liquidity_order_allowed"] is True


def test_pair_liquidity_amber_when_both_legs_are_acceptable_below_green():
    result = analyze_pair_liquidity("SELL", depth_quote(500, 500), "BUY", depth_quote(300, 300))

    assert result["pair_liquidity_condition"] == "AMBER"
    assert result["liquidity_order_allowed"] is True


def test_pair_liquidity_red_when_one_leg_buy_orders_below_threshold():
    bad = depth_quote(50, 500)
    result = analyze_pair_liquidity("SELL", bad, "BUY", depth_quote(500, 500))

    assert result["pair_liquidity_condition"] == "RED"
    assert result["liquidity_order_allowed"] is False


def test_pair_liquidity_red_when_one_leg_sell_orders_below_threshold():
    bad = depth_quote(500, 500)
    for row in bad["depth"]["sell"]:
        row["orders"] = 10
    result = analyze_pair_liquidity("SELL", depth_quote(500, 500), "BUY", bad)

    assert result["pair_liquidity_condition"] == "RED"
    assert result["liquidity_order_allowed"] is False


def test_pair_liquidity_red_when_trade_activity_below_threshold():
    result = analyze_pair_liquidity("SELL", depth_quote(500, 99), "BUY", depth_quote(500, 500))

    assert result["pair_liquidity_condition"] == "RED"
    assert result["liquidity_order_allowed"] is False


def test_pair_liquidity_amber_when_one_leg_green_one_amber():
    result = analyze_pair_liquidity("SELL", depth_quote(1500, 1500), "BUY", depth_quote(500, 500))

    assert result["pair_liquidity_condition"] == "AMBER"
    assert result["liquidity_order_allowed"] is True


def test_liquidity_uses_volume_proxy_when_number_of_trades_missing():
    result = analyze_pair_liquidity("SELL", depth_quote(500, 500), "BUY", depth_quote(500, 500))

    assert result["sell_leg_liquidity"]["trade_count_source"] == "VOLUME_PROXY"
    assert result["sell_leg_liquidity"]["trade_activity_count"] == 500


def test_liquidity_uses_actual_number_of_trades_when_available():
    result = analyze_pair_liquidity("SELL", depth_quote(500, 500, number_of_trades=700), "BUY", depth_quote(500, 500))

    assert result["sell_leg_liquidity"]["trade_count_source"] == "ACTUAL_TRADE_COUNT"
    assert result["sell_leg_liquidity"]["trade_activity_count"] == 700


def test_cmp_fetch_uses_nse_symbol_format():
    broker = MockKiteAdapter()

    cmp = fetch_cmp_from_kite(broker, ["RELIANCE"])

    assert cmp == {"RELIANCE": 1000.0}


def test_nfo_instrument_resolver_finds_correct_option_contract():
    resolver = KiteOptionResolver(instruments=instruments())

    contract = resolver.nearest_contract("RELIANCE", "2026-08-27", "CE", 1051)

    assert contract["tradingsymbol"] == "RELIANCE26AUG1050CE"


def test_next_50_otm_strike_rounding_for_dhan():
    assert next_otm_strike(1198.26, "CE", 50) == 1200
    assert next_otm_strike(1005, "CE", 50) == 1000
    assert next_otm_strike(1060, "CE", 50) == 1050
    assert next_otm_strike(1084.14, "PE", 50) == 1100
    assert next_otm_strike(1080, "PE", 50) == 1050
    assert next_otm_strike(1080.01, "CE", 50) == 1100


def test_ce_spread_uses_5pct_sell_and_10pct_hedge_and_metrics():
    preview = build_kite_spread_preview("RELIANCE", 1000, "BEAR_CALL_SPREAD", "2026-08-27", 1, KiteOptionResolver(instruments=instruments()), MockKiteAdapter(), AllowRisk())

    assert preview["sell_leg_tradingsymbol"] == "RELIANCE26AUG1050CE"
    assert preview["buy_leg_tradingsymbol"] == "RELIANCE26AUG1100CE"
    assert preview["sell_target_strike"] == 1050
    assert preview["hedge_target_strike"] == 1100
    assert preview["sell_limit_price"] == preview["sell_leg_premium"]
    assert preview["buy_limit_price"] == preview["buy_leg_premium"]
    assert preview["net_credit"] == 7
    assert preview["max_gain"] == 1750
    assert preview["max_loss"] == 10750
    assert preview["breakeven"] == 1057


def test_defined_risk_spread_ignores_single_leg_veto_as_advisory():
    preview = build_kite_spread_preview("RELIANCE", 1000, "BEAR_CALL_SPREAD", "2026-08-27", 1, KiteOptionResolver(instruments=instruments()), MockKiteAdapter(), BlockRisk())

    assert preview["risk_decision"] == "APPROVED"
    assert "RISK_VETO_ENGINE_BLOCKED" not in preview["risk_reason"]
    assert "Single-leg risk veto treated as advisory" in preview["risk_veto_advisory"]


def test_pe_spread_uses_5pct_sell_and_10pct_hedge_and_metrics():
    preview = build_kite_spread_preview("RELIANCE", 1000, "BULL_PUT_SPREAD", "2026-08-27", 1, KiteOptionResolver(instruments=instruments()), MockKiteAdapter(), AllowRisk())

    assert preview["sell_leg_tradingsymbol"] == "RELIANCE26AUG950PE"
    assert preview["buy_leg_tradingsymbol"] == "RELIANCE26AUG900PE"
    assert preview["sell_target_strike"] == 950
    assert preview["hedge_target_strike"] == 900
    assert preview["breakeven"] == 943


def test_expiry_comparison_prefers_current_when_gain_above_threshold():
    result = expiry_comparison(chain=comparison_chain(current_sell=30, current_buy=5, next_sell=40, next_buy=5))

    assert result["recommended_expiry"] == "CURRENT_MONTH"
    assert result["current_month"]["max_gain"] == 6250


def test_expiry_comparison_moves_to_next_when_current_gain_low_and_next_acceptable():
    result = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=30, next_buy=5))

    assert result["recommended_expiry"] == "NEXT_MONTH"
    assert result["current_month"]["max_gain"] == 1750
    assert result["next_month"]["max_gain"] == 6250
    assert result["recommended_preview"]["expiry"] == "2026-09-24"


def test_expiry_comparison_marks_no_trade_when_both_gains_low():
    result = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=13, next_buy=5))

    assert result["recommended_expiry"] == "NO_TRADE"
    assert "max gain below" in result["recommendation_reason"]


def test_expiry_comparison_does_not_recommend_next_when_event_risk_exists():
    result = expiry_comparison(
        chain=comparison_chain(current_sell=12, current_buy=5, next_sell=30, next_buy=5),
        event_data={"next": {"event_risk": True}},
    )

    assert result["recommended_expiry"] == "NO_TRADE"
    assert "event risk" in result["recommendation_reason"]


def test_expiry_comparison_does_not_recommend_next_when_pop_below_threshold(monkeypatch):
    monkeypatch.setattr(risk_config, "MIN_POP_FOR_SPREAD", 80)

    result = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=30, next_buy=5))

    assert result["recommended_expiry"] == "NO_TRADE"
    assert "POP below" in result["recommendation_reason"]


def test_expiry_comparison_does_not_recommend_next_when_max_loss_too_high(monkeypatch):
    monkeypatch.setattr(risk_config, "MAX_ACCEPTABLE_PAIR_LOSS_INR", 5000)

    result = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=30, next_buy=5))

    assert result["recommended_expiry"] == "NO_TRADE"
    assert "max loss above" in result["recommendation_reason"]


def test_expiry_comparison_ce_math_is_correct():
    result = expiry_comparison(chain=comparison_chain(current_sell=30, current_buy=5))
    current = result["current_month"]

    assert current["net_credit"] == 25
    assert current["max_gain"] == 6250
    assert current["max_loss"] == 6250
    assert current["breakeven"] == 1075


def test_expiry_comparison_pe_math_is_correct():
    result = expiry_comparison(strategy="BULL_PUT_SPREAD", chain=comparison_chain(current_sell=30, current_buy=5))
    current = result["current_month"]

    assert current["net_credit"] == 25
    assert current["max_gain"] == 6250
    assert current["max_loss"] == 6250
    assert current["breakeven"] == 925


def test_bajajfinance_ce_hedge_uses_nearest_available_1250_for_10pct_target():
    local_instruments = [
        {"tradingsymbol": "BAJFINANCE26AUG1200CE", "name": "BAJFINANCE", "expiry": "2026-08-27", "instrument_type": "CE", "strike": 1200, "last_price": 9.8, "lot_size": 750},
        {"tradingsymbol": "BAJFINANCE26AUG1250CE", "name": "BAJFINANCE", "expiry": "2026-08-27", "instrument_type": "CE", "strike": 1250, "last_price": 3.1, "lot_size": 750},
        {"tradingsymbol": "BAJFINANCE26AUG1300CE", "name": "BAJFINANCE", "expiry": "2026-08-27", "instrument_type": "CE", "strike": 1300, "last_price": 1.9, "lot_size": 750},
    ]

    preview = build_kite_spread_preview(
        "BAJFINANCE",
        1141.20,
        "BEAR_CALL_SPREAD",
        "2026-08-27",
        1,
        KiteOptionResolver(instruments=local_instruments),
        None,
        AllowRisk(),
    )

    assert preview["raw_hedge_target_strike"] == 1255.32
    assert preview["buy_leg_tradingsymbol"] == "BAJFINANCE26AUG1250CE"
    assert preview["hedge_target_strike"] == 1250
    assert preview["hedge_strike"] == 1250


def test_ce_hedge_uses_raw_10pct_target_instead_of_tiny_next_strike_gap():
    local_instruments = [
        {"tradingsymbol": "DELHIVERY26AUG500CE", "name": "DELHIVERY", "expiry": "2026-08-27", "instrument_type": "CE", "strike": 500, "last_price": 6.9, "lot_size": 2075},
        {"tradingsymbol": "DELHIVERY26AUG505CE", "name": "DELHIVERY", "expiry": "2026-08-27", "instrument_type": "CE", "strike": 505, "last_price": 5.8, "lot_size": 2075},
        {"tradingsymbol": "DELHIVERY26AUG520CE", "name": "DELHIVERY", "expiry": "2026-08-27", "instrument_type": "CE", "strike": 520, "last_price": 2.0, "lot_size": 2075},
    ]

    preview = build_kite_spread_preview(
        "DELHIVERY",
        473.3,
        "BEAR_CALL_SPREAD",
        "2026-08-27",
        1,
        KiteOptionResolver(instruments=local_instruments),
        None,
        AllowRisk(),
    )

    assert preview["raw_sell_target_strike"] == 496.97
    assert preview["raw_hedge_target_strike"] == 520.63
    assert preview["sell_leg_tradingsymbol"] == "DELHIVERY26AUG500CE"
    assert preview["buy_leg_tradingsymbol"] == "DELHIVERY26AUG520CE"
    assert preview["hedge_strike"] > preview["sell_strike"]
    assert preview["net_credit"] == 4.9


def test_pe_hedge_uses_raw_10pct_target_and_stays_below_sell_strike():
    local_instruments = [
        {"tradingsymbol": "DELHIVERY26AUG450PE", "name": "DELHIVERY", "expiry": "2026-08-27", "instrument_type": "PE", "strike": 450, "last_price": 6.9, "lot_size": 2075},
        {"tradingsymbol": "DELHIVERY26AUG445PE", "name": "DELHIVERY", "expiry": "2026-08-27", "instrument_type": "PE", "strike": 445, "last_price": 5.8, "lot_size": 2075},
        {"tradingsymbol": "DELHIVERY26AUG425PE", "name": "DELHIVERY", "expiry": "2026-08-27", "instrument_type": "PE", "strike": 425, "last_price": 2.0, "lot_size": 2075},
    ]

    preview = build_kite_spread_preview(
        "DELHIVERY",
        473.3,
        "BULL_PUT_SPREAD",
        "2026-08-27",
        1,
        KiteOptionResolver(instruments=local_instruments),
        None,
        AllowRisk(),
    )

    assert preview["raw_sell_target_strike"] == 449.63
    assert preview["raw_hedge_target_strike"] == 425.97
    assert preview["sell_leg_tradingsymbol"] == "DELHIVERY26AUG450PE"
    assert preview["buy_leg_tradingsymbol"] == "DELHIVERY26AUG425PE"
    assert preview["hedge_strike"] < preview["sell_strike"]
    assert preview["net_credit"] == 4.9


def test_spread_blocked_when_contract_unresolved():
    preview = build_kite_spread_preview("RELIANCE", 1000, "BEAR_CALL_SPREAD", "2026-08-27", 1, KiteOptionResolver(instruments=[]), MockKiteAdapter(), AllowRisk())

    assert preview["risk_decision"] == "BLOCKED"
    assert "CONTRACT_UNRESOLVED" in preview["risk_reason"]


def test_spread_blocked_when_cmp_unavailable():
    preview = build_kite_spread_preview("RELIANCE", None, "BEAR_CALL_SPREAD", "2026-08-27", 1, KiteOptionResolver(instruments=instruments()), MockKiteAdapter(), AllowRisk())

    assert preview["risk_decision"] == "BLOCKED"
    assert "CMP_UNAVAILABLE" in preview["risk_reason"]


def test_spread_blocked_when_option_premium_unavailable():
    class NoQuote(MockKiteAdapter):
        def get_quote(self, instruments):
            return {item: {"last_price": 0, "volume": 0, "oi": 0} for item in instruments}

    preview = build_kite_spread_preview("RELIANCE", 1000, "BEAR_CALL_SPREAD", "2026-08-27", 1, KiteOptionResolver(instruments=instruments()), NoQuote(), AllowRisk())

    assert "OPTION_PREMIUM_UNAVAILABLE" in preview["risk_reason"]


def test_spread_blocked_when_net_credit_non_positive():
    class BadCredit(MockKiteAdapter):
        def get_quote(self, instruments):
            return {item: {"last_price": 5 if "1050CE" in item else 12, "volume": 100, "oi": 100} for item in instruments}

    preview = build_kite_spread_preview("RELIANCE", 1000, "BEAR_CALL_SPREAD", "2026-08-27", 1, KiteOptionResolver(instruments=instruments()), BadCredit(), AllowRisk())

    assert "NET_CREDIT_NON_POSITIVE" in preview["risk_reason"]


def test_current_holdings_are_highlighted_dark_green(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    repo = KiteSpreadRepository(tmp_path / "app.db")
    repo.upsert_watchlist("RELIANCE", "Reliance", "HOLDING", is_current_holding=True, holding_qty=10)

    html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads"))

    assert "DHAN" in html
    assert "RELIANCE" in html
    assert "current-holding" in html or "HOLDING" in html


def test_dhan_page_seeds_income_growth_fno_holdings(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")

    html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads"))

    assert "DHAN - Income Growth F&O Paired Option Spreads" in html
    for holding in INCOME_GROWTH_FNO_HOLDINGS:
        assert holding.symbol in html
    assert "NUVAMA" not in html
    assert "BAJFINANCE" in html
    assert "2310" in html
    assert "max covered CE lots: 1" in html or "Max CE Lots" in html


def test_dhan_page_exposes_paper_and_live_execution_modes(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")

    paper_html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads", dhan_paper_trading=True))
    live_html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads", dhan_paper_trading=False))

    assert 'name="dhan_paper_trading" value="1" checked' in paper_html
    assert 'name="dhan_paper_trading" value="0"' in paper_html
    assert 'name="dhan_paper_trading" value="0" checked' in live_html
    assert "LIVE submits the BUY hedge first" in paper_html


def test_dhan_stock_rows_have_simple_pe_ce_evaluation_actions(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")

    html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads"))

    assert "Current F&O Stock List - Select PE or CE" in html
    assert "Run Analysis" in html
    assert "/kite-spreads/open-symbol" in html
    assert "Run Analysis on All Stocks" in html
    assert "/kite-spreads/analyze-all" in html
    assert "Evaluate PE" in html
    assert "Evaluate CE" in html
    assert "/kite-spreads/evaluate-symbol" in html
    assert "BAJFINANCE|BULL_PUT_SPREAD" in html
    assert "BAJFINANCE|BEAR_CALL_SPREAD" in html
    assert "Market Setup for Popup Evaluation" not in html


def test_dhan_stock_rows_show_fresh_cmp_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(app, "refresh_dhan_watchlist_quotes", lambda rows: rows[0].update({"cmp": 1141.2, "day_change_pct": 8.32}) if rows else None)

    html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads"))

    assert "CMP / Day" in html
    assert "1141.20" in html
    assert "8.32%" in html


def test_dhan_stock_rows_show_52_week_high_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")

    html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads"))

    assert "52W High Gap" in html
    assert "21.25% below" in html
    assert "dhan-52w-far" in html


def test_dhan_configure_stocks_and_dma_zone_recommend_actions():
    html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_show_config=True,
            dhan_watchlist=[
                {
                    "id": 1,
                    "symbol": "BUYME",
                    "company_name": "Buy Zone Ltd",
                    "active": 1,
                    "cmp": 90,
                    "dma_50": 100,
                    "dma_200": 110,
                    "stock_bucket": "MANUAL",
                    "holding_qty": 0,
                    "max_covered_lots": 0,
                },
                {
                    "id": 2,
                    "symbol": "SELLME",
                    "company_name": "Sell Zone Ltd",
                    "active": 1,
                    "cmp": 120,
                    "dma_50": 100,
                    "dma_200": 110,
                    "stock_bucket": "MANUAL",
                    "holding_qty": 0,
                    "max_covered_lots": 0,
                },
                {
                    "id": 3,
                    "symbol": "HIDDEN",
                    "company_name": "Hidden Ltd",
                    "active": 0,
                    "cmp": 100,
                    "dma_50": 100,
                    "dma_200": 100,
                },
            ],
            dhan_pair_orders=[],
            dhan_holding_positions=[],
        )
    )

    assert "Configure DHAN Stocks" in html
    assert 'id="dhan-config-modal"' in html
    assert 'formaction="/kite-spreads/configure-open"' in html
    assert 'formaction="/kite-spreads/configure-close"' in html
    assert "Upload F&amp;O Opportunities Sheet" in html
    assert 'name="dhan_fno_sheet" type="file"' in html
    assert 'formaction="/kite-spreads/fno-sheet-analyze"' in html
    assert 'formaction="/kite-spreads/fno-sheet-add-selected"' in html
    assert 'formaction="/kite-spreads/fno-sheet-evaluate-top10"' in html
    assert 'formaction="/kite-spreads/add-stock"' in html
    assert 'formaction="/kite-spreads/deactivate" name="dhan_watchlist_id" value="1"' in html
    assert "DMA Zone" in html
    assert "BUY ZONE" in html
    assert "SELL ZONE" in html
    assert "HIDDEN" not in html
    assert 'value="BUYME|BULL_PUT_SPREAD">PE</button>' in html
    assert 'class="dhan-action-btn dhan-action-pe dhan-action-recommended"' in html
    assert 'value="SELLME|BEAR_CALL_SPREAD">CE</button>' in html
    assert 'class="dhan-action-btn dhan-action-ce dhan-action-recommended"' in html


def test_dhan_configure_stocks_modal_locks_remove_for_open_positions():
    html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_show_config=True,
            dhan_watchlist=[
                {
                    "id": 1,
                    "symbol": "LOCKME",
                    "company_name": "Locked Ltd",
                    "active": 1,
                    "cmp": 100,
                    "dma_50": 95,
                    "dma_200": 90,
                    "stock_bucket": "MANUAL",
                    "holding_qty": 0,
                    "max_covered_lots": 0,
                },
            ],
            dhan_pair_orders=[],
            dhan_holding_positions=[
                {
                    "symbol": "LOCKME",
                    "option_type": "CE",
                    "sell_qty_abs": 250,
                    "buy_qty_abs": 0,
                    "pair_status": "SHORT CE UNHEDGED",
                }
            ],
        )
    )

    assert "Locked: open position" in html
    assert 'formaction="/kite-spreads/deactivate" name="dhan_watchlist_id" value="1">Remove</button>' not in html
    assert 'formaction="/kite-spreads/deactivate" name="dhan_watchlist_id" value="1" disabled' in html


def test_dhan_configure_stocks_modal_hidden_until_requested():
    html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_watchlist=[],
            dhan_pair_orders=[],
            dhan_holding_positions=[],
        )
    )

    assert 'formaction="/kite-spreads/configure-open"' in html
    assert 'id="dhan-config-modal"' not in html


def test_fresh_kite_quote_includes_52_week_high_gap():
    quotes = fetch_fresh_equity_quotes_from_kite(MockKiteAdapter(), ["RELIANCE"])

    assert quotes["RELIANCE"]["yearly_high"] == 1250
    assert quotes["RELIANCE"]["pct_to_52_high"] == -20.0


def test_dhan_selected_opportunity_renders_modal_execution_review(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = expiry_comparison(chain=comparison_chain(current_sell=30, current_buy=5, next_sell=50, next_buy=5))["recommended_preview"]

    html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_opportunities=[preview],
            dhan_selected_index="0",
            dhan_selected_symbol="RELIANCE",
            dhan_popup_strategy="BEAR_CALL_SPREAD",
        )
    )

    assert 'id="dhan-pair-order-modal"' in html
    assert 'live-modal-backdrop visible' in html
    assert "DHAN paired execution ticket" in html
    assert "Fresh Kite CMP" in html
    assert "Defined max loss" in html
    assert "SELL 5% OTM" in html
    assert "BUY 10% OTM HEDGE" in html
    assert "POP" in html
    assert 'formaction="/kite-spreads/close-popup"' in html
    assert 'id="dhan-place-pair-order"' in html
    assert 'id="dhan-pair-review"' in html
    assert 'id="dhan-pair-countdown"' in html
    assert "Tick acknowledgement to start 10s review" in html
    assert "GO - Place LIMIT Order" in html
    assert '<pre class="console">' not in html
    assert "sell_order_payload" not in html


def test_dhan_popup_uses_recommended_expiry_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=30, next_buy=5))["recommended_preview"]

    html = app.render_kite_spreads_panel(
        app.PageState(active_tab="kite-spreads", dhan_opportunities=[preview], dhan_selected_index="0")
    )

    assert "Comparison: Current, Next, and Mixed Expiry" in html
    assert "Selected expiry: <strong>NEXT_MONTH</strong>" in html
    assert 'name="dhan_selected_expiry_choice" value="NEXT_MONTH" data-expiry-preview-action="/kite-spreads/preview-pair" checked' in html
    assert 'name="dhan_selected_expiry_choice" value="CURRENT_MONTH" data-expiry-preview-action="/kite-spreads/preview-pair"' in html
    assert 'name="dhan_selected_expiry_choice" value="NEXT_SELL_CURRENT_BUY" data-expiry-preview-action="/kite-spreads/preview-pair"' in html
    assert "SELL next month + BUY current hedge" in html


def test_dhan_popup_allows_acknowledged_soft_no_trade_pair_to_start_review(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=13, next_buy=5))["recommended_preview"]

    html = app.render_kite_spreads_panel(
        app.PageState(active_tab="kite-spreads", dhan_opportunities=[preview], dhan_selected_index="0")
    )

    assert 'id="dhan-pair-order-modal"' in html
    assert "Selected expiry: <strong>NO_TRADE</strong>" in html
    assert 'data-orderable="1"' in html
    assert 'data-auto-clear="0"' in html
    assert 'id="dhan-pair-review" type="button" class="secondary" disabled' in html
    assert 'id="dhan-place-pair-order" type="submit" formaction="/kite-spreads/submit-pair" class="danger" disabled' in html


def test_dhan_quality_clear_enables_review_without_acknowledgement(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = expiry_comparison(chain=comparison_chain(current_sell=50, current_buy=5, next_sell=55, next_buy=5))["recommended_preview"]
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "RETURN_ON_RISK_TOO_LOW"
    preview["reason"] = preview["risk_reason"]
    preview["pop_estimate"] = 80
    preview["max_gain"] = 12000
    preview["current_month_preview"]["risk_decision"] = "BLOCKED"
    preview["current_month_preview"]["risk_reason"] = "RETURN_ON_RISK_TOO_LOW"
    preview["current_month_preview"]["reason"] = "RETURN_ON_RISK_TOO_LOW"
    preview["current_month_preview"]["pop_estimate"] = 80
    preview["current_month_preview"]["max_gain"] = 12000

    html = app.render_kite_spreads_panel(
        app.PageState(active_tab="kite-spreads", dhan_opportunities=[preview], dhan_selected_index="0")
    )

    assert app.dhan_pair_quality_auto_clears(preview)
    assert 'data-auto-clear="1"' in html
    assert "Basic clear available" in html
    assert 'id="dhan-pair-review" type="button" class="secondary">' in html


def test_dhan_basic_pop_gain_clear_allows_blocked_pair_review(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = approved_preview()
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "return on risk below 8.0%, liquidity weak"
    preview["reason"] = preview["risk_reason"]
    preview["pop_estimate"] = 81.5
    preview["max_gain"] = 5962.5

    html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_watchlist=[],
            dhan_pair_orders=[],
            dhan_holding_positions=[],
            dhan_opportunities=[preview],
            dhan_selected_index="0",
        )
    )

    assert app.dhan_pair_simple_quality_clears(preview)
    assert "BASIC CLEAR" in html
    assert "Basic clear available" in html
    assert 'data-orderable="1"' in html
    assert 'data-auto-clear="1"' in html
    assert 'id="dhan-pair-review" type="button" class="secondary">' in html


def test_dhan_acknowledgement_pop_ror_clear_requires_checkbox(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = approved_preview()
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "CALENDAR_HEDGE_EXPIRES_BEFORE_SHORT; RETURN_ON_RISK_WARNING"
    preview["reason"] = preview["risk_reason"]
    preview["pop_estimate"] = 71.5
    preview["return_on_risk_pct"] = 10.5
    preview["max_gain"] = 4200

    unchecked_html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_watchlist=[],
            dhan_pair_orders=[],
            dhan_holding_positions=[],
            dhan_opportunities=[preview],
            dhan_selected_index="0",
        )
    )
    checked_html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_watchlist=[],
            dhan_pair_orders=[],
            dhan_holding_positions=[],
            dhan_opportunities=[preview],
            dhan_selected_index="0",
            dhan_confirm_pair_order=True,
        )
    )

    assert app.dhan_pair_acknowledgement_quality_clears(preview)
    assert not app.dhan_pair_simple_quality_clears(preview)
    assert "ACK CLEAR" in unchecked_html
    assert "Acknowledgement clear available" in unchecked_html
    assert 'data-orderable="1"' in unchecked_html
    assert 'data-auto-clear="0"' in unchecked_html
    assert 'id="dhan-pair-review" type="button" class="secondary" disabled' in unchecked_html
    assert 'id="dhan-pair-review" type="button" class="secondary">' in checked_html


def test_dhan_popup_blocks_new_pair_when_same_side_position_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = approved_preview()
    preview["pop_estimate"] = 81.5
    preview["max_gain"] = 5962.5

    html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_watchlist=[],
            dhan_pair_orders=[],
            dhan_holding_positions=[
                {
                    "symbol": "RELIANCE",
                    "option_type": "CE",
                    "sell_qty_abs": 250,
                    "buy_qty_abs": 0,
                    "pair_status": "SHORT CE UNHEDGED",
                }
            ],
            dhan_opportunities=[preview],
            dhan_selected_index="0",
            dhan_confirm_pair_order=True,
        )
    )

    assert app.dhan_existing_option_position_for_pair(preview, [{"symbol": "RELIANCE", "option_type": "CE", "sell_qty_abs": 250}])
    assert "OPEN POSITION" in html
    assert "use Repair from Current Kite Option Holdings / Pair Status" in html
    assert 'data-orderable="0"' in html
    assert 'id="dhan-pair-review" type="button" class="secondary" disabled' in html


def test_dhan_submit_allows_basic_pop_gain_clear_with_confirmation(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    preview = approved_preview()
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "return on risk below 8.0%, liquidity weak"
    preview["reason"] = preview["risk_reason"]
    preview["pop_estimate"] = 81.5
    preview["max_gain"] = 5962.5

    result = app.submit_pair_order(preview, repo, broker, user_confirmed=True, paper_trading=True)
    pair = repo.get_pair(result["pair_id"])
    payload = json.loads(pair["payload_json"])

    assert result["buy_leg_order_id"] == "KITE-1"
    assert pair["risk_decision"] == "APPROVED"
    assert "Basic clear" in payload["risk_reason"]


def test_dhan_submit_allows_acknowledged_pop_ror_clear(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    preview = approved_preview()
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "CALENDAR_HEDGE_EXPIRES_BEFORE_SHORT; RETURN_ON_RISK_WARNING"
    preview["reason"] = preview["risk_reason"]
    preview["pop_estimate"] = 71.5
    preview["return_on_risk_pct"] = 10.5
    preview["max_gain"] = 4200

    result = app.submit_pair_order(preview, repo, broker, user_confirmed=True, paper_trading=True)
    pair = repo.get_pair(result["pair_id"])
    payload = json.loads(pair["payload_json"])

    assert result["buy_leg_order_id"] == "KITE-1"
    assert pair["risk_decision"] == "APPROVED"
    assert payload["risk_override"] == "DHAN_ACK_POP_ROR_CLEAR"
    assert "Acknowledgement clear" in payload["risk_reason"]


def test_dhan_red_liquidity_allows_paper_popup_flow_but_blocks_live(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = approved_preview()
    preview["pair_liquidity_condition"] = "RED"
    preview["liquidity_order_allowed"] = False
    preview["liquidity_reason"] = "Poor liquidity — order blocked."
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "LIQUIDITY_RED_ORDER_BLOCKED"
    preview["reason"] = preview["risk_reason"]

    paper_html = app.render_kite_spreads_panel(
        app.PageState(active_tab="kite-spreads", dhan_opportunities=[preview], dhan_selected_index="0", dhan_confirm_pair_order=True)
    )
    live_html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_opportunities=[preview],
            dhan_selected_index="0",
            dhan_confirm_pair_order=True,
            dhan_paper_trading=False,
        )
    )

    assert "Liquidity Condition" in paper_html
    assert "Paper mode: RED liquidity is shown for execution-flow testing; live order would be blocked." in paper_html
    assert 'data-orderable="1"' in paper_html
    assert 'id="dhan-pair-review" type="button" class="secondary">' in paper_html
    assert "Place Order disabled because liquidity condition is RED." in live_html
    assert 'data-orderable="0"' in live_html
    assert app.dhan_pair_is_defined_risk_orderable(preview, allow_red_liquidity=True)
    assert not app.dhan_pair_is_defined_risk_orderable(preview, allow_red_liquidity=False)


def test_dhan_amber_liquidity_allows_acknowledged_review(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = approved_preview()
    preview["pair_liquidity_condition"] = "AMBER"
    preview["liquidity_order_allowed"] = True
    preview["liquidity_reason"] = "Acceptable liquidity — order allowed with caution."

    html = app.render_kite_spreads_panel(
        app.PageState(active_tab="kite-spreads", dhan_opportunities=[preview], dhan_selected_index="0", dhan_confirm_pair_order=True)
    )

    assert "Liquidity is acceptable but not strong. Use limit order and verify slippage." in html
    assert 'data-orderable="1"' in html
    assert 'id="dhan-pair-review" type="button" class="secondary">' in html


def test_red_liquidity_blocks_live_submit_but_allows_paper_flow(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    preview = approved_preview()
    preview["pair_liquidity_condition"] = "RED"
    preview["liquidity_order_allowed"] = False
    preview["liquidity_reason"] = "Poor liquidity — order blocked."

    try:
        submit_kite_pair(preview, repo, broker, user_confirmed=True, mode="LIVE")
    except ValueError as exc:
        assert "LIQUIDITY_RED_ORDER_BLOCKED" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("RED liquidity must block live submission")
    assert broker.placed == []

    paper_broker = MockKiteAdapter()
    outcome = submit_kite_pair(preview, repo, paper_broker, user_confirmed=True, mode="PAPER")
    assert outcome["mode"] == "PAPER"
    assert outcome["buy_leg_order_id"]
    assert len(paper_broker.placed) == 2
    assert paper_broker.placed[0]["transaction_type"] == "BUY"
    assert paper_broker.placed[1]["transaction_type"] == "SELL"
    assert paper_broker.placed[1]["price"] == 13.2


def test_dhan_popup_allows_manual_expiry_override_for_each_approved_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    current_approved = expiry_comparison(chain=comparison_chain(current_sell=30, current_buy=5, next_sell=35, next_buy=5))["recommended_preview"]
    next_approved = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=35, next_buy=5))["recommended_preview"]

    current_html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads", dhan_opportunities=[current_approved], dhan_selected_index="0"))
    next_html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads", dhan_opportunities=[next_approved], dhan_selected_index="0"))

    assert 'value="CURRENT_MONTH" data-expiry-preview-action="/kite-spreads/preview-pair" checked' in current_html
    assert 'value="NEXT_MONTH"' in current_html
    assert 'value="NEXT_MONTH" disabled' not in current_html
    assert 'value="NEXT_MONTH" data-expiry-preview-action="/kite-spreads/preview-pair" checked' in next_html
    assert 'value="CURRENT_MONTH"' in next_html


def test_dhan_best_selection_prefers_gain_3000_and_loss_40000_quality_row():
    high_pop_low_gain = {
        "recommended_expiry": "CURRENT_MONTH",
        "pop_estimate": 95,
        "max_gain": 2500,
        "max_loss": 15000,
        "return_on_risk_pct": 16,
    }
    lower_pop_quality = {
        "recommended_expiry": "CURRENT_MONTH",
        "pop_estimate": 80,
        "max_gain": 3200,
        "max_loss": 39000,
        "return_on_risk_pct": 8.2,
    }
    assert app.best_dhan_opportunity_index(
        [high_pop_low_gain, lower_pop_quality],
        min_gain=app.DHAN_SELECTION_MIN_GAIN_INR,
        max_loss=app.DHAN_SELECTION_MAX_LOSS_INR,
    ) == "1"


def test_dhan_opportunity_table_highlights_pop_and_gain_and_opens_popup(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = expiry_comparison(chain=comparison_chain(current_sell=30, current_buy=5, next_sell=50, next_buy=5))["recommended_preview"]
    preview["pop_estimate"] = 85
    preview["max_gain"] = 12500
    preview["max_loss"] = 35000
    preview["current_month"]["pop"] = 85
    preview["current_month"]["max_gain"] = 12500
    preview["current_month"]["max_loss"] = 35000

    html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_opportunities=[preview],
            dhan_selected_index="",
        )
    )

    assert "Opportunity Table - Compare POP, Gain and Risk" in html
    assert 'id="dhan-opportunity-table"' in html
    assert "dhan-opportunities-panel dhan-best-pair-section" in html
    assert "Best pair ready: green rows satisfy POP, max gain, max loss, liquidity, and order-shape checks." in html
    assert 'formaction="/kite-spreads/preview-pair" name="dhan_selected_index" value="0">RELIANCE</button>' in html
    assert 'class="sort-header" data-sort-col="7">Current POP' in html
    assert 'class="sort-header" data-sort-col="5">Current Gain' in html
    assert 'class="sort-header" data-sort-col="14">Recommended' in html
    assert 'class="sort-header" data-sort-col="29">Best Pick' in html
    assert 'class="dhan-best-pick-cell"><strong>BEST PICK</strong>' in html
    assert 'class="dhan-best-pick-row"' in html
    assert 'formaction="/kite-spreads/preview-pair"' in html
    assert "Open Popup" in html
    assert "CURRENT_MONTH" in html
    assert "12500.00" in html
    assert 'formaction="/kite-spreads/clear-pair-monitor"' in html
    assert "Clear Monitor" in html


def test_dhan_opportunity_data_expires_after_ten_minutes_in_render(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    old_stamp = (app.datetime.now(app.INDIA_TIME_ZONE) - app.timedelta(minutes=11)).isoformat(timespec="seconds")
    preview = expiry_comparison(chain=comparison_chain(current_sell=30, current_buy=5, next_sell=50, next_buy=5))["recommended_preview"]

    html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_opportunities=[preview],
            dhan_opportunities_generated_at=old_stamp,
        )
    )

    assert "Analysis is older than 10 minutes" in html
    assert "RELIANCE</button>" in html
    assert "Recalculate Opportunity Table" in html


def test_dhan_checkbox_can_unlock_defined_risk_warning_pair(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = expiry_comparison(chain=comparison_chain(current_sell=30, current_buy=5, next_sell=50, next_buy=5))["recommended_preview"]
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "RETURN_ON_RISK_TOO_LOW"
    preview["reason"] = preview["risk_reason"]

    html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_opportunities=[preview],
            dhan_selected_index="0",
        )
    )

    assert 'id="dhan-pair-review" type="button" class="secondary" disabled' in html
    assert 'data-orderable="1"' in html
    assert app.dhan_pair_is_defined_risk_orderable(preview)


def test_dhan_page_script_has_breathing_gate_before_go(tmp_path, monkeypatch):
    html = Path(app.__file__).read_text(encoding="utf-8")

    assert "startDhanPairCountdown" in html
    assert "Ready. Cancel or GO." in html
    assert "Submitting order to Kite" in html


def test_dhan_submit_overrides_warning_only_defined_risk_pair(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    preview = approved_preview()
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "RETURN_ON_RISK_TOO_LOW; MAX_LOSS_TOO_HIGH"
    preview["reason"] = preview["risk_reason"]

    result = app.submit_pair_order(preview, repo, broker, user_confirmed=True, paper_trading=True)

    pair = repo.get_pair(result["pair_id"])
    assert result["buy_leg_order_id"] == "KITE-1"
    assert "USER_CONFIRMED_DEFINED_RISK_PAIR" in pair["payload_json"]


def test_dhan_apply_expiry_choice_uses_requested_approved_preview():
    current_preview = expiry_comparison(chain=comparison_chain(current_sell=30, current_buy=5, next_sell=35, next_buy=5))["recommended_preview"]
    next_preview = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=35, next_buy=5))["recommended_preview"]

    current_choice = app.apply_dhan_expiry_choice(current_preview, "CURRENT_MONTH")
    next_choice = app.apply_dhan_expiry_choice(next_preview, "NEXT_MONTH")

    assert current_choice["expiry"] == "2026-08-27"
    assert next_choice["expiry"] == "2026-09-24"


def test_dhan_apply_mixed_expiry_choice_uses_next_sell_and_current_buy():
    preview = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=35, next_buy=5))["recommended_preview"]

    mixed_choice = app.apply_dhan_expiry_choice(preview, "NEXT_SELL_CURRENT_BUY")

    assert mixed_choice["selected_expiry_choice"] == "NEXT_SELL_CURRENT_BUY"
    assert mixed_choice["sell_expiry"] == "2026-09-24"
    assert mixed_choice["buy_expiry"] == "2026-08-27"
    assert mixed_choice["sell_leg_tradingsymbol"] == "RELIANCE09241050CE"
    assert mixed_choice["buy_leg_tradingsymbol"] == "RELIANCE08271100CE"
    assert mixed_choice["risk_decision"] == "BLOCKED"
    assert "CALENDAR_HEDGE_EXPIRES_BEFORE_SHORT" in mixed_choice["risk_reason"]


def test_dhan_mixed_expiry_choice_is_not_orderable_as_defined_risk_vertical():
    preview = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=35, next_buy=5))["recommended_preview"]
    mixed_choice = app.apply_dhan_expiry_choice(preview, "NEXT_SELL_CURRENT_BUY")

    assert not app.dhan_pair_is_defined_risk_orderable(mixed_choice)


def test_dhan_apply_expiry_choice_blocks_unapproved_selected_expiry():
    preview = expiry_comparison(chain=comparison_chain(current_sell=30, current_buy=5, next_sell=35, next_buy=5), event_data={"next": {"event_risk": True}})["recommended_preview"]

    try:
        app.apply_dhan_expiry_choice(preview, "NEXT_MONTH")
    except ValueError as exc:
        assert "liquidity, event, and risk checks" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Manual override should be blocked when both expiries are not approved")


def test_dhan_order_backend_log_includes_outcome_pair_and_execution_rows(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    result = app.submit_pair_order(approved_preview(), repo, broker, user_confirmed=True, paper_trading=True)

    log_text = app.format_dhan_order_backend_log(result, repo, broker)

    assert "DHAN Kite order backend log" in log_text
    assert result["pair_id"] in log_text
    assert "BUY_HEDGE_SUBMITTED" in log_text
    assert "HEDGE_FIRST" in log_text


def test_dhan_live_submit_records_live_hedge_first_pair_without_paper_mode(tmp_path):
    class LiveMockBroker(MockKiteAdapter):
        paper_trading = False

    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = LiveMockBroker()

    result = app.submit_pair_order(approved_preview(), repo, broker, user_confirmed=True, paper_trading=False)
    pair = repo.get_pair(result["pair_id"])

    assert pair["mode"] == "LIVE"
    assert pair["execution_mode"] == "HEDGE_FIRST"
    assert result["buy_leg_order_id"] == "KITE-1"
    assert result["sell_leg_order_id"] == "KITE-2"
    assert pair["sell_leg_placed"] == 1


def test_dhan_console_log_renders_near_top_before_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")

    html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            console_log="DHAN Kite order backend log\nsubmitted",
        )
    )

    assert "DHAN Kite order backend log" in html
    assert html.index("DHAN Kite order backend log") < html.index("Current F&O Stock List")
    assert html.index("DHAN Kite order backend log") < html.index("Pair Order Monitor")


def test_dhan_pair_monitor_shows_scheduler_job_status(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    app.DHAN_SCHEDULER_STATUS.update(
        {
            "running": False,
            "mode": "LIVE",
            "last_started_at": "2026-08-03T09:15:00+05:30",
            "last_stopped_at": "",
            "last_run_at": "2026-08-03T09:16:00+05:30",
            "last_result": {"checked": 2, "modified": 1, "failed": 0, "exit_required": 0},
            "last_error": "",
        }
    )

    html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads"))

    assert "Job Status" in html
    assert "STOPPED" in html
    assert "LIVE mode" in html
    assert "Checked 2 | modified 1 | failed 0 | exit-required 0" in html
    app.DHAN_SCHEDULER_STATUS.update({"mode": "PAPER", "last_result": {}, "last_run_at": "", "last_error": ""})


def test_dhan_pair_monitor_can_be_cleared_locally(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    app.submit_pair_order(approved_preview(), repo, broker, user_confirmed=True, paper_trading=True)

    deleted = repo.clear_pair_monitor()

    assert deleted["pair_orders_deleted"] == 1
    assert deleted["execution_logs_deleted"] >= 2
    assert repo.list_pair_orders() == []


def test_dhan_export_outputs_include_expiry_comparison_files(tmp_path, monkeypatch):
    monkeypatch.setattr("kite_spread_config.KITE_SPREAD_OUTPUT_DIR", tmp_path / "outputs")
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    candidate = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=30, next_buy=5))["recommended_preview"]

    repo.export_outputs([candidate])

    candidates_csv = (tmp_path / "outputs" / "kite_spread_candidates.csv").read_text(encoding="utf-8")
    comparison_csv = (tmp_path / "outputs" / "kite_spread_expiry_comparison.csv").read_text(encoding="utf-8")
    assert "current_month_expiry" in candidates_csv
    assert "next_month_max_gain" in candidates_csv
    assert "recommended_expiry" in candidates_csv
    assert "expiry_type" in comparison_csv
    assert "CURRENT_MONTH" in comparison_csv
    assert "NEXT_MONTH" in comparison_csv


def test_dhan_opportunity_table_is_saved_and_reloaded_from_app_db(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(app, "refresh_dhan_watchlist_quotes", lambda rows: None)
    repo = KiteSpreadRepository(tmp_path / "app.db")
    candidate = expiry_comparison(chain=comparison_chain(current_sell=30, current_buy=5, next_sell=50, next_buy=5))["recommended_preview"]
    stamp = app.dhan_opportunity_stamp()

    saved = repo.save_opportunities([candidate], stamp, "DHAN")
    loaded, loaded_stamp = repo.list_opportunities("DHAN")
    state = app.PageState(active_tab="kite-spreads")
    app.load_dhan_state(state)
    html = app.render_kite_spreads_panel(state)

    assert saved == 1
    assert loaded_stamp == stamp
    assert loaded[0]["symbol"] == "RELIANCE"
    assert state.dhan_opportunities
    assert state.dhan_opportunities_generated_at == stamp
    assert "RELIANCE</button>" in html
    assert "Recalculate Opportunity Table" in html


def test_dhan_submit_does_not_override_missing_contract_pair(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    preview = approved_preview()
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "CONTRACT_UNRESOLVED"
    preview["sell_leg_tradingsymbol"] = ""

    try:
        app.submit_pair_order(preview, repo, broker, user_confirmed=True, paper_trading=True)
    except ValueError as exc:
        assert "not orderable" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Missing-contract pair should not be overrideable")


def test_dhan_without_selected_opportunity_does_not_render_popup(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")

    html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads", dhan_opportunities=[], dhan_selected_index=""))

    assert 'id="dhan-pair-order-modal"' not in html


def test_dhan_evaluate_can_fill_missing_market_data_from_kite(monkeypatch):
    class FakeBroker(MockKiteAdapter):
        def __init__(self, *args, **kwargs):
            super().__init__()

        def get_instruments(self, exchange):
            return instruments()

    monkeypatch.setattr(app, "DhanBrokerAdapter", FakeBroker)
    spot_by_symbol = {}
    contracts_by_symbol = {}

    adapter, notes, fresh_quotes = app.enrich_dhan_market_data_from_kite(["RELIANCE"], spot_by_symbol, contracts_by_symbol)

    assert adapter is not None
    assert spot_by_symbol["RELIANCE"] == 1000
    assert fresh_quotes["RELIANCE"]["day_change_pct"] == 2.04
    assert len(contracts_by_symbol["RELIANCE"]) == 6
    assert any("Fresh Kite LTP/day-change fetched" in note for note in notes)


def test_ce_spread_is_blocked_when_income_growth_shares_do_not_cover_lot_size():
    local_instruments = [
        {
            "tradingsymbol": "WAAREEENER26AUG1400CE",
            "name": "WAAREEENER",
            "expiry": "2026-08-27",
            "instrument_type": "CE",
            "strike": 1400,
            "last_price": 12,
            "lot_size": 150,
        },
        {
            "tradingsymbol": "WAAREEENER26AUG1500CE",
            "name": "WAAREEENER",
            "expiry": "2026-08-27",
            "instrument_type": "CE",
            "strike": 1500,
            "last_price": 5,
            "lot_size": 150,
        },
    ]

    preview = build_kite_spread_preview(
        "WAAREEENER",
        1330,
        "BEAR_CALL_SPREAD",
        "2026-08-27",
        1,
        KiteOptionResolver(instruments=local_instruments),
        None,
        AllowRisk(),
    )

    assert preview["risk_decision"] == "BLOCKED"
    assert "CE_NOT_FULLY_COVERED_BY_SHARES_130_LT_150" in preview["risk_reason"]


def test_nuvama_is_excluded_from_dhan_even_if_already_in_watchlist(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    universe = KiteSpreadUniverse(repo)
    repo.upsert_watchlist("NUVAMA", "NUVAMA", "INCOME_GROWTH", is_current_holding=False, holding_qty=0, fno_enabled=True)
    universe.sync_income_growth_fno_holdings()

    symbols = [row["symbol"] for row in universe.list_watchlist()]

    assert "NUVAMA" not in symbols
    assert "BAJFINANCE" in symbols


def test_gpt_suggestions_are_saved_into_db(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    universe = KiteSpreadUniverse(repo)

    saved = universe.save_gpt_suggestions([{"symbol": "PFC", "company_name": "PFC", "gpt_view": "CE_SELL", "reason": "Weak"}])

    assert saved == 1
    assert repo.list_watchlist()[0]["gpt_view"] == "CE_SELL"


def approved_preview() -> dict:
    return build_kite_spread_preview("RELIANCE", 1000, "BEAR_CALL_SPREAD", "2026-08-27", 1, KiteOptionResolver(instruments=instruments()), MockKiteAdapter(), AllowRisk())


def test_dhan_current_position_table_clubs_open_option_buckets():
    positions = [
        {"tradingsymbol": "RELIANCE26AUG1050CE", "name": "RELIANCE", "instrument_type": "CE", "quantity": -250, "average_price": 20, "last_price": 18, "pnl": 500},
        {"tradingsymbol": "RELIANCE26AUG1100CE", "name": "RELIANCE", "instrument_type": "CE", "quantity": -250, "average_price": 8, "last_price": 7, "pnl": 250},
        {"tradingsymbol": "RELIANCE26AUG1200CE", "name": "RELIANCE", "instrument_type": "CE", "quantity": 250, "average_price": 3, "last_price": 4, "pnl": -250},
    ]
    rows = app.analyze_dhan_holding_positions(
        positions,
        [{"symbol": "RELIANCE", "active": 1, "cmp": 1000, "dma_50": 950, "dma_200": 900}],
    )
    html = app.render_dhan_holding_positions(rows)

    assert rows[0]["sell_qty_abs"] == 500
    assert rows[0]["buy_qty_abs"] == 250
    assert rows[0]["repair_qty"] == 250
    assert rows[0]["pair_status"] == "SHORT CE UNHEDGED"
    assert rows[0]["dma_zone"] == "SELL ZONE"
    assert "Current Kite Option Holdings / Pair Status" in html
    assert "CMP / DMA Zone" in html
    assert "SELL ZONE" in html
    assert "OTM 5.00% | POP 70.00% approx" in html
    assert "SHORT CE UNHEDGED" in html
    assert 'formaction="/kite-spreads/repair-preview" name="dhan_repair" value="RELIANCE|CE|BUY_HEDGE"' in html


def test_dhan_current_position_table_marks_pending_repair_order_amber():
    positions = [
        {"tradingsymbol": "RELIANCE26AUG1050CE", "name": "RELIANCE", "instrument_type": "CE", "quantity": -250},
    ]
    orders = [
        {
            "order_id": "KITE-99",
            "tradingsymbol": "RELIANCE26AUG1100CE",
            "name": "RELIANCE",
            "transaction_type": "BUY",
            "status": "OPEN",
            "pending_quantity": 250,
            "price": 5.5,
        }
    ]
    rows = app.analyze_dhan_holding_positions(
        positions,
        [{"symbol": "RELIANCE", "active": 1, "cmp": 1000, "dma_50": 1050, "dma_200": 1100}],
        orders,
    )
    html = app.render_dhan_holding_positions(rows)

    assert rows[0]["pair_status"] == "CE REPAIR ORDER PLACED"
    assert rows[0]["action"] == "ORDER_PLACED"
    assert rows[0]["dma_zone"] == "BUY ZONE"
    assert "KITE-99" in rows[0]["suggestion"]
    assert "BUY ZONE" in html
    assert 'class="dhan-repair-pending-row"' in html
    assert '<span class="ipo-badge warn">CE REPAIR ORDER PLACED</span>' in html
    assert "Order Placed" in html
    assert 'formaction="/kite-spreads/repair-preview"' not in html


def test_dhan_repair_popup_and_submit_single_missing_hedge_order():
    opportunity = expiry_comparison()
    holding_row = {
        "symbol": "RELIANCE",
        "option_type": "CE",
        "sell_qty_abs": 500,
        "buy_qty_abs": 250,
        "pair_status": "SHORT CE UNHEDGED",
    }
    selected = app.apply_dhan_repair_expiry_choice(opportunity, "BUY_HEDGE")
    preview = app.build_dhan_repair_preview_from_opportunity(selected, holding_row, "BUY_HEDGE")

    assert preview["transaction_type"] == "BUY"
    assert preview["quantity"] == 250
    assert preview["selected_expiry_choice"] == "CURRENT_MONTH"

    html = app.render_dhan_repair_modal(
        app.PageState(active_tab="kite-spreads", dhan_repair_preview=preview, dhan_paper_trading=True)
    )
    assert "DHAN Repair Order - RELIANCE" in html
    assert "BUY CE HEDGE" in html
    assert 'id="dhan-repair-countdown">10</div>' in html
    assert 'formaction="/kite-spreads/repair-submit" disabled>Place Order</button>' in html

    broker = MockKiteAdapter()
    outcome = app.submit_dhan_repair_order(preview, broker, user_confirmed=True, mode="PAPER")

    assert outcome["order_id"] == "KITE-1"
    assert len(broker.placed) == 1
    assert broker.placed[0]["transaction_type"] == "BUY"
    assert broker.placed[0]["quantity"] == 250


def test_dhan_repair_sell_leg_defaults_next_month_and_can_choose_current():
    opportunity = expiry_comparison(chain=comparison_chain(current_sell=12, current_buy=5, next_sell=30, next_buy=5))
    holding_row = {
        "symbol": "RELIANCE",
        "option_type": "CE",
        "sell_qty_abs": 250,
        "buy_qty_abs": 500,
        "pair_status": "BUY CE HEDGE ONLY",
    }

    default_next = app.apply_dhan_repair_expiry_choice(opportunity, "SELL_LEG")
    current = app.apply_dhan_repair_expiry_choice(opportunity, "SELL_LEG", "CURRENT_MONTH")
    next_preview = app.build_dhan_repair_preview_from_opportunity(default_next, holding_row, "SELL_LEG")

    assert default_next["selected_expiry_choice"] == "NEXT_MONTH"
    assert current["selected_expiry_choice"] == "CURRENT_MONTH"
    assert next_preview["transaction_type"] == "SELL"
    assert next_preview["quantity"] == 250
    assert next_preview["limit_price"] == 30


def test_paper_mode_does_not_call_real_kite_place_order(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = KiteBrokerAdapter(kite=None, paper_trading=True)

    result = submit_kite_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER")

    assert result["buy_leg_order_id"].startswith("PAPER-KITE")
    assert result["sell_leg_order_id"].startswith("PAPER-KITE")
    assert len(broker.call_log) == 2


def test_live_order_requires_explicit_confirmation(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()

    try:
        submit_kite_pair(approved_preview(), repo, broker, user_confirmed=False, mode="LIVE")
    except ValueError as exc:
        assert "Explicit confirmation" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Live order should require explicit confirmation")


def test_hedge_first_places_buy_and_parks_sell_above_cmp(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()

    result = submit_kite_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER", execution_mode="HEDGE_FIRST")
    pair = repo.get_pair(result["pair_id"])
    payload = json.loads(pair["payload_json"])

    assert result["sell_leg_order_id"] == "KITE-2"
    assert len(broker.placed) == 2
    assert broker.placed[0]["transaction_type"] == "BUY"
    assert broker.placed[0]["price"] == 5.0
    assert broker.placed[1]["transaction_type"] == "SELL"
    assert broker.placed[1]["price"] == 13.2
    assert payload["sell_cmp_limit_price"] == 12.0
    assert payload["sell_initial_limit_price"] == 13.2


def test_rejected_hedge_prevents_sell_leg_placement(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    result = submit_kite_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER")
    broker.orders = [{"order_id": result["buy_leg_order_id"], "status": "REJECTED"}]

    summary = run_kite_pair_scheduler_once(repo, broker)

    assert summary["failed"] == 1
    assert len(broker.placed) == 2
    assert broker.cancelled == [("regular", result["sell_leg_order_id"])]


def test_scheduler_reprices_parked_sell_to_cmp_after_hedge_complete_without_duplicates(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    result = submit_kite_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER")
    broker.orders = [
        {"order_id": result["buy_leg_order_id"], "status": "COMPLETE"},
        {"order_id": result["sell_leg_order_id"], "status": "OPEN"},
    ]

    first = run_kite_pair_scheduler_once(repo, broker)
    second = run_kite_pair_scheduler_once(repo, broker)
    pair = repo.get_pair(result["pair_id"])

    assert len(broker.placed) == 2
    assert broker.placed[1]["transaction_type"] == "SELL"
    assert first["modified"] == 1
    assert second["modified"] == 0
    assert broker.modified == [("regular", result["sell_leg_order_id"], {"order_type": "LIMIT", "price": 12.0})]
    assert pair["pair_status"] == "HEDGE_FILLED_SELL_REPRICED"


def test_simultaneous_mode_modifies_sibling_when_one_leg_complete(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    result = submit_kite_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER", execution_mode="SIMULTANEOUS")
    broker.orders = [
        {"order_id": result["sell_leg_order_id"], "status": "COMPLETE"},
        {"order_id": result["buy_leg_order_id"], "status": "OPEN"},
    ]

    summary = run_kite_pair_scheduler_once(repo, broker)

    assert summary["modified"] == 1
    assert broker.modified[0][1] == result["buy_leg_order_id"]


def test_exit_required_if_naked_short_risk_beyond_timeout(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    preview = approved_preview()
    pair_id = repo.create_pair(preview, mode="PAPER", execution_mode="SIMULTANEOUS")
    old = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat(timespec="seconds")
    repo.update_pair(pair_id, sell_leg_order_id="SELL1", buy_leg_order_id="BUY1", sell_leg_status="COMPLETE", buy_leg_status="OPEN", sell_leg_placed=1, buy_leg_modified_at=old, one_leg_filled_at=old)
    broker = MockKiteAdapter()
    broker.orders = [{"order_id": "SELL1", "status": "COMPLETE"}, {"order_id": "BUY1", "status": "OPEN"}]

    summary = run_kite_pair_scheduler_once(repo, broker)

    assert summary["exit_required"] == 1
    assert repo.get_pair(pair_id)["pair_status"] == "EXIT_REQUIRED"
