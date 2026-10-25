from copy import deepcopy
from datetime import datetime,timedelta,timezone
import pytest
from execution_pair_analytics import pair_pnl
from test_protected_execution import preview, Broker, approve
from trade_protected_execution import ProtectedExecutionRepository,start_execution,reconcile_execution,confirm_short

NOW=datetime(2026,10,24,10,tzinfo=timezone.utc)

def record():
    payload=lambda symbol,side:dict(tradingsymbol=symbol,transaction_type=side,quantity=10,exchange='NFO',product='NRML')
    return dict(state='OPEN',preview=dict(estimated_fees=2,final_margin=100),legs=[
        dict(payload=payload('H','BUY'),filled=10,average=3),dict(payload=payload('S','SELL'),filled=10,average=6)])

def quotes():
    return {'NFO:'+s:dict(timestamp=NOW,depth=dict(buy=[dict(price=2,quantity=20)],sell=[dict(price=3,quantity=20)])) for s in ('H','S')}

def test_partial_exit_separates_realized_and_open_and_capture():
    r=record();r['exit_legs']=[dict(payload=dict(r['legs'][1]['payload'],transaction_type='BUY',quantity=4),filled=4,average=4,order_id='X')]
    p=pair_pnl(r,quotes(),NOW)
    assert p['original_entry_credit']==30
    assert p['realized_pnl']==8
    assert p['gross_pnl']==8
    assert p['estimated_net_pnl']==6
    assert p['profit_captured_pct']==pytest.approx(16/30*100)
    assert p['return_on_margin']==6
    assert p['unmatched']


def test_unknowns_stale_and_incorrect_allocations():
    r=record();q=quotes();q['NFO:H']['timestamp']=NOW-timedelta(minutes=3)
    assert pair_pnl(r,q,NOW)['gross_pnl'] is None
    r['preview']={}
    assert pair_pnl(r,quotes(),NOW)['estimated_net_pnl'] is None
    assert pair_pnl(r,quotes(),NOW)['return_on_margin'] is None
    r['legs'][0]['average']=float('nan')
    assert pair_pnl(r,quotes(),NOW)['entry_credit'] is None
    r=record();r['legs'][0]['filled']=0;r['legs'][1]['filled']=0
    assert pair_pnl(r,{},NOW)['gross_pnl'] is None
    r=record();r['exit_legs']=[dict(payload=dict(r['legs'][0]['payload'],product='MIS',transaction_type='SELL'),filled=1,average=2,order_id='X')]
    assert pair_pnl(r,quotes(),NOW)['realized_pnl'] is None


def test_duplicate_trades_restart_and_account_mode_isolation(tmp_path,preview):
    broker=Broker();repo=ProtectedExecutionRepository(tmp_path/'pair.db')
    row=start_execution(repo,'A','key',preview,'LIVE',broker,lambda _:None)
    broker.fill();oid=broker.orders[-1]['order_id'];broker.fills[oid]*=2
    row=reconcile_execution(repo,'A',row['id'],broker)
    assert row['hedge_filled']==10 and len(row['hedge_trades'])==1
    row=confirm_short(repo,'A',row['id'],broker,approve,True)
    broker.fill();row=reconcile_execution(repo,'A',row['id'],broker)
    assert row['state']=='SPREAD_ACTIVE'
    broker.orders=[];broker.fills={}
    repo=ProtectedExecutionRepository(repo.path)
    assert reconcile_execution(repo,'A',row['id'],broker)['state']=='SPREAD_ACTIVE'
    with pytest.raises(PermissionError):repo.get('B',row['id'])
    broker.paper_trading=True
    with pytest.raises(PermissionError):reconcile_execution(repo,'A',row['id'],broker)


def test_conflicting_trade_identity_fails_closed(tmp_path,preview):
    broker=Broker();repo=ProtectedExecutionRepository(tmp_path/'conflict.db')
    row=start_execution(repo,'A','key',preview,'LIVE',broker,lambda _:None)
    broker.fill()
    original=broker.fills['1'][0]
    broker.fills['1'].append(dict(original,average_price=original['average_price']+1))
    row=reconcile_execution(repo,'A',row['id'],broker)
    assert row['state']=='RECONCILIATION_REQUIRED'
    assert pair_pnl(row,{},NOW)['gross_pnl'] is None


def test_closed_net_requires_complete_actual_charge_coverage():
    r=record();r['state']='CLOSED';r['exit_legs']=[]
    for i,leg in enumerate(r['legs']):
        leg['trades']=[dict(quantity=10,fees=1)]
        r['exit_legs'].append(dict(payload=dict(leg['payload'],transaction_type='SELL' if i==0 else 'BUY'),
            filled=10,average=2 if i==0 else 3,order_id=str(i),trades=[dict(quantity=10,fees=1)]))
    assert pair_pnl(r,{},NOW)['realized_net_pnl']==16
    del r['exit_legs'][0]['trades'][0]['fees']
    assert pair_pnl(r,{},NOW)['realized_net_pnl'] is None
