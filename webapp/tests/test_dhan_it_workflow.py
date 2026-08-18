from __future__ import annotations

import json
from datetime import date
from datetime import datetime, timedelta, timezone

import app
from dhan_it_pair_execution import DhanItPairRepository, submit_dhan_it_pair
from dhan_it_pair_monitor import run_dhan_it_pair_monitor_once
from dhan_it_signal_engine import evaluate_it_signal
from dhan_it_spread_builder import build_dhan_it_spread
from dhan_it_universe import IT_FNO_SYMBOLS, dhan_it_stock_config, dhan_it_universe_rows, is_dhan_it_symbol
from kite_pair_execution import round_limit_price_to_tick


class AllowRisk:
    def evaluate(self, trade):
        return {"decision": "APPROVED", "reason_codes": []}


class MockBroker:
    def __init__(self):
        self.placed = []
        self.modified = []
        self.orders = []
        self.quotes = {}

    def place_order(self, payload):
        self.placed.append(payload)
        return {"order_id": f"MOCK-{len(self.placed)}", "status": "OPEN"}

    def get_orders(self):
        return self.orders

    def modify_order(self, variety, order_id, payload):
        self.modified.append((variety, order_id, payload))
        return {"order_id": order_id}

    def get_quote(self, instruments):
        keys = instruments if isinstance(instruments, list) else [instruments]
        return {key: self.quotes.get(str(key).replace("NFO:", ""), self.quotes.get(key, depth_quote(500, 500))) for key in keys}


def depth_quote(orders: int, activity: int, *, ltp: float = 10.0) -> dict:
    return {
        "last_price": ltp,
        "volume": activity,
        "depth": {
            "buy": [{"price": max(ltp - 0.1, 0.05), "orders": orders, "quantity": orders * 10}],
            "sell": [{"price": ltp + 0.1, "orders": orders, "quantity": orders * 10}],
        },
    }


def option_row(symbol: str, expiry: str, strike: int, opt: str, price: float, liquidity: bool = True) -> dict:
    return {
        "tradingsymbol": f"{symbol}{expiry[5:7]}{expiry[8:10]}{strike}{opt}",
        "name": symbol,
        "expiry": expiry,
        "instrument_type": opt,
        "strike": strike,
        "last_price": price,
        "lot_size": 250,
        "volume": 1000 if liquidity else 0,
        "oi": 5000 if liquidity else 0,
        "depth": {
            "buy": [{"price": max(price - 0.1, 0.05)}] if liquidity else [],
            "sell": [{"price": price + 0.1}] if liquidity else [],
        },
    }


def it_chain(
    symbol: str = "TCS",
    current_sell: float = 35,
    current_buy: float = 10,
    next_sell: float = 35,
    next_buy: float = 10,
    liquidity: bool = True,
) -> list[dict]:
    return [
        option_row(symbol, "2026-08-27", 1050, "CE", current_sell, liquidity),
        option_row(symbol, "2026-08-27", 1100, "CE", current_buy, liquidity),
        option_row(symbol, "2026-09-24", 1050, "CE", next_sell, liquidity),
        option_row(symbol, "2026-09-24", 1100, "CE", next_buy, liquidity),
        option_row(symbol, "2026-08-27", 950, "PE", current_sell, liquidity),
        option_row(symbol, "2026-08-27", 900, "PE", current_buy, liquidity),
        option_row(symbol, "2026-09-24", 950, "PE", next_sell, liquidity),
        option_row(symbol, "2026-09-24", 900, "PE", next_buy, liquidity),
    ]


def build_preview(strategy: str = "BEAR_CALL_SPREAD", **kwargs) -> dict:
    return build_dhan_it_spread(
        symbol=kwargs.get("symbol", "TCS"),
        strategy_type=strategy,
        spot=kwargs.get("spot", 1000),
        lots=1,
        option_chain_data=kwargs.get("chain", it_chain(kwargs.get("symbol", "TCS"))),
        kite_adapter=None,
        risk_engine=AllowRisk(),
        market_data={"today": date(2026, 8, 4)},
        technical_data={},
        event_data=kwargs.get("event_data", {}),
    )


def approved_preview() -> dict:
    preview = build_preview("BEAR_CALL_SPREAD")
    assert preview["risk_decision"] == "APPROVED"
    return preview


def test_dhan_it_universe_contains_six_orderable_it_fno_symbols_with_ltm_canonical():
    assert IT_FNO_SYMBOLS == ["TCS", "INFY", "HCLTECH", "TECHM", "WIPRO", "LTM"]
    assert [row["symbol"] for row in dhan_it_universe_rows()] == IT_FNO_SYMBOLS
    assert is_dhan_it_symbol("infy")
    assert is_dhan_it_symbol("WIPRO")
    assert is_dhan_it_symbol("LTM")
    assert not is_dhan_it_symbol("LTI")
    assert not is_dhan_it_symbol("LTIS")
    assert not is_dhan_it_symbol("LTIM")
    assert not is_dhan_it_symbol("LTIMINDTREE")
    assert not is_dhan_it_symbol("RELIANCE")
    by_symbol = {row["symbol"]: row for row in dhan_it_universe_rows()}
    assert by_symbol["WIPRO"]["company_name"] == "Wipro Ltd"
    assert by_symbol["WIPRO"]["risk_bucket"] == "CONSERVATIVE"
    assert by_symbol["WIPRO"]["target_short_otm_pct"] == 7.0
    assert by_symbol["WIPRO"]["target_hedge_otm_pct"] == 12.0
    assert by_symbol["WIPRO"]["max_open_spreads"] == 2
    assert by_symbol["LTM"]["company_name"] == "LTIMindtree Ltd"
    assert by_symbol["LTM"]["risk_bucket"] == "MODERATE"
    assert by_symbol["LTM"]["target_short_otm_pct"] == 9.0
    assert by_symbol["LTM"]["target_hedge_otm_pct"] == 14.0
    assert by_symbol["LTM"]["short_call_delta_min"] == 0.12
    assert by_symbol["LTM"]["short_call_delta_max"] == 0.16
    assert by_symbol["LTM"]["max_open_spreads"] == 1


def test_signal_engine_is_canonical_ce_watch_no_trade_only_and_blocks_event_risk():
    ce = evaluate_it_signal(
        "TCS",
        market_data={"cmp": 1000, "close": 995, "high": 1012, "low": 990},
        technical_data={"dma_50": 980, "dma_200": 1020, "resistance_20d": 1010, "rsi": 62, "previous_rsi": 67, "nifty_it_regime": "BEARISH"},
    )
    watch = evaluate_it_signal("INFY", market_data={"cmp": 1000, "day_change_pct": 3.2}, technical_data={"dma_50": 980, "dma_200": 1020, "nifty_it_regime": "BEARISH"})
    blocked = evaluate_it_signal("TECHM", market_data={"cmp": 1000}, event_data={"event_risk": True})
    assert ce["recommended_strategy"] == "BEAR_CALL_SPREAD"
    assert watch["recommended_strategy"] == "WATCH"
    assert blocked["recommended_strategy"] == "NO_TRADE"
    assert {ce["recommended_strategy"], watch["recommended_strategy"], blocked["recommended_strategy"]} <= {"BEAR_CALL_SPREAD", "WATCH", "NO_TRADE"}


def test_dhan_it_quote_keys_use_wipro_and_canonical_ltm_only():
    keys = [app._dhan_it_quote_key(symbol) for symbol in IT_FNO_SYMBOLS]

    assert "NSE:WIPRO" in keys
    assert "NSE:LTM" in keys
    assert "NSE:LTI" not in keys
    assert "NSE:LTIS" not in keys
    assert "NSE:LTIM" not in keys
    assert "NSE:LTIMINDTREE" not in keys


