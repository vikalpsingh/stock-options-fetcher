from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from monthly_risk_control import (
    PROTECTIVE_HEDGE,
    RISK_INCREASING,
    RISK_REDUCING,
    MonthlyRiskConfig,
    MonthlyRiskEngine,
    MonthlyRiskRepository,
    classify_order_risk_change,
)
from kite_broker_adapter import KiteBrokerAdapter, KiteBrokerError


def _seed_closed_pnl(db_path, account: str, key: str, pnl: float) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS closed_trade_pnl (
                id INTEGER PRIMARY KEY, account_id TEXT, month_key TEXT,
                net_realised_pnl REAL
            )"""
        )
        conn.execute(
            "INSERT INTO closed_trade_pnl(account_id, month_key, net_realised_pnl) VALUES (?, ?, ?)",
            (account, key, pnl),
        )


def _repo(tmp_path, account="A", limit=200_000):
    db = tmp_path / "risk.sqlite3"
    repo = MonthlyRiskRepository(db)
    repo.save_config(MonthlyRiskConfig(account_id=account, monthly_max_loss_inr=limit))
    return db, repo


@pytest.mark.parametrize(
    "pnl,state,locked",
    [
        (100_000, "GREEN", False),
        (-100_000, "AMBER", False),
        (-199_999, "ORANGE", False),
        (-200_000, "RED", True),
        (-200_001, "RED", True),
    ],
)
def test_monthly_loss_state_machine(tmp_path, pnl, state, locked):
    db, repo = _repo(tmp_path)
    _seed_closed_pnl(db, "A", "2026-10", pnl)

    snapshot = repo.latest_snapshot("A", date(2026, 10, 17))

    assert snapshot["risk_state"] == state
    assert bool(snapshot["hard_locked"]) is locked
    assert snapshot["remaining_loss_budget"] == max(0, 200_000 - max(0, -pnl))


def test_new_naked_sell_is_blocked_while_locked(tmp_path):
    db, repo = _repo(tmp_path)
    _seed_closed_pnl(db, "A", "2026-10", -200_000)
    engine = MonthlyRiskEngine(db)

    decision = engine.evaluate_order(
        {"tradingsymbol": "NIFTY26OCT25000CE", "transaction_type": "SELL", "quantity": 75},
        account_id="A", current_positions=[], day=date(2026, 10, 17),
    )

    assert decision.allowed is False
    assert decision.risk_change == RISK_INCREASING


def test_buy_back_short_is_allowed_while_locked(tmp_path):
    db, repo = _repo(tmp_path)
    _seed_closed_pnl(db, "A", "2026-10", -210_000)

    decision = MonthlyRiskEngine(db).evaluate_order(
        {"tradingsymbol": "NIFTY26OCT25000CE", "transaction_type": "BUY", "quantity": 25},
        account_id="A",
        current_positions=[{"tradingsymbol": "NIFTY26OCT25000CE", "quantity": -75}],
        day=date(2026, 10, 17),
    )

    assert decision.allowed is True
    assert decision.risk_change == RISK_REDUCING


def test_protective_hedge_hint_is_allowed_while_locked(tmp_path):
    db, repo = _repo(tmp_path)
    _seed_closed_pnl(db, "A", "2026-10", -210_000)

    decision = MonthlyRiskEngine(db).evaluate_order(
        {"tradingsymbol": "NIFTY26OCT24500PE", "transaction_type": "BUY", "quantity": 75,
         "risk_change": PROTECTIVE_HEDGE},
        account_id="A", current_positions=[], day=date(2026, 10, 17),
    )

    assert decision.allowed is True


def test_unknown_classification_fails_closed_while_locked(tmp_path):
    db, repo = _repo(tmp_path)
    _seed_closed_pnl(db, "A", "2026-10", -210_000)

    decision = MonthlyRiskEngine(db).evaluate_order(
        {"tradingsymbol": "NIFTY26OCT25000CE", "quantity": 0},
        account_id="A", current_positions=[], day=date(2026, 10, 17),
    )

    assert decision.allowed is False


def test_hard_lock_persists_but_new_month_starts_clean(tmp_path):
    db, repo = _repo(tmp_path)
    _seed_closed_pnl(db, "A", "2026-10", -200_000)
    assert repo.latest_snapshot("A", date(2026, 10, 17))["hard_locked"] == 1

    restarted = MonthlyRiskRepository(db)
    assert restarted.latest_snapshot("A", date(2026, 10, 18))["hard_locked"] == 1
    november = restarted.latest_snapshot("A", date(2026, 11, 1))
    assert november["hard_locked"] == 0
    assert november["booked_pnl"] == 0


def test_accounts_have_separate_limits_and_ledgers(tmp_path):
    db = tmp_path / "risk.sqlite3"
    repo = MonthlyRiskRepository(db)
    repo.save_config(MonthlyRiskConfig(account_id="A", monthly_max_loss_inr=100_000))
    repo.save_config(MonthlyRiskConfig(account_id="B", monthly_max_loss_inr=300_000))
    _seed_closed_pnl(db, "A", "2026-10", -100_000)
    _seed_closed_pnl(db, "B", "2026-10", -100_000)

    assert repo.latest_snapshot("A", date(2026, 10, 17))["hard_locked"] == 1
    assert repo.latest_snapshot("B", date(2026, 10, 17))["hard_locked"] == 0


def test_profit_giveback_preserves_peak(tmp_path):
    db, repo = _repo(tmp_path)
    _seed_closed_pnl(db, "A", "2026-10", 100_000)
    first = repo.latest_snapshot("A", date(2026, 10, 10))
    assert first["peak_month_pnl"] == 100_000

    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE closed_trade_pnl SET net_realised_pnl=40000 WHERE account_id='A'")
    second = repo.latest_snapshot("A", date(2026, 10, 17))
    assert second["peak_month_pnl"] == 100_000
    assert second["giveback_amount"] == 60_000
    assert second["giveback_percent"] == 60


def test_classifier_detects_increase_and_reduction():
    positions = [{"tradingsymbol": "TCS26OCT3000CE", "quantity": -100}]
    assert classify_order_risk_change(
        {"tradingsymbol": "TCS26OCT3000CE", "transaction_type": "SELL", "quantity": 25}, positions
    ) == RISK_INCREASING
    assert classify_order_risk_change(
        {"tradingsymbol": "TCS26OCT3000CE", "transaction_type": "BUY", "quantity": 25}, positions
    ) == RISK_REDUCING


def test_quarterly_and_yearly_history_are_aggregated_from_persisted_months(tmp_path):
    db, repo = _repo(tmp_path)
    for key, pnl in (("2026-07", 10_000), ("2026-08", -5_000), ("2026-10", 20_000)):
        _seed_closed_pnl(db, "A", key, pnl)
        year, month = (int(part) for part in key.split("-"))
        repo.latest_snapshot("A", date(year, month, 15))

    quarters = {row["period"]: row for row in repo.period_history("A", "quarter")}
    years = {row["period"]: row for row in repo.period_history("A", "year")}

    assert quarters["2026-Q3"]["booked_pnl"] == 5_000
    assert quarters["2026-Q3"]["months"] == 2
    assert quarters["2026-Q4"]["booked_pnl"] == 20_000
    assert years["2026"]["booked_pnl"] == 25_000


class _FakeLiveKite:
    def __init__(self, positions):
        self._positions = positions
        self.placed = []

    def positions(self):
        return {"net": list(self._positions)}

    def place_order(self, **payload):
        self.placed.append(payload)
        return "ORDER-1"


def test_live_adapter_blocks_new_risk_before_broker_call(tmp_path, monkeypatch):
    db, repo = _repo(tmp_path, account="A")
    _seed_closed_pnl(db, "A", "2026-10", -200_000)
    repo.latest_snapshot("A", date(2026, 10, 17))
    monkeypatch.setenv("TRADING_APP_DB_PATH", str(db))
    kite = _FakeLiveKite([])
    adapter = KiteBrokerAdapter(kite=kite, paper_trading=False, account_id="A")

    with pytest.raises(KiteBrokerError, match="MONTHLY_RISK_BLOCKED"):
        adapter.place_order({
            "tradingsymbol": "NIFTY26OCT25000CE",
            "transaction_type": "SELL",
            "quantity": 75,
            "_risk_context": {"strategy": "TEST_SPREAD"},
        })

    assert kite.placed == []


def test_live_adapter_allows_buy_to_close_when_locked(tmp_path, monkeypatch):
    db, repo = _repo(tmp_path, account="A")
    _seed_closed_pnl(db, "A", "2026-10", -200_000)
    repo.latest_snapshot("A", date(2026, 10, 17))
    monkeypatch.setenv("TRADING_APP_DB_PATH", str(db))
    symbol = "NIFTY26OCT25000CE"
    kite = _FakeLiveKite([{"tradingsymbol": symbol, "quantity": -75}])
    adapter = KiteBrokerAdapter(kite=kite, paper_trading=False)

    result = adapter.place_order({
        "tradingsymbol": symbol,
        "transaction_type": "BUY",
        "quantity": 75,
        "_risk_context": {"account_id": "A", "strategy": "EXIT"},
    })

    assert result["order_id"] == "ORDER-1"
    assert len(kite.placed) == 1
    assert "_risk_context" not in kite.placed[0]
