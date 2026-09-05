from __future__ import annotations

from datetime import date

from pnl_service import (
    PnlFilters,
    PnlRepository,
    aggregate_by_dimension,
    aggregate_summary,
    calculate_daily_roi,
    classify_asset_class,
    classify_strategy_theme,
    max_drawdown,
    period_bounds,
    profit_factor,
    snapshot_from_kite_positions,
)


def test_daily_roi_returns_none_when_capital_is_zero() -> None:
    assert calculate_daily_roi(5000, 0) is None
    assert calculate_daily_roi(5000, 100000) == 5.0


def test_period_bounds_supports_dynamic_year_and_custom_dates() -> None:
    today = date(2026, 9, 5)
    assert period_bounds("Today", today=today) == (today, today)
    assert period_bounds("This Week", today=today) == (date(2026, 8, 31), today)
    assert period_bounds("This Year", today=today, year=2025) == (
        date(2025, 1, 1),
        date(2025, 12, 31),
    )
    assert period_bounds("Custom", today=today, from_date="2026-09-04", to_date="2026-09-01") == (
        date(2026, 9, 1),
        date(2026, 9, 4),
    )


def test_profit_factor_and_max_drawdown_are_daily_curve_safe() -> None:
    values = [1200, -300, 500, -100, -700]
    assert profit_factor(values) == 1.5455
    assert max_drawdown(values) == -800


def test_aggregate_summary_uses_capital_once_for_spread_group() -> None:
    records = [
        {
            "trade_date": "2026-09-05",
            "account_id": "monika",
            "strategy": "DHAN-IT",
            "position_group_id": "PAIR-1",
            "realized_pnl": 600,
            "unrealized_pnl": 0,
            "net_realized_pnl": 600,
            "charges": 0,
            "capital_deployed": 40000,
        },
        {
            "trade_date": "2026-09-05",
            "account_id": "monika",
            "strategy": "DHAN-IT",
            "position_group_id": "PAIR-1",
            "realized_pnl": 400,
            "unrealized_pnl": 0,
            "net_realized_pnl": 400,
            "charges": 0,
            "capital_deployed": 40000,
        },
    ]
    summary = aggregate_summary(records)
    assert summary["net_realized_pnl"] == 1000
    assert summary["capital_deployed"] == 40000
    assert summary["roi_pct"] == 2.5


def test_strategy_aggregation_keeps_roi_as_net_over_capital_not_sum_of_daily_roi() -> None:
    records = [
        {
            "trade_date": "2026-09-01",
            "account_id": "default",
            "strategy": "DHAN",
            "position_group_id": "A",
            "net_realized_pnl": 100,
            "realized_pnl": 100,
            "capital_deployed": 1000,
        },
        {
            "trade_date": "2026-09-02",
            "account_id": "default",
            "strategy": "DHAN",
            "position_group_id": "B",
            "net_realized_pnl": 100,
            "realized_pnl": 100,
            "capital_deployed": 100000,
        },
    ]
    dhan = aggregate_by_dimension(records, "strategy")[0]
    assert dhan["net_realized_pnl"] == 200
    assert dhan["capital_deployed"] == 101000
    assert dhan["roi_pct"] == 0.198


def test_pnl_repository_upsert_is_idempotent(tmp_path) -> None:
    repo = PnlRepository(tmp_path / "pnl.db")
    record = {
        "trade_date": "2026-09-05",
        "account_id": "monika",
        "broker": "ZERODHA",
        "source": "KITE_POSITIONS",
        "strategy": "DHAN",
        "theme": "F&O Stock Spread",
        "asset_class": "FNO_OPTIONS",
        "underlying": "CAMS",
        "tradingsymbol": "CAMS26SEP900CE",
        "position_group_id": "PAIR-CAMS",
        "realized_pnl": 100,
        "unrealized_pnl": 10,
        "gross_pnl": 110,
        "charges": 5,
        "net_realized_pnl": 95,
        "capital_deployed": 25000,
        "roi_pct": 0.38,
        "snapshot_at": "2026-09-05T10:00:00",
    }
    assert repo.upsert_daily_records([record]) == 1
    updated = {**record, "realized_pnl": 150, "net_realized_pnl": 145}
    assert repo.upsert_daily_records([updated]) == 1
    rows = repo.query_daily_records(PnlFilters(period="This Year", year=2026))
    assert len(rows) == 1
    assert rows[0]["realized_pnl"] == 150
    assert rows[0]["net_realized_pnl"] == 145


def test_kite_position_snapshot_classifies_strategy_and_asset_class_without_live_call() -> None:
    positions = [
        {
            "tradingsymbol": "TECHM26SEP1700CE",
            "exchange": "NFO",
            "product": "NRML",
            "quantity": -600,
            "average_price": 15,
            "last_price": 9.5,
            "realised": 0,
            "unrealised": 3300,
            "tag": "DHAN-IT_PAIR",
        },
        {
            "tradingsymbol": "NIFTY26SEP24500PE",
            "exchange": "NFO",
            "quantity": -75,
            "average_price": 80,
            "last_price": 60,
            "realised": 1200,
        },
    ]
    records = snapshot_from_kite_positions(positions, account_id="monika", trade_date=date(2026, 9, 5))
    assert records[0]["strategy"] == "DHAN-IT"
    assert records[0]["theme"] == "Information Technology"
    assert records[0]["asset_class"] == "FNO_OPTIONS"
    assert records[1]["strategy"] == "NIFTY Income"
    assert records[1]["asset_class"] == "INDEX_OPTIONS"
    assert classify_asset_class({"tradingsymbol": "RELIANCE", "exchange": "NSE", "product": "CNC"}) == "EQUITY"
    assert classify_strategy_theme({"tag": "52W_AI_CALL"})[0] == "52W AI Call Spread"
