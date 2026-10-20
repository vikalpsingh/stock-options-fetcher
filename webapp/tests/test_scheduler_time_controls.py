from datetime import datetime

import app


IST = app.INDIA_TIME_ZONE


def test_save_scheduler_times_validates_and_becomes_effective_tomorrow(monkeypatch):
    stored = {}

    def job(name):
        return {
            "name": name,
            "purpose": "test",
            "schedule": "test",
            "load": lambda: {},
            "save": lambda **updates: stored.setdefault(name, dict(updates)),
        }

    monkeypatch.setattr(app, "scheduled_job_definitions", lambda: {
        "position_close_open": job("close"),
        "income_growth_gpt": job("gpt"),
        "intraday_position_close": job("guard"),
        "eod_pnl_snapshot": job("pnl"),
    })
    values = {
        "position_close_open_schedule_time": "09:25",
        "income_growth_gpt_schedule_time": "09:40",
        "intraday_position_close_start_time": "09:35",
        "intraday_position_close_end_time": "15:10",
        "intraday_position_close_interval_minutes": "10",
        "eod_pnl_snapshot_schedule_time": "16:05",
    }
    saved = app.save_scheduled_job_times(values, datetime(2026, 10, 19, 12, 0, tzinfo=IST))

    assert saved["position_close_open"]["schedule_time"] == "09:25"
    assert saved["intraday_position_close"]["interval_minutes"] == 10
    assert all(item["schedule_effective_from"] == "2026-10-20" for item in saved.values())


def test_next_run_uses_new_time_from_tomorrow():
    state = {"enabled": True, "schedule_time": "10:15", "schedule_effective_from": "2026-10-20"}
    next_run = app.next_scheduled_job_run(
        "position_close_open", state, datetime(2026, 10, 19, 8, 0, tzinfo=IST)
    )
    assert next_run == datetime(2026, 10, 20, 10, 15, tzinfo=IST)
    assert app.scheduled_job_not_effective_yet(state, datetime(2026, 10, 19, 15, 0, tzinfo=IST)) is True
    assert app.scheduled_job_not_effective_yet(state, datetime(2026, 10, 20, 8, 0, tzinfo=IST)) is False


def test_invalid_intraday_window_is_rejected(monkeypatch):
    monkeypatch.setattr(app, "scheduled_job_definitions", lambda: {
        "intraday_position_close": {
            "name": "guard", "purpose": "test", "schedule": "test", "load": lambda: {}, "save": lambda **updates: updates,
        }
    })
    try:
        app.save_scheduled_job_times({
            "intraday_position_close_start_time": "15:15",
            "intraday_position_close_end_time": "09:30",
            "intraday_position_close_interval_minutes": "15",
        }, datetime(2026, 10, 19, 12, 0, tzinfo=IST))
    except ValueError as exc:
        assert "later than" in str(exc)
    else:
        raise AssertionError("Invalid intraday window should be rejected")


def test_scheduler_panel_renders_editable_time_controls(monkeypatch):
    monkeypatch.setattr(app, "scheduler_master_state", lambda: {"enabled": True, "message": "Running"})
    monkeypatch.setattr(app, "scheduled_job_definitions", lambda: {
        "position_close_open": {
            "name": "Default Close Orders", "purpose": "test", "schedule": "Weekdays",
            "load": lambda: {"enabled": True, "schedule_time": "09:25", "status": "WAITING"},
            "save": lambda **updates: updates,
        }
    })
    page = app.render_scheduler_control_panel()
    assert 'name="position_close_open_schedule_time"' in page
    assert 'value="09:25"' in page
    assert 'formaction="/scheduler/save-times"' in page
    assert "effective tomorrow" in page
