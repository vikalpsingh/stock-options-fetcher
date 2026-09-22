from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import app
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
    assert state.ai52_monitor_config["selected_symbols"] == ["COFORGE", "DIVISLAB"]
    assert state.ai52_monitor_config["execution_mode"] == "ALERT_ONLY"
    assert state.ai52_monitor_config["auto_execute_armed"] is False
    assert state.ai52_monitor_session["status"] == "STOPPED_BY_USER"
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
    assert "Monitoring requires this page/session to remain active" in html
