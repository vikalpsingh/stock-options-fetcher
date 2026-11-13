"""Durable group exit intent and fill-driven next-action planning.

No broker submissions here. Activation waits for the shared execution worker and
manual/scheduler ownership integration. Existing fill ledger remains authoritative.
"""
import hashlib
import json
from nifty_options_engine.analytics import strategy_performance
from smart_closer_engine import evaluate_group, released_hedge_quantity
from smart_closer_repository import now_text


def create_exit_intent(repo, account, group_id, mode, quotes, now, *, exit_charges, actor):
    """Authorize the entire group once, never a winning wing. Serialized with settings."""
    if not actor:
        raise PermissionError('Explicit authorized actor required.')
    with repo.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        group=next((g for g in repo.groups(account,mode) if g['strategy_group_id']==group_id),None)
        if not group: raise PermissionError('Unknown account/mode-owned group.')
        prior=db.execute('SELECT * FROM smart_exit_intents WHERE strategy_group_id=? AND account_id=?',(group_id,account)).fetchone()
        if prior: return dict(prior)
        decision=evaluate_group(group,quotes,now,config=repo.config(account),estimated_exit_charges=exit_charges)
        if decision['decision']!='EXIT_ELIGIBLE':
            raise PermissionError('Complete strategy is not exit eligible: '+', '.join(decision['reasons'] or [decision['decision']]))
        snapshot=dict(mode=mode,capital_version=group['capital_version'],capital=group['capital'],
            decision=decision,pairs=group['pairs'],leg_ids=sorted(l['leg_id'] for l in group['strategy']['legs']),
            closing_reason='CAPITAL_PROFIT_TARGET',actor=actor)
        stamp=now_text()
        db.execute('INSERT INTO smart_exit_intents VALUES(?,?,?,?,?,?)',
            (group_id,account,'EXIT_INTENT_CREATED',json.dumps(snapshot,allow_nan=False),stamp,stamp))
        db.execute("UPDATE smart_strategy_groups SET status='CLOSING' WHERE strategy_group_id=?",(group_id,))
        repo._audit(db,account,group_id,'EXIT_INTENT_CREATED',actor,snapshot)
        return dict(db.execute('SELECT * FROM smart_exit_intents WHERE strategy_group_id=?',(group_id,)).fetchone())


def next_exit_actions(group, intent, orders):
    """Plan quantities using confirmed ledger fills, reserving pending exit quantity.

    `orders` is a reconciled coordinator snapshot (leg_id, purpose, side, quantity,
    filled, status, order_id). Missing/ambiguous state blocks all new submissions.
    Returned actions are proposals, not order authorization or broker payloads.
    """
    snap=json.loads(intent['snapshot'])
    if (intent['account_id']!=group['account_id'] or intent['strategy_group_id']!=group['strategy_group_id']
            or snap['mode']!=group['strategy']['mode']):
        raise PermissionError('Exit account, group or mode mismatch.')
    if (snap['capital_version']!=group['capital_version'] or snap['pairs']!=group['pairs']
            or snap['leg_ids']!=sorted(l['leg_id'] for l in group['strategy']['legs'])):
        raise PermissionError('Group membership/capital changed after intent.')
    p=strategy_performance(group['strategy']);legs={l['leg_id']:l for l in p['legs']}
    def result(state, reason='', actions=None):
        return dict(state=state,reason=reason,actions=actions or [])
    if any(l['invalid'] or l['entered']!=l['quantity'] for l in legs.values()):
        return result('REVIEW_REQUIRED','Entry allocations are incomplete or invalid.')
    if group['status'] in {'REVIEW_REQUIRED','CAPITAL_UNVERIFIED','HEDGE_MISSING','UNMATCHED','FAILED_SAFE'}:
        return result('REVIEW_REQUIRED','Resolve account/position reconciliation before exit proposals.')
    pending={key:0 for key in legs};seen=set();rejected=False
    for order in orders:
        key=order.get('leg_id');oid=order.get('order_id');status=order.get('status')
        if key not in legs or not oid or oid in seen:
            return result('RECONCILING','Unknown or duplicate order identity.')
        seen.add(oid);leg=legs[key]
        side='BUY' if leg['entry_side']=='SELL' else 'SELL'
        quantity,filled=order.get('quantity'),order.get('filled')
        if (order.get('purpose')!='EXIT' or order.get('side')!=side
            or type(quantity) is not int or type(filled) is not int or not 0<=filled<=quantity or quantity<=0):
            return result('REVIEW_REQUIRED','Exit order side/quantity conflicts with ownership.')
        ledger_filled=sum(f['quantity'] for f in leg['fills'] if f['purpose']=='EXIT' and f['order_id']==oid)
        if ledger_filled!=filled:
            return result('RECONCILING','Order fills and persisted trade allocations disagree.')
        if status in {'SUBMITTING','SUBMISSION_UNKNOWN'} or status not in {'OPEN','PENDING','PARTIAL','COMPLETE','CANCELLED','REJECTED'}:
            return result('RECONCILING','Submission outcome must be reconciled; no blind retry.')
        if status=='COMPLETE' and filled!=quantity:
            return result('RECONCILING','Complete order has inconsistent fill quantity.')
        if status in {'REJECTED','CANCELLED'}:rejected=True
        else:pending[key]+=quantity-filled
    # Every allocated exit must appear in the reconciled snapshot.
    if any(f['order_id'] not in seen for l in legs.values() for f in l['fills'] if f['purpose']=='EXIT'):
        return result('RECONCILING','Missing exit order reconciliation.')
    if any(pending[key]>leg['remaining'] for key,leg in legs.items()):
        return result('FAILED_SAFE','Pending exits exceed remaining owned quantity.')
    if rejected:
        return result('FAILED_SAFE','Rejected/cancelled exit requires review; retain remaining protection.')
    actions=[]
    for pair in group['pairs']:
        short,hedge=legs[pair['short_leg_id']],legs[pair['hedge_leg_id']]
        try:
            released=released_hedge_quantity(short['entered'],short['exited'],hedge['remaining'],pending[hedge['leg_id']])
        except ValueError:
            return result('FAILED_SAFE','Protective allocation is missing or over-reserved.')
        if released:
            actions.append(dict(leg_id=hedge['leg_id'],side='SELL',quantity=released,pair_id=pair['pair_id']))
        remaining=short['remaining']-pending[short['leg_id']]
        if remaining:
            actions.append(dict(leg_id=short['leg_id'],side='BUY',quantity=remaining,pair_id=pair['pair_id']))
    if not any(l['remaining'] for l in legs.values()):
        # Broker net-position reconciliation is still mandatory before CLOSED.
        return result('RECONCILING','All ledger quantities closed; verify broker flatness before CLOSED.')
    partially_closed=any(l['exited'] for l in legs.values())
    state='PARTIAL_GROUP_EXIT' if partially_closed else 'CLOSING_SHORTS'
    if actions and all(a['side']=='SELL' for a in actions):state='CLOSING_HEDGES'
    return result(state,actions=actions)


def deterministic_exit_tag(group_id, leg_id, sequence):
    """20 alphanumeric characters; stable across retries/restarts."""
    if type(sequence) is not int or sequence<0: raise ValueError('Invalid sequence.')
    return 'SC'+hashlib.sha256(f'{group_id}|{leg_id}|{sequence}'.encode()).hexdigest()[:18]