def test_builds_current_month_ce_spread_when_gain_threshold_is_met():
    preview = build_preview("BEAR_CALL_SPREAD")
    assert preview["screen_name"] == "DHAN-IT"
    assert preview["recommended_expiry"] == "CURRENT_MONTH"
    assert preview["sell_leg_tradingsymbol"].endswith("1050CE")
    assert preview["buy_leg_tradingsymbol"].endswith("1100CE")
    assert preview["current_month"]["expiry"] == preview["expiry"]
    assert preview["quantity"] == preview["lot_size"]
    assert preview["max_gain"] >= 5000


def test_dhan_it_spread_builder_uses_wipro_ltm_configured_otm_anchors():
    wipro_chain = [
        option_row("WIPRO", "2026-08-27", 1080, "CE", 18),
        option_row("WIPRO", "2026-08-27", 1120, "CE", 5),
        option_row("WIPRO", "2026-09-24", 1080, "CE", 18),
        option_row("WIPRO", "2026-09-24", 1120, "CE", 5),
    ]
    ltm_chain = [
        option_row("LTM", "2026-08-27", 1100, "CE", 22),
        option_row("LTM", "2026-08-27", 1150, "CE", 6),
        option_row("LTM", "2026-09-24", 1100, "CE", 22),
        option_row("LTM", "2026-09-24", 1150, "CE", 6),
    ]

    wipro = build_dhan_it_spread(
        symbol="WIPRO",
        strategy_type="BEAR_CALL_SPREAD",
        spot=1000,
        lots=1,
        option_chain_data=wipro_chain,
        risk_engine=AllowRisk(),
        market_data={"today": date(2026, 8, 4)},
    )
    ltm = build_dhan_it_spread(
        symbol="LTM",
        strategy_type="BEAR_CALL_SPREAD",
        spot=1000,
        lots=1,
        option_chain_data=ltm_chain,
        risk_engine=AllowRisk(),
        market_data={"today": date(2026, 8, 4)},
    )

    assert dhan_it_stock_config("WIPRO")["target_short_otm_pct"] == 7.0
    assert wipro["sell_leg_tradingsymbol"].endswith("1080CE")
    assert wipro["buy_leg_tradingsymbol"].endswith("1120CE")
    assert dhan_it_stock_config("LTM")["target_short_otm_pct"] == 9.0
    assert ltm["sell_leg_tradingsymbol"].endswith("1100CE")
    assert ltm["buy_leg_tradingsymbol"].endswith("1150CE")
    assert "LTIS" not in {row["name"] for row in ltm_chain}


def test_builds_current_month_pe_spread_when_gain_threshold_is_met():
    preview = build_preview("BULL_PUT_SPREAD")
    assert preview["recommended_expiry"] == "CURRENT_MONTH"
    assert preview["sell_leg_tradingsymbol"].endswith("950PE")
    assert preview["buy_leg_tradingsymbol"].endswith("900PE")


def test_rolls_to_next_month_when_current_gain_is_low_and_next_is_approved():
    chain = it_chain(current_sell=14, current_buy=10, next_sell=35, next_buy=10)
    preview = build_preview("BEAR_CALL_SPREAD", chain=chain)
    assert preview["recommended_expiry"] == "NEXT_MONTH"
    assert preview["expiry"] == "2026-09-24"
    assert preview["current_month"]["max_gain"] < 2000
    assert preview["next_month"]["max_gain"] >= 2000


def test_no_trade_when_current_and_next_fail_gain_or_risk_checks():
    chain = it_chain(current_sell=14, current_buy=10, next_sell=14, next_buy=10)
    preview = build_preview("BEAR_CALL_SPREAD", chain=chain)
    assert preview["recommended_expiry"] == "NO_TRADE"
    assert preview["risk_decision"] == "NO_TRADE"


def test_event_risk_and_low_liquidity_block_the_spread():
    event_preview = build_preview("BEAR_CALL_SPREAD", event_data={"event_risk": True})
    low_liquidity = build_preview("BEAR_CALL_SPREAD", chain=it_chain(liquidity=False))
    assert event_preview["risk_decision"] == "NO_TRADE"
    assert low_liquidity["risk_decision"] == "NO_TRADE"


def test_contract_unresolved_is_no_trade():
    preview = build_dhan_it_spread(
        symbol="TCS",
        strategy_type="BEAR_CALL_SPREAD",
        spot=1000,
        lots=1,
        option_chain_data=[],
        kite_adapter=None,
        risk_engine=AllowRisk(),
        market_data={"today": date(2026, 8, 4)},
        technical_data={},
        event_data={},
    )
    assert preview["risk_decision"] == "NO_TRADE"
    reason = str(preview.get("risk_reason") or preview.get("reason"))
    assert "risk engine did not approve" in reason or "CONTRACT" in reason


def test_dhan_it_panel_renders_comparison_and_popup_states():
    approved = approved_preview()
    approved["current_month"]["pop"] = 85
    approved["current_month"]["max_gain"] = 12500
    approved["current_month"]["max_loss"] = 35000
    blocked = dict(approved, recommended_expiry="NO_TRADE", risk_decision="NO_TRADE", reason="Blocked for test")
    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_call_watch_cards=[
                {
                    "symbol": "NIFTY IT",
                    "label": "NIFTY IT Sector Index",
                    "status": "AMBER",
                    "decision": "REGIME_ONLY",
                    "order_allowed": False,
                    "trend": "MIXED",
                    "nifty_it_regime": "MIXED",
                },
                {
                    "symbol": "TCS",
                    "label": "Tata Consultancy Services Ltd",
                    "status": "GREEN",
                    "decision": "ALLOWED",
                    "order_allowed": True,
                    "trend": "BEARISH",
                    "nifty_it_regime": "MIXED",
                    "price": 1000,
                    "dma_50": 1010,
                    "dma_200": 1020,
                    "reasons": ["Stock is below 50/200 DMA and IT regime is not bullish."],
                },
            ],
            dhan_it_opportunities=[approved, blocked],
            dhan_it_news_alerts=[
                {
                    "symbol": "IT-SECTOR",
                    "title": "TCS quarterly results update before market",
                    "link": "https://example.com/tcs-results",
                    "published_date": "08 Aug 2026",
                    "sentiment": "neutral",
                    "alert_type": "RESULT_UPDATE",
                }
            ],
            dhan_it_selected_index="0",
        )
    )
    assert "Compare POP, Gain and Risk" in html
    assert "Decision News" in html
    assert "RESULT ALERT 1" in html
    assert "TCS quarterly results update before market" in html
    assert html.count('formaction="/dhan-it/refresh-news"') == 1
    assert "Refresh News" in html
    assert 'name="dhan_it_refresh_symbol"' not in html
    assert "Refresh TCS" not in html
    assert "Refresh TECHM" not in html
    assert "DHAN-IT Call Spread Watch" in html
    assert "NIFTY IT Sector Index" in html
    assert 'formaction="/dhan-it/open-call-symbol" name="dhan_it_open_symbol" value="TCS"' in html
    assert 'id="dhan-it-opportunity-table"' in html
    assert 'id="dhan-it-comparison-table"' in html
    assert 'class="sort-header" data-sort-col="12">Max Gain' in html
    assert 'class="sort-header" data-sort-col="18">Best Pick' in html
    assert 'formaction="/dhan-it/preview" name="dhan_it_selected_index" value="0">TCS</button>' in html
    assert 'formaction="/dhan-it/preview" name="dhan_it_preview_choice" value="0|CURRENT_MONTH">TCS<small>Open order ticket</small></button>' in html
    assert 'class="dhan-best-pick-cell"><strong>BEST PICK - 1 lot(s)</strong>' in html
    assert 'class="dhan-best-pick-row"' in html
    assert "CURRENT_MONTH" in html
    assert "NEXT_MONTH" in html
    assert 'name="dhan_it_trade_mode"' in html
    assert 'value="PAPER" selected' in html
    assert 'name="dhan_it_expiry_mode" value="CURRENT_MONTH" data-expiry-preview-action="/dhan-it/preview"' in html
    assert 'name="dhan_it_expiry_mode" value="NEXT_MONTH" data-expiry-preview-action="/dhan-it/preview"' in html
    assert 'name="dhan_it_expiry_mode" value="NEXT_SELL_CURRENT_BUY" data-expiry-preview-action="/dhan-it/preview"' in html
    assert 'value="CURRENT_AND_NEXT">Current + Next Month</option>' in html
    assert 'id="dhan-it-confirm-order"' in html
    assert 'data-orderable="1"' in html
    assert 'id="dhan-it-review" type="button" class="secondary">' in html
    assert 'id="dhan-it-countdown"' in html
    assert "Tick max-loss acknowledgement to start 10s review" in html
    assert "I UNDERSTAND the RISK of MAX LOSS" in html
    assert "SELL LEG" in html
    assert "BUY HEDGE" in html
    assert "50/200 DMA Gate" in html
    assert 'id="dhan-it-place-order"' in html
    assert 'id="dhan-it-place-order" type="submit" class="secondary" formaction="/dhan-it/submit" disabled' in html
    assert ">Place Order</button>" in html
    assert "Blocked for test" in html


