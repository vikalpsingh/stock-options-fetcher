from __future__ import annotations

from datetime import date

import app
from dhan_it_pair_execution import DhanItPairRepository, submit_dhan_it_pair
from dhan_it_pair_monitor import run_dhan_it_pair_monitor_once
from dhan_it_signal_engine import evaluate_it_signal
from dhan_it_spread_builder import build_dhan_it_spread
from dhan_it_universe import IT_FNO_SYMBOLS, dhan_it_universe_rows, is_dhan_it_symbol


class AllowRisk:
    def evaluate(self, trade):
        return {"decision": "APPROVED", "reason_codes": []}


class MockBroker:
    def __init__(self):
        self.placed = []
        self.orders = []

    def place_order(self, payload):
        self.placed.append(payload)
        return {"order_id": f"MOCK-{len(self.placed)}", "status": "OPEN"}

    def get_orders(self):
        return self.orders


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


def test_dhan_it_universe_is_fixed_to_four_it_fno_symbols():
    assert IT_FNO_SYMBOLS == ["TCS", "INFY", "HCLTECH", "TECHM"]
    assert [row["symbol"] for row in dhan_it_universe_rows()] == IT_FNO_SYMBOLS
    assert is_dhan_it_symbol("infy")
    assert not is_dhan_it_symbol("RELIANCE")


def test_signal_engine_recommends_ce_or_pe_and_blocks_event_risk():
    ce = evaluate_it_signal("TCS", market_data={"cmp": 1000}, technical_data={"ema20": 1010, "ema50": 1020, "rsi": 55})
    pe = evaluate_it_signal("INFY", market_data={"cmp": 1000}, technical_data={"ema20": 990, "ema50": 980, "rsi": 55})
    blocked = evaluate_it_signal("TECHM", market_data={"cmp": 1000}, event_data={"event_risk": True})
    assert ce["recommended_strategy"] == "BEAR_CALL_SPREAD"
    assert pe["recommended_strategy"] == "BULL_PUT_SPREAD"
    assert blocked["trader_view"] == "AVOID"


def test_builds_current_month_ce_spread_when_gain_threshold_is_met():
    preview = build_preview("BEAR_CALL_SPREAD")
    assert preview["screen_name"] == "DHAN-IT"
    assert preview["recommended_expiry"] == "CURRENT_MONTH"
    assert preview["sell_leg_tradingsymbol"].endswith("1050CE")
    assert preview["buy_leg_tradingsymbol"].endswith("1100CE")
    assert preview["max_gain"] >= 5000


def test_builds_current_month_pe_spread_when_gain_threshold_is_met():
    preview = build_preview("BULL_PUT_SPREAD")
    assert preview["recommended_expiry"] == "CURRENT_MONTH"
    assert preview["sell_leg_tradingsymbol"].endswith("950PE")
    assert preview["buy_leg_tradingsymbol"].endswith("900PE")


def test_rolls_to_next_month_when_current_gain_is_low_and_next_is_approved():
    chain = it_chain(current_sell=18, current_buy=10, next_sell=35, next_buy=10)
    preview = build_preview("BEAR_CALL_SPREAD", chain=chain)
    assert preview["recommended_expiry"] == "NEXT_MONTH"
    assert preview["expiry"] == "2026-09-24"
    assert preview["current_month"]["max_gain"] < 5000
    assert preview["next_month"]["max_gain"] >= 5000


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
            dhan_it_opportunities=[approved, blocked],
            dhan_it_selected_index="0",
        )
    )
    assert "Compare POP, Gain and Risk" in html
    assert 'id="dhan-it-opportunity-table"' in html
    assert 'id="dhan-it-comparison-table"' in html
    assert 'class="sort-header" data-sort-col="12">Max Gain' in html
    assert 'class="sort-header" data-sort-col="18">Best Pick' in html
    assert 'formaction="/dhan-it/preview" name="dhan_it_selected_index" value="0">TCS</button>' in html
    assert html.count('formaction="/dhan-it/preview" name="dhan_it_selected_index" value="0">TCS</button>') >= 2
    assert 'class="dhan-best-pick-cell"><strong>BEST PICK - 1 lot(s)</strong>' in html
    assert 'class="dhan-best-pick-row"' in html
    assert "CURRENT_MONTH" in html
    assert "NEXT_MONTH" in html
    assert 'name="dhan_it_trade_mode"' in html
    assert 'value="PAPER" selected' in html
    assert 'name="dhan_it_expiry_mode" value="CURRENT_MONTH" data-expiry-preview-action="/dhan-it/preview"' in html
    assert 'name="dhan_it_expiry_mode" value="NEXT_MONTH" data-expiry-preview-action="/dhan-it/preview"' in html
    assert 'name="dhan_it_expiry_mode" value="NEXT_SELL_CURRENT_BUY" data-expiry-preview-action="/dhan-it/preview"' in html
    assert 'id="dhan-it-confirm-order"' in html
    assert 'data-orderable="1"' in html
    assert 'id="dhan-it-review" type="button" class="secondary" disabled' in html
    assert 'id="dhan-it-countdown"' in html
    assert "Tick acknowledgement to start 10s review" in html
    assert 'id="dhan-it-place-order"' in html
    assert 'id="dhan-it-place-order" type="submit" class="secondary" formaction="/dhan-it/submit" disabled' in html
    assert "Submit Paper Order" in html
    assert "Blocked for test" in html


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
    assert "Quality-clear available" in html
    assert 'id="dhan-it-review" type="button" class="secondary">' in html


