from pathlib import Path
from datetime import date, timedelta

import pytest
import app

from trade_terminal import TradeTerminalRepository, has_blocks, score_validations, validation


def test_watchlist_sync_is_persistent_and_deduplicated(tmp_path: Path) -> None:
    repo = TradeTerminalRepository(tmp_path / "trade.db")
    repo.sync_watchlist("A1", ["TCS", "INFY", "TCS"], "DHAN_IT")
    repo.add_symbol("A1", "RELIANCE")

    assert [row["symbol"] for row in repo.symbols("A1")] == ["INFY", "RELIANCE", "TCS"]


def test_daily_best_trade_scan_is_saved_and_replaced(tmp_path: Path) -> None:
    repo = TradeTerminalRepository(tmp_path / "trade.db")
    repo.save_daily_scan("A1", "2026-10-18", [{"symbol": "TCS", "rank_score": 78.5}])
    assert repo.daily_scan("A1", "2026-10-18")["rows"][0]["symbol"] == "TCS"

    repo.save_daily_scan("A1", "2026-10-18", [{"symbol": "INFY", "rank_score": 82.0}])
    loaded = repo.daily_scan("A1", "2026-10-18")
    assert [row["symbol"] for row in loaded["rows"]] == ["INFY"]


def test_direction_snapshot_is_persisted_per_account_symbol_and_day(tmp_path: Path) -> None:
    repo = TradeTerminalRepository(tmp_path / "trade.db")
    repo.save_direction_snapshot("A1", "TCS", "2026-10-18", {"strategy_candidate": "CE BUY", "technical_score": 82})
    loaded = repo.direction_snapshot("A1", "TCS", "2026-10-18")
    assert loaded["strategy_candidate"] == "CE BUY"
    assert loaded["technical_score"] == 82
    assert loaded["saved_at"]


def test_execution_reservation_blocks_duplicate_final_click(tmp_path: Path) -> None:
    repo = TradeTerminalRepository(tmp_path / "trade.db")
    preview = {
        "symbol": "TCS",
        "tradingsymbol": "TCS26OCT3000CE",
        "side": "BUY",
        "quantity": 175,
        "limit_price": 12.05,
        "review_nonce": "fixed-review",
    }
    checks = [validation("Contract", "PASS", "Verified")]
    audit_id, _ = repo.reserve("A1", preview, "PAPER", checks, "Exit below support")
    repo.complete(audit_id, "OPEN", "PAPER-1", {"status": "OPEN"})

    with pytest.raises(PermissionError, match="Duplicate trade submission blocked"):
        repo.reserve("A1", preview, "PAPER", checks, "Exit below support")


def test_block_status_fails_closed() -> None:
    checks = [
        validation("Quote", "PASS", "Fresh"),
        validation("Naked SELL", "BLOCK", "Undefined risk"),
    ]
    assert has_blocks(checks) is True


def test_equal_weight_score_and_hard_block_override() -> None:
    score, decision = score_validations(
        [
            validation("Quote", "PASS", "Fresh"),
            validation("POP", "WARNING", "Below preferred range"),
            validation("Naked SELL", "BLOCK", "Undefined risk"),
        ]
    )
    assert score == 50.0
    assert decision == "DO NOT PLACE"


def test_score_allows_high_quality_review_without_blocks() -> None:
    score, decision = score_validations(
        [
            validation("Quote", "PASS", "Fresh"),
            validation("POP", "PASS", "Preferred range"),
            validation("Liquidity", "WARNING", "Depth is acceptable with caution"),
            validation("Margin", "PASS", "Available"),
        ]
    )
    assert score == 87.5
    assert decision == "ELIGIBLE TO PLACE"