def test_dhan_it_cards_and_parent_table_render_wipro_and_ltm_defaults():
    rows = dhan_it_universe_rows()
    cards = app.build_dhan_it_call_watch_cards_from_rows(
        [
            {"symbol": "NIFTY IT", "company_name": "NIFTY IT Sector Index", "cmp": 30000, "dma_50": 31000, "dma_200": 32000},
            *[
                {
                    **row,
                    "cmp": 1000,
                    "dma_50": 1050,
                    "dma_200": 1100,
                    "source": "test fixture",
                }
                for row in rows
            ],
        ],
        [],
    )

    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=rows,
            dhan_it_call_watch_cards=cards,
            dhan_it_holding_positions=[],
        )
    )

    assert "IT CE-spread execution: TCS, INFY, HCLTECH, TECHM, WIPRO, LTM." in html
    assert "Wipro Ltd" in html
    assert "LTIMindtree Ltd" in html
    assert "WIPRO" in html
    assert "LTM" in html
    assert "LTIS" not in html
    assert "LTIMINDTREE" not in html
    for symbol in IT_FNO_SYMBOLS:
        assert f'formaction="/dhan-it/open-call-symbol" name="dhan_it_open_symbol" value="{symbol}"' in html
    assert 'formaction="/dhan-it/open-symbol" name="dhan_it_open_symbol"' not in html
    assert "Risk / OTM" in html
    assert "Delta Band" in html
    assert "SELL 7.00%" in html
    assert "HEDGE 12.00%" in html
    assert "SELL 9.00%" in html
    assert "HEDGE 14.00%" in html
    assert "Delta 0.12-0.16" in html


def test_dhan_it_ltm_stock_list_click_path_renders_ltm_execution_ticket():
    ltm_chain = [
        option_row("LTM", "2026-08-27", 1100, "CE", 22),
        option_row("LTM", "2026-08-27", 1150, "CE", 6),
        option_row("LTM", "2026-09-24", 1100, "CE", 22),
        option_row("LTM", "2026-09-24", 1150, "CE", 6),
    ]
    for contract in ltm_chain:
        contract["name"] = "LTIMINDTREE LIMITED"
        contract["underlying"] = ""
    ltm_preview = build_dhan_it_spread(
        symbol="LTM",
        strategy_type="BEAR_CALL_SPREAD",
        spot=1000,
        lots=1,
        option_chain_data=ltm_chain,
        risk_engine=AllowRisk(),
        market_data={"today": date(2026, 8, 4)},
    )
    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[ltm_preview],
            dhan_it_selected_index="0",
            dhan_it_selected_symbols=["LTM"],
            dhan_it_strategy="BEAR_CALL_SPREAD",
            dhan_it_call_watch_cards=[],
            dhan_it_holding_positions=[],
        )
    )

    assert "DHAN-IT Order Ticket - LTM" in html
    assert "LTM08271100CE" in html
    assert "LTM08271150CE" in html
    assert "LTIS" not in html
    assert "LTTS" not in html


def test_dhan_it_ltm_kite_contract_fetch_groups_by_tradingsymbol_when_name_differs(monkeypatch):
    class FakeBroker(MockBroker):
        def __init__(self, *args, **kwargs):
            super().__init__()

        def get_quote(self, instruments):
            return {
                "NSE:LTM": {
                    "last_price": 3509.9,
                    "ohlc": {"close": 3475.0},
                }
            }

        def get_instruments(self, exchange):
            contracts = [
                {
                    **option_row("LTM", "2026-08-27", 3900, "CE", 22),
                    "tradingsymbol": "LTM26AUG3900CE",
                },
                {
                    **option_row("LTM", "2026-08-27", 4000, "CE", 6),
                    "tradingsymbol": "LTM26AUG4000CE",
                },
            ]
            for contract in contracts:
                contract["name"] = "LTIMINDTREE LIMITED"
                contract["underlying"] = ""
            return contracts

    monkeypatch.setattr(app, "DhanBrokerAdapter", FakeBroker)
    spot_by_symbol: dict[str, float] = {}
    contracts_by_symbol: dict[str, list[dict]] = {}

    _adapter, _notes, fresh_quotes = app.enrich_dhan_market_data_from_kite(
        ["LTM"],
        spot_by_symbol,
        contracts_by_symbol,
    )

    assert spot_by_symbol["LTM"] == 3509.9
    assert fresh_quotes["LTM"]["day_change_pct"] == 1.0
    assert [row["tradingsymbol"] for row in contracts_by_symbol["LTM"]] == [
        "LTM26AUG3900CE",
        "LTM26AUG4000CE",
    ]


def test_dhan_it_current_and_next_expiry_mode_is_available_for_evaluation():
    html = app.render_dhan_it_panel(
        app.PageState(active_tab="dhan-it", dhan_it_rows=dhan_it_universe_rows(), dhan_it_expiry_mode="CURRENT_AND_NEXT")
    )

    assert "Current + Next Month" in html
    assert "Use Current + Next Month to populate both Opportunity and Compare tables" in html
    assert 'name="dhan_it_expiry_mode"' in html


def test_dhan_it_holding_position_analyzer_scopes_to_it_symbols_and_suggests_pairs():
    rows = app.analyze_dhan_it_holding_positions(
        holdings=[
            {"tradingsymbol": "TCS", "quantity": 100, "average_price": 3000, "last_price": 3200, "pnl": 20000},
            {"tradingsymbol": "RELIANCE", "quantity": 50, "average_price": 1000, "last_price": 1100},
        ],
        positions=[
            {"tradingsymbol": "TCS26AUG4000CE", "name": "TCS", "instrument_type": "CE", "quantity": -175, "pnl": 1200},
            {"tradingsymbol": "TCS26AUG4200CE", "name": "TCS", "instrument_type": "CE", "quantity": 175, "pnl": -300},
            {"tradingsymbol": "INFY26AUG1700CE", "name": "INFY", "instrument_type": "CE", "quantity": -400, "pnl": -2500},
            {"tradingsymbol": "RELIANCE26AUG3000CE", "name": "RELIANCE", "instrument_type": "CE", "quantity": -250},
        ],
    )
    by_symbol = {row["symbol"]: row for row in rows}

    assert set(by_symbol) == set(IT_FNO_SYMBOLS)
    assert by_symbol["TCS"]["pair_status"] == "PAIR ACTIVE"
    assert by_symbol["TCS"]["cmp"] == 3200
    assert by_symbol["TCS"]["option_pnl"] == 900
    assert by_symbol["TCS"]["sell_options"][0]["strike"] == "4000"
    assert by_symbol["TCS"]["buy_options"][0]["strike"] == "4200"
    assert by_symbol["INFY"]["pair_status"] == "SHORT CE UNHEDGED"
    assert by_symbol["INFY"]["option_pnl"] == -2500
    assert by_symbol["INFY"]["sell_qty_abs"] == 400
    assert by_symbol["INFY"]["buy_qty_abs"] == 0
    assert by_symbol["HCLTECH"]["pair_status"] == "NO CE PAIR"
    assert by_symbol["TECHM"]["suggestion"] == "Build CE SELL + BUY hedge pair from DHAN-IT popup."
    assert by_symbol["WIPRO"]["pair_status"] == "NO CE PAIR"
    assert by_symbol["LTM"]["pair_status"] == "NO CE PAIR"


