"""Isolated smart closer tests: temporary SQLite, synthetic fills, no broker network."""
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from smart_closer_config import configuration
from smart_closer_repository import SmartCloserRepository
from smart_closer_engine import evaluate_group, reconcile_groups, scan_due, released_hedge_quantity

NOW=datetime(2026,11,6,10,0,tzinfo=ZoneInfo('Asia/Kolkata'))


@pytest.fixture
def strategy(tmp_path):
    repo=SmartCloserRepository(tmp_path/'smart.db');repo.ensure_schema()
    legs=[]
    for side, strike, direction, price in [('CE',25000,'SELL',250),('CE',25300,'BUY',50),('PE',24000,'SELL',250),('PE',23700,'BUY',50)]:
        legs.append(dict(name='NIFTY',tradingsymbol=f'NIFTY{strike}{side}',option_type=side,
            instrument_type=side,strike=strike,expiry='2026-11-24',quantity=130,lot_size=65,
            instrument_token=strike,exchange='NFO',product='NRML',transaction_type=direction,tick_size=.05))
    sid=repo.create_strategy('A','ENTRY1','IRON_CONDOR',legs,'PAPER')
    repo.register('A',sid,'PAPER')
    for i,(leg,price) in enumerate(zip(legs,[250,50,250,50])):
        order=f'O{i}'
        repo.register_order('A',sid,leg['tradingsymbol'],order)
        repo.record_fill('A',dict(order_id=order,trade_id=f'T{i}',quantity=130,price=price,fees=10,
            filled_at=NOW.isoformat(),tradingsymbol=leg['tradingsymbol'],transaction_type=leg['transaction_type']))
    repo.verify_capital('A',sid,'PAPER',200000,'MANUAL_VERIFIED',actor='test-admin',evidence='fixture allocation')
    group=repo.groups('A','PAPER')[0]
    positions=[{**l,'quantity':130 if l['transaction_type']=='BUY' else -130} for l in legs]
    results,_=reconcile_groups([group],positions,[],NOW);repo.save_reconciliation('A',results)
    return repo,repo.groups('A','PAPER')[0],positions


def quotes_for(group, profit):
    # Entry gross credit 52000; desired open gross profit supplied explicitly.
    short_price=250-profit/260
    out={}
    for leg in group['strategy']['legs']:
        price=short_price if leg['entry_side']=='SELL' else 50
        out['NFO:'+leg['tradingsymbol']]=dict(timestamp=NOW.isoformat(),depth=dict(
            buy=[dict(price=price,quantity=1000)],sell=[dict(price=price,quantity=1000)]))
    return out


def evaluate(group,profit,**kwargs):
    # Effectively zero slippage for arithmetic fixtures; production default remains 1%.
    return evaluate_group(group,quotes_for(group,profit),NOW,
        config=configuration({'max_slippage_pct':.00000001}),estimated_exit_charges=60,**kwargs)


def test_registration_restart_pairs_and_modes(strategy):
    repo,g,_=strategy
    restarted=SmartCloserRepository(repo.db_path);restarted.ensure_schema()
    restarted.register('A',g['strategy_group_id'],'PAPER')
    assert len(restarted.groups('A','PAPER'))==1
    assert len(restarted.groups('A','PAPER')[0]['pairs'])==2
    assert len(g['strategy']['legs'])==4
    assert not restarted.groups('B','PAPER') and not restarted.groups('A','LIVE')


@pytest.mark.parametrize('gross,decision',[(16100,'HOLD'),(20101,'EXIT_ELIGIBLE'),(21100,'EXIT_ELIGIBLE'),(20050,'HOLD')])
def test_capital_target_net_profit(strategy,gross,decision):
    _,g,_=strategy
    result=evaluate(g,gross)
    assert result['target_amount']==20000
    assert result['estimated_net_profit']==pytest.approx(gross-100,abs=.001)
    assert result['return_pct']==pytest.approx((gross-100)/2000,abs=.001)
    assert result['decision']==decision


