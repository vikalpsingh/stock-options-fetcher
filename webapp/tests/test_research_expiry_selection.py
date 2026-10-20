from datetime import date
from types import SimpleNamespace

import pytest

import app


def test_auto_research_expiry_rolls_to_next_month_below_nine_calendar_dte():
    policy = app.research_monthly_expiry_policy(date(2026, 10, 19), "AUTO")

    assert policy["front_calendar_dte"] == 8
    assert policy["rolled_to_next_month"] is True
    assert policy["target_expiry"].month == 11


def test_research_expiry_can_be_selected_explicitly():
    current = app.research_monthly_expiry_policy(date(2026, 10, 19), "CURRENT")
    following = app.research_monthly_expiry_policy(date(2026, 10, 1), "NEXT")

    assert current["target_expiry"].month == 10
    assert current["rolled_to_next_month"] is False
    assert following["target_expiry"].month == 11
    assert following["rolled_to_next_month"] is True


def test_research_expiry_rejects_unknown_mode():
    with pytest.raises(ValueError, match="AUTO, CURRENT or NEXT"):
        app.research_monthly_expiry_policy(date(2026, 10, 19), "INVALID")


def test_retarget_research_sell_rows_uses_selected_month_and_preserves_lots(monkeypatch):
    fake_kite = object()
    monkeypatch.setattr(app, "kite_orders", SimpleNamespace(kite_client=lambda: fake_kite))
    monkeypatch.setattr(
        app,
        "cached_kite_instruments",
        lambda kite, exchange: [
            {
                "tradingsymbol": "TCS26OCT3000CE",
                "name": "TCS",
                "instrument_type": "CE",
                "strike": 3000,
                "expiry": date(2026, 10, 27),
                "lot_size": 175,
            },
            {
                "tradingsymbol": "TCS26NOV3000CE",
                "name": "TCS",
                "instrument_type": "CE",
                "strike": 3000,
                "expiry": date(2026, 11, 24),
                "lot_size": 175,
            },
        ],
    )
    monkeypatch.setattr(
        app,
        "cached_kite_quote",
        lambda kite, symbols, ttl_seconds=0: {
            "NFO:TCS26NOV3000CE": {
                "last_price": 10.0,
                "depth": {"buy": [{"price": 10.0}]},
            }
        },
    )
    monkeypatch.setattr(app, "option_sell_markup_percent_setting", lambda: 10.0)
    rows = [{"tradingsymbol": "TCS26OCT3000CE", "quantity": 350, "price": "8.00"}]
    policy = app.research_monthly_expiry_policy(date(2026, 10, 19), "AUTO")

    result = app.retarget_research_sell_rows(rows, policy)

    assert result[0]["tradingsymbol"] == "TCS26NOV3000CE"
    assert result[0]["quantity"] == 350
    assert result[0]["price"] == "11.00"


def test_research_panel_exposes_expiry_selector():
    state = app.PageState(active_tab="research", research_expiry_mode="NEXT")

    page = app.render_research_panel(state)

    assert 'name="research_expiry_mode"' in page
    assert "Auto — next month below 9 DTE" in page
    assert 'value="NEXT" selected' in page


def test_research_gpt_prompt_makes_auto_rollover_mandatory():
    prompt = app.research_gpt_prompt_with_current_positions(
        "exchange,tradingsymbol\nNFO,TCS26NOV3000CE\n",
        [],
        {},
        date(2026, 10, 19),
        "AUTO",
    )

    assert "fewer than 9 calendar DTE" in prompt
    assert "Mandatory expiry for every new NFO option order: 24 Nov 2026 (November 2026)" in prompt