def test_dhan_it_holding_position_table_renders_below_call_watch():
    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_call_watch_cards=[],
            dhan_it_holding_positions=[
                {
                    "symbol": "TCS",
                    "equity_qty": 100,
                    "average_price": 3000,
                    "last_price": 3200,
                    "pnl": 20000,
                    "sell_count": 1,
                    "buy_count": 1,
                    "sell_symbols": "TCS26AUG4000CE",
                    "buy_symbols": "TCS26AUG4200CE",
                    "pair_status": "PAIR ACTIVE",
                    "suggestion": "Monitor pair; avoid duplicate CE spread.",
                    "action": "MONITOR",
                },
                {
                    "symbol": "INFY",
                    "equity_qty": 0,
                    "average_price": "",
                    "last_price": "",
                    "pnl": "",
                    "sell_count": 0,
                    "buy_count": 0,
                    "sell_symbols": "",
                    "buy_symbols": "",
                    "pair_status": "NO CE PAIR",
                    "suggestion": "Build CE SELL + BUY hedge pair from DHAN-IT popup.",
                    "action": "BUILD_PAIR",
                },
            ],
        )
    )

    assert "DHAN-IT Call Spread Watch" in html
    assert "Current Kite Option Holdings / CE Pair Status" in html
    assert html.index("DHAN-IT Call Spread Watch") < html.index("Current Kite Option Holdings / CE Pair Status")
    assert "PAIR ACTIVE" in html
    assert "NO CE PAIR" in html
    assert "Holding Qty" not in html
    assert "SELL CE Option Holdings" in html
    assert "BUY CE Hedge Holdings" in html
    assert "<th>CMP</th>" in html
    assert "<th>% Change</th>" in html
    assert "3200.00" in html
    assert "<th>P&L</th>" in html
    assert 'formaction="/dhan-it/open-call-symbol" name="dhan_it_open_symbol" value="INFY"' in html


def test_dhan_it_pair_status_cmp_uses_live_call_watch_card_when_no_equity_holding():
    rows = [
        {
            "symbol": "TCS",
            "equity_qty": 0,
            "average_price": "",
            "last_price": "",
            "cmp": "",
            "pnl": "",
            "sell_count": 1,
            "buy_count": 0,
            "sell_symbols": "TCS26AUG4000CE",
            "buy_symbols": "",
            "pair_status": "SHORT CE UNHEDGED",
            "suggestion": "BUY hedge leg or rebuild paired CE spread.",
            "action": "BUY_HEDGE",
        }
    ]
    cards = [{"symbol": "TCS", "price": 3344.25, "day_change_pct": 2.45}]

    enriched = app.enrich_dhan_it_holding_positions_with_call_watch_cmp(rows, cards)
    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_call_watch_cards=cards,
            dhan_it_holding_positions=rows,
        )
    )

    assert enriched[0]["cmp"] == 3344.25
    assert enriched[0]["day_change_pct"] == 2.45
    assert enriched[0]["cmp_source"] == "DHAN-IT live card"
    assert "<th>CMP</th>" in html
    assert "<th>% Change</th>" in html
    assert "3344.25" in html
    assert "2.45%" in html


def test_dhan_it_pair_status_day_change_falls_back_to_current_stock_list_row():
    rows = [
        {
            "symbol": "TECHM",
            "equity_qty": 0,
            "average_price": "",
            "last_price": "",
            "cmp": "",
            "pnl": "",
            "sell_count": 0,
            "buy_count": 0,
            "sell_symbols": "",
            "buy_symbols": "",
            "pair_status": "NO CE PAIR",
            "suggestion": "Build CE SELL + BUY hedge pair from DHAN-IT popup.",
            "action": "BUILD_PAIR",
        }
    ]
    cards = [{"symbol": "TECHM"}]
    stock_rows = [{"symbol": "TECHM", "cmp": 1643.0, "day_change_pct": 3.21}]

    enriched = app.enrich_dhan_it_holding_positions_with_call_watch_cmp(rows, cards, stock_rows)
    html = app.render_dhan_it_holding_positions(enriched)

    assert enriched[0]["cmp"] == 1643.0
    assert enriched[0]["cmp_source"] == "DHAN-IT stock list"
    assert enriched[0]["day_change_pct"] == 3.21
    assert enriched[0]["day_change_source"] == "DHAN-IT stock list"
    assert "1643.00" in html
    assert "3.21%" in html


def test_dhan_it_holding_position_table_offers_repair_for_incomplete_pair():
    html = app.render_dhan_it_holding_positions(
        [
            {
                "symbol": "INFY",
                "equity_qty": 0,
                "average_price": "",
                "last_price": "",
                "pnl": "",
                "sell_count": 1,
                "buy_count": 0,
                "sell_qty_abs": 400,
                "buy_qty_abs": 0,
                "sell_symbols": "INFY26AUG1700CE",
                "buy_symbols": "",
                "pair_status": "SHORT CE UNHEDGED",
                "suggestion": "BUY hedge leg or rebuild paired CE spread.",
                "action": "BUY_HEDGE",
            }
        ]
    )

    assert "SHORT CE UNHEDGED" in html
    assert 'dhan-it-option-chip sell' in html
    assert 'dhan-it-option-empty">No BUY CE' in html
    assert 'formaction="/dhan-it/repair-preview" name="dhan_it_repair" value="INFY|BUY_HEDGE"' in html


def test_dhan_it_repair_preview_and_submit_single_limit_order():
    opportunity = approved_preview()
    holding_row = {"symbol": "TCS", "sell_qty_abs": 250, "buy_qty_abs": 0, "pair_status": "SHORT CE UNHEDGED"}
    preview = app.build_dhan_it_repair_preview_from_opportunity(opportunity, holding_row, "BUY_HEDGE")
    broker = MockBroker()

    assert preview["transaction_type"] == "BUY"
    assert preview["tradingsymbol"] == opportunity["buy_leg_tradingsymbol"]
    assert preview["quantity"] == 250

    outcome = app.submit_dhan_it_repair_order(preview, broker, user_confirmed=True, mode="PAPER")

    assert outcome["order_id"] == "MOCK-1"
    assert len(broker.placed) == 1
    assert broker.placed[0]["exchange"] == "NFO"
    assert broker.placed[0]["order_type"] == "LIMIT"
    assert broker.placed[0]["transaction_type"] == "BUY"
    assert broker.placed[0]["tradingsymbol"] == opportunity["buy_leg_tradingsymbol"]