def test_trade_review_renders_client_cancel_cmp_trend_and_nearby_pop() -> None:
    state = app.PageState(
        active_tab="trade",
        trade_watchlist=[],
        trade_contracts=[],
        trade_market={},
        trade_recent_orders=[],
        trade_checks=[validation("Quote", "PASS", "Fresh")],
        trade_preview={
            "tradingsymbol": "PGEL26OCT580PE",
            "symbol": "PGEL",
            "side": "BUY",
            "mode": "PAPER",
            "strike": 580,
            "option_type": "PE",
            "expiry": "2026-10-29",
            "quantity": 950,
            "limit_price": 5.0,
            "premium_value": 4750,
            "stock_cmp": 610,
            "day_change_pct": -1.2,
            "trend_score": -6,
            "trend_label": "BEARISH",
            "trend_reasons": ["CMP below 50 DMA"],
            "pop": 44.5,
            "delta": -0.445,
            "iv_percent": 31.2,
            "decision_score": 100,
            "decision": "ELIGIBLE TO PLACE",
            "nearby_strikes": [{"tradingsymbol": "PGEL26OCT560PE", "strike": 560, "ltp": 3.2, "bid": 3.1, "ask": 3.3, "pop": 35.5, "volume": 20, "oi": 500, "selected": False}],
        },
    )
    rendered = app.render_trade_panel(state)
    assert 'type="button" class="secondary" id="trade-modal-cancel"' in rendered
    assert "Stock CMP" in rendered
    assert "Trend −10 to +10" in rendered
    assert "35.50%" in rendered
    assert "Select &amp; Evaluate" in rendered
    assert "Recalculated for PGEL26OCT580PE" in rendered
    assert '<details class="trade-check-disclosure">' in rendered
    assert "Show all execution checks" in rendered
    assert "includes Verified contract through Execution mode" in rendered
    assert '<button type="submit" formnovalidate>Refresh Stock</button>' in rendered
    assert "Your capital is at risk. Accept possible loss" not in rendered
    assert "Exit / invalidation plan" not in rendered


def test_best_trade_scan_renders_saved_results_and_explicit_recalculate() -> None:
    state = app.PageState(
        active_tab="trade",
        trade_watchlist=[{"symbol": "TCS", "source": "DHAN_IT"}],
        trade_contracts=[{
            "tradingsymbol": "TCS26OCT3000CE", "expiry": "2026-10-29", "strike": 3000,
            "instrument_type": "CE", "lot_size": 175,
        }],
        trade_market={},
        trade_recent_orders=[],
        trade_contract_symbol="TCS26OCT3000CE",
        trade_side="SELL",
        trade_applied_suggestion={"symbol": "TCS", "contract": "TCS26OCT3000CE", "side": "SELL", "source": "BEST_FOR_TRADE"},
        trade_best_scan_open=True,
        trade_best_scan={
            "scan_date": "2026-10-18",
            "created_at": "2026-10-18T10:00:00+05:30",
            "rows": [{
                "symbol": "TCS", "regime": "BEARISH", "rank_score": 81.25,
                "pop": 76.5, "premium_yield_pct": 1.25,
                "annualized_premium_yield_pct": 15.0, "side": "SELL",
                "contract": "TCS26OCT3000CE", "technical_structure": "defined-risk CE SELL",
                "expiry": "2026-10-29", "dte": 11, "ltp": 25.0, "spread_pct": 2.0,
                "eligible": True, "risk_note": "Defined-risk hedge required.",
            }],
        },
    )
    rendered = app.render_trade_panel(state)
    assert "BEST for TRADE — Daily Market Scan" in rendered
    assert "81.25" in rendered
    assert "76.50%" in rendered
    assert 'formaction="/trade/best/recalculate"' in rendered
    assert 'formaction="/trade/best/select"' in rendered
    assert 'form="trade-terminal-panel" formmethod="post" formaction="/trade/best/select" formnovalidate' in rendered
    assert 'data-trade-best-open' in rendered
    assert '<input type="hidden" name="active_tab" value="trade">' in rendered
    assert "Find BEST for TRADE" in rendered
    assert '<option value="TCS26OCT3000CE" selected>' in rendered
    assert '<option value="SELL" selected>SELL</option>' in rendered
    assert "Suggested contract" in rendered
    assert "Direction" in rendered
    assert 'data-applied-suggestion="1"' in rendered
    assert "scrollIntoView" in app.render_page(state).decode("utf-8")


