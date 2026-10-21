"""Isolated durable basket checks: no broker clients and temporary databases only."""
from datetime import datetime, timedelta, timezone

import pytest

from trade_protected_execution import (
    ProtectedExecutionRepository, submit_basket_hedges, reconcile_basket,
    confirm_basket_shorts, submit_basket_exit,
)


class PaperBroker:
    paper_trading = True
    dry_run = False

    def __init__(self):
        self.sent = []
        self.timeout = False

    def place_order(self, payload):
        self.sent.append(dict(payload))
        if self.timeout:
            raise TimeoutError()
        return {'order_id': str(len(self.sent))}


def review(repo, condor=False):
    specs = [('PE', 22000, 'BUY', 20), ('PE', 22300, 'SELL', 60)]
    if condor:
        specs += [('CE', 24000, 'BUY', 20), ('CE', 23700, 'SELL', 60)]
    legs, payloads = [], []
    for index, (kind, strike, side, price) in enumerate(specs):
        symbol = f'NIFTY{strike}{kind}'
        legs.append(dict(account_id='A', tradingsymbol=symbol, option_type=kind,
                         strike=strike, expiry='2026-11-26', instrument_token=index + 1,
                         quantity=130, lot_size=65, transaction_type=side))
        payloads.append(dict(tradingsymbol=symbol, quantity=130, transaction_type=side,
                             exchange='NFO', product='NRML', order_type='LIMIT', price=price))
    return repo.create_basket_review('A', dict(legs=legs, order_payloads=payloads), 'PAPER')


def start(repo, record, broker):
    return submit_basket_hedges(repo, 'A', record['id'], broker, lambda *args: None,
                                acknowledged=True,
                                now=datetime.fromisoformat(record['reviewed_at']) + timedelta(seconds=11))


@pytest.fixture
def setup(tmp_path):
    return ProtectedExecutionRepository(tmp_path / 'basket.db'), PaperBroker()


def test_countdown_ack_and_buy_only_restart(setup):
    repo, broker = setup
    row = review(repo)
    with pytest.raises(PermissionError):
        submit_basket_hedges(repo, 'A', row['id'], broker, lambda *args: None, True,
                             now=datetime.fromisoformat(row['reviewed_at']))
    with pytest.raises(PermissionError):
        submit_basket_hedges(repo, 'A', row['id'], broker, lambda *args: None)
    assert not broker.sent
    row = start(repo, row, broker)
    assert [o['transaction_type'] for o in broker.sent] == ['BUY']
    restored = ProtectedExecutionRepository(repo.path)
    assert restored.get('A', row['id'])['state'] == 'HEDGE_PENDING'
    with pytest.raises(PermissionError):
        start(restored, row, broker)
    assert len(broker.sent) == 1


def test_condor_resume_reapproves_only_unsent_short(setup):
    repo, broker = setup
    row = start(repo, review(repo, True), broker)
    approvals = []

    def approve(record, stage):
        approvals.append(stage)
        if len(approvals) == 2:
            raise PermissionError('Fresh risk now blocks second short')

    with pytest.raises(PermissionError):
        confirm_basket_shorts(repo, 'A', row['id'], broker, approve, True)
    assert [o['transaction_type'] for o in broker.sent] == ['BUY', 'BUY', 'SELL']
    confirm_basket_shorts(repo, 'A', row['id'], broker, approve, True)
    assert approvals == ['SELL', 'SELL', 'SELL']
    assert len(broker.sent) == 4
    assert len({o['tag'] for o in broker.sent}) == 4
    row = reconcile_basket(repo, 'A', row['id'], broker)
    assert row['state'] == 'OPEN'
    with pytest.raises(PermissionError):
        confirm_basket_shorts(repo, 'A', row['id'], broker, approve, True)
    assert len(broker.sent) == 4


def test_unknown_buy_never_sells_or_retries(setup):
    repo, broker = setup
    broker.timeout = True
    row = start(repo, review(repo, True), broker)
    with pytest.raises(PermissionError):
        confirm_basket_shorts(repo, 'A', row['id'], broker, lambda *args: None, True)
    assert len(broker.sent) == 1
    assert repo.get('A', row['id'])['state'] == 'RECONCILIATION_REQUIRED'


def test_full_paper_lifecycle_keeps_hedge_until_short_closed(setup):
    repo, broker = setup
    row = start(repo, review(repo), broker)
    confirm_basket_shorts(repo, 'A', row['id'], broker, lambda *args: None, True)
    prices = {leg['payload']['tradingsymbol']: 10 for leg in row['legs']}
    with pytest.raises(PermissionError):
        submit_basket_exit(repo, 'A', row['id'], broker, lambda *args: None, prices, True, True)
    submit_basket_exit(repo, 'A', row['id'], broker, lambda *args: None, prices, True)
    assert [o['transaction_type'] for o in broker.sent] == ['BUY', 'SELL', 'BUY']
    row = reconcile_basket(repo, 'A', row['id'], broker)
    assert row['state'] == 'SHORT_CLOSED_HEDGE_OPEN'
    submit_basket_exit(repo, 'A', row['id'], broker, lambda *args: None, prices, True, True)
    row = reconcile_basket(repo, 'A', row['id'], broker)
    assert row['state'] == 'CLOSED'
    assert len(broker.sent) == 4


def test_reservation_blocks_duplicate_basket(setup):
    repo, broker = setup
    first, second = review(repo), review(repo)
    start(repo, first, broker)
    with pytest.raises(PermissionError):
        start(repo, second, broker)
    assert len(broker.sent) == 1

@pytest.mark.parametrize('filled', [0, 65])
def test_accepted_or_partial_hedge_never_authorizes_sell(tmp_path, filled):
    class ExchangeStub(PaperBroker):
        paper_trading = False

        def get_orders(self):
            return [{**order, 'order_id': str(index + 1), 'status': 'OPEN',
                     'filled_quantity': filled} for index, order in enumerate(self.sent)]

        def get_order_trades(self, oid):
            if not filled:
                return []
            return [{**self.sent[int(oid) - 1], 'order_id': oid, 'trade_id': 'F' + oid,
                     'quantity': filled, 'average_price': 20}]

    repo, broker = ProtectedExecutionRepository(tmp_path / 'stub.db'), ExchangeStub()
    row = review(repo)
    row['mode'] = 'LIVE'  # Exercise real receipt verification with an in-memory stub only.
    row = repo.save(row)
    row = start(repo, row, broker)
    approvals = []
    with pytest.raises(PermissionError):
        confirm_basket_shorts(repo, 'A', row['id'], broker,
                              lambda *args: approvals.append(args), True)
    assert not approvals
    assert len(broker.sent) == 1
    assert repo.get('A', row['id'])['state'] == ('HEDGE_PARTIAL' if filled else 'HEDGE_PENDING')
