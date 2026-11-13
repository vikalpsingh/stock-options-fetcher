"""Pure complete-group liquidation valuation; never submits a broker order."""
from collections import defaultdict
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo
from app_time import is_quote_fresh
from nifty_options_engine.analytics import strategy_performance
from nifty_options_engine.ticket import depth_limit
from smart_closer_config import configuration

IST=ZoneInfo('Asia/Kolkata')
TERMINAL={'COMPLETE','CANCELLED','REJECTED'}


def local(now):
    if now.tzinfo is None: raise ValueError('Timezone-aware clock required.')
    return now.astimezone(IST)


def scan_due(now, config, *, trading_day, authenticated):
    config=configuration(config);now=local(now)
    if not config['enabled'] or not authenticated or not trading_day: return False
    start=datetime.strptime(config['first_profit_scan'],'%H:%M').time()
    end=datetime.strptime(config['last_profit_scan'],'%H:%M').time()
    minutes=(now.hour*60+now.minute)-(start.hour*60+start.minute)
    return start<=now.time().replace(tzinfo=None)<=end and minutes%config['scan_interval_minutes']==0


def reconcile_groups(groups, positions, orders, now):
    """One account/mode snapshot. Shared symbols reconcile aggregate allocations.

    Caller must supply all that account's strategy allocations, not only one wing.
    A mismatch blocks every affected group; never allocate netted long/short legs.
    """
    now=local(now)
    identities={(g['account_id'],g['strategy']['mode']) for g in groups}
    if len(identities)>1: raise ValueError('Reconcile one account and execution mode at a time.')
    key=lambda r:(r.get('exchange','NFO'),r['tradingsymbol'],r.get('product','NRML'))
    expected=defaultdict(int); directions=defaultdict(set); actual=defaultdict(int); pending=set()
    performances={}
    for group in groups:
        p=strategy_performance(group['strategy']);performances[group['strategy_group_id']]=p
        for leg in p['legs']:
            if not leg['remaining']: continue
            sign=1 if leg['entry_side']=='BUY' else -1
            expected[key(leg)]+=sign*leg['remaining'];directions[key(leg)].add(sign)
    for row in positions: actual[key(row)]+=int(row.get('quantity') or 0)
    for order in orders:
        if order.get('status') not in TERMINAL: pending.add(key(order))
    all_keys={key(l) for p in performances.values() for l in p['legs']}
    bad={k for k in all_keys if actual[k]!=expected[k] or len(directions[k])>1}
    results=[]
    for group in groups:
        p=performances[group['strategy_group_id']]; reasons=[]
        if any(l['invalid'] or l['entered']!=l['quantity'] for l in p['legs']): reasons.append('Incomplete or inconsistent entry fills')
        if any(key(l) in bad for l in p['legs']): reasons.append('Broker position differs from persisted allocations')
        if any(key(l) in pending for l in p['legs']): reasons.append('Outstanding contract order requires ownership reconciliation')
        by_id={l['leg_id']:l for l in p['legs']}
        for pair in group['pairs']:
            short,hedge=by_id[pair['short_leg_id']],by_id[pair['hedge_leg_id']]
            if short['remaining']>hedge['remaining']: reasons.append('HEDGE_MISSING')
        if any(str(l['expiry'])[:10]<now.date().isoformat() and l['remaining'] for l in p['legs']): reasons.append('Expired position requires review')
        status='REVIEW_REQUIRED' if reasons else 'CAPITAL_UNVERIFIED' if not group['capital_verified'] else 'CLOSED' if p['status']=='FULLY_CLOSED' else 'PARTIALLY_CLOSED' if any(l['exited'] for l in p['legs']) else 'ACTIVE_VERIFIED'
        results.append(dict(strategy_group_id=group['strategy_group_id'],status=status,reasons=reasons,
                            reconciliation_day=now.date().isoformat(),last_checked_at=now.isoformat()))
    unmatched=[k for k,v in actual.items() if v and k not in expected]
    return results, unmatched


