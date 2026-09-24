from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import app
import sell_on_rise_monitor as monitor_module
from sell_on_rise_monitor import (
    Candle,
    QuoteObservation,
    SellOnRiseMonitorConfig,
    SellOnRiseMonitorRepository,
    build_completed_candles_from_quotes,
    evaluate_pattern,
    monitoring_window,
    summarize_quote_movement,
    build_monitor_rows,
    build_price_tape,
    calculate_monitor_history,
    detect_rise_then_decline,
    downsample_monitor_history,
    signal_idempotency_key,
    validate_monitor_config,
)


IST = ZoneInfo("Asia/Kolkata")


def _ts(minute: int) -> datetime:
    return datetime(2026, 9, 11, 9, minute, tzinfo=IST)


def _candle(minute: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle("TEST", _ts(minute), open_, high, low, close, volume=None, complete=True)


def _valid_config(**overrides) -> SellOnRiseMonitorConfig:
    cfg = SellOnRiseMonitorConfig(selected_symbols=["TEST"], expiry="2026-09-29")
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def test_monitoring_window_start_time_is_ist():
    cfg = _valid_config(monitor_mode="SCHEDULED", monitor_start_time_ist="09:30", monitor_duration_minutes=150)

    window = monitoring_window(cfg, trading_day=date(2026, 9, 11))

    assert window["actual_start_timestamp_ist"] == "2026-09-11T09:30:00+05:30"
    assert window["expected_end_timestamp_ist"] == "2026-09-11T12:00:00+05:30"


def test_start_now_mode_calculates_end_time():
    start = datetime(2026, 9, 11, 10, 5, tzinfo=IST)

    window = monitoring_window(_valid_config(monitor_mode="START_NOW", monitor_duration_minutes=30), started_now_at=start)

    assert window["actual_start_timestamp_ist"] == "2026-09-11T10:05:00+05:30"
    assert window["expected_end_timestamp_ist"] == "2026-09-11T10:35:00+05:30"


def test_invalid_intervals_and_durations_are_rejected():
    cfg = _valid_config(quote_check_interval_seconds=3, monitor_duration_minutes=500, candle_timeframe_minutes=2)

    errors = validate_monitor_config(cfg)

    assert any("interval" in error for error in errors)
    assert any("duration" in error for error in errors)
    assert any("timeframe" in error for error in errors)


def test_completed_candles_exclude_incomplete_bucket():
    observations = [
        QuoteObservation("TEST", _ts(30), 100.0),
        QuoteObservation("TEST", _ts(30) + timedelta(seconds=20), 101.0),
        QuoteObservation("TEST", _ts(31), 102.0),
    ]

    candles = build_completed_candles_from_quotes(observations, 1, now=_ts(31) + timedelta(seconds=30))

    assert len(candles) == 1
    assert candles[0].open == 100.0
    assert candles[0].high == 101.0
    assert candles[0].close == 101.0


def test_rebound_rejection_requires_confirmation_break_below_rejection_low():
    candles = [
        _candle(31, 100.0, 100.2, 99.0, 99.2),
        _candle(32, 99.2, 99.5, 98.0, 98.2),
        _candle(33, 98.2, 98.4, 97.0, 97.2),
        _candle(34, 97.2, 98.2, 97.1, 98.0),
        _candle(35, 98.0, 99.1, 97.8, 99.0),
        _candle(36, 99.0, 100.2, 98.5, 98.8),
        _candle(37, 98.8, 98.9, 98.0, 98.2),
    ]

    result = evaluate_pattern(
        "TEST",
        candles,
        _valid_config(),
        evaluation={"previous_close": 99.5, "state": "NEAR_HIGH_REJECTION"},
        existing_state={"monitor_session_id": "S1", "short_strike": "105", "hedge_strike": "110"},
        now=_ts(38),
    )

    assert result["pattern_state"] == "REJECTION_CONFIRMED"
    assert result["decision"] == "SELL_SIGNAL"
    assert result["pattern"]["rejection_type"] in {"FAILED_BREAKOUT", "SHOOTING_STAR", "LOWER_HIGH_REVERSAL"}
    assert result["signal_key"]


def test_resistance_touch_without_confirmation_does_not_signal():
    candles = [
        _candle(31, 100.0, 100.2, 99.0, 99.2),
        _candle(32, 99.2, 99.5, 98.0, 98.2),
        _candle(33, 98.2, 98.4, 97.0, 97.2),
        _candle(34, 97.2, 98.2, 97.1, 98.0),
        _candle(35, 98.0, 99.1, 97.8, 99.0),
        _candle(36, 99.0, 100.2, 98.5, 98.8),
    ]

    result = evaluate_pattern("TEST", candles, _valid_config(), evaluation={"previous_close": 99.5}, now=_ts(37))

    assert result["decision"] in {"WAIT_FOR_CONFIRMATION", "REJECTION_CANDIDATE"}
    assert result["pattern_state"] != "REJECTION_CONFIRMED"
    assert not result["signal_key"]


def test_duplicate_signal_is_prevented_by_database_unique_key(tmp_path):
    repo = SellOnRiseMonitorRepository(tmp_path / "monitor.sqlite3")
    cfg = _valid_config()
    repo.save_config(cfg)
    session = repo.create_or_update_session(cfg, start_now=True)
    key = signal_idempotency_key(
        trading_date="2026-09-11",
        monitor_session_id=session["session_id"],
        symbol="TEST",
        expiry="2026-09-29",
        rejection_timestamp="2026-09-11T09:36:00+05:30",
        confirmation_timestamp="2026-09-11T09:37:00+05:30",
        short_strike="105",
        hedge_strike="110",
    )
    result = {"symbol": "TEST", "signal_key": key, "decision": "SELL_SIGNAL"}

    assert repo.create_signal_once(session["session_id"], result) is True
    assert repo.create_signal_once(session["session_id"], result) is False


def test_scan_increment_respects_configured_interval(tmp_path):
    repo = SellOnRiseMonitorRepository(tmp_path / "monitor.sqlite3")
    cfg = _valid_config(quote_check_interval_seconds=60)
    session = repo.create_or_update_session(cfg, start_now=True)

    repo.increment_scan(session["session_id"], interval_seconds=60)
    refreshed = repo.latest_session()

    assert refreshed["scans_completed"] == 1
    next_scan = datetime.fromisoformat(refreshed["next_scan_at"])
    updated = datetime.fromisoformat(refreshed["updated_at"])
    assert 55 <= (next_scan - updated).total_seconds() <= 65


def test_latest_observations_return_price_from_scan_call(tmp_path):
    repo = SellOnRiseMonitorRepository(tmp_path / "monitor.sqlite3")
    cfg = _valid_config()
    session = repo.create_or_update_session(cfg, start_now=True)
    repo.save_observations(
        session["session_id"],
        [
            QuoteObservation("TEST", _ts(30), 100.0, day_change_pct=1.2),
            QuoteObservation("TEST", _ts(31), 101.5, day_change_pct=1.7),
        ],
    )

    latest = repo.latest_observations(session["session_id"])

    assert latest["TEST"]["ltp"] == 101.5
    assert latest["TEST"]["day_change_pct"] == 1.7
    assert latest["TEST"]["quote_timestamp_ist"] == "2026-09-11T09:31:00+05:30"


def test_quote_movement_distinguishes_rise_top_and_decline():
    now = _ts(31)
    def observations(prices):
        return [QuoteObservation("TEST", _ts(30) + timedelta(seconds=10 * index), price) for index, price in enumerate(prices)]

    assert summarize_quote_movement(observations([100, 100.1, 100.2, 100.3]), now=now)["movement"] == "STILL RISING"
    assert summarize_quote_movement(observations([100, 100.3, 100.24, 100.20]), now=now)["movement"] == "TOPPING WATCH"
    decline = summarize_quote_movement(observations([100, 100.4, 100.3, 100.2]), now=now)
    assert decline["movement"] == "DECLINE STARTING"
    assert decline["pullback_pct"] > 0.15
    assert summarize_quote_movement(observations([100, 100.4, 100.3, 100.2]), now=_ts(32))["movement"] == "STALE QUOTE"


def test_monitor_row_reports_option_movement_separately():
    now = datetime.now(IST).replace(microsecond=0)
    option_points = [
        {"timestamp_ist": (now - timedelta(seconds=30 - index * 10)).isoformat(), "price": price}
        for index, price in enumerate([20.0, 20.4, 20.3, 20.2])
    ]
    rows = build_monitor_rows(
        _valid_config(), None, {}, {"TEST": {"best_ce_symbol": "TEST26SEP105CE"}},
        latest_quotes={"TEST": {"ltp": 100.0}},
        quote_history={"TEST26SEP105CE": option_points},
        option_symbols={"TEST": "TEST26SEP105CE"},
    )
    assert rows[0]["option_symbol"] == "TEST26SEP105CE"
    assert rows[0]["option_ltp"] == 20.2
    assert rows[0]["option_movement"]["movement"] == "DECLINE STARTING"


def test_price_tape_preserves_price_and_per_quote_direction():
    quotes = [
        {"timestamp_ist": (_ts(30) + timedelta(seconds=10 * index)).isoformat(), "price": price}
        for index, price in enumerate([100.0, 100.2, 100.1, 100.1])
    ]
    tape = build_price_tape(quotes)
    assert [point["direction"] for point in tape] == ["flat", "up", "down", "flat"]
    assert tape[1]["change_pct"] == 0.2
    assert tape[2]["change_pct"] == -0.1
    assert tape[3]["price"] == 100.1


def test_monitor_renders_compact_table_and_one_hour_chart():
    state = app.PageState(
        active_tab="52w-ai-call-spread",
        ai52_candidates=[{"symbol": "GLENMARK"}, {"symbol": "WELCORP"}],
        ai52_monitor_config=SellOnRiseMonitorConfig(selected_symbols=["GLENMARK", "WELCORP"]).to_dict(),
        ai52_monitor_rows=[
            {"symbol": "GLENMARK", "spot": 2464.6, "interval_return_pct": -0.02, "history": [
                {"timestamp_ist": "2026-09-11T10:00:00+05:30", "time": "10:00:00", "price": 2464.6, "interval_return_pct": None},
                {"timestamp_ist": "2026-09-11T10:00:10+05:30", "time": "10:00:10", "price": 2465.0, "interval_return_pct": 0.016},
                {"timestamp_ist": "2026-09-11T10:00:20+05:30", "time": "10:00:20", "price": 2464.5, "interval_return_pct": -0.020},
            ]},
            {"symbol": "WELCORP", "spot": 0, "history": []},
        ],
    )
    page = app.render_ai52_call_spread_panel(state)
    assert "10s stock price tape" not in page
    assert "Largest latest interval movement" in page
    assert "GLENMARK · Cumulative movement comparison" in page
    assert page.count('class="ai52-chart-symbol"') == 2
    assert "Multiple stocks use cumulative percentage" in page
    assert "Full trading day" in page
    assert "cleared at 15:50 IST" in page
    assert "browser chart data at 720 points per symbol" in page
    assert "actual quote time in IST at 30-minute intervals" in page
    assert "signed Y-axis shows percentage movement" in page
    assert "0.00% START line is the common baseline" in page
    assert "Zoom in" in page and "Zoom out" in page
    assert "-0.020%" in page


def test_monitor_history_handles_irregular_time_dedup_and_one_hour_bound():
    base = _ts(30)
    quotes = [
        {"timestamp_ist": base.isoformat(), "price": 100},
        {"timestamp_ist": (base + timedelta(seconds=17)).isoformat(), "price": 101},
        {"timestamp_ist": (base + timedelta(seconds=17)).isoformat(), "price": 102},
        {"timestamp_ist": (base + timedelta(seconds=77)).isoformat(), "price": 103},
        {"timestamp_ist": (base - timedelta(minutes=61)).isoformat(), "price": 90},
        {"timestamp_ist": (base + timedelta(seconds=80)).isoformat(), "price": 0},
    ]
    history = calculate_monitor_history(quotes)
    assert [point["price"] for point in history] == [100.0, 102.0, 103.0]
    assert history[1]["interval_return_pct"] == 2.0
    assert history[2]["one_minute_return_pct"] == 0.9804
    assert history[-1]["off_recent_peak_pct"] == 0.0


def test_repository_keeps_trading_day_and_rejects_out_of_order_quotes(tmp_path):
    repo = SellOnRiseMonitorRepository(tmp_path / "monitor.sqlite3")
    session = repo.create_or_update_session(_valid_config(), start_now=True)
    base = _ts(30)
    quotes = [QuoteObservation("TEST", base + timedelta(seconds=10 * index), 100 + index / 100) for index in range(400)]
    assert repo.save_observations(session["session_id"], quotes) == 400
    stored = repo.observations(session["session_id"], "TEST")
    assert len(stored) == 400
    assert datetime.fromisoformat(stored[-1]["timestamp_ist"]) - datetime.fromisoformat(stored[0]["timestamp_ist"]) > timedelta(hours=1)
    assert repo.save_observations(session["session_id"], [QuoteObservation("TEST", base, 999)]) == 0
    assert repo.save_observations(session["session_id"], [QuoteObservation("TEST", base + timedelta(seconds=4010), 0)]) == 0


def test_browser_history_is_bounded_and_keeps_endpoints_and_extremes():
    history = [
        {"timestamp_ist": (_ts(30) + timedelta(seconds=index)).isoformat(), "price": 100 + (20 if index == 500 else index / 1000)}
        for index in range(1500)
    ]
    sampled = downsample_monitor_history(history)
    assert len(sampled) <= 720
    assert sampled[0] == history[0]
    assert sampled[-1] == history[-1]
    assert any(point["price"] == 120 for point in sampled)


def test_market_data_is_cleared_at_1550_without_removing_config(tmp_path):
    repo = SellOnRiseMonitorRepository(tmp_path / "monitor.sqlite3")
    cfg = _valid_config()
    repo.save_config(cfg)
    session = repo.create_or_update_session(cfg, start_now=True)
    session_day = date.fromisoformat(session["trading_date"])
    close = datetime.combine(session_day, datetime.strptime("15:50", "%H:%M").time(), tzinfo=IST)
    repo.save_observations(session["session_id"], [QuoteObservation("TEST", close - timedelta(seconds=10), 100)])
    deleted = repo.clear_market_data_after_close(close)
    assert deleted == 1
    assert repo.observations(session["session_id"], "TEST") == []
    assert repo.load_config().selected_symbols == ["TEST"]
    assert repo.latest_session()["status"] == "COMPLETED"


def test_full_market_data_reset_preserves_config_and_audit(tmp_path):
    repo = SellOnRiseMonitorRepository(tmp_path / "monitor.sqlite3")
    cfg = _valid_config()
    repo.save_config(cfg)
    session = repo.create_or_update_session(cfg, start_now=True)
    repo.save_observations(session["session_id"], [QuoteObservation("TEST", _ts(30), 100.0)])
    repo.save_pattern_state(session["session_id"], "TEST", {"pattern_state": "OBSERVING"})
    assert repo.create_signal_once(
        session["session_id"],
        {"symbol": "TEST", "signal_key": "test-full-reset", "decision": "SELL_SIGNAL"},
    )
    audit_count = len(repo.audit_rows())

    deleted = repo.clear_all_market_data(status="STOPPED_FULL_RESET")

    assert deleted["sell_on_rise_quote_observation"] == 1
    assert deleted["sell_on_rise_pattern_state"] == 1
    assert deleted["sell_on_rise_signal"] == 1
    assert repo.observations(session["session_id"], "TEST") == []
    assert repo.latest_pattern_states(session["session_id"]) == {}
    assert repo.load_config().selected_symbols == ["TEST"]
    assert len(repo.audit_rows()) == audit_count
    assert repo.latest_session()["status"] == "STOPPED_FULL_RESET"


def test_storage_health_warns_then_hard_clears_monitor_data(tmp_path, monkeypatch):
    repo = SellOnRiseMonitorRepository(tmp_path / "monitor.sqlite3")
    session = repo.create_or_update_session(_valid_config(), start_now=True)
    monkeypatch.setattr(monitor_module, "MONITOR_STORAGE_WARN_POINTS", 2)
    monkeypatch.setattr(monitor_module, "MONITOR_STORAGE_HARD_POINTS", 4)

    repo.save_observations(
        session["session_id"],
        [QuoteObservation("TEST", _ts(30) + timedelta(seconds=10 * index), 100 + index) for index in range(2)],
    )
    warning = repo.enforce_storage_health()
    assert warning["warning"] is True
    assert warning["cleared"] is False
    assert warning["total_points"] == 2

    repo.save_observations(
        session["session_id"],
        [QuoteObservation("TEST", _ts(30) + timedelta(seconds=10 * index), 100 + index) for index in range(2, 4)],
    )
    health = repo.enforce_storage_health()
    assert health["total_points"] == 0
    assert repo.observations(session["session_id"], "TEST") == []
    assert repo.latest_session()["status"] == "STOPPED_STORAGE_GUARD"


def test_twenty_rises_followed_by_four_declines_is_ready_to_sell():
    prices = [100 + index for index in range(21)] + [119.5, 119.0, 118.5, 118.0]
    history = [{"price": price} for price in prices]
    signal = detect_rise_then_decline(history)
    assert signal["ready_to_sell"] is True
    assert signal["rise_count"] == 20
    assert signal["decline_count"] == 4
    assert signal["message"].startswith("READY TO SELL")


def test_reversal_signal_requires_all_four_down_observations():
    prices = [100 + index for index in range(21)] + [119.5, 119.0, 118.5]
    signal = detect_rise_then_decline([{"price": price} for price in prices])
    assert signal["ready_to_sell"] is False


def test_clear_audit_rows_only_removes_monitor_logs(tmp_path):
    repo = SellOnRiseMonitorRepository(tmp_path / "monitor.sqlite3")
    cfg = _valid_config()
    session = repo.create_or_update_session(cfg, start_now=True)
    repo.save_observations(session["session_id"], [QuoteObservation("TEST", _ts(30), 100.0)])
    repo.audit(session["session_id"], "TEST", "SCAN", "First scan", {})

    deleted = repo.clear_audit_rows()

    assert deleted >= 1
    assert repo.audit_rows() == []
    assert repo.observations(session["session_id"], "TEST")
    assert repo.latest_session()["session_id"] == session["session_id"]


def test_imported_candidates_sync_stops_monitor_and_refreshes_symbols(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "app.sqlite3")
    repo = SellOnRiseMonitorRepository(app.APP_DB_PATH)
    old_config = SellOnRiseMonitorConfig(selected_symbols=["OLD"], execution_mode="AUTO_EXECUTE", auto_execute_armed=True)
    old_session = repo.create_or_update_session(old_config, start_now=True, status="MONITORING")
    repo.save_observations(old_session["session_id"], [QuoteObservation("OLD", _ts(30), 100.0)])
    state = app.PageState(
        active_tab="52w-ai-call-spread",
        ai52_candidates=[{"symbol": "DIVISLAB"}, {"symbol": "COFORGE"}, {"symbol": "DIVISLAB"}],
        ai52_monitor_config=old_config.to_dict(),
    )

    sync = app.sync_ai52_monitor_with_imported_candidates(state, "CSV_UPLOAD:test.csv")
    app.load_ai52_state(state)

    assert sync["symbols"] == ["DIVISLAB", "COFORGE"]
    assert sync["cleared_points"] == 1
    assert state.ai52_monitor_config["selected_symbols"] == ["COFORGE", "DIVISLAB"]
    assert state.ai52_monitor_config["execution_mode"] == "ALERT_ONLY"
    assert state.ai52_monitor_config["auto_execute_armed"] is False
    assert state.ai52_monitor_session["status"] == "STOPPED_UNIVERSE_REFRESH"
    assert [row["symbol"] for row in state.ai52_monitor_rows] == ["COFORGE", "DIVISLAB"]
    assert all(row["spot"] == 0 for row in state.ai52_monitor_rows)


def test_52w_ai_page_renders_sell_on_rise_monitor_section():
    state = app.PageState(
        active_tab="52w-ai-call-spread",
        ai52_candidates=[
            {
                "symbol": "DIVISLAB",
                "company": "Divi's Laboratories",
                "evaluation": {"decision": "WATCH FOR REJECTION", "live_cmp": 9000},
            }
        ],
        ai52_monitor_config=SellOnRiseMonitorConfig(selected_symbols=["DIVISLAB"]).to_dict(),
    )

    html = app.render_ai52_call_spread_panel(state)

    assert "Sell-on-Rise Pattern Monitor" in html
    assert "Price movement" in html
    assert "OBSERVING" in html
    assert 'name="ai52_monitor_symbols" value="DIVISLAB"' in html
    assert "/52w-ai-call-spread/monitor-scan" in html
    assert "/52w-ai-call-spread/monitor-stop-clear-logs" in html
    assert "Stop &amp; Clear Logs" in html
    assert "/52w-ai-call-spread/monitor-clear-market-data" in html
    assert "Clear All Price Data" in html
    assert "Monitoring requires this page/session to remain active" in html
