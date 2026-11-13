"""Smart closer configuration. Entry/risk-engine configuration is untouched."""
from math import isfinite

DEFAULTS = dict(enabled=False, dry_run=True, broker='ZERODHA', timezone='Asia/Kolkata',
    reconcile_time='09:00', first_profit_scan='09:25', last_profit_scan='15:20',
    scan_interval_minutes=5, profit_target_pct=10.0, min_target_pct=.1, max_target_pct=100.,
    profit_basis='INITIAL_STRATEGY_CAPITAL', max_quote_age_seconds=15,
    max_slippage_pct=1., max_order_retries=2, require_verified_capital=True,
    require_verified_pairs=True, require_complete_strategy_group=True,
    default_iron_condor_exit='FULL_GROUP', allow_independent_wing_profit_exit=False,
    close_short_first=True, confirm_fills_before_hedge_sale=True,
    block_duplicate_exit_orders=True, block_unmatched_positions=True)


def positive(value):
    if isinstance(value, bool):
        raise ValueError('A finite positive number is required.')
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ValueError('A finite positive number is required.')
    return number


def configuration(values=None):
    result = {**DEFAULTS, **(values or {})}
    if set(result)-set(DEFAULTS):
        raise ValueError('Unknown smart closer setting.')
    for key in ('enabled', 'dry_run'):
        if type(result[key]) is not bool:
            raise ValueError(key+' must be a boolean.')
    for key in ('broker','timezone','profit_basis','require_verified_capital','require_verified_pairs',
                'require_complete_strategy_group','default_iron_condor_exit',
                'allow_independent_wing_profit_exit','close_short_first','confirm_fills_before_hedge_sale',
                'block_duplicate_exit_orders','block_unmatched_positions'):
        if type(result[key]) is not type(DEFAULTS[key]) or result[key] != DEFAULTS[key]:
            raise ValueError('Mandatory smart closer policy: '+key)
    for key in ('profit_target_pct','min_target_pct','max_target_pct','max_quote_age_seconds',
                'max_slippage_pct','scan_interval_minutes'):
        result[key] = positive(result[key])
    if not result['min_target_pct'] <= result['profit_target_pct'] <= result['max_target_pct'] <= 100:
        raise ValueError('Profit target is outside the configured safe range.')
    if result['scan_interval_minutes'] != int(result['scan_interval_minutes']):
        raise ValueError('Scan interval must be whole minutes.')
    if type(result['max_order_retries']) is not int or not 0 <= result['max_order_retries'] <= 2:
        raise ValueError('Retries must be between zero and two.')
    from datetime import datetime
    for key in ('reconcile_time','first_profit_scan','last_profit_scan'):
        value=result[key]
        if datetime.strptime(value,'%H:%M').strftime('%H:%M') != value:
            raise ValueError('Schedule must use HH:MM.')
    if not result['reconcile_time'] < result['first_profit_scan'] <= result['last_profit_scan']:
        raise ValueError('Invalid scheduler time ordering.')
    return result
