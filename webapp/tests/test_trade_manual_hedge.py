import pytest

from trade_hedged_order_builder import build_protective_pe_spreads, protective_pe_contracts
from trade_execution_ui import render_hedge_selector
from trade_protected_execution import ProtectedExecutionRepository, start_execution, reconcile_execution, confirm_short


def market():
    short = dict(name="TEST", tradingsymbol="TEST100PE", strike=100, instrument_type="PE",
                 expiry="2026-11-24", lot_size=10)
    contracts = [short] + [{**short, "tradingsymbol": f"TEST{strike}PE", "strike": strike}
                           for strike in (99, 98, 97, 96, 95, 94, 90)]
    quotes = {f"NFO:{c['tradingsymbol']}": {
        "depth": {"buy": [{"price": 10 if c["strike"] == 100 else 1}],
                  "sell": [{"price": 2 if c["strike"] == 90 else 11}]},
        "volume": 100, "oi": 100,
    } for c in contracts}
    return short, contracts, quotes


def build(selected="", cap=100):
    short, contracts, quotes = market()
    return build_protective_pe_spreads(
        short, contracts, quotes, 10, max_loss_cap=cap, selected_hedge_symbol=selected,
        margin_provider=lambda _: {"initial": {"total": 100}, "final": {"total": 50}},
    )


def test_manual_choice_reaches_farther_strike_beyond_automatic_candidates():
    assert not any(row["eligible"] for row in build())
    rows = build("TEST90PE")
    assert len(rows) == 1
    assert rows[0]["eligible"]
    assert rows[0]["net_credit"] == 80
    assert rows[0]["max_loss"] == 20
    assert rows[0]["order_payloads"][0]["tradingsymbol"] == "TEST90PE"


@pytest.mark.parametrize("change", [
    {"expiry": "2026-12-24"}, {"name": "OTHER"}, {"instrument_type": "CE"},
    {"lot_size": 20}, {"strike": 110},
])
def test_invalid_manual_contract_cannot_fall_back_to_another_hedge(change):
    short, contracts, quotes = market()
    contracts[-1].update(change)
    with pytest.raises(ValueError, match="verified lower-strike PE"):
        build_protective_pe_spreads(short, contracts, quotes, 10, max_loss_cap=100,
                                   selected_hedge_symbol="TEST90PE")


def test_unknown_contract_is_rejected():
    with pytest.raises(ValueError):
        build("INVENTED")


def test_manual_choice_does_not_override_max_loss():
    row = build("TEST90PE", cap=10)[0]
    assert not row["eligible"]
    assert "within cap" in row["reason"]


def test_manual_choice_does_not_override_liquidity():
    short, contracts, quotes = market()
    quotes["NFO:TEST90PE"]["oi"] = 0
    row = build_protective_pe_spreads(short, contracts, quotes, 10, max_loss_cap=100,
                                     selected_hedge_symbol="TEST90PE")[0]
    assert not row["eligible"]
    assert "liquidity" in row["reason"]


def test_selector_available_without_an_approved_strategy():
    short, contracts, _ = market()
    markup = render_hedge_selector({
        "hedge_contract_choices": protective_pe_contracts(short, contracts),
        "selected_hedge_symbol": "TEST90PE",
    })
    assert 'value="TEST90PE" selected' in markup
    assert 'formaction="/trade/review"' in markup
    assert "does not place an order" in markup
    assert 'formaction="/trade/submit"' not in markup


def test_selected_far_hedge_completes_paper_flow_without_live_client(tmp_path, monkeypatch):
    from kite_broker_adapter import KiteBrokerAdapter
    broker = KiteBrokerAdapter(paper_trading=True)
    monkeypatch.setattr(broker, "_client", lambda: pytest.fail("No live client allowed"))
    repo = ProtectedExecutionRepository(tmp_path / "paper.db")
    preview = {**build("TEST90PE")[0], "hedged_order_acknowledged": True}
    row = start_execution(repo, "TEST", "manual-hedge", preview, "PAPER", broker, lambda _: None)
    assert len(broker.call_log) == 1
    assert broker.call_log[0]["payload"]["tradingsymbol"] == "TEST90PE"
    row = reconcile_execution(repo, "TEST", row["id"], broker)
    assert row["state"] == "HEDGE_FILLED"
    row = confirm_short(repo, "TEST", row["id"], broker,
                        lambda _: {"quantity": 10, "price": 10}, acknowledged=True)
    assert broker.call_log[1]["payload"]["tradingsymbol"] == "TEST100PE"
    assert reconcile_execution(repo, "TEST", row["id"], broker)["state"] == "SPREAD_ACTIVE"
