import ast
import math
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trade_hedged_order_builder import build_protective_pe_spreads
from trade_protected_execution import (
    ProtectedExecutionRepository, start_execution, reconcile_execution, confirm_short,
)
from trade_execution_ui import render_execution_monitor


@pytest.fixture
def preview():
    contracts = [
        dict(tradingsymbol="TEST100PE", instrument_type="PE", strike=100, expiry="2026-11-24", lot_size=10),
        dict(tradingsymbol="TEST90PE", instrument_type="PE", strike=90, expiry="2026-11-24", lot_size=10),
    ]
    quotes = {f"NFO:{c['tradingsymbol']}": dict(
        depth={"buy": [{"price": bid}], "sell": [{"price": bid + 1}]}, volume=100, oi=100)
        for c, bid in zip(contracts, [6, 2])}
    row = build_protective_pe_spreads(
        contracts[0], contracts, quotes, 10, max_loss_cap=100,
        margin_provider=lambda _: {"initial": {"total": 100}, "final": {"total": 80}},
    )[0]
    return {**row, "symbol": "TEST", "lots": 1, "hedged_order_acknowledged": True}


class Broker:
    """In-memory exchange only. No client, credentials or network."""
    paper_trading = False
    dry_run = False

    def __init__(self):
        self.orders = []
        self.fills = {}
        self.timeout = False

    def place_order(self, payload):
        oid = str(len(self.orders) + 1)
        self.orders.append({**payload, "order_id": oid, "status": "OPEN", "filled_quantity": 0})
        if self.timeout:
            raise TimeoutError("private external error")
        return {"order_id": oid}

    def get_orders(self):
        return self.orders

    def get_order_trades(self, oid):
        return self.fills.get(oid, [])

    def fill(self, qty=10):
        order = self.orders[-1]
        order.update(status="COMPLETE" if qty == 10 else "OPEN", filled_quantity=qty)
        self.fills[order["order_id"]] = [
            {**order, "trade_id": "T" + order["order_id"], "quantity": qty, "average_price": order["price"]}
        ]

    def get_positions(self):
        return {"net": [dict(tradingsymbol="TEST90PE", exchange="NFO", product="NRML", quantity=10)]}


@pytest.fixture
def setup(tmp_path, preview):
    repo, broker = ProtectedExecutionRepository(tmp_path / "test.db"), Broker()
    row = start_execution(repo, "A", "nonce", preview, "LIVE", broker, lambda _: None)
    return repo, broker, row


def approve(record):
    return dict(quantity=10, price=6)


def test_start_only_buys_and_survives_restart(setup):
    repo, broker, row = setup
    assert [o["transaction_type"] for o in broker.orders] == ["BUY"]
    restored = ProtectedExecutionRepository(repo.path).get("A", row["id"])
    assert restored["state"] == "HEDGE_PENDING"
    again = start_execution(repo, "A", "nonce", row["preview"], "LIVE", broker, lambda _: None)
    assert again["id"] == row["id"]
    assert len(broker.orders) == 1
    with pytest.raises(PermissionError):
        repo.get("B", row["id"])


def test_manual_reconcile_and_confirm_lifecycle(setup):
    repo, broker, row = setup
    broker.fill()
    row = reconcile_execution(repo, "A", row["id"], broker)
    assert row["state"] == "HEDGE_FILLED"
    assert len(broker.orders) == 1
    with pytest.raises(PermissionError):
        confirm_short(repo, "A", row["id"], broker, approve)
    row = confirm_short(repo, "A", row["id"], broker, approve, True)
    assert row["state"] == "SELL_PENDING"
    with pytest.raises(PermissionError):
        confirm_short(repo, "A", row["id"], broker, approve, True)
    assert len(broker.orders) == 2
    broker.fill()
    assert reconcile_execution(repo, "A", row["id"], broker)["state"] == "SPREAD_ACTIVE"


@pytest.mark.parametrize("status,qty", [("OPEN", 0), ("OPEN", 5), ("REJECTED", 0), ("CANCELLED", 0)])
def test_pending_partial_rejected_cancelled_never_sell(setup, status, qty):
    repo, broker, row = setup
    if qty:
        broker.fill(qty)
    broker.orders[0]["status"] = status
    with pytest.raises(PermissionError):
        confirm_short(repo, "A", row["id"], broker, approve, True)
    assert len(broker.orders) == 1


def test_timeout_reconciles_tag_without_retry(tmp_path, preview):
    repo, broker = ProtectedExecutionRepository(tmp_path / "test.db"), Broker()
    broker.timeout = True
    row = start_execution(repo, "A", "nonce", preview, "LIVE", broker, lambda _: None)
    assert row["state"] == "HEDGE_SUBMISSION_UNKNOWN"
    row = reconcile_execution(repo, "A", row["id"], broker)
    assert row["hedge_order_id"] == "1"
    broker.fill()
    row = confirm_short(repo, "A", row["id"], broker, approve, True)
    assert row["state"] == "SHORT_SUBMISSION_UNKNOWN"
    row = reconcile_execution(repo, "A", row["id"], broker)
    assert row["sell_order_id"] == "2"
    assert len(broker.orders) == 2