def evaluate_group(group, quotes, now, *, config=None, estimated_exit_charges=None):
    config=configuration(config);now=local(now)
    result=dict(strategy_group_id=group['strategy_group_id'],decision='BLOCKED',reasons=[],
                estimated_net_profit=None,return_pct=None,target_amount=None,
                profit_target_pct=group['target_pct'] if group['target_locked'] else config['profit_target_pct'],
                exit_prices={},maximum_net_profit=None,last_checked_at=now.isoformat())
    def block(reason):
        result['reasons'].append(reason)
        return result
    if group['status'] not in {'ACTIVE_VERIFIED','PARTIALLY_CLOSED'} or group['reconciliation_day']!=now.date().isoformat():
        return block('Fresh successful account reconciliation required')
    capital=group['capital']
    if not group['capital_verified'] or not capital or not isfinite(capital) or capital<=0: return block('CAPITAL_UNVERIFIED')
    result['target_amount']=capital*result['profit_target_pct']/100
    if estimated_exit_charges is None or isinstance(estimated_exit_charges,bool) or not isfinite(estimated_exit_charges) or estimated_exit_charges<0:
        return block('Verified exit charge estimate required')
    marks={};slippage=0.
    p=strategy_performance(group['strategy'])
    if p['fees'] is None: return block('Actual entry/completed-fill charges unavailable')
    for leg in p['legs']:
        qty=leg['remaining']
        if leg['invalid'] or qty<0: return block('Invalid quantity allocation')
        if not qty: continue
        quote=quotes.get('NFO:'+leg['tradingsymbol']) or {}
        if not is_quote_fresh(quote,config['max_quote_age_seconds'],now): return block('Stale quote: '+leg['tradingsymbol'])
        side='BUY' if leg['entry_side']=='SELL' else 'SELL'
        depth=depth_limit(quote,side,qty)
        price=depth['limit']
        if depth['shortfall'] or not price or not isfinite(price) or price<=0: return block('Insufficient executable depth: '+leg['tradingsymbol'])
        book=quote.get('depth') or {}
        bid=(book.get('buy') or [{}])[0].get('price');ask=(book.get('sell') or [{}])[0].get('price')
        if not bid or not ask or not 0<bid<=ask: return block('Invalid bid/ask')
        top=ask if side=='BUY' else bid
        if abs(price-top)/top*100>config['max_slippage_pct']: return block('Depth exceeds slippage ceiling')
        marks[leg['tradingsymbol']]={'ask' if side=='BUY' else 'bid':price}
        result['exit_prices'][leg['leg_id']]=price
        slippage+=price*qty*config['max_slippage_pct']/100
    p=strategy_performance(group['strategy'],marks)
    if p['total_net'] is None: return block('Fill-based liquidation P&L unavailable')
    result.update(realized_gross=p['realised_gross'],unrealized_gross=p['open_mtm'],
                  actual_charges=p['fees'],estimated_exit_charges=estimated_exit_charges,
                  slippage_allowance=slippage,initial_net_credit=p['entry_credit'])
    result['estimated_net_profit']=p['total_net']-estimated_exit_charges-slippage
    result['return_pct']=result['estimated_net_profit']/capital*100
    # Conservative attainable credit bound; preserve prior realised exits exactly once.
    remaining_credit=sum((1 if l['entry_side']=='SELL' else -1)*l['average_entry']*l['remaining'] for l in p['legs'])
    result['maximum_net_profit']=p['realised_gross']+remaining_credit-p['fees']-estimated_exit_charges
    if result['target_amount']>result['maximum_net_profit']: return block('TARGET UNREACHABLE')
    result['decision']='EXIT_ELIGIBLE' if result['estimated_net_profit']>=result['target_amount'] else 'HOLD'
    return result


def released_hedge_quantity(short_entered, short_closed, hedge_remaining, hedge_pending=0):
    """Only confirmed short fills release protection; pending hedge sales reserve it."""
    values=(short_entered,short_closed,hedge_remaining,hedge_pending)
    if any(type(q) is not int or q<0 for q in values) or short_closed>short_entered:
        raise ValueError('Invalid confirmed quantities.')
    outstanding_short=short_entered-short_closed
    if hedge_remaining-hedge_pending<outstanding_short:
        raise ValueError('Protection missing or over-reserved; emergency review required.')
    return hedge_remaining-hedge_pending-outstanding_short
