"""Position close direction and last-boundary checks; no broker calls on import."""
from functools import wraps
from threading import RLock

_CLOSE_LOCK = RLock()


def serialized_position_close(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        # Both in-process scheduler jobs and manual closes share this boundary.
        with _CLOSE_LOCK:
            return function(*args, **kwargs)
    return wrapped


def key(row):
    return tuple(str(row.get(field) or '').upper() for field in
                 ('exchange', 'tradingsymbol', 'product'))


def bind_close_order(order, position):
    quantity = int(position['quantity'])
    if not quantity or key(order) != key(position):
        raise ValueError('Close order does not match an active position.')
    return {**order, 'transaction_type': 'BUY' if quantity < 0 else 'SELL',
            'quantity': abs(quantity)}


def validate_close_submission(order, positions, pending_orders):
    matches = [p for p in positions if key(p) == key(order)]
    if len(matches) != 1:
        raise ValueError('Close blocked: current position is missing or ambiguous; refresh.')
    expected = bind_close_order(order, matches[0])
    quantity = int(order.get('quantity') or 0)
    if str(order.get('transaction_type') or '').upper() != expected['transaction_type']:
        raise ValueError('Close blocked: order side would increase current position; rebuild preview.')
    if not 0 < quantity <= expected['quantity']:
        raise ValueError('Close blocked: quantity exceeds current remaining position; refresh.')
    # Fail closed on any unresolved order. Do not modify a partially filled order
    # with a remaining quantity interpreted as its original total quantity.
    if any(key(o) == key(order) and str(o.get('status') or '').upper()
           not in {'COMPLETE', 'CANCELLED', 'REJECTED'} for o in pending_orders):
        raise ValueError('Close blocked: outstanding contract order requires reconciliation.')