def test_dhan_it_red_liquidity_allows_paper_popup_flow_but_blocks_live():
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
    assert "Paper mode: RED liquidity is shown for execution-flow testing; live order would be blocked." in paper_html
    assert 'data-orderable="1"' in paper_html
    assert 'id="dhan-it-review" type="button" class="secondary">' in paper_html
    assert "Place Order disabled because liquidity condition is RED." in live_html
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


def test_dhan_it_red_liquidity_blocks_live_submit_but_allows_paper_flow(tmp_path):
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
    outcome = submit_dhan_it_pair(preview, repo, paper_broker, user_confirmed=True, mode="PAPER")
    assert outcome["mode"] == "PAPER"
    assert outcome["buy_leg_order_id"]
    assert len(paper_broker.placed) == 1
    assert paper_broker.placed[0]["transaction_type"] == "BUY"


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
    assert "Submit Live Order" in html
    assert "Live hedge-first execution" in html
    assert "Live order button is disabled until DHAN_IT_LIVE_ENABLED=YES" not in html
    assert 'data-orderable="1"' in html
    assert 'id="dhan-it-review" type="button" class="secondary">' in html
    assert 'name="dhan_it_submit_mode"' not in html


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


def test_paper_submit_records_buy_hedge_only_first(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    result = submit_dhan_it_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER")
    pair = repo.get_pair(result["pair_id"])
    assert len(broker.placed) == 1
    assert broker.placed[0]["transaction_type"] == "BUY"
    assert pair["buy_leg_order_id"] == "MOCK-1"
    assert not pair["sell_leg_order_id"]
    assert pair["pair_status"] == "SUBMITTED"


def test_monitor_places_sell_only_after_buy_hedge_completes(tmp_path):
    repo = DhanItPairRepository(tmp_path / "dhan_it.db")
    broker = MockBroker()
    result = submit_dhan_it_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER")
    run_dhan_it_pair_monitor_once(repo, broker)
    pair_before_fill = repo.get_pair(result["pair_id"])
    assert len(broker.placed) == 1
    assert pair_before_fill["sell_leg_placed"] == 0
    broker.orders = [{"order_id": "MOCK-1", "status": "COMPLETE"}]
    monitor_result = run_dhan_it_pair_monitor_once(repo, broker)
    pair_after_fill = repo.get_pair(result["pair_id"])
    assert monitor_result["placed"] == 1
    assert len(broker.placed) == 2
    assert broker.placed[1]["transaction_type"] == "SELL"
    assert pair_after_fill["sell_leg_placed"] == 1
    assert pair_after_fill["pair_status"] == "HEDGE_FILLED_WAITING_SELL"


def test_existing_dhan_and_new_dhan_it_panels_render_without_loading_live_data():
    dhan_html = app.render_kite_spreads_panel(app.PageState(active_tab="kite-spreads", dhan_watchlist=[]))
    dhan_it_html = app.render_dhan_it_panel(app.PageState(active_tab="dhan-it", dhan_it_rows=dhan_it_universe_rows()))
    assert 'id="kite-spreads-panel"' in dhan_html
    assert "DHAN-IT" in dhan_it_html


def test_dhan_it_stock_list_marks_call_pair_sell_when_day_change_above_three_pct():
    rows = dhan_it_universe_rows()
    rows[0]["cmp"] = 4100
    rows[0]["day_change_pct"] = 3.25
    rows[1]["cmp"] = 1650
    rows[1]["day_change_pct"] = 2.99

    html = app.render_dhan_it_panel(app.PageState(active_tab="dhan-it", dhan_it_rows=rows))

    assert "CMP / Day" in html
    assert "Daily change above 3% is marked as CALL PAIR SELL" in html
    assert "3.25%" in html
    assert "2.99%" in html
    assert html.count("CALL PAIR SELL") == 2
    assert 'dhan-it-call-pair-indicator">CALL PAIR SELL</span>' in html
