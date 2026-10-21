from copy import deepcopy
from datetime import datetime, timezone
from nifty_options_engine.reconciliation import reconcile_nifty_hedge_allocations


def positions():
    base = dict(account_id='A', expiry='2026-11-17', option_type='PE', average_price=100, product='NRML')
    return [dict(base, tradingsymbol='NIFTY_SHORT', strike=22000, quantity=-195),
            dict(base, tradingsymbol='NIFTY_LONG', strike=21700, quantity=130),
            dict(base, tradingsymbol='NIFTY_CALL', strike=24000, option_type='CE', quantity=260)]


def test_partial_suggestion_reserves_long():
    result = reconcile_nifty_hedge_allocations(positions(), [])
    short,long,call = result['positions']
    assert short['hedge_status']=='PARTIALLY_HEDGED'
    assert short['matched_hedge_qty']==130 and short['unmatched_short_qty']==65
    assert short['confirmed_hedge_qty']==0
    assert long['free_long_qty']==0 and long['reserved_long_qty']==130
    assert call['free_long_qty']==260
    assert result['confirmation_required']


def test_cannot_reuse_suggested_hedge():
    rows = positions()
    rows.append(dict(rows[0], tradingsymbol='NIFTY_SHORT2', strike=22100, quantity=-130))
    result = reconcile_nifty_hedge_allocations(rows, [])
    assert sum(row['matched_hedge_qty'] for row in result['positions'])==130


def test_expiry_and_account_segregated():
    rows = positions(); rows[1]['expiry']='2026-11-24'
    assert reconcile_nifty_hedge_allocations(rows, [])['positions'][0]['matched_hedge_qty']==0
    rows[1]['expiry']=rows[0]['expiry']; rows[1]['account_id']='B'
    assert reconcile_nifty_hedge_allocations(rows, [])['positions'][0]['matched_hedge_qty']==0


def test_persisted_allocations_have_priority():
    rows = positions()
    allocations = [dict(rows[0], quantity=-130, strategy_id='S', allocation_id='a',fill_ids=['f1']),
                   dict(rows[1], strategy_id='S', allocation_id='b',fill_ids=['f2'])]
    result = reconcile_nifty_hedge_allocations(rows, allocations)
    assert result['positions'][0]['confirmed_hedge_qty']==130
    assert result['positions'][1]['allocated_long_qty']==130
    assert result['positions'][1]['free_long_qty']==0


def test_reserved_other_strategy_not_reassigned():
    rows = positions()
    allocation = dict(rows[1], strategy_id='OTHER', allocation_id='a',fill_ids=['f1'])
    result = reconcile_nifty_hedge_allocations(rows, [allocation])
    assert result['positions'][0]['matched_hedge_qty']==0
    assert result['positions'][1]['free_long_qty']==0


def test_pending_hedge_disposal_blocks_availability():
    rows = positions()
    orders = [dict(rows[1],transaction_type='SELL',status='OPEN')]
    result = reconcile_nifty_hedge_allocations(rows, [], orders)
    assert result['positions'][1]['free_long_qty']==0
    assert result['positions'][1]['hedge_status']=='UNKNOWN'


def test_opening_cash_is_not_pnl():
    # Extract this pure helper only: never import app.py or its scheduler/database.
    from pathlib import Path
    source=Path('app.py').read_text(encoding='utf-8-sig')
    source=source[source.index('def _nifty_position_action_pnl_projection('):source.index('def build_hedge_repair_candidate(')]
    namespace={'Any':object,'_nifty_leg_float':lambda row,key:float(row.get(key) or 0)}
    exec(compile(source,'pnl_helper','exec'),namespace)
    result=namespace['_nifty_position_action_pnl_projection']({'pnl':1183},'SELL_AGAINST_LONG',14469)
    assert result['current_pnl']==1183 and result['limit_cash_flow']==14469
    assert result['projected_pnl_after_limit'] is None


def test_management_table_and_single_ticket():
    from nifty_options_engine.ui import active_positions_section
    data=dict(active_positions=reconcile_nifty_hedge_allocations(positions(),[]),
        context={'quotes':{},'now':datetime.now(timezone.utc)},selection={'mode':'LIVE'},
        risk={'current_defined_max_loss':None},config={'max_total_nifty_defined_loss_inr':60000},executions=[])
    html=active_positions_section(data)
    assert html.count('>Manage</button>')==3
    assert 'Suggested Hedge Match' in html and 'Qty -195' in html
    assert 'independent hedge disposal are blocked' in html
    assert 'No durable execution record' in html
