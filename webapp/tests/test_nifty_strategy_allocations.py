import pytest

from nifty_options_engine.ledger import NiftyStrategyRepository
from nifty_options_engine.reconciliation import allocate_nifty_positions
from nifty_options_engine.risk_validator import calculate_nifty_portfolio_risk


def ticket():
    return [
        dict(tradingsymbol="NIFTYTEST23000PE", strike=23000, option_type="PE",
             expiry="2026-11-24", instrument_token=1, quantity=130, lot_size=65,
             transaction_type="SELL", product="NRML"),
        dict(tradingsymbol="NIFTYTEST22700PE", strike=22700, option_type="PE",
             expiry="2026-11-24", instrument_token=2, quantity=130, lot_size=65,
             transaction_type="BUY", product="NRML"),
    ]


def fill(row, order, trade, quantity=130, price=10, side=None):
    return dict(tradingsymbol=row["tradingsymbol"], transaction_type=side or row["transaction_type"],
                order_id=order, trade_id=trade, quantity=quantity, price=price,
                filled_at="2026-10-20T10:00:00+05:30", fees=2)


@pytest.fixture
def repo(tmp_path):
    repository = NiftyStrategyRepository(tmp_path / "isolated.sqlite3")
    repository.ensure_schema()
    repository.ensure_schema()
    return repository


def populated(repo, mode="LIVE"):
    legs = ticket()
    strategy = repo.create_strategy("A", "request", "BULL_PUT_SPREAD", legs, mode)
    for index, leg in enumerate(legs):
        repo.register_order("A", strategy, leg["tradingsymbol"], str(index))
        repo.record_fill("A", fill(leg, str(index), f"t{index}", price=100 if index == 0 else 40))
    broker = [{**row, "account_id": "A", "quantity": -130 if index == 0 else 130,
               "average_price": 100 if index == 0 else 40, "pnl": 1000}
              for index, row in enumerate(legs)]
    return strategy, broker


def test_schema_is_additive_and_strategy_request_is_idempotent(repo):
    first = repo.create_strategy("A", "r", "BULL_PUT_SPREAD", ticket())
    assert repo.create_strategy("A", "r", "BULL_PUT_SPREAD", ticket()) == first
    changed = ticket()
    changed[0]["quantity"] = 65
    with pytest.raises(ValueError, match="different ticket"):
        repo.create_strategy("A", "r", "BULL_PUT_SPREAD", changed)


def test_same_request_cannot_cross_paper_live(repo):
    repo.create_strategy("A", "r", "BULL_PUT_SPREAD", ticket(), "PAPER")
    with pytest.raises(ValueError, match="different ticket"):
        repo.create_strategy("A", "r", "BULL_PUT_SPREAD", ticket(), "LIVE")


def test_confirmed_fills_reconcile_to_broker_net(repo):
    _, broker = populated(repo)
    allocation = repo.position_allocations("A")
    result = calculate_nifty_portfolio_risk(broker, strategy_allocations=allocation)
    assert result["risk_status"] == "PASS"
    assert result["current_defined_max_loss"] == 31200
    assert repo.position_allocations("B") == []
    assert repo.position_allocations("A", "PAPER") == []


def test_duplicate_fill_not_double_counted_and_conflict_rejected(repo):
    populated(repo)
    row = fill(ticket()[0], "0", "t0", price=100)
    assert repo.record_fill("A", row) is False
    assert abs(repo.position_allocations("A")[0]["quantity"]) == 130
    row["price"] = 999
    with pytest.raises(ValueError, match="Conflicting duplicate"):
        repo.record_fill("A", row)


def test_unmapped_fills_are_not_guessed(repo):
    with pytest.raises(ValueError, match="UNMATCHED"):
        repo.record_fill("A", fill(ticket()[0], "missing", "t0"))


def test_order_ownership_and_fill_side_cannot_be_reassigned(repo):
    strategy, _ = populated(repo)
    with pytest.raises(ValueError, match="allocated elsewhere"):
        repo.register_order("A", strategy, ticket()[1]["tradingsymbol"], "0")
    with pytest.raises(ValueError, match="contract/side"):
        repo.record_fill("A", fill(ticket()[0], "0", "new", side="BUY"))


def test_partial_close_updates_remaining_quantity_and_preserves_entry_cost(repo):
    strategy, broker = populated(repo)
    repo.register_order("A", strategy, ticket()[0]["tradingsymbol"], "exit", "EXIT")
    repo.record_fill("A", fill(ticket()[0], "exit", "close", quantity=65, price=80, side="BUY"))
    broker[0]["quantity"] = -65
    result = allocate_nifty_positions(broker, repo.position_allocations("A"))
    assert not result["block_new_entries"]
    short = next(row for row in result["positions"] if row["quantity"] < 0)
    assert short["quantity"] == -65 and short["average_price"] == 100


def test_exit_overfill_and_missing_broker_position_fail_closed(repo):
    strategy, broker = populated(repo)
    repo.register_order("A", strategy, ticket()[0]["tradingsymbol"], "exit", "EXIT")
    repo.record_fill("A", fill(ticket()[0], "exit", "close", quantity=195, price=80, side="BUY"))
    result = allocate_nifty_positions(broker, repo.position_allocations("A"))
    assert result["block_new_entries"]
    result = allocate_nifty_positions([], repo.position_allocations("A"))
    assert result["block_new_entries"]


def test_duplicate_allocations_cannot_double_count_hedge(repo):
    _, broker = populated(repo)
    allocations = repo.position_allocations("A")
    result = allocate_nifty_positions(broker, allocations + [allocations[1]])
    assert result["block_new_entries"]
    assert "DUPLICATE_OR_UNVERIFIED_ALLOCATION" in result["errors"]


def test_broker_quantity_reduction_must_be_reconciled(repo):
    _, broker = populated(repo)
    broker[1]["quantity"] = 65
    result = calculate_nifty_portfolio_risk(broker, strategy_allocations=repo.position_allocations("A"))
    assert result["risk_status"] == "BLOCK"
    assert result["current_defined_max_loss"] is None


def test_pending_hedge_disposal_blocks_entry(repo):
    _, broker = populated(repo)
    pending = {**broker[1], "transaction_type": "SELL", "status": "OPEN"}
    result = calculate_nifty_portfolio_risk(
        broker, strategy_allocations=repo.position_allocations("A"), pending_orders=[pending])
    assert result["risk_status"] == "BLOCK"
    assert "HEDGE_DISPOSAL_PENDING" in result["hard_block_reasons"]


def test_paper_fill_cannot_cover_live_short(repo):
    _, broker = populated(repo, "PAPER")
    result = calculate_nifty_portfolio_risk(broker, strategy_allocations=repo.position_allocations("A", "LIVE"))
    assert result["risk_status"] == "BLOCK"
