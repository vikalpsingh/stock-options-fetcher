"""Exercise the page/controller without importing app.py or contacting Kite."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from test_nifty_ticket_service import market
from nifty_options_engine.page import execute_action, page_data
from nifty_options_engine.ui import render_page
from nifty_options_engine.ledger import NiftyStrategyRepository
from trade_protected_execution import ProtectedExecutionRepository
from kite_broker_adapter import KiteBrokerAdapter


def test_page_paper_lifecycle_and_analytics(tmp_path, market, monkeypatch):
    selection, context, config = market
    path = tmp_path / 'page.db'
    monkeypatch.setattr(KiteBrokerAdapter, '_client', lambda self: pytest.fail('Broker access forbidden'))

    def loader(selection):
        value = deepcopy(context)
        ledger = NiftyStrategyRepository(path)
        ledger.ensure_schema()
        value['allocations'] = ledger.position_allocations('A', selection['mode'])
        value['positions'] = deepcopy(value['allocations'])
        return value

    factory = lambda mode: KiteBrokerAdapter(paper_trading=True)
    form = {key: [str(value)] for key, value in selection.items()}
    form['structure'] = ['PE']
    record, ticket = execute_action('/nifty-2/review', form, 'A', path, config, loader, factory)
    assert ticket['eligible']
    action = {'execution_id': [record['id']], 'ack': ['yes']}
    with pytest.raises(PermissionError, match='countdown'):
        execute_action('/nifty-2/start', action, 'A', path, config, loader, factory)
    repo = ProtectedExecutionRepository(path)
    record['reviewed_at'] = (datetime.now(timezone.utc)-timedelta(seconds=12)).isoformat()
    repo.save(record)
    for endpoint, expected in [('start','HEDGE_PENDING'), ('reconcile','HEDGE_FILLED'),
                                ('confirm-sell','SHORT_PENDING'), ('reconcile','OPEN'),
                                ('close-shorts','EXIT_PENDING'), ('reconcile','SHORT_CLOSED_HEDGE_OPEN'),
                                ('close-hedges','EXIT_PENDING'), ('reconcile','CLOSED')]:
        record, _ = execute_action('/nifty-2/'+endpoint, action, 'A', path, config, loader, factory)
        assert record['state'] == expected
    assert not NiftyStrategyRepository(path).position_allocations('A','PAPER')
    data = page_data('A', path, config, loader, form)
    html = render_page(data).decode('utf-8')
    assert 'Execution window' in html and 'Monthly performance' in html
    assert 'FULLY_CLOSED' in html
    assert data['analytics']['rows'][0]['realised_gross'] == -260  # bid/ask round-trip costs
    assert data['analytics']['rows'][0]['hedge_cost'] == 2730
    assert '<script>alert' not in render_page(error='<script>alert(1)</script>').decode()


def test_live_action_requires_typed_ack_before_adapter_creation(tmp_path, market):
    selection, context, config = market
    from nifty_options_engine.ticket import build_ticket
    from nifty_options_engine.service import persist_review
    ticket = build_ticket(selection, context, config)
    ticket['mode'] = 'LIVE'
    record = persist_review(tmp_path/'live.db', 'A', ticket)
    with pytest.raises(PermissionError, match='PLACE LIVE ORDERS'):
        execute_action('/nifty-2/start', {'execution_id':[record['id']]}, 'A', tmp_path/'live.db', config,
                       lambda _: pytest.fail('No data needed'), lambda _: pytest.fail('No adapter allowed'))


def test_market_adapter_uses_read_only_kite_and_temporary_database(tmp_path, market):
    from nifty_options_engine.service import load_market_context
    selection, context, config = market

    class KiteReadOnly:
        def orders(self):
            return []
        def positions(self):
            return {'net': []}
        def quote(self, keys):
            return {**context['quotes'], 'NSE:NIFTY 50': {'last_price':23000, 'timestamp':context['now']},
                    'NSE:INDIA VIX': {'last_price':15, 'timestamp':context['now']}}
        def margins(self):
            return {'equity':{'available':{'live_balance':100000}}}
        def basket_order_margins(self, orders):
            assert len(orders)==2
            return {'initial':{'total':50000}, 'final':{'total':40000}}
        def place_order(self, *args, **kwargs):
            pytest.fail('Market context must never submit orders')

    loaded = load_market_context(KiteReadOnly(), 'A', tmp_path/'context.db', selection, config,
                                  context['now'], context['instruments'])
    assert loaded['margin']==50000 and loaded['market_open']
    assert loaded['monthly']['risk_state'] in {'GREEN','AMBER','ORANGE','RED'}
    assert loaded['positions']==[] and loaded['orders']==[]


def test_actions_require_ack_and_account_ownership(tmp_path, market):
    selection, context, config = market
    from nifty_options_engine.ticket import build_ticket
    from nifty_options_engine.service import persist_review
    path = tmp_path/'ack.db'
    record = persist_review(path, 'A', build_ticket(selection, context, config))
    record['reviewed_at'] = (datetime.now(timezone.utc)-timedelta(seconds=12)).isoformat()
    ProtectedExecutionRepository(path).save(record)
    action = {'execution_id':[record['id']]}
    with pytest.raises(PermissionError, match='acknowledgement'):
        execute_action('/nifty-2/start', action, 'A', path, config, lambda _:context,
                       lambda _:KiteBrokerAdapter(paper_trading=True))
    with pytest.raises(PermissionError, match='account'):
        execute_action('/nifty-2/start', action, 'B', path, config, lambda _:context,
                       lambda _:pytest.fail('Wrong account must not construct adapter'))


def test_recovery_guidance_and_currency():
    from nifty_options_engine.ui import execution_guidance, money
    record = {'state':'RECOVERY_READY','legs':[{'filled':65,'payload':{'transaction_type':'SELL'}}]}
    assert 'filled short quantity first' in execution_guidance(record)
    record['legs'][0]['filled'] = 0
    assert 'orphan hedges' in execution_guidance(record)
    record['state'] = 'SHORT_PARTIAL'
    assert 'Pending entry orders must finish' in execution_guidance(record)
    record['state'] = 'CLOSED'
    assert 'No position was opened' in execution_guidance(record)
    assert money(100) == '\u20b9100.00'