def test_duplicate_fills_and_risk_blocks(setup):
    repo, broker, row = setup
    broker.fill()
    broker.fills["1"] *= 2
    assert reconcile_execution(repo, "A", row["id"], broker)["hedge_filled"] == 10
    broker.fills["1"] = broker.fills["1"][:1]
    def deny(_):
        raise PermissionError("Monthly loss limit")
    with pytest.raises(PermissionError):
        confirm_short(repo, "A", row["id"], broker, deny, True)
    assert len(broker.orders) == 1


def test_account_coverage_reservation_and_compare_swap(setup):
    repo, broker, row = setup
    with pytest.raises(PermissionError):
        start_execution(repo, "A", "another", row["preview"], "LIVE", broker, lambda _: None)
    repo.save(row)
    with pytest.raises(PermissionError):
        repo.save(row)
    assert len(broker.orders) == 1


def test_removed_hedge_blocks_sell(setup):
    repo, broker, row = setup
    broker.fill()
    broker.get_positions = lambda: {"net": []}
    with pytest.raises(PermissionError):
        confirm_short(repo, "A", row["id"], broker, approve, True)
    assert len(broker.orders) == 1


def test_concurrent_confirmation_places_at_most_one_short(setup):
    repo, broker, row = setup
    broker.fill()
    def attempt(_):
        try:
            confirm_short(repo, "A", row["id"], broker, approve, True)
        except PermissionError:
            pass
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(attempt, range(2)))
    assert len(broker.orders) == 2


def test_pending_hedge_exit_blocks_short(setup):
    repo, broker, row = setup
    broker.fill()
    broker.orders.append({**broker.orders[0], "order_id": "EXIT", "transaction_type": "SELL", "status": "OPEN"})
    with pytest.raises(PermissionError):
        confirm_short(repo, "A", row["id"], broker, approve, True)
    assert len(broker.orders) == 2


def test_paper_adapter_no_network_and_buy_only(tmp_path, preview, monkeypatch):
    from kite_broker_adapter import KiteBrokerAdapter
    broker = KiteBrokerAdapter(paper_trading=True)
    monkeypatch.setattr(broker, "_client", lambda: pytest.fail("No broker client allowed"))
    repo = ProtectedExecutionRepository(tmp_path / "paper.db")
    row = start_execution(repo, "A", "nonce", preview, "PAPER", broker, lambda _: None)
    assert len(broker.call_log) == 1
    row = reconcile_execution(repo, "A", row["id"], broker)
    assert row["state"] == "HEDGE_FILLED" and len(broker.call_log) == 1
    row = confirm_short(repo, "A", row["id"], broker, approve, True)
    assert len(broker.call_log) == 2
    assert reconcile_execution(repo, "A", row["id"], broker)["state"] == "SPREAD_ACTIVE"


def test_monitor_escapes_data_and_shows_manual_confirmation(setup):
    repo, broker, row = setup
    row["note"] = "<script>bad</script>"
    rendered = render_execution_monitor([row], "A")
    assert "<script>" not in rendered
    assert "/trade/execution/reconcile" in rendered
    assert 'disabled>Confirm SELL' in rendered


@pytest.mark.parametrize("fault", ["margin", "loss", "checks", "identity", "stale", "ce", None])
def test_app_renewed_approval_isolated_from_app_import(preview, fault):
    # Compile only this pure orchestration function: importing app initializes
    # runtime databases. All market/review dependencies below are test doubles.
    tree = ast.parse((Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8-sig"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "approve_protected_short")
    if fault == "ce":
        preview.update(strategy_type="BEAR_CALL_SPREAD", short_symbol="TEST100CE",
                       hedge_symbol="TEST110CE", hedge_strike=110, option_type="CE")
    fresh = {**preview, "available_funds": 1000, "ltp": 6}
    record = dict(preview=preview, mode="PAPER", hedge_average_price=3)
    if fault == "margin":
        fresh["available_funds"] = 0
    if fault == "loss":
        record["hedge_average_price"] = 5
    if fault == "identity":
        fresh["hedge_symbol"] = "OTHER"
    if fault == "stale":
        record["mode"] = "LIVE"
        fresh["short_quote_timestamp"] = "2020-01-01T00:00:00+00:00"
    namespace = dict(PageState=object, Any=object, math=math, os=os,
                     datetime=datetime, INDIA_TIME_ZONE=timezone.utc, app_now=lambda: datetime.now(timezone.utc),
                     load_trade_terminal_state=lambda _: None,
                     build_trade_review=lambda _: (fresh, []),
                     trade_has_blocks=lambda _: fault == "checks", _dhan_metric_float=lambda v: float(v or 0))
    exec(compile(ast.Module(body=[function], type_ignores=[]), "approval", "exec"), namespace)
    if fault not in {None, "ce"}:
        with pytest.raises(PermissionError):
            namespace["approve_protected_short"](SimpleNamespace(), record)
    else:
        assert namespace["approve_protected_short"](SimpleNamespace(), record)["max_loss"] == 70