def test_best_strategy_result_can_default_manual_order_on_parent_page() -> None:
    state = app.PageState(
        active_tab="trade",
        trade_symbol="TCS",
        trade_watchlist=[{"symbol": "TCS", "source": "DHAN_IT"}],
        trade_contracts=[{
            "tradingsymbol": "TCS26OCT3000CE", "expiry": "2026-10-29", "strike": 3000,
            "instrument_type": "CE", "lot_size": 175,
        }],
        trade_market={"symbol": "TCS"},
        trade_recent_orders=[],
        trade_contract_symbol="TCS26OCT3000CE",
        trade_side="SELL",
        trade_direction_result={
            "strategy_candidate": "CE SELL", "technical_score": 78,
            "reason": "Resistance rejection confirmed.", "final_decision": "WATCH",
            "option_liquidity_status": "PASS", "event_risk_status": "PASS", "risk_engine_status": "BLOCK",
            "primary_timeframe": "1D",
            "indicators": {"price": 3000, "ema20": 3020, "sma50": 3050, "sma200": 2900, "rsi_14": 46},
            "hourly_confirmation": {"candle_count": 300, "ema20": 2995, "sma50": 3010, "sma200": 3040},
            "selected_contract": {"tradingsymbol": "TCS26OCT3000CE", "side": "SELL", "expiry": "2026-10-29"},
            "scores": {"CE_SELL": {"strategy": "CE SELL", "score": 78, "signal": "Resistance rejection", "classification": "CONFIRM", "components": {"trend": 24, "momentum": 15, "structure": 18, "volume": 12, "sector": 9}, "evidence": ["Lower highs"], "contradictory_evidence": [], "invalidation": "Close above resistance"}},
        },
    )
    rendered = app.render_trade_panel(state)
    assert "TCS · ₹3000.00" in rendered
    assert "3-month / 1-hour confirmation" in rendered
    assert 'formaction="/trade/direction/apply"' in rendered
    assert "Use SELL TCS26OCT3000CE in Manual Option Order" in rendered
    assert '<option value="TCS26OCT3000CE" selected>' in rendered
    assert '<option value="SELL" selected>SELL</option>' in rendered
    assert "trade-best-modal" not in rendered


def test_market_intelligence_compares_current_and_next_expiry(monkeypatch) -> None:
    today = app.app_now().date()
    current = today + timedelta(days=8)
    following = today + timedelta(days=38)
    instruments = []
    for expiry, suffix in ((current, "OCT"), (following, "NOV")):
        for option_type in ("CE", "PE"):
            instruments.append(
                {
                    "expiry": expiry,
                    "strike": 1000,
                    "instrument_type": option_type,
                    "tradingsymbol": f"TEST26{suffix}1000{option_type}",
                    "lot_size": 100,
                }
            )

    def fake_quotes(_kite, keys, ttl_seconds=0):
        return {
            key: {
                "last_price": 25,
                "volume": 500,
                "oi": 5000,
                "depth": {"buy": [{"price": 24.9}], "sell": [{"price": 25.1}]},
            }
            for key in keys
        }

    monkeypatch.setattr(app, "cached_kite_quote", fake_quotes)
    result = app.build_trade_market_intelligence(
        object(),
        instruments,
        {"cmp": 1020, "dma_50": 1000, "dma_200": 950, "day_change_pct": 1.5},
    )
    assert result["regime"] == "BULLISH"
    assert result["preferred_expiry"] == "NEXT"
    assert len(result["expiry_comparison"]) == 4
    assert len(result["expiry_comparison_all"]) == 12
    assert {row["otm_pct"] for row in result["expiry_comparison_all"]} == {0, 5, 10}
    assert {row["option_type"] for row in result["expiry_comparison"]} == {"CE", "PE"}
    assert all(row["ltp"] == 25 for row in result["expiry_comparison"])
    assert len(result["five_pct_direction_choices"]) == 4
    preferred = [row for row in result["five_pct_direction_choices"] if row["status"] == "PREFERRED"]
    assert {row["label"] for row in preferred} == {"5% OTM CE BUY", "5% OTM PE SELL"}
    assert next(row for row in preferred if row["side"] == "SELL")["defined_risk_required"] is True


def test_tradingview_symbol_mapping_is_exchange_aware_and_safe() -> None:
    nse = app.tradingview_symbol_context("NSE", "INFY")
    bse = app.tradingview_symbol_context("BSE", "500209")
    invalid = app.tradingview_symbol_context("NSE", "BAD/SYMBOL?<script>")
    unsupported = app.tradingview_symbol_context("NFO", "INFY")

    assert nse["widget_symbol"] == "NSE:INFY"
    assert nse["url"] == "https://www.tradingview.com/chart/?symbol=NSE%3AINFY"
    assert bse["widget_symbol"] == "BSE:500209"
    assert invalid["available"] is False
    assert unsupported["available"] is False


