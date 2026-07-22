from __future__ import annotations

from datetime import date, timedelta

from income.covered_call import (
    CoveredCallInput,
    build_covered_call_recommendation,
    calculate_covered_call_capacity,
    classify_income_symbol_category,
    select_atr_guarded_call_strike,
    select_monthly_expiry,
)


def test_capacity_separates_raw_capacity_from_recommended_lots() -> None:
    capacity = calculate_covered_call_capacity(
        symbol="PGEL",
        holding_qty=7350,
        lot_size=950,
        spot_price=483,
        category=classify_income_symbol_category("PGEL"),
        user_max_lots=3,
    )

    assert capacity.capacity_lots == 7
    assert capacity.recommended_lots == 1
    assert capacity.recommended_quantity == 950
    assert capacity.max_total_covered_pct == 15.0


def test_existing_short_ce_reduces_recommended_lots() -> None:
    capacity = calculate_covered_call_capacity(
        symbol="PFC",
        holding_qty=3515,
        lot_size=1300,
        spot_price=431,
        existing_short_ce_qty=2600,
        category=classify_income_symbol_category("PFC"),
        user_max_lots=1,
    )

    assert capacity.capacity_lots == 2
    assert capacity.existing_short_ce_lots == 2
    assert capacity.recommended_lots == 0
    assert "EXISTING_CE_ALREADY_USES_CAPACITY" in capacity.reason_codes


def test_expiry_selector_prefers_28_to_42_day_window() -> None:
    today = date(2026, 7, 22)
    instruments = [
        {"expiry": today + timedelta(days=7)},
        {"expiry": today + timedelta(days=31)},
        {"expiry": today + timedelta(days=55)},
    ]

    choice = select_monthly_expiry(instruments, as_of=today)

    assert choice.expiry == today + timedelta(days=31)
    assert choice.decision == "PREFERRED_MONTHLY"


def test_atr_guarded_strike_respects_otm_cap_for_growth_stock() -> None:
    strike, meta = select_atr_guarded_call_strike(
        spot_price=483,
        available_strikes=[500, 520, 550, 600],
        category=classify_income_symbol_category("PGEL"),
        today_change_pct=1.5,
        week_change_pct=2.5,
    )

    assert strike == 520
    assert meta["method"] == "ATR_GUARDRAIL"


def test_recommendation_blocks_low_premium() -> None:
    today = date(2026, 7, 22)
    recommendation = build_covered_call_recommendation(
        CoveredCallInput(
            symbol="PFC",
            holding_qty=3515,
            lot_size=1300,
            spot_price=431,
            strike=490,
            expiry=today + timedelta(days=35),
            premium=1.0,
            category=classify_income_symbol_category("PFC"),
        ),
        as_of=today,
    )

    assert recommendation.decision == "NO_TRADE_LOW_PREMIUM"
    assert "LOW_PREMIUM_YIELD" in recommendation.reason_codes


def test_recommendation_approves_explainable_covered_call() -> None:
    today = date(2026, 7, 22)
    recommendation = build_covered_call_recommendation(
        CoveredCallInput(
            symbol="PFC",
            holding_qty=3515,
            lot_size=1300,
            spot_price=431,
            strike=490,
            expiry=today + timedelta(days=35),
            premium=5.0,
            category=classify_income_symbol_category("PFC"),
            today_change_pct=-0.5,
            week_change_pct=-1.0,
        ),
        as_of=today,
    )

    assert recommendation.decision == "SELL_NOW"
    assert recommendation.recommended_lots == 1
    assert recommendation.max_profit == 6500
    assert recommendation.premium_yield_pct > 1.0
