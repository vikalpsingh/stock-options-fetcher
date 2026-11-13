"""NIFTY dashboard presentation and final entry gates; existing ledgers remain authoritative."""
from decimal import Decimal, InvalidOperation


def monthly_view(snapshot):
    row = snapshot or {}
    result = dict(row, display_state='UNKNOWN', verified=False)
    try:
        used, cap = Decimal(str(row['loss_used'])), Decimal(str(row['max_monthly_loss']))
        source = str(row.get('data_status') or '')
        if not used.is_finite() or not cap.is_finite() or used < 0 or cap <= 0 or not source or 'NO_REALISED_DATA' in source:
            return result
        pct = used/cap*100
        state = 'HARD BLOCK' if row.get('hard_locked') or pct >= 100 else 'RED' if pct >= 75 else 'AMBER' if pct >= 50 else 'GREEN'
        result.update(display_state=state, verified=True, remaining_display=float(max(Decimal(0),cap-used).quantize(Decimal('.01'))))
    except (KeyError, ValueError, TypeError, InvalidOperation):
        pass
    return result


def entry_readiness(context, selected_sides):
    session = context.get('market_session') or {}
    dtv = context.get('dtv') or {}
    monthly = monthly_view(context.get('monthly'))
    if not session.get('new_entries_allowed'):
        return 'MARKET CLOSED' if session.get('status') == 'MARKET_CLOSED' else 'DATA UNAVAILABLE', 'Exchange session: '+session.get('reason','UNKNOWN')
    if (dtv.get('freshness') or {}).get('status') != 'FRESH':
        return 'DATA UNAVAILABLE', 'Fresh spot, completed daily and current intraday data are required.'
    # Recheck cached evidence against the current authorization clock.
    from .directional_trend import timestamp
    try:
        now = timestamp(context.get('now') or session['asof'])
        quote_at = timestamp(dtv['freshness']['quote_timestamp'])
        if not 0 <= (now-quote_at).total_seconds() <= 30:
            return 'DATA UNAVAILABLE', 'Spot quote exceeded the 30-second freshness limit.'
    except (KeyError, ValueError, TypeError):
        return 'DATA UNAVAILABLE', 'Spot quote timestamp unavailable.'
    if not monthly['verified'] or monthly['display_state'] == 'HARD BLOCK':
        return 'RISK BLOCKED', 'Monthly loss ledger is unknown or hard-locked.'
    for side in selected_sides:
        if dtv.get(side.lower()+'_status', 'BLOCK') == 'BLOCK':
            return 'NO TRADE', (dtv.get('reasons') or {}).get(side,'Directional evidence unavailable.')
    return 'READY FOR PREVIEW', 'Direction eligible only; all existing ticket and account checks still apply.'