def test_kite_candle_technical_checklist_is_independent_of_tradingview() -> None:
    class FakeKite:
        def historical_data(self, instrument_token, from_date, to_date, interval):
            assert instrument_token == 123
            assert interval == "day"
            return [
                {"close": 800 + index, "high": 805 + index, "low": 795 + index}
                for index in range(220)
            ]

    technical = app.build_trade_technical_checklist(FakeKite(), 123, 1030)
    assert technical["source"] == "ZERODHA_KITE_HISTORICAL_DAILY"
    assert technical["dma_20"] > technical["dma_50"] > technical["dma_200"]
    assert technical["breakout"] is True
    assert "CE BUY" in technical["supports"]


def test_trade_market_intelligence_renders_lazy_tradingview_widget() -> None:
    state = app.PageState(
        active_tab="trade",
        trade_watchlist=[],
        trade_contracts=[],
        trade_recent_orders=[],
        trade_market={
            "cmp": 1500,
            "day_change_pct": 6.25,
            "intelligence": {"regime": "BULLISH", "score": 7},
            "result_date": {
                "next_result_date_display": "28 Oct 2026",
                "result_date_near": True,
                "result_date_message": "Quarterly results is on 28 Oct 2026 hence blocking the trade",
            },
            "tradingview": app.tradingview_symbol_context("NSE", "TCS"),
            "technical_checklist": {
                "dma_20": 1490,
                "dma_50": 1450,
                "dma_200": 1300,
                "rsi_14": 61,
                "rsi_direction": "RISING",
                "support": 1420,
                "resistance": 1510,
                "sector_alignment": "UNKNOWN",
                "supports": "CE BUY / defined-risk PE SELL",
                "thesis_invalidation": "Below 1420",
            },
        },
    )
    rendered = app.render_trade_panel(state)
    assert "https://www.tradingview.com/chart/?symbol=NSE%3ATCS" in rendered
    assert "Show Kite Candlestick Chart / Hide Chart" in rendered
    full_page = app.render_page(state).decode("utf-8")
    assert "lightweight-charts@5.0.9" in full_page
    assert "loadTradeKiteChart" in full_page
    assert "CandlestickSeries" in full_page
    assert "Technical Trade Confirmation" in rendered
    assert "Open Full TradingView Chart" in rendered
    assert "no TradingView credentials or private layouts are embedded" in rendered
    assert "trade-kite-chart-view-" in full_page
    assert 'id="trade-kite-chart-range"' in rendered
    assert '<option value="1M" selected>1 month</option>' in rendered
    assert '<option value="1D">1 day</option>' in rendered
    assert '<option value="1W">1 week</option>' in rendered
    assert '<option value="3M">3 months</option>' in rendered
    assert '<option value="1Y">1 year</option>' in rendered
    assert '<option value="5Y">5 years</option>' in rendered
    assert "filterTradeCandlesByRange" in full_page
    assert "Bullish biased" in rendered
    assert "trade-day-strong-up" in rendered
    assert "+6.25%" in rendered
    assert 'class="trade-result-card"' in rendered
    assert "Quarterly results is on 28 Oct 2026" in rendered
    assert "Expiry snapshot distance" in rendered
    assert '<option value="5" selected>5% OTM</option>' in rendered
    assert "Technical outcome: CE BUY / defined-risk PE SELL" in rendered
    assert "trade-expiry-otm-filter" in full_page
    assert "applyTradeExpiryOtmFilter" in full_page
    assert "trade-technical-card up" in rendered
    assert "trade-intelligence-cards" in rendered
    assert "<th>Check</th><th>Value</th><th>Observation</th><th>Check</th><th>Value</th><th>Observation</th>" in rendered
    intelligence_heading = rendered.index("Market Intelligence — CE/PE &amp; Expiry Decision Support")
    intelligence_status = rendered.index("Refreshed from the selected NSE stock quote", intelligence_heading)
    assert "Open Full TradingView Chart" not in rendered[intelligence_heading:intelligence_status]
    chart_position = rendered.index("Show Kite Candlestick Chart / Hide Chart")
    direction_matrix_position = rendered.index("5% OTM Direction Matrix")
    expiry_snapshot_position = rendered.index("Current vs Next Expiry — ATM CE/PE Snapshot")
    assert chart_position < direction_matrix_position < expiry_snapshot_position
    assert "trade-expiry-decision-block" in rendered
    assert "Technical Direction Engine" in rendered
    assert 'formaction="/trade/direction"' in rendered
    assert "Best strategy" in rendered