def test_impossible_target_and_missing_capital(strategy):
    _,g,_=strategy
    g['target_pct']=30;g['target_locked']=1
    assert evaluate(g,25000)['reasons']==['TARGET UNREACHABLE']
    g['capital_verified']=0
    assert evaluate(g,25000)['reasons']==['CAPITAL_UNVERIFIED']


def test_capital_frozen_version_and_target_override(strategy):
    repo,g,_=strategy;sid=g['strategy_group_id']
    with pytest.raises(ValueError,match='frozen'):
        repo.verify_capital('A',sid,'PAPER',300000,'MANUAL_VERIFIED',actor='admin',evidence='changed')
    repo.set_target('A',sid,8,actor='admin')
    repo.save_config('A',{'profit_target_pct':15},actor='admin')
    updated=repo.groups('A','PAPER')[0]
    assert updated['capital']==200000
    assert evaluate_group(updated,quotes_for(updated,16101),NOW,config=repo.config('A'),estimated_exit_charges=60)['target_amount']==16000
    with repo.connect() as db:
        assert db.execute('SELECT count(*) FROM smart_closer_audit').fetchone()[0]>=3


@pytest.mark.parametrize('wing',['CE','PE'])
def test_winning_wing_never_exits_independently(strategy,wing):
    _,g,_=strategy;q=quotes_for(g,0)
    # Winning wing +26000, losing wing -13000 => combined 13000 before costs.
    for leg in g['strategy']['legs']:
        if leg['entry_side']=='SELL':
            price=50 if leg['option_type']==wing else 350
            q['NFO:'+leg['tradingsymbol']]['depth']={'buy':[dict(price=price,quantity=1000)],'sell':[dict(price=price,quantity=1000)]}
    result=evaluate_group(g,q,NOW,estimated_exit_charges=60)
    assert result['decision']=='HOLD' and result['estimated_net_profit']<13000
    assert len(result['exit_prices'])==4


def test_partial_realized_once_and_duplicate_fill(strategy):
    repo,g,_=strategy;leg=next(l for l in g['strategy']['legs'] if l['entry_side']=='SELL')
    repo.register_order('A',g['strategy_group_id'],leg['tradingsymbol'],'EXIT1','EXIT')
    fill=dict(order_id='EXIT1',trade_id='C1',quantity=65,price=100,fees=5,filled_at=NOW.isoformat(),tradingsymbol=leg['tradingsymbol'],transaction_type='BUY')
    repo.record_fill('A',fill);repo.record_fill('A',fill)
    g=repo.groups('A','PAPER')[0]
    result=evaluate_group(g,quotes_for(g,0),NOW,estimated_exit_charges=60)
    assert result['realized_gross']==9750
    assert result['actual_charges']==45
    assert result['unrealized_gross']==0


@pytest.mark.parametrize('fault',['position','pending','hedge','expired'])
def test_reconciliation_blocks_unsafe_allocations(strategy,fault):
    _,g,positions=strategy;orders=[]
    if fault=='position': positions[0]['quantity']=-65
    if fault=='hedge': positions[1]['quantity']=0
    if fault=='pending': orders=[{**positions[0],'status':'OPEN'}]
    if fault=='expired':
        for leg in g['strategy']['legs']:leg['expiry']='2026-11-01'
    results,_=reconcile_groups([g],positions,orders,NOW)
    assert results[0]['status']=='REVIEW_REQUIRED'


def test_double_allocated_symbol_detected(strategy):
    _,g,positions=strategy
    other=deepcopy(g);other['strategy_group_id']='other'
    results,_=reconcile_groups([g,other],positions,[],NOW)
    assert all(r['status']=='REVIEW_REQUIRED' for r in results)


def test_quotes_fees_and_failed_reconciliation(strategy):
    repo,g,_=strategy;q=quotes_for(g,25000)
    first=next(iter(q.values()));first['timestamp']=(NOW-timedelta(seconds=16)).isoformat()
    assert evaluate_group(g,q,NOW,estimated_exit_charges=60)['decision']=='BLOCKED'
    assert evaluate_group(g,quotes_for(g,25000),NOW)['decision']=='BLOCKED'
    repo.fail_reconciliation('A','PAPER')
    assert evaluate(repo.groups('A','PAPER')[0],25000)['decision']=='BLOCKED'


