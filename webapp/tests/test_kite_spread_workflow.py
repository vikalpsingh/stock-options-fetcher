from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import app
from kite_broker_adapter import KiteBrokerAdapter
from kite_option_resolver import KiteOptionResolver, next_otm_strike
from kite_pair_execution import submit_kite_pair
from kite_pair_scheduler import run_kite_pair_scheduler_once
from kite_spread_engine import build_kite_spread_preview, fetch_cmp_from_kite, fetch_fresh_equity_quotes_from_kite
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
                "depth": {"buy": [{"price": ltp - 0.1}], "sell": [{"price": ltp + 0.1}]},
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
    assert next_otm_strike(1255.32, "CE", 50) == 1300
    assert next_otm_strike(1084.14, "PE", 50) == 1050


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


def test_bajajfinance_ce_hedge_uses_next_available_1300_for_10pct_target():
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
    assert preview["buy_leg_tradingsymbol"] == "BAJFINANCE26AUG1300CE"
    assert preview["hedge_target_strike"] == 1300
    assert preview["hedge_strike"] == 1300


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
    assert "/kite-spreads/analyze-symbol" in html
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


def test_fresh_kite_quote_includes_52_week_high_gap():
    quotes = fetch_fresh_equity_quotes_from_kite(MockKiteAdapter(), ["RELIANCE"])

    assert quotes["RELIANCE"]["yearly_high"] == 1250
    assert quotes["RELIANCE"]["pct_to_52_high"] == -20.0


def test_dhan_selected_opportunity_renders_modal_execution_review(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = approved_preview()

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


def test_dhan_opportunity_table_highlights_pop_and_gain_and_opens_popup(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = approved_preview()
    preview["pop_estimate"] = 85
    preview["max_gain"] = 12000

    html = app.render_kite_spreads_panel(
        app.PageState(
            active_tab="kite-spreads",
            dhan_opportunities=[preview],
            dhan_selected_index="",
        )
    )

    assert "Opportunity Table - Compare POP, Gain and Risk" in html
    assert 'id="dhan-opportunity-table"' in html
    assert 'class="sort-header" data-sort-col="14">POP' in html
    assert 'class="sort-header" data-sort-col="11">Max Gain' in html
    assert 'class="sort-header" data-sort-col="17">Risk Decision' in html
    assert 'formaction="/kite-spreads/preview-pair"' in html
    assert "Open Popup" in html
    assert html.count("dhan-good-metric") >= 2
    assert "85.00%" in html
    assert "12000.00" in html
    assert 'formaction="/kite-spreads/clear-pair-monitor"' in html
    assert "Clear Monitor" in html


def test_dhan_checkbox_can_unlock_defined_risk_warning_pair(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.db")
    preview = approved_preview()
    preview["risk_decision"] = "BLOCKED"
    preview["risk_reason"] = "RETURN_ON_RISK_TOO_LOW; MAX_LOSS_TOO_HIGH"
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
    assert result["sell_leg_order_id"] == ""
    assert pair["sell_leg_placed"] == 0


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


def test_nuvama_blocks_ce_but_can_still_be_evaluated_for_pe():
    ce_preview = build_kite_spread_preview(
        "NUVAMA",
        1000,
        "BEAR_CALL_SPREAD",
        "2026-08-27",
        1,
        KiteOptionResolver(instruments=[
            {"tradingsymbol": "NUVAMA26AUG1050CE", "name": "NUVAMA", "expiry": "2026-08-27", "instrument_type": "CE", "strike": 1050, "last_price": 12, "lot_size": 75},
            {"tradingsymbol": "NUVAMA26AUG1100CE", "name": "NUVAMA", "expiry": "2026-08-27", "instrument_type": "CE", "strike": 1100, "last_price": 5, "lot_size": 75},
        ]),
        None,
        AllowRisk(),
    )
    pe_preview = build_kite_spread_preview(
        "NUVAMA",
        1000,
        "BULL_PUT_SPREAD",
        "2026-08-27",
        1,
        KiteOptionResolver(instruments=[
            {"tradingsymbol": "NUVAMA26AUG950PE", "name": "NUVAMA", "expiry": "2026-08-27", "instrument_type": "PE", "strike": 950, "last_price": 12, "lot_size": 75},
            {"tradingsymbol": "NUVAMA26AUG900PE", "name": "NUVAMA", "expiry": "2026-08-27", "instrument_type": "PE", "strike": 900, "last_price": 5, "lot_size": 75},
        ]),
        None,
        AllowRisk(),
    )

    assert "CE_COVERAGE_BLOCKED_NO_SHARES" in ce_preview["risk_reason"]
    assert "CE_COVERAGE_BLOCKED_NO_SHARES" not in pe_preview["risk_reason"]


def test_gpt_suggestions_are_saved_into_db(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    universe = KiteSpreadUniverse(repo)

    saved = universe.save_gpt_suggestions([{"symbol": "PFC", "company_name": "PFC", "gpt_view": "CE_SELL", "reason": "Weak"}])

    assert saved == 1
    assert repo.list_watchlist()[0]["gpt_view"] == "CE_SELL"


def approved_preview() -> dict:
    return build_kite_spread_preview("RELIANCE", 1000, "BEAR_CALL_SPREAD", "2026-08-27", 1, KiteOptionResolver(instruments=instruments()), MockKiteAdapter(), AllowRisk())


def test_paper_mode_does_not_call_real_kite_place_order(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = KiteBrokerAdapter(kite=None, paper_trading=True)

    result = submit_kite_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER")

    assert result["buy_leg_order_id"].startswith("PAPER-KITE")
    assert len(broker.call_log) == 1


def test_live_order_requires_explicit_confirmation(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()

    try:
        submit_kite_pair(approved_preview(), repo, broker, user_confirmed=False, mode="LIVE")
    except ValueError as exc:
        assert "Explicit confirmation" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Live order should require explicit confirmation")


def test_hedge_first_does_not_place_sell_until_buy_complete(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()

    result = submit_kite_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER", execution_mode="HEDGE_FIRST")

    assert result["sell_leg_order_id"] == ""
    assert len(broker.placed) == 1
    assert broker.placed[0]["transaction_type"] == "BUY"


def test_rejected_hedge_prevents_sell_leg_placement(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    result = submit_kite_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER")
    broker.orders = [{"order_id": result["buy_leg_order_id"], "status": "REJECTED"}]

    summary = run_kite_pair_scheduler_once(repo, broker)

    assert summary["failed"] == 1
    assert len(broker.placed) == 1


def test_scheduler_places_sell_after_hedge_complete_without_duplicates(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    broker = MockKiteAdapter()
    result = submit_kite_pair(approved_preview(), repo, broker, user_confirmed=True, mode="PAPER")
    broker.orders = [{"order_id": result["buy_leg_order_id"], "status": "COMPLETE"}]

    run_kite_pair_scheduler_once(repo, broker)
    run_kite_pair_scheduler_once(repo, broker)

    assert len(broker.placed) == 2
    assert broker.placed[1]["transaction_type"] == "SELL"


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