def test_dhan_it_repair_popup_shows_trader_metrics_and_countdown_controls():
    opportunity = approved_preview()
    holding_row = {"symbol": "TCS", "sell_qty_abs": 250, "buy_qty_abs": 0, "pair_status": "SHORT CE UNHEDGED"}
    preview = app.build_dhan_it_repair_preview_from_opportunity(opportunity, holding_row, "BUY_HEDGE")

    html = app.render_dhan_it_repair_modal(
        app.PageState(active_tab="dhan-it", dhan_it_repair_preview=preview)
    )

    assert "DHAN-IT Repair Order - TCS" in html
    assert "OTM / POP" in html
    assert "RoR / Max Loss" in html
    assert "Trader Context" in html
    assert 'id="dhan-it-repair-confirm"' in html
    assert 'id="dhan-it-repair-review" type="button" class="secondary" disabled' in html
    assert 'id="dhan-it-repair-countdown">10</div>' in html
    assert 'id="dhan-it-repair-place-order" type="submit" class="secondary" formaction="/dhan-it/repair-submit" disabled>Place Order</button>' in html


def test_dhan_it_repair_sell_ce_defaults_next_month_for_higher_premium_and_can_choose_current():
    opportunity = build_preview("BEAR_CALL_SPREAD", chain=it_chain(current_sell=18, current_buy=10, next_sell=35, next_buy=10))
    holding_row = {
        "symbol": "TCS",
        "sell_qty_abs": 0,
        "buy_qty_abs": 250,
        "pair_status": "BUY HEDGE ONLY",
        "buy_options": [{"tradingsymbol": "TCS26AUG1100CE", "quantity": 250}],
    }

    default_selected = app.apply_dhan_it_repair_expiry_choice(opportunity, holding_row, "SELL_CE", "")
    current_selected = app.apply_dhan_it_repair_expiry_choice(opportunity, holding_row, "SELL_CE", "CURRENT_MONTH")
    next_preview = app.build_dhan_it_repair_preview_from_opportunity(default_selected, holding_row, "SELL_CE")
    current_preview = app.build_dhan_it_repair_preview_from_opportunity(current_selected, holding_row, "SELL_CE")

    assert default_selected["selected_expiry_choice"] == "NEXT_MONTH"
    assert next_preview["transaction_type"] == "SELL"
    assert next_preview["tradingsymbol"] == "TCS09241050CE"
    assert next_preview["limit_price"] == 35
    assert current_selected["selected_expiry_choice"] == "CURRENT_MONTH"
    assert current_preview["tradingsymbol"] == "TCS08271050CE"
    assert current_preview["limit_price"] == 18


def test_dhan_it_repair_sell_popup_has_current_next_reload_options():
    opportunity = build_preview("BEAR_CALL_SPREAD", chain=it_chain(current_sell=18, current_buy=10, next_sell=35, next_buy=10))
    holding_row = {"symbol": "TCS", "sell_qty_abs": 0, "buy_qty_abs": 250, "pair_status": "BUY HEDGE ONLY"}
    selected = app.apply_dhan_it_repair_expiry_choice(opportunity, holding_row, "SELL_CE", "")
    preview = app.build_dhan_it_repair_preview_from_opportunity(selected, holding_row, "SELL_CE")

    html = app.render_dhan_it_repair_modal(app.PageState(active_tab="dhan-it", dhan_it_repair_preview=preview))

    assert "SELL leg expiry" in html
    assert 'name="dhan_it_repair" value="TCS|SELL_CE"' in html
    assert 'name="dhan_it_repair_expiry_mode" value="CURRENT_MONTH" data-expiry-preview-action="/dhan-it/repair-preview"' in html
    assert 'name="dhan_it_repair_expiry_mode" value="NEXT_MONTH" data-expiry-preview-action="/dhan-it/repair-preview" checked' in html
    assert "Next month higher premium" in html


def test_dhan_it_repair_buy_hedge_prefers_current_month_even_when_short_is_next_month():
    opportunity = build_preview("BEAR_CALL_SPREAD", chain=it_chain(current_sell=14, current_buy=10, next_sell=35, next_buy=10))
    opportunity["current_month"]["risk_decision"] = "BLOCKED"
    opportunity["current_month_preview"]["risk_decision"] = "BLOCKED"
    holding_row = {
        "symbol": "TCS",
        "sell_qty_abs": 225,
        "buy_qty_abs": 0,
        "pair_status": "SHORT CE UNHEDGED",
        "sell_options": [{"tradingsymbol": "TCS26SEP2600CE", "quantity": -225}],
    }

    selected = app.apply_dhan_it_repair_expiry_choice(opportunity, holding_row, "BUY_HEDGE", "CURRENT_MONTH")
    preview = app.build_dhan_it_repair_preview_from_opportunity(selected, holding_row, "BUY_HEDGE")

    assert selected["expiry"] == "2026-08-27"
    assert preview["transaction_type"] == "BUY"
    assert preview["quantity"] == 225
    assert preview["tradingsymbol"] == "TCS08271100CE"


def test_dhan_it_single_month_mode_shapes_opportunity_but_keeps_compare_rows():
    preview = build_preview("BEAR_CALL_SPREAD", chain=it_chain(current_sell=18, current_buy=10, next_sell=35, next_buy=10))
    selected = app.apply_dhan_it_evaluation_expiry_mode(preview, "CURRENT_MONTH")

    assert preview["recommended_expiry"] == "CURRENT_MONTH"
    assert selected["recommended_expiry"] == "CURRENT_MONTH"
    assert selected["sell_leg_tradingsymbol"] == "TCS08271050CE"
    assert selected["buy_leg_tradingsymbol"] == "TCS08271100CE"
    assert selected["next_month"]["sell_leg_tradingsymbol"] == "TCS09241050CE"


def test_dhan_it_quality_clear_enables_review_without_acknowledgement():
    preview = build_preview("BEAR_CALL_SPREAD", chain=it_chain(current_sell=55, current_buy=10, next_sell=60, next_buy=10))
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "RETURN_ON_RISK_TOO_LOW"
    preview["reason"] = preview["risk_reason"]
    preview["pop_estimate"] = 80
    preview["max_gain"] = 12000

    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
        )
    )

    assert app.dhan_pair_quality_auto_clears(preview)
    assert 'data-auto-clear="1"' in html
    assert "Soft-blocker override available" in html
    assert 'id="dhan-it-review" type="button" class="secondary">' in html


def test_dhan_it_builder_uses_two_thousand_profit_threshold():
    preview = build_preview("BEAR_CALL_SPREAD", chain=it_chain(current_sell=18, current_buy=10, next_sell=35, next_buy=10))

    assert preview["recommended_expiry"] == "CURRENT_MONTH"
    assert preview["max_gain"] == 2000
    assert preview["risk_decision"] == "APPROVED"


def test_dhan_it_near_cmp_strike_profile_moves_targets_one_percent_closer():
    chain = it_chain() + [
        option_row("TCS", "2026-08-27", 1150, "CE", 38),
        option_row("TCS", "2026-08-27", 1200, "CE", 12),
        option_row("TCS", "2026-09-24", 1150, "CE", 39),
        option_row("TCS", "2026-09-24", 1200, "CE", 13),
    ]
    preview = build_dhan_it_spread(
        symbol="TCS",
        strategy_type="BEAR_CALL_SPREAD",
        spot=1100,
        lots=1,
        option_chain_data=chain,
        kite_adapter=None,
        risk_engine=AllowRisk(),
        market_data={"today": date(2026, 8, 4)},
        technical_data={"sell_otm_pct": 4.0, "hedge_otm_pct": 9.0},
        event_data={},
    )

    assert preview["raw_sell_target_strike"] == 1144
    assert preview["raw_hedge_target_strike"] == 1199
    assert preview["sell_leg_tradingsymbol"] == "TCS08271150CE"
    assert preview["buy_leg_tradingsymbol"] == "TCS08271200CE"


