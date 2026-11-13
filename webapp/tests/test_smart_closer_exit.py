"""Group intent/planner milestone; no broker adapter or network calls."""
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_smart_closer import strategy, quotes_for, NOW
from smart_closer_exit import create_exit_intent, next_exit_actions, deterministic_exit_tag
from smart_closer_repository import SmartCloserRepository


def intent(repo,g):
    return create_exit_intent(repo,'A',g['strategy_group_id'],'PAPER',quotes_for(g,25000),NOW,exit_charges=60,actor='test-admin')


def close_fill(repo,g,leg,qty,oid,status='COMPLETE',order_qty=None):
    side='BUY' if leg['entry_side']=='SELL' else 'SELL'
    repo.register_order('A',g['strategy_group_id'],leg['tradingsymbol'],oid,'EXIT')
    if qty:
        repo.record_fill('A',dict(order_id=oid,trade_id=oid+'fill',quantity=qty,price=100,fees=5,
            filled_at=NOW.isoformat(),tradingsymbol=leg['tradingsymbol'],transaction_type=side))
    return dict(leg_id=leg['leg_id'],purpose='EXIT',side=side,quantity=order_qty or qty or 130,
                filled=qty,status=status,order_id=oid)


def test_intent_is_group_wide_and_restart_idempotent(strategy):
    repo,g,_=strategy;i=intent(repo,g)
    restarted=SmartCloserRepository(repo.db_path)
    assert intent(restarted,g)==i
    snapshot=json.loads(i['snapshot'])
    assert len(snapshot['leg_ids'])==4 and len(snapshot['pairs'])==2
    assert snapshot['capital']==200000
    result=next_exit_actions(repo.groups('A','PAPER')[0],i,[])
    assert len(result['actions'])==2 and all(a['side']=='BUY' for a in result['actions'])
    with repo.connect() as db:
        assert db.execute('SELECT count(*) FROM smart_exit_intents').fetchone()[0]==1


def test_concurrent_intents_share_one_claim(strategy):
    repo,g,_=strategy
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:intent(SmartCloserRepository(repo.db_path),g),range(2)))
    assert results[0]==results[1]


def test_losing_group_cannot_create_intent(strategy):
    repo,g,_=strategy
    with pytest.raises(PermissionError):
        create_exit_intent(repo,'A',g['strategy_group_id'],'PAPER',quotes_for(g,16000),NOW,exit_charges=60,actor='admin')
    with repo.connect() as db:assert db.execute('SELECT count(*) FROM smart_exit_intents').fetchone()[0]==0


def test_partial_short_releases_only_matched_hedge(strategy):
    repo,g,_=strategy;i=intent(repo,g)
    short=next(l for l in g['strategy']['legs'] if l['entry_side']=='SELL' and l['option_type']=='CE')
    order=close_fill(repo,g,short,65,'S1','PARTIAL',130)
    result=next_exit_actions(repo.groups('A','PAPER')[0],i,[order])
    sells=[a for a in result['actions'] if a['side']=='SELL']
    assert len(sells)==1 and sells[0]['quantity']==65
    assert len([a for a in result['actions'] if a['side']=='BUY'])==1
    assert result['state']=='PARTIAL_GROUP_EXIT'


def test_pending_hedge_sale_is_reserved(strategy):
    repo,g,_=strategy;i=intent(repo,g)
    short=next(l for l in g['strategy']['legs'] if l['entry_side']=='SELL' and l['option_type']=='CE')
    hedge=next(l for l in g['strategy']['legs'] if l['entry_side']=='BUY' and l['option_type']=='CE')
    orders=[close_fill(repo,g,short,65,'S1','PARTIAL',130),close_fill(repo,g,hedge,0,'H1','OPEN',65)]
    result=next_exit_actions(repo.groups('A','PAPER')[0],i,orders)
    assert all(a['side']=='BUY' for a in result['actions'])


@pytest.mark.parametrize('status',['REJECTED','CANCELLED','SUBMISSION_UNKNOWN','SUBMITTING'])
def test_failed_or_ambiguous_short_never_releases_hedge(strategy,status):
    repo,g,_=strategy;i=intent(repo,g)
    short=next(l for l in g['strategy']['legs'] if l['entry_side']=='SELL')
    order=close_fill(repo,g,short,0,'S1',status)
    result=next_exit_actions(repo.groups('A','PAPER')[0],i,[order])
    assert not result['actions'] and result['state'] in {'FAILED_SAFE','RECONCILING'}


def test_all_fills_require_final_broker_reconciliation(strategy):
    repo,g,_=strategy;i=intent(repo,g)
    orders=[close_fill(repo,g,l,130,str(n)) for n,l in enumerate(g['strategy']['legs'])]
    result=next_exit_actions(repo.groups('A','PAPER')[0],i,orders)
    assert result['state']=='RECONCILING' and not result['actions']


def test_order_status_without_trade_fills_is_not_confirmation(strategy):
    repo,g,_=strategy;i=intent(repo,g)
    short=next(l for l in g['strategy']['legs'] if l['entry_side']=='SELL')
    order=close_fill(repo,g,short,0,'S1','OPEN');order.update(filled=130,status='COMPLETE')
    assert next_exit_actions(g,i,[order])['state']=='RECONCILING'


def test_wrong_mode_and_stable_tag(strategy):
    repo,g,_=strategy
    with pytest.raises(PermissionError):
        create_exit_intent(repo,'A',g['strategy_group_id'],'LIVE',{},NOW,exit_charges=60,actor='admin')
    tag=deterministic_exit_tag('group','leg',0)
    assert tag==deterministic_exit_tag('group','leg',0) and len(tag)==20 and tag.isalnum()
    assert tag!=deterministic_exit_tag('group','leg',1)


def test_one_wing_closed_does_not_close_group(strategy):
    repo,g,_=strategy;i=intent(repo,g)
    orders=[close_fill(repo,g,l,130,str(n)) for n,l in enumerate(g['strategy']['legs']) if l['option_type']=='CE']
    result=next_exit_actions(repo.groups('A','PAPER')[0],i,orders)
    assert result['state']=='PARTIAL_GROUP_EXIT'
    assert len(result['actions'])==1 and result['actions'][0]['side']=='BUY'


def test_hedge_rejection_retains_residual_long(strategy):
    repo,g,_=strategy;i=intent(repo,g)
    short=next(l for l in g['strategy']['legs'] if l['entry_side']=='SELL' and l['option_type']=='CE')
    hedge=next(l for l in g['strategy']['legs'] if l['entry_side']=='BUY' and l['option_type']=='CE')
    orders=[close_fill(repo,g,short,130,'S1'),close_fill(repo,g,hedge,0,'H1','REJECTED')]
    result=next_exit_actions(repo.groups('A','PAPER')[0],i,orders)
    assert result['state']=='FAILED_SAFE' and not result['actions']


def test_reconciliation_does_not_reset_exit_intent(strategy):
    from smart_closer_engine import reconcile_groups
    repo,g,positions=strategy;intent(repo,g)
    results,_=reconcile_groups([g],positions,[],NOW)
    repo.save_reconciliation('A',results)
    assert repo.groups('A','PAPER')[0]['status']=='CLOSING'