@pytest.mark.parametrize('closed,remaining,pending,release',[(0,130,0,0),(65,130,0,65),(65,130,65,0),(65,65,0,0),(130,130,0,130)])
def test_fill_confirmed_hedge_release(closed,remaining,pending,release):
    assert released_hedge_quantity(130,closed,remaining,pending)==release


def test_missing_hedge_and_invalid_config():
    with pytest.raises(ValueError):released_hedge_quantity(130,0,65)
    for config in ({'profit_target_pct':float('nan')},{'profit_target_pct':0},{'close_short_first':False},{'dry_run':'false'}):
        with pytest.raises(ValueError):configuration(config)
    assert configuration()['dry_run'] and not configuration()['enabled']


@pytest.mark.parametrize('hour,minute,due',[(9,15,False),(9,25,True),(9,30,True),(9,31,False),(15,20,True),(15,25,False)])
def test_scan_clock(hour,minute,due):
    cfg=configuration({'enabled':True})
    assert scan_due(NOW.replace(hour=hour,minute=minute),cfg,trading_day=True,authenticated=True)==due
    assert not scan_due(NOW,cfg,trading_day=False,authenticated=True)
    assert not scan_due(NOW,cfg,trading_day=True,authenticated=False)


@pytest.mark.parametrize('side',['CE','PE'])
def test_standalone_pair_and_cross_expiry(tmp_path,side):
    repo=SmartCloserRepository(tmp_path/'pair.db');repo.ensure_schema()
    strike=25000
    legs=[dict(name='NIFTY',tradingsymbol='SHORT'+side,option_type=side,strike=strike,expiry='2026-11-24',quantity=65,lot_size=65,instrument_token=1,transaction_type='SELL'),
          dict(name='NIFTY',tradingsymbol='HEDGE'+side,option_type=side,strike=strike+(300 if side=='CE' else -300),expiry='2026-11-24',quantity=65,lot_size=65,instrument_token=2,transaction_type='BUY')]
    kind='BEAR_CALL_SPREAD' if side=='CE' else 'BULL_PUT_SPREAD'
    sid=repo.create_strategy('A','pair',kind,legs)
    repo.register('A',sid,'PAPER')
    assert len(repo.groups('A','PAPER')[0]['pairs'])==1
    legs[1]['expiry']='2026-12-24'
    with pytest.raises(ValueError):repo.create_strategy('A','bad',kind,legs)


def test_readonly_kite_failure_invalidates_daily_approval(strategy):
    from smart_closer_service import reconcile_strategy_positions
    repo,g,_=strategy
    with repo.connect() as db:
        db.execute("UPDATE nifty_strategies SET mode='LIVE' WHERE strategy_id=?",(g['strategy_group_id'],))
    class Kite:
        def positions(self): raise RuntimeError('mock disconnect')
        def place_order(self,*a,**kw): pytest.fail('No broker writes allowed')
    with pytest.raises(RuntimeError):reconcile_strategy_positions(repo,'A','LIVE',Kite(),NOW)
    assert repo.groups('A','LIVE')[0]['reconciliation_day'] is None


def test_dry_preview_never_receives_broker(strategy):
    from smart_closer_service import preview_strategy_closes
    repo,g,_=strategy
    rows=preview_strategy_closes(repo,'A','PAPER',quotes_for(g,25000),NOW,lambda *args:60)
    assert len(rows)==1 and rows[0]['decision']=='EXIT_ELIGIBLE'
    with repo.connect() as db:
        assert db.execute('SELECT count(*) FROM smart_exit_intents').fetchone()[0]==0


def test_shared_symbol_valid_allocation_and_account_separation(strategy):
    _,g,positions=strategy
    other=deepcopy(g);other['strategy_group_id']='other'
    for row in positions:row['quantity']*=2
    results,_=reconcile_groups([g,other],positions,[],NOW)
    assert all(r['status']=='ACTIVE_VERIFIED' for r in results)
    other['account_id']='B'
    with pytest.raises(ValueError):reconcile_groups([g,other],positions,[],NOW)