def test_dhan_it_red_liquidity_allows_paper_popup_flow_but_blocks_live_popup_flow():
    preview = approved_preview()
    preview["pair_liquidity_condition"] = "RED"
    preview["liquidity_order_allowed"] = False
    preview["liquidity_reason"] = "Poor liquidity — order blocked."
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "LIQUIDITY_RED_ORDER_BLOCKED"
    preview["reason"] = preview["risk_reason"]

    paper_html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
            dhan_it_confirm_order=True,
        )
    )
    live_html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
            dhan_it_confirm_order=True,
            dhan_it_paper_trading=False,
        )
    )

    assert "Liquidity Condition" in paper_html
    assert "Poor liquidity — paper flow allowed; live order blocked" in paper_html
    assert 'data-orderable="1"' in paper_html
    assert 'id="dhan-it-review" type="button" class="secondary">' in paper_html
    assert "DHAN-IT blocks RED liquidity in both Paper and Live mode" in live_html
    assert 'data-orderable="0"' in live_html


def test_dhan_it_amber_liquidity_allows_acknowledged_review():
    preview = approved_preview()
    preview["pair_liquidity_condition"] = "AMBER"
    preview["liquidity_order_allowed"] = True
    preview["liquidity_reason"] = "Acceptable liquidity — order allowed with caution."

    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
            dhan_it_confirm_order=True,
        )
    )

    assert "Liquidity is acceptable but not strong. Use limit order and verify slippage." in html
    assert 'data-orderable="1"' in html
    assert 'id="dhan-it-review" type="button" class="secondary">' in html


def test_dhan_it_popup_blocks_trade_when_quarterly_result_is_within_ten_days():
    preview = approved_preview()
    result_day = datetime.now(app.INDIA_TIME_ZONE).date() + timedelta(days=4)
    preview["next_result_date"] = result_day.isoformat()

    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
            dhan_it_confirm_order=True,
        )
    )

    assert "Next result date" in html
    assert f"Quarterly results is on {result_day.strftime('%d %b %Y')} hence blocking the trade" in html
    assert 'data-orderable="0"' in html
    assert 'id="dhan-it-review" type="button" class="secondary" disabled' in html


def test_dhan_it_red_liquidity_blocks_live_but_allows_paper_submit(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    preview = approved_preview()
    preview["pair_liquidity_condition"] = "RED"
    preview["liquidity_order_allowed"] = False
    preview["liquidity_reason"] = "Poor liquidity — order blocked."

    try:
        submit_dhan_it_pair(preview, repo, broker, user_confirmed=True, mode="LIVE")
    except ValueError as exc:
        assert "LIQUIDITY_RED_ORDER_BLOCKED" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("RED liquidity must block live submission")
    assert broker.placed == []

    paper_broker = MockBroker()
    result = submit_dhan_it_pair(preview, repo, paper_broker, user_confirmed=True, mode="PAPER")
    assert result["pair_id"]
    assert len(paper_broker.placed) == 2


def test_dhan_it_submit_blocks_near_quarterly_result_even_in_paper(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    preview = approved_preview()
    result_day = datetime.now(app.INDIA_TIME_ZONE).date() + timedelta(days=2)
    guarded = app.apply_dhan_result_date_guard(preview | {"next_result_date": result_day.isoformat()})

    try:
        submit_dhan_it_pair(guarded, repo, broker, user_confirmed=True, mode="PAPER")
    except ValueError as exc:
        assert "DHAN_IT_RISK_REWARD_BLOCKED" in str(exc)
        assert f"Quarterly results is on {result_day.strftime('%d %b %Y')} hence blocking the trade" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("near result date must block DHAN-IT order submission")
    assert broker.placed == []


def test_dhan_it_bilateral_depth_clears_red_wide_liquidity_for_live_review_and_submit(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    preview = approved_preview()
    preview["pair_liquidity_condition"] = "RED"
    preview["liquidity_order_allowed"] = False
    preview["liquidity_reason"] = "Liquidity condition is RED.; WIDE_BID_ASK; LIQUIDITY_RED_ORDER_BLOCKED"
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "WIDE_BID_ASK; LIQUIDITY_RED_ORDER_BLOCKED"
    preview["reason"] = preview["risk_reason"]
    preview["sell_leg_buy_orders"] = 20
    preview["sell_leg_sell_orders"] = 20
    preview["hedge_leg_buy_orders"] = 20
    preview["hedge_leg_sell_orders"] = 20
    preview["sell_leg_liquidity"] = {
        "top_5_buy_order_count": 20,
        "top_5_sell_order_count": 20,
        "liquidity_condition": "RED",
        "liquidity_reason": "WIDE_BID_ASK",
    }
    preview["hedge_leg_liquidity"] = {
        "top_5_buy_order_count": 20,
        "top_5_sell_order_count": 20,
        "liquidity_condition": "RED",
        "liquidity_reason": "WIDE_BID_ASK",
    }

    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
            dhan_it_confirm_order=True,
            dhan_it_paper_trading=False,
        )
    )

    assert "Depth override: both legs have at least 20 buy and sell limit orders" in html
    assert 'data-orderable="1"' in html
    assert 'id="dhan-it-review" type="button" class="secondary">' in html
    assert 'id="dhan-it-place-order" type="submit" class="danger" formaction="/dhan-it/submit" disabled' in html

    result = submit_dhan_it_pair(preview, repo, broker, user_confirmed=True, mode="LIVE")
    pair = repo.get_pair(result["pair_id"])
    payload = json.loads(pair["payload_json"])

    assert result["pair_id"]
    assert len(broker.placed) == 2
    assert payload["risk_override"] == "DHAN_IT_BILATERAL_DEPTH_CLEAR"
    assert "bilateral depth" in payload["risk_reason"]


def test_dhan_it_stale_option_quote_blocks_submit(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    preview = approved_preview()
    preview["option_quote_generated_at"] = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat(timespec="seconds")

    try:
        submit_dhan_it_pair(preview, repo, broker, user_confirmed=True, mode="PAPER")
    except ValueError as exc:
        assert "QUOTE_STALE_ORDER_BLOCKED" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("stale DHAN-IT option quotes must block submit")
    assert broker.placed == []


def test_dhan_it_popup_uses_main_live_mode_selector():
    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[approved_preview()],
            dhan_it_selected_index="0",
            dhan_it_paper_trading=False,
            dhan_it_confirm_order=True,
        )
    )

    assert 'name="dhan_it_trade_mode"' in html
    assert 'value="LIVE" selected' in html
    assert ">Place Order</button>" in html
    assert "Live hedge-first execution" in html
    assert "Live order button is disabled until DHAN_IT_LIVE_ENABLED=YES" not in html
    assert 'data-orderable="1"' in html
    assert 'id="dhan-it-review" type="button" class="secondary">' in html
    assert 'name="dhan_it_submit_mode"' not in html


def test_dhan_it_standard_cycle_ack_unlocks_place_order_for_defined_risk_soft_block():
    preview = approved_preview()
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "POP below DHAN-IT minimum; max loss above configured limit"
    preview["reason"] = preview["risk_reason"]
    preview["pop_estimate"] = 66.5
    preview["return_on_risk_pct"] = 14.09
    preview["max_gain"] = 7410.0
    preview["max_loss"] = 52590.0

    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
            dhan_it_confirm_order=True,
        )
    )

    assert 'data-orderable="1"' in html
    assert 'id="dhan-it-review" type="button" class="secondary">' in html
    assert 'id="dhan-it-place-order" type="submit" class="secondary" formaction="/dhan-it/submit" disabled' in html
    assert "I UNDERSTAND the RISK of MAX LOSS" in html