def test_trade_chart_candles_validate_and_preserve_selected_symbol(monkeypatch) -> None:
    class FakeKite:
        def historical_data(self, instrument_token, from_date, to_date, interval):
            count = 30 if interval == "day" else 40
            return [
                {
                    "date": app.app_now() - timedelta(minutes=15 * (count - index)) if interval == "15minute" else date(2026, 9, 1) + timedelta(days=index),
                    "open": 100 + index,
                    "high": 102 + index,
                    "low": 99 + index,
                    "close": 101 + index,
                    "volume": 1000 + index,
                }
                for index in range(count)
            ]

    monkeypatch.setattr(app, "cached_value", lambda _key, loader, _ttl: loader())
    payload = app.load_trade_chart_candles(FakeKite(), 991)
    assert len(payload["daily"]) == 30
    assert len(payload["intraday_15m"]) == 40
    assert len(payload["hourly_3m"]) == 40
    assert payload["source"] == "ZERODHA_KITE_HISTORICAL"
    delhivery = app.tradingview_symbol_context("NSE", "DELHIVERY")
    assert delhivery["widget_symbol"] == "NSE:DELHIVERY"
    assert delhivery["url"].endswith("symbol=NSE%3ADELHIVERY")


def test_chart_reload_fetches_selected_kite_interval_and_range() -> None:
    calls = []

    class FakeKite:
        def historical_data(self, instrument_token, from_date, to_date, interval):
            calls.append((instrument_token, from_date, to_date, interval))
            return [{
                "date": app.app_now(), "open": 100, "high": 102, "low": 99,
                "close": 101, "volume": 1000,
            }]

    result = app.reload_trade_chart_window(FakeKite(), 991, "60", "3M")
    assert result["requested_interval"] == "60"
    assert result["requested_range"] == "3M"
    assert result["source"] == "ZERODHA_KITE_HISTORICAL_RELOAD"
    assert result["rows"][0]["close"] == 101
    assert calls[0][0] == 991
    assert all(call[3] == "60minute" for call in calls)


def test_chart_reload_supports_five_year_daily_window_in_chunks() -> None:
    calls = []

    class FakeKite:
        def historical_data(self, instrument_token, from_date, to_date, interval):
            calls.append((from_date, to_date, interval))
            return [{
                "date": from_date, "open": 100, "high": 102, "low": 99,
                "close": 101, "volume": 1000,
            }]

    result = app.reload_trade_chart_window(FakeKite(), 992, "D", "5Y")
    assert result["requested_range"] == "5Y"
    assert len(calls) >= 2
    assert all(call[2] == "day" for call in calls)
    assert len(result["rows"]) == len(calls)


def test_chart_reload_controls_preserve_server_selected_values() -> None:
    state = app.PageState(
        active_tab="trade", trade_symbol="TCS", trade_watchlist=[], trade_contracts=[],
        trade_recent_orders=[], trade_chart_interval="60", trade_chart_range="3M",
        trade_market={"symbol": "TCS", "tradingview": app.tradingview_symbol_context("NSE", "TCS"), "chart_data": {"reloaded_rows": [{"time": "2026-10-18T10:00:00+05:30", "open": 1, "high": 2, "low": 1, "close": 2}], "reloaded_interval": "60", "reloaded_range": "3M"}},
    )
    rendered = app.render_trade_panel(state)
    assert 'name="trade_chart_interval"' in rendered
    assert '<option value="60" selected>1 hour</option>' in rendered
    assert '<option value="3M" selected>3 months</option>' in rendered
    assert 'formaction="/trade/chart/reload"' in rendered
    assert "Reload from Kite" in rendered
    assert 'data-server-selection="1"' in rendered
    assert "normalizeTradeChartTimes" in app.render_page(state).decode("utf-8")

