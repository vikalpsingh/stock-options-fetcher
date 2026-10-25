"""LIVE control-flow tests use an in-memory exchange, never a broker client."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from test_nifty_ticket_service import market
from nifty_options_engine.page import execute_action
from nifty_options_engine.ledger import NiftyStrategyRepository
from nifty_options_engine.service import live_snapshot_gate
from trade_protected_execution import ProtectedExecutionRepository


class Exchange:
    paper_trading = False
    dry_run = False
    def __init__(self):
        self.orders = []
        self.trades = {}
    def place_order(self, payload):
        oid = str(len(self.orders)+1)
        self.orders.append({**payload, 'order_id':oid, 'status':'OPEN', 'filled_quantity':0})
        return {'order_id':oid}
    def get_orders(self):
        return self.orders
    def get_order_trades(self, oid):
        return self.trades.get(oid, [])
    def get_positions(self):
        quantities = {}
        for trades in self.trades.values():
            for trade in trades:
                symbol = trade['tradingsymbol']
                quantities[symbol] = quantities.get(symbol,0)+trade['quantity']*(1 if trade['transaction_type']=='BUY' else -1)
        return {'net':[dict(tradingsymbol=symbol, quantity=quantity, product='NRML',exchange='NFO') for symbol,quantity in quantities.items()]}
    def fill(self, quantity=130):
        order = self.orders[-1]
        order.update(status='COMPLETE' if quantity==130 else 'OPEN', filled_quantity=quantity)
        self.trades[order['order_id']] = [{**order, 'trade_id':'T'+order['order_id'], 'quantity':quantity,
                                         'average_price':order['price'], 'fill_timestamp':'2026-10-21T10:01:00+05:30'}]


@pytest.fixture
def live(tmp_path, market):
    selection, context, config = market
    selection['mode'] = 'LIVE'
    config['live_enabled'] = True
    context.update(live_ack_enabled=True,session_fingerprint='hashed-session',live_risk_gate={'allowed':True})
    path = tmp_path/'live.db'
    broker = Exchange()
    def loader(selection):
        value = deepcopy(context)
        ledger = NiftyStrategyRepository(path);ledger.ensure_schema()
        value['allocations'] = ledger.position_allocations('A','LIVE')
        value['positions'] = deepcopy(value['allocations'])
        value['orders'] = deepcopy(broker.orders)
        return value
    form = {key:[str(value)] for key,value in selection.items()};form['structure']=['PE']
    record, _ = execute_action('/nifty-2/review',form,'A',path,config,loader,lambda _:broker)
    assert record
    record['reviewed_at'] = (datetime.now(timezone.utc)-timedelta(seconds=12)).isoformat()
    ProtectedExecutionRepository(path).save(record)
    action = {'execution_id':[record['id']], 'ack':['yes'], 'live_ack':['PLACE LIVE ORDERS']}
    def run(endpoint, test_mode=False):
        if endpoint.startswith('close-'):
            execute_action('/nifty-2/review-exit',action,'A',path,config,loader,lambda _:broker,test_mode)
        return execute_action('/nifty-2/'+endpoint,action,'A',path,config,loader,lambda _:broker,test_mode)[0]
    return run,broker,context,action


def test_verified_live_stub_full_lifecycle(live):
    run,broker,_,_ = live
    assert run('start')['state']=='HEDGE_PENDING'
    with pytest.raises(PermissionError): run('confirm-sell')
    assert len(broker.orders)==1
    broker.fill(65)
    with pytest.raises(PermissionError): run('confirm-sell')
    assert len(broker.orders)==1
    broker.fill()
    assert run('reconcile')['state']=='HEDGE_FILLED'
    assert run('confirm-sell')['state']=='SHORT_PENDING'
    assert [o['transaction_type'] for o in broker.orders]==['BUY','SELL']
    broker.fill()
    assert run('reconcile')['state']=='OPEN'
    with pytest.raises(PermissionError): run('confirm-sell')
    run('close-shorts');broker.fill()
    assert run('reconcile')['state']=='SHORT_CLOSED_HEDGE_OPEN'
    run('close-hedges');broker.fill()
    assert run('reconcile')['state']=='CLOSED'
    assert [o['transaction_type'] for o in broker.orders]==['BUY','SELL','BUY','SELL']


@pytest.mark.parametrize('fault',['test_mode','account','regime','monthly','permission'])
def test_live_gate_rechecks_before_buy(live,fault):
    run,broker,context,_ = live
    if fault=='account':context['session_fingerprint']='different'
    if fault=='regime':context['live_risk_gate']={'allowed':False,'reason':'Event block'}
    if fault=='monthly':context['monthly']['hard_locked']=True
    if fault=='permission':context['live_ack_enabled']=False
    with pytest.raises(PermissionError):run('start',fault=='test_mode')
    assert not broker.orders


def test_new_regime_block_holds_hedge_before_sell(live):
    run,broker,context,_ = live
    run('start');broker.fill()
    context['live_risk_gate']={'allowed':False,'reason':'New event block'}
    with pytest.raises(PermissionError):run('confirm-sell')
    assert len(broker.orders)==1


def test_existing_risk_gate_fails_closed():
    assert not live_snapshot_gate({})['allowed']
    snapshot=dict(no_trade_decision={'allowed':True,'no_trade':False},
                  data_quality={'status':'GOOD','live_order_enabled':True},
                  confidence_score={'action':'FULL_SIZE','position_size_multiplier':1,'hard_blocks':[]},
                  suggestion={'allowed':True})
    assert live_snapshot_gate(snapshot)['allowed']
    snapshot['confidence_score']['hard_blocks']=['EVENT']
    assert not live_snapshot_gate(snapshot)['allowed']


def test_account_change_blocks_reconciliation(live):
    run,broker,context,_ = live
    run('start');broker.fill()
    context['session_fingerprint']='other-account'
    with pytest.raises(PermissionError,match='account changed'):run('reconcile')
    assert len(broker.orders)==1


def test_removed_hedge_blocks_live_short(live):
    run,broker,_,_ = live
    run('start');broker.fill()
    broker.get_positions=lambda: {'net':[]}
    with pytest.raises(PermissionError,match='coverage'):run('confirm-sell')
    assert len(broker.orders)==1


def test_short_must_close_before_hedge_disposal(live):
    run,broker,_,_ = live
    run('start');broker.fill();run('confirm-sell');broker.fill();run('reconcile')
    with pytest.raises(PermissionError):run('close-hedges')
    assert len(broker.orders)==2


def test_existing_half_size_gate_caps_requested_lots():
    snapshot=dict(no_trade_decision={'allowed':True,'no_trade':False},
                  data_quality={'status':'GOOD','live_order_enabled':True},
                  confidence_score={'action':'HALF_SIZE','position_size_multiplier':.5,'hard_blocks':[]},
                  suggestion={'allowed':True})
    assert not live_snapshot_gate(snapshot,lots=2)['allowed']
    assert live_snapshot_gate(snapshot,lots=1)['allowed']


def test_live_structure_must_match_existing_strategy_approval():
    snapshot=dict(no_trade_decision={'allowed':True,'no_trade':False},
                  data_quality={'status':'GOOD','live_order_enabled':True},
                  confidence_score={'action':'FULL_SIZE','position_size_multiplier':1,'hard_blocks':[]},
                  suggestion={'allowed':True,'selected_strategy':'BULL_PUT_SPREAD'})
    assert live_snapshot_gate(snapshot,strategy_type='BULL_PUT_SPREAD')['allowed']
    assert not live_snapshot_gate(snapshot,strategy_type='BEAR_CALL_SPREAD')['allowed']


def test_cancelled_partial_short_cleanup_uses_actual_fills(live):
    run, broker, _, _ = live
    run('start'); broker.fill(); run('confirm-sell'); broker.fill(65)
    broker.orders[-1]['status'] = 'CANCELLED'
    assert run('reconcile')['state'] == 'RECOVERY_READY'
    with pytest.raises(PermissionError): run('confirm-sell')
    run('close-shorts')
    assert broker.orders[-1]['transaction_type'] == 'BUY'
    assert broker.orders[-1]['quantity'] == 65
    broker.fill(65); broker.orders[-1]['status'] = 'COMPLETE'
    assert run('reconcile')['state'] == 'SHORT_CLOSED_HEDGE_OPEN'
    run('close-hedges')
    assert broker.orders[-1]['quantity'] == 130
    broker.fill()
    assert run('reconcile')['state'] == 'CLOSED'


def test_rejected_short_allows_owned_orphan_cleanup(live):
    run, broker, _, _ = live
    run('start'); broker.fill(); run('confirm-sell')
    broker.orders[-1]['status'] = 'REJECTED'
    assert run('reconcile')['state'] == 'RECOVERY_READY'
    run('close-shorts')
    assert broker.orders[-1]['transaction_type'] == 'SELL'
    assert broker.orders[-1]['tradingsymbol'] == broker.orders[0]['tradingsymbol']
    broker.fill()
    assert run('reconcile')['state'] == 'CLOSED'


def test_pending_partial_short_cannot_start_cleanup(live):
    run, broker, _, _ = live
    run('start'); broker.fill(); run('confirm-sell'); broker.fill(65)
    assert run('reconcile')['state'] == 'SHORT_PARTIAL'
    with pytest.raises(PermissionError): run('close-shorts')
    assert len(broker.orders) == 2


def test_cancelled_partial_hedge_cleanup(live):
    run, broker, _, _ = live
    run('start'); broker.fill(65)
    broker.orders[-1]['status'] = 'CANCELLED'
    assert run('reconcile')['state'] == 'RECOVERY_READY'
    run('close-shorts')
    assert broker.orders[-1]['quantity'] == 65
    assert broker.orders[-1]['transaction_type'] == 'SELL'
    broker.fill(65); broker.orders[-1]['status'] = 'COMPLETE'
    assert run('reconcile')['state'] == 'CLOSED'


def test_cancelled_partial_short_exit_resubmits_only_residual(live):
    run, broker, _, _ = live
    run('start'); broker.fill(); run('confirm-sell'); broker.fill(); run('close-shorts')
    broker.fill(65); broker.orders[-1]['status'] = 'CANCELLED'
    assert run('reconcile')['state'] == 'EXIT_RECOVERY_READY'
    run('close-shorts')
    assert broker.orders[-1]['quantity'] == 65
    assert broker.orders[-1]['transaction_type'] == 'BUY'
    assert len({order['tag'] for order in broker.orders}) == len(broker.orders)
    with pytest.raises(PermissionError): run('close-shorts')
    assert len(broker.orders) == 4
    broker.fill(65); broker.orders[-1]['status'] = 'COMPLETE'
    assert run('reconcile')['state'] == 'SHORT_CLOSED_HEDGE_OPEN'
    run('close-hedges'); broker.fill()
    result = run('reconcile')
    assert result['state'] == 'CLOSED'
    assert len(result['exit_legs']) == 3  # failed attempt is retained for P&L


def test_rejected_hedge_exit_requires_new_explicit_action(live):
    run, broker, _, _ = live
    run('start'); broker.fill(); run('confirm-sell'); broker.fill()
    run('close-shorts'); broker.fill(); run('close-hedges')
    broker.orders[-1]['status'] = 'REJECTED'
    assert run('reconcile')['state'] == 'SHORT_CLOSED_HEDGE_OPEN'
    assert len(broker.orders) == 4
    run('close-hedges')
    assert len(broker.orders) == 5
    assert broker.orders[-1]['quantity'] == 130
    broker.fill()
    assert run('reconcile')['state'] == 'CLOSED'


def test_pending_partial_exit_blocks_replacement_and_hedge_disposal(live):
    run, broker, _, _ = live
    run('start'); broker.fill(); run('confirm-sell'); broker.fill(); run('close-shorts')
    broker.fill(65)
    assert run('reconcile')['state'] == 'PARTIALLY_CLOSED'
    with pytest.raises(PermissionError): run('close-shorts')
    with pytest.raises(PermissionError): run('close-hedges')
    assert len(broker.orders) == 3


def test_short_buy_rejection_keeps_hedge_and_requires_explicit_retry(live):
    run,broker,_,_=live
    run('start');broker.fill();run('confirm-sell');broker.fill();run('close-shorts')
    broker.orders[-1]['status']='REJECTED'
    assert run('reconcile')['state']=='EXIT_RECOVERY_READY'
    with pytest.raises(PermissionError):run('close-hedges')
    assert len(broker.orders)==3
    run('close-shorts')
    assert broker.orders[-1]['transaction_type']=='BUY'
    assert broker.orders[-1]['quantity']==130


def test_short_exit_timeout_recovers_by_tag_without_duplicate(live):
    run,broker,_,_=live
    run('start');broker.fill();run('confirm-sell');broker.fill()
    original=broker.place_order
    def accepted_but_disconnected(payload):
        original(payload)
        raise TimeoutError('simulated disconnect')
    broker.place_order=accepted_but_disconnected
    result=run('close-shorts')
    assert result['exit_legs'][0]['status']=='SUBMISSION_UNKNOWN'
    broker.place_order=original
    assert run('reconcile')['state']=='EXIT_PENDING'
    with pytest.raises(PermissionError):run('close-shorts')
    assert len(broker.orders)==3
    broker.fill()
    assert run('reconcile')['state']=='SHORT_CLOSED_HEDGE_OPEN'


def test_illiquid_hedge_does_not_block_short_risk_reduction(live):
    run,broker,context,_=live
    run('start');broker.fill();run('confirm-sell');broker.fill()
    hedge=broker.orders[0]['tradingsymbol']
    context['quotes']['NFO:'+hedge]={}
    run('close-shorts');broker.fill()
    assert run('reconcile')['state']=='SHORT_CLOSED_HEDGE_OPEN'
    with pytest.raises(PermissionError):run('close-hedges')
    assert len(broker.orders)==3


def test_pending_scheduler_close_blocks_manual_submission(live):
    run,broker,_,_=live
    run('start');broker.fill();run('confirm-sell');broker.fill()
    broker.orders.append(dict(broker.orders[-1],order_id='scheduler',transaction_type='BUY',status='OPEN',filled_quantity=0,tag='scheduler'))
    with pytest.raises(PermissionError):run('close-shorts')
    assert len(broker.orders)==3


def test_repeated_close_click_does_not_duplicate_pending_order(live):
    run,broker,_,_=live
    run('start');broker.fill();run('confirm-sell');broker.fill()
    run('close-shorts')
    with pytest.raises(PermissionError):run('close-shorts')
    assert len(broker.orders)==3