def test_dhan_it_dma_red_allows_good_liquidity_defined_risk_pair_submit(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    preview = approved_preview()
    preview.update(
        {
            "symbol": "TECHM",
            "dma_status": "RED",
            "dma_decision": "CONFIRM_REQUIRED",
            "dma_reasons": "50/200 DMA gate RED",
            "pair_liquidity_condition": "GREEN",
            "liquidity_order_allowed": True,
            "liquidity_reason": "Good liquidity",
            "pop_estimate": 71.3,
            "return_on_risk_pct": 9.66,
            "max_gain": 4230.0,
            "max_loss": 43770.0,
        }
    )

    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
            dhan_it_confirm_order=True,
            dhan_it_paper_trading=False,
        )
    )

    assert "DMA RED shown as warning only because this defined-risk pair has good executable liquidity." in html
    assert 'data-orderable="1"' in html
    assert 'id="dhan-it-review" type="button" class="secondary">' in html

    result = submit_dhan_it_pair(preview, repo, broker, user_confirmed=True, mode="LIVE")

    assert result["pair_id"]
    assert len(broker.placed) == 2


def test_dhan_it_paper_red_liquidity_ack_enables_countdown_for_execution_flow():
    preview = approved_preview()
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "POP below 70.0%; max loss above ₹40,000, liquidity weak"
    preview["reason"] = preview["risk_reason"]
    preview["pop_estimate"] = 66.5
    preview["return_on_risk_pct"] = 14.09
    preview["max_gain"] = 7410.0
    preview["max_loss"] = 52590.0
    preview["pair_liquidity_condition"] = "RED"
    preview["liquidity_order_allowed"] = False
    preview["liquidity_reason"] = "Poor liquidity — paper flow allowed; live order blocked."

    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
            dhan_it_confirm_order=True,
            dhan_it_paper_trading=True,
        )
    )

    assert "Poor liquidity — paper flow allowed; live order blocked" in html
    assert 'data-orderable="1"' in html
    assert 'id="dhan-it-review" type="button" class="secondary">' in html
    assert 'id="dhan-it-place-order" type="submit" class="secondary" formaction="/dhan-it/submit" disabled' in html


def test_dhan_it_submit_accepts_defined_risk_soft_pop_and_loss_breaches(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    preview = approved_preview()
    preview["pop_estimate"] = 66.5
    preview["return_on_risk_pct"] = 14.09
    preview["max_gain"] = 7410.0
    preview["max_loss"] = 52590.0

    result = submit_dhan_it_pair(preview, repo, broker, user_confirmed=True, mode="PAPER")
    pair = repo.get_pair(result["pair_id"])
    payload = json.loads(pair["payload_json"])

    assert len(broker.placed) == 2
    assert broker.placed[0]["transaction_type"] == "BUY"
    assert broker.placed[1]["transaction_type"] == "SELL"
    assert payload["accepted_risk_warnings"] == [
        "POP below DHAN-IT minimum",
        "max loss above configured limit",
    ]


def test_dhan_it_submit_accepts_acknowledged_soft_blocked_opportunity(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    preview = approved_preview()
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "risk engine did not approve, POP below 70.0%, max loss above ₹40,000"
    preview["reason"] = preview["risk_reason"]
    preview["pop_estimate"] = 66.5
    preview["return_on_risk_pct"] = 14.09
    preview["max_gain"] = 7410.0
    preview["max_loss"] = 52590.0

    result = submit_dhan_it_pair(preview, repo, broker, user_confirmed=True, mode="PAPER")
    pair = repo.get_pair(result["pair_id"])
    payload = json.loads(pair["payload_json"])

    assert len(broker.placed) == 2
    assert payload["risk_override"] == "DHAN_IT_USER_ACCEPTED_SOFT_BLOCKERS"
    assert payload["risk_decision_original"] == "BLOCKED"
    assert "User accepted DHAN-IT soft blockers" in payload["risk_reason"]


def test_dhan_it_popup_mixed_expiry_changes_selected_values():
    preview = build_preview("BEAR_CALL_SPREAD", chain=it_chain(current_sell=18, current_buy=10, next_sell=35, next_buy=10))
    selected = app.apply_dhan_expiry_choice(preview, "NEXT_SELL_CURRENT_BUY")

    assert selected["sell_expiry"] == "2026-09-24"
    assert selected["buy_expiry"] == "2026-08-27"
    assert selected["sell_leg_tradingsymbol"] == "TCS09241050CE"
    assert selected["buy_leg_tradingsymbol"] == "TCS08271100CE"
    assert selected["risk_decision"] == "BLOCKED"

    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
            dhan_it_expiry_mode="NEXT_SELL_CURRENT_BUY",
        )
    )

    assert "SELL 2026-09-24 / BUY 2026-08-27" in html
    assert 'value="NEXT_SELL_CURRENT_BUY" data-expiry-preview-action="/dhan-it/preview" checked' in html
    assert "TCS09241050CE" in html
    assert "TCS08271100CE" in html


def test_dhan_it_popup_uses_next_month_legs_when_recommended_next_month():
    preview = build_preview("BEAR_CALL_SPREAD", chain=it_chain(current_sell=14, current_buy=10, next_sell=35, next_buy=10))
    selected = app.apply_dhan_expiry_choice(preview, "NEXT_MONTH")

    assert preview["recommended_expiry"] == "NEXT_MONTH"
    assert selected["sell_leg_tradingsymbol"] == "TCS09241050CE"
    assert selected["buy_leg_tradingsymbol"] == "TCS09241100CE"
    assert selected["sell_expiry"] == "2026-09-24"
    assert selected["buy_expiry"] == "2026-09-24"

    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
            dhan_it_expiry_mode="AUTO_COMPARE",
        )
    )

    assert "Selected expiry" in html
    assert "2026-09-24" in html
    assert "<span>SELL LEG</span>" in html
    assert "<strong>TCS09241050CE</strong>" in html
    assert "<span>BUY HEDGE</span>" in html
    assert "<strong>TCS09241100CE</strong>" in html
    assert 'name="dhan_it_preview_choice" value="0|NEXT_MONTH"' in html


def test_dhan_it_compare_link_uses_clicked_next_month_even_when_not_recommended():
    preview = build_preview(
        "BEAR_CALL_SPREAD",
        symbol="TECHM",
        chain=it_chain(symbol="TECHM", current_sell=35, current_buy=10, next_sell=22.9, next_buy=2.65),
    )
    assert preview["recommended_expiry"] == "CURRENT_MONTH"
    preview["next_month"]["risk_decision"] = "NO_TRADE"
    preview["next_month"]["risk_reason"] = "POP below DHAN-IT minimum; max loss above configured limit"
    preview["next_month_preview"]["risk_decision"] = "NO_TRADE"
    preview["next_month_preview"]["risk_reason"] = preview["next_month"]["risk_reason"]
    selected = app.apply_dhan_expiry_choice(preview, "NEXT_MONTH", allow_unapproved_preview=True)

    assert selected["sell_leg_tradingsymbol"] == "TECHM09241050CE"
    assert selected["buy_leg_tradingsymbol"] == "TECHM09241100CE"
    assert selected["sell_expiry"] == "2026-09-24"
    assert selected["buy_expiry"] == "2026-09-24"

    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[preview],
            dhan_it_selected_index="0",
            dhan_it_expiry_mode="NEXT_MONTH",
        )
    )
    ticket = html.split('id="dhan-it-order-modal"', 1)[1]

    assert 'name="dhan_it_preview_choice" value="0|NEXT_MONTH"' in html
    assert 'value="NEXT_MONTH" data-expiry-preview-action="/dhan-it/preview" checked' in ticket
    assert "<strong>TECHM09241050CE</strong>" in ticket
    assert "<strong>TECHM09241100CE</strong>" in ticket
    assert "<strong>TECHM08271050CE</strong>" not in ticket
    assert "<strong>TECHM08271100CE</strong>" not in ticket


