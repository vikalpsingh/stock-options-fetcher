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
                        strike=strike, expiry=selection['expiry'], lot_size=65, tick_size=0.05, instrument_token=index+1)
                   for index, strike in enumerate((22000, 22300))]
    quotes = {'NFO:' + row['tradingsymbol']: dict(timestamp=now.isoformat(), last_price=price+1 if price==20 else price,
              depth=dict(buy=[dict(price=price, quantity=1000)],
                         sell=[dict(price=price+1, quantity=1000)]), oi=10000, volume=10000)
              for row, price in zip(instruments, (20, 60))}
    context = dict(now=now, instruments=instruments, quotes=quotes, positions=[], allocations=[],
                   orders=[], monthly=dict(risk_state='GREEN', hard_locked=False), margin=50000,
                   funds=100000, spot=23000, market_open=True, live_ack_enabled=False)
    # Explicit mocked directional evidence keeps baseline execution tests independent of Kite history.
    context['dtv'] = dict(ce_status='ALLOW', pe_status='ALLOW', calculated_at=now.isoformat(),
                          valid_until=(now+timedelta(minutes=2)).isoformat(), reasons={'CE':'Fixture', 'PE':'Fixture'})
    return selection, context, income_v2_config()


def test_ticket_executable_costs_and_master_quantity(market):
    selection, context, config = market
    ticket = build_ticket(selection, context, config)
    assert ticket['eligible'], ticket['checks']
    assert ticket['net_credit'] == 39 * 130
    assert ticket['net_max_profit'] == 39 * 130 - 500
    assert ticket['max_loss'] == 300 * 130 - 39 * 130 + 500
    assert [leg['quantity'] for leg in ticket['legs']] == [130, 130]


@pytest.mark.parametrize('fault', ['stale', 'missing_ask', 'monthly', 'live'])
def test_ticket_blocks_missing_fresh_risk_evidence(market, fault):
    selection, context, config = market
    quote = context['quotes']['NFO:NIFTY22000PE']
    if fault == 'stale':
        selection['mode'] = 'LIVE'
        config['live_enabled'] = True
        context.update(live_ack_enabled=True, session_fingerprint='test', live_risk_gate={'allowed':True})
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


def test_quick_pair_advice_override_keeps_capital_and_monthly_checks(market):
    selection,context,config=market
    context['dtv']['pe_status']='BLOCK'
    assert not build_ticket(selection,context,config)['eligible']
    selection['quick_pair']='PE'
    assert not build_ticket(selection,context,config)['eligible']
    selection['skip_strategy_validation']=True
    ticket=build_ticket(selection,context,config)
    assert ticket['eligible']
    assert all(p['tradingsymbol'].endswith('PE') for p in ticket['order_payloads'])
    assert any(c['name']=='Directional Trend Veto PE' and c['status']=='WARNING' for c in ticket['checks'])
    context['monthly']['hard_locked']=True
    assert not build_ticket(selection,context,config)['eligible']


def test_quick_pair_selects_exact_side_and_lots():
    from nifty_options_engine.page import selection_from_form
    selected=selection_from_form({'structure':['BOTH'],'quick_pair':['CE'],'lots':['3'],'auto_best':['yes']})
    assert selected['include_ce'] and not selected['include_pe']
    assert selected['lots']=='3' and not selected['auto_best']
    with pytest.raises(ValueError):selection_from_form({'quick_pair':['BOTH']})


def test_skip_strategy_choice_is_explicit_and_scoped(market):
    from nifty_options_engine.page import selection_from_form
    selection,context,config=market
    context['dtv']['pe_status']='BLOCK'
    selection['skip_strategy_validation']=True
    assert not build_ticket(selection,context,config)['eligible']  # ordinary flow cannot bypass
    assert not selection_from_form({'skip_strategy_validation':['true']})['skip_strategy_validation']
    assert selection_from_form({'skip_strategy_validation':['yes']})['skip_strategy_validation']
    from nifty_options_engine.ui import quick_pair_review_form
    html=quick_pair_review_form(selection)
    assert 'value="PE"' in html and 'value="CE"' in html and 'directional advice only' in html
