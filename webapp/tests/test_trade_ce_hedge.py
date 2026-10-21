import pytest

from trade_hedged_order_builder import build_protective_spreads, protective_contracts
from trade_execution_ui import render_execution_monitor, render_hedge_selector
from trade_protected_execution import ProtectedExecutionRepository, start_execution, reconcile_execution, confirm_short


@pytest.fixture
def market():
    short = dict(name="TEST", tradingsymbol="TEST100CE", strike=100, instrument_type="CE",
                 expiry="2026-11-24", lot_size=10)
    contracts = [short] + [{**short, "tradingsymbol": f"TEST{strike}CE", "strike": strike}
                           for strike in (101, 102, 103, 104, 105, 106, 110)]
    quotes = {f"NFO:{row['tradingsymbol']}": {
        "depth": {"buy": [{"price": 10 if row["strike"] == 100 else 1}],
                  "sell": [{"price": 2 if row["strike"] == 110 else 11}]},
        "volume": 100, "oi": 100,
    } for row in contracts}
    return short, contracts, quotes


def build(market, **kwargs):
    return build_protective_spreads(*market, 10, max_loss_cap=kwargs.pop("cap", 100),
                                   selected_hedge_symbol=kwargs.pop("selected", "TEST110CE"), **kwargs)


def test_ce_far_cover_and_risk_math(market):
    assert not any(row["eligible"] for row in build(market, selected=""))
    row = build(market)[0]
    assert row["strategy_type"] == "BEAR_CALL_SPREAD"
    assert row["option_type"] == "CE"
    assert row["hedge_strike"] > row["short_strike"]
    assert (row["net_credit"], row["max_profit"], row["max_loss"], row["breakeven"]) == (80, 80, 20, 108)
    assert row["eligible"]
    assert row["order_payloads"][0]["tradingsymbol"] == "TEST110CE"


@pytest.mark.parametrize("change", [
    {"expiry": "2026-12-24"}, {"name": "OTHER"}, {"instrument_type": "PE"},
    {"lot_size": 20}, {"strike": 90}, {"strike": 100},
])
def test_ce_invalid_cover_blocks_without_fallback(market, change):
    market[1][-1].update(change)
    with pytest.raises(ValueError, match="higher-strike CE"):
        build(market)


def test_ce_cap_and_liquidity_remain_blocking(market):
    assert not build(market, cap=10)[0]["eligible"]
    market[2]["NFO:TEST110CE"]["oi"] = 0
    assert not build(market)[0]["eligible"]


def test_ce_selector_and_monitor_paper_lifecycle(market, tmp_path, monkeypatch):
    from kite_broker_adapter import KiteBrokerAdapter
    preview = {**build(market)[0], "hedged_order_acknowledged": True,
               "selected_hedge_symbol": "TEST110CE",
               "hedge_contract_choices": protective_contracts(market[0], market[1])}
    markup = render_hedge_selector(preview)
    assert "Protective BUY CE" in markup and "higher-strike" in markup
    assert 'value="TEST110CE" selected' in markup
    broker = KiteBrokerAdapter(paper_trading=True)
    monkeypatch.setattr(broker, "_client", lambda: pytest.fail("No LIVE client allowed"))
    repo = ProtectedExecutionRepository(tmp_path / "paper.db")
    row = start_execution(repo, "A", "ce", preview, "PAPER", broker, lambda _: None)
    assert len(broker.call_log) == 1
    assert broker.call_log[0]["payload"]["transaction_type"] == "BUY"
    row = reconcile_execution(repo, "A", row["id"], broker)
    assert row["state"] == "HEDGE_FILLED"
    row = confirm_short(repo, "A", row["id"], broker, lambda _: {"quantity": 10, "price": 10}, True)
    assert len(broker.call_log) == 2
    assert broker.call_log[1]["payload"]["tradingsymbol"] == "TEST100CE"
    row = reconcile_execution(repo, "A", row["id"], broker)
    assert row["state"] == "SPREAD_ACTIVE"
    assert "Bear Call Spread" in render_execution_monitor([row], "A")


def test_ce_partial_fill_cannot_submit_short(market, tmp_path):
    class Broker:
        paper_trading = False
        dry_run = False

        def __init__(self):
            self.orders = []

        def place_order(self, payload):
            self.orders.append({**payload, "order_id": "H1", "filled_quantity": 5, "status": "OPEN"})
            return {"order_id": "H1"}

        def get_orders(self):
            return self.orders

        def get_order_trades(self, oid):
            return [{**self.orders[0], "quantity": 5, "trade_id": "T1", "average_price": 2}]

    broker = Broker()
    repo = ProtectedExecutionRepository(tmp_path / "partial.db")
    preview = {**build(market)[0], "hedged_order_acknowledged": True}
    row = start_execution(repo, "A", "partial", preview, "LIVE", broker, lambda _: None)
    with pytest.raises(PermissionError, match="full verified"):
        confirm_short(repo, "A", row["id"], broker, lambda _: pytest.fail("Cannot approve partial coverage"), True)
    assert len(broker.orders) == 1
    assert repo.get("A", row["id"])["state"] == "PARTIAL_HEDGE"


def test_ce_wrong_strike_direction_cannot_start(market, tmp_path):
    from kite_broker_adapter import KiteBrokerAdapter
    preview = {**build(market)[0], "hedged_order_acknowledged": True, "hedge_strike": 90}
    broker = KiteBrokerAdapter(paper_trading=True)
    with pytest.raises(PermissionError, match="strike direction"):
        start_execution(ProtectedExecutionRepository(tmp_path / "bad.db"), "A", "bad",
                        preview, "PAPER", broker, lambda _: None)
    assert not broker.call_log