def test_dhan_it_opportunity_data_expires_after_ten_minutes_in_render():
    old_stamp = (app.datetime.now(app.INDIA_TIME_ZONE) - app.timedelta(minutes=11)).isoformat(timespec="seconds")
    html = app.render_dhan_it_panel(
        app.PageState(
            active_tab="dhan-it",
            dhan_it_rows=dhan_it_universe_rows(),
            dhan_it_opportunities=[approved_preview()],
            dhan_it_opportunities_generated_at=old_stamp,
        )
    )

    assert "Analysis is older than 10 minutes" in html
    assert 'formaction="/dhan-it/preview" name="dhan_it_selected_index" value="0">TCS</button>' not in html


def test_paper_submit_places_buy_and_parks_sell_above_cmp(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    preview = approved_preview()
    result = submit_dhan_it_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER")
    pair = repo.get_pair(result["pair_id"])
    payload = json.loads(pair["payload_json"])

    assert len(broker.placed) == 2
    assert broker.placed[0]["transaction_type"] == "BUY"
    assert broker.placed[0]["price"] == preview["buy_limit_price"]
    assert broker.placed[1]["transaction_type"] == "SELL"
    assert broker.placed[1]["price"] == round(preview["sell_limit_price"] * 1.10, 2)
    assert pair["buy_leg_order_id"] == "MOCK-1"
    assert pair["sell_leg_order_id"] == "MOCK-2"
    assert pair["sell_leg_placed"] == 1
    assert pair["pair_status"] == "SUBMITTED_WAITING_HEDGE"
    assert payload["sell_reprice_after_hedge"] is True


def test_monitor_reprices_parked_sell_after_buy_hedge_completes(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    preview = approved_preview()
    result = submit_dhan_it_pair(preview, repo, broker, user_confirmed=True, mode="PAPER")
    run_dhan_it_pair_monitor_once(repo, broker)
    pair_before_fill = repo.get_pair(result["pair_id"])
    assert len(broker.placed) == 2
    assert pair_before_fill["sell_leg_placed"] == 1
    broker.orders = [{"order_id": "MOCK-1", "status": "COMPLETE"}, {"order_id": "MOCK-2", "status": "OPEN"}]
    monitor_result = run_dhan_it_pair_monitor_once(repo, broker)
    pair_after_fill = repo.get_pair(result["pair_id"])
    payload_after_fill = json.loads(pair_after_fill["payload_json"])

    assert monitor_result["modified"] == 1
    assert monitor_result["placed"] == 0
    assert len(broker.placed) == 2
    assert broker.modified == [("regular", "MOCK-2", {"order_type": "LIMIT", "price": preview["sell_limit_price"]})]
    assert pair_after_fill["sell_leg_placed"] == 1
    assert pair_after_fill["pair_status"] == "HEDGE_FILLED_SELL_REPRICED"
    assert payload_after_fill["sell_repriced_after_hedge_at"]


def test_dhan_it_limit_prices_are_rounded_to_zerodha_tick_size(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    preview = approved_preview()
    preview["buy_limit_price"] = 5.03
    preview["buy_leg_premium"] = 5.03
    preview["sell_limit_price"] = 11.94
    preview["sell_leg_premium"] = 11.94

    result = submit_dhan_it_pair(preview, repo, broker, user_confirmed=True, mode="PAPER")
    pair = repo.get_pair(result["pair_id"])
    payload = json.loads(pair["payload_json"])

    assert round_limit_price_to_tick(11.94) == 11.95
    assert broker.placed[0]["transaction_type"] == "BUY"
    assert broker.placed[0]["price"] == 5.05
    assert broker.placed[1]["transaction_type"] == "SELL"
    assert broker.placed[1]["price"] == 13.15
    assert payload["sell_cmp_limit_price"] == 11.95
    assert payload["sell_initial_limit_price"] == 13.15

    broker.orders = [{"order_id": "MOCK-1", "status": "COMPLETE"}, {"order_id": "MOCK-2", "status": "OPEN"}]
    monitor_result = run_dhan_it_pair_monitor_once(repo, broker)

    assert monitor_result["modified"] == 1
    assert broker.modified == [("regular", "MOCK-2", {"order_type": "LIMIT", "price": 11.95})]


def test_monitor_blocks_sell_when_refreshed_liquidity_turns_red(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    result = submit_dhan_it_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER")
    repo.update_pair(result["pair_id"], sell_leg_order_id="", sell_leg_placed=0, sell_leg_status="PENDING")
    broker.orders = [{"order_id": "MOCK-1", "status": "COMPLETE"}]
    broker.quotes = {"TCS08271050CE": depth_quote(4, 500)}

    monitor_result = run_dhan_it_pair_monitor_once(repo, broker)
    pair_after_check = repo.get_pair(result["pair_id"])

    assert monitor_result["failed"] == 1
    assert len(broker.placed) == 2
    assert pair_after_check["sell_leg_placed"] == 0
    assert pair_after_check["pair_status"] == "HEDGE_FILLED_SELL_BLOCKED_LIQUIDITY"


def test_existing_dhan_and_new_dhan_it_panels_render_without_loading_live_data():
    dhan_html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads", dhan_watchlist=[]))
    dhan_it_html = app.render_dhan_it_panel(app.PageState(active_tab="dhan-it", dhan_it_rows=dhan_it_universe_rows()))
    assert 'id="kite-spreads-panel"' in dhan_html
    assert "DHAN-IT" in dhan_it_html
    assert "DHAN-IT Call Spread Watch" in dhan_it_html


def test_dhan_it_pair_monitor_has_dhan_scheduler_controls_and_five_minute_interval():
    app.DHAN_IT_SCHEDULER_STATUS.update(
        {
            "running": False,
            "mode": "PAPER",
            "last_started_at": "2026-08-09T09:15:00+05:30",
            "last_stopped_at": "",
            "last_run_at": "2026-08-09T09:20:00+05:30",
            "last_result": {"checked": 2, "modified": 1, "placed": 0, "failed": 0, "exit_required": 0},
            "last_error": "",
        }
    )

    html = app.render_dhan_it_panel(app.PageState(active_tab="dhan-it", dhan_it_rows=dhan_it_universe_rows()))

    assert "Pair Order Monitor" in html
    assert "Job Status" in html
    assert "300s" in html
    assert "Checked 2 | modified 1 | placed 0 | failed 0 | exit-required 0" in html
    assert 'formaction="/dhan-it/monitor-run"' in html
    assert 'formaction="/dhan-it/scheduler-start"' in html
    assert 'formaction="/dhan-it/scheduler-stop"' in html
    assert 'formaction="/dhan-it/load"' in html
    assert 'formaction="/dhan-it/clear-pair-monitor"' in html
    assert "Clear Monitor" in html
    app.DHAN_IT_SCHEDULER_STATUS.update({"mode": "PAPER", "last_result": {}, "last_run_at": "", "last_error": ""})


def test_dhan_it_stock_list_marks_watch_rise_when_day_change_above_three_pct():
    rows = dhan_it_universe_rows()
    rows[0]["cmp"] = 4100
    rows[0]["day_change_pct"] = 3.25
    rows[1]["cmp"] = 1650
    rows[1]["day_change_pct"] = 2.99

    html = app.render_dhan_it_panel(app.PageState(active_tab="dhan-it", dhan_it_rows=rows))

    assert "CMP / Day" in html
    assert "creates WATCH RISE only" in html
    assert "3.25%" in html
    assert "2.99%" in html
    assert html.count("WATCH RISE") >= 1
    assert "CALL PAIR SELL" not in html
    assert "PE_SELL_CANDIDATE" not in html
    assert "BULL_PUT_SPREAD" not in html
    assert 'dhan-it-call-pair-indicator">WATCH RISE</span>' in html
