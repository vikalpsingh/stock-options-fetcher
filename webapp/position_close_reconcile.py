"""Durable daily close intent shared by both jobs; no runtime I/O on import."""
import json
import sqlite3
from position_close_safety import key, bind_close_order


def plan_close(order, positions, orders):
    matches = [p for p in positions if key(p) == key(order)]
    if len(matches) != 1:
        raise ValueError('Current position missing or ambiguous; reconcile.')
    target = bind_close_order(order, matches[0])
    if target['transaction_type'] != order['transaction_type']:
        raise ValueError('Position direction changed; rebuild close preview.')
    active = [o for o in orders if key(o) == key(order) and str(o.get('status') or '').strip().upper() not in {'COMPLETE','CANCELLED','REJECTED'}]
    if not active:
        return 'PLACE', target, None
    if len(active) != 1:
        raise ValueError('Multiple outstanding contract orders; reconcile duplicates before closing.')
    current = active[0]
    if current.get('transaction_type') != target['transaction_type']:
        raise ValueError('Opposite-side outstanding order requires reconciliation.')
    filled = int(current.get('filled_quantity') or 0)
    pending = int(current['pending_quantity']) if current.get('pending_quantity') is not None else int(current['quantity'])-filled
    if pending == target['quantity']:
        return 'SKIP', target, current
    if current.get('status') != 'OPEN' or current.get('order_type') != 'LIMIT':
        raise ValueError('Quantity mismatch on non-OPEN LIMIT order; reconcile before modifying.')
    target['quantity'] += filled  # Kite modification quantity is total, not remaining.
    return 'MODIFY', target, current


def execute_close(kite, order, db_path, account, day, reprice):
    intent = json.dumps([account, day, *key(order)])
    with sqlite3.connect(str(db_path), timeout=15) as db:
        db.execute('CREATE TABLE IF NOT EXISTS close_intents (id TEXT PRIMARY KEY, order_id TEXT)')
        db.execute('BEGIN IMMEDIATE')
        prior = db.execute('SELECT order_id FROM close_intents WHERE id=?',(intent,)).fetchone()
        book = kite.orders()
        if prior:
            known = [o for o in book if str(o.get('order_id')) == prior[0]]
            if not known or known[0].get('status') == 'COMPLETE':
                raise ValueError('Previous close submission requires reconciliation; no automatic retry.')
            if known[0].get('status') not in {'CANCELLED','REJECTED'}:
                pass
        action, target, existing = plan_close(order, kite.positions()['net'], book)
        if action == 'SKIP':
            return 'SKIPPED_EXISTING', str(existing['order_id']), 'Matching pending close quantity preserved.'
        target = reprice(target)
        db.execute('INSERT OR REPLACE INTO close_intents VALUES (?,NULL)',(intent,))
        db.commit()  # Persist before broker call: timeout/restart must never blindly retry.
        if action == 'MODIFY':
            oid = str(existing['order_id'])
            kite.modify_order(variety=existing.get('variety') or 'regular',order_id=oid,
                              quantity=target['quantity'],price=target['price'],order_type='LIMIT')
        else:
            payload = dict(target)
            variety = payload.pop('variety','regular')
            oid = str(kite.place_order(variety=variety, **payload))
        db.execute('UPDATE close_intents SET order_id=? WHERE id=?',(oid,intent))
        return 'LIVE_SENT', oid, action.lower() + '; broker acceptance is not fill confirmation.'
