"""Per-profile execution-mode preference, expiring at the next IST date."""
from zoneinfo import ZoneInfo


def trading_day(now):
    if now.tzinfo is None:
        raise ValueError('Timezone-aware clock required')
    return now.astimezone(ZoneInfo('Asia/Kolkata')).date().isoformat()


def saved_mode(settings, account, now):
    row = (settings.get('nifty_execution_day_modes') or {}).get(account) or {}
    return row.get('mode') if row.get('day') == trading_day(now) and row.get('mode') in {'PAPER','LIVE'} else 'PAPER'


def mode_update(settings, account, mode, now):
    if mode not in {'PAPER','LIVE'}:
        raise ValueError('Choose PAPER or LIVE')
    rows = dict(settings.get('nifty_execution_day_modes') or {})
    rows[account] = {'day':trading_day(now), 'mode':mode}
    return {'nifty_execution_day_modes':rows}
