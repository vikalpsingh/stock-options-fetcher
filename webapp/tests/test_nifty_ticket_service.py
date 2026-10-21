"""NIFTY ticket/service tests with synthetic quotes and temporary ledgers."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from nifty_options_engine.config import income_v2_config
from nifty_options_engine.ticket import build_ticket
from nifty_options_engine.service import persist_review, sync_execution_fills, approve_entry
from nifty_options_engine.ledger import NiftyStrategyRepository
from trade_protected_execution import ProtectedExecutionRepository, submit_basket_hedges, reconcile_basket


@pytest.fixture
def market():
    now = datetime(2026, 10, 21, 10, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    selection = dict(include_pe=True, lots='2', expiry='2026-11-24',
                     short_pe='NIFTY22300PE', hedge_pe='NIFTY22000PE', mode='PAPER')
    instruments = [dict(name='NIFTY', tradingsymbol=f'NIFTY{strike}PE', instrument_type='PE',
                        strike=strike, expiry=selection['expiry'], lot_size=65, instrument_token=index+1)
                   for index, strike in enumerate((22000, 22300))]
    quotes = {'NFO:' + row['tradingsymbol']: dict(timestamp=now.isoformat(),
              depth=dict(buy=[dict(price=price, quantity=1000)],
                         sell=[dict(price=price+1, quantity=1000)]), oi=10000, volume=10000)
              for row, price in zip(instruments, (20, 60))}
    context = dict(now=now, instruments=instruments, quotes=quotes, positions=[], allocations=[],
                   orders=[], monthly=dict(risk_state='GREEN', hard_locked=False), margin=50000,
                   funds=100000, spot=23000, market_open=True, live_ack_enabled=False)
    return selection, context, income_v2_config()


def test_ticket_executable_costs_and_master_quantity(market):
    selection, context, config = market
    ticket = build_ticket(selection, context, config)
    assert ticket['eligible'], ticket['checks']
    assert ticket['net_credit'] == 39 * 130
    assert ticket['net_max_profit'] == 39 * 130 - 500
    assert ticket['max_loss'] == 300 * 130 - 39 * 130 + 500
    assert [leg['quantity'] for leg in ticket['legs']] == [130, 130]


@pytest.mark.parametrize('fault', ['stale', 'missing_ask', 'depth', 'monthly', 'margin', 'live'])
def test_ticket_blocks_missing_fresh_risk_evidence(market, fault):
    selection, context, config = market
    quote = context['quotes']['NFO:NIFTY22000PE']
    if fault == 'stale':
        quote['timestamp'] = (context['now'] - timedelta(minutes=3)).isoformat()
    elif fault == 'missing_ask':
        quote['depth']['sell'] = []
    elif fault == 'depth':
        quote['depth']['sell'][0]['quantity'] = 1
    elif fault == 'monthly':
        context['monthly']['hard_locked'] = True
    elif fault == 'margin':
        context['margin'] = None
    else:
        selection['mode'] = 'LIVE'
    assert not build_ticket(selection, context, config)['eligible']


def test_paper_fill_sync_is_durable_idempotent_and_cost_reapproved(tmp_path, market):
    selection, context, config = market
    path = tmp_path / 'ledger.db'
    ticket = build_ticket(selection, context, config)
    record = persist_review(path, 'A', ticket)
    repo = ProtectedExecutionRepository(path)

    class Paper:
        paper_trading = True
        dry_run = False
        def place_order(self, payload):
            assert payload['transaction_type'] == 'BUY'
            return {'order_id': 'SIMULATED'}

    broker = Paper()
    submit_basket_hedges(repo, 'A', record['id'], broker, lambda *args: None, True,
                         datetime.fromisoformat(record['reviewed_at']) + timedelta(seconds=11))
    record = reconcile_basket(repo, 'A', record['id'], broker)
    sync_execution_fills(path, record)
    sync_execution_fills(path, record)
    ledger = NiftyStrategyRepository(path)
    allocations = ledger.position_allocations('A', 'PAPER')
    assert len(allocations) == 1 and allocations[0]['quantity'] == 130
    assert len(ledger.strategies('A')[0]['legs'][0]['fills']) == 1
    assert not ledger.position_allocations('A', 'LIVE')
    context['allocations'] = allocations
    context['positions'] = deepcopy(allocations)
    assert approve_entry(record, context, config)['risk_status'] == 'PASS'
    record['legs'][0]['average'] += 10
    with pytest.raises(PermissionError, match='Actual hedge cost'):
        approve_entry(record, context, config)

@pytest.mark.parametrize('setting', ['enabled', 'allowed_strategies'])
def test_ticket_respects_disabled_settings(market, setting):
    selection, context, config = market
    config[setting] = False if setting == 'enabled' else ['BEAR_CALL_SPREAD']
    assert not build_ticket(selection, context, config)['eligible']


def test_entry_rechecks_monthly_lock_after_review(tmp_path, market):
    selection, context, config = market
    record = persist_review(tmp_path / 'review.db', 'A', build_ticket(selection, context, config))
    context['monthly']['hard_locked'] = True
    with pytest.raises(PermissionError, match='Monthly loss guard'):
        approve_entry(record, context, config)
