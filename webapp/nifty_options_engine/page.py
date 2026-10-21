"""NIFTY 2.0 page orchestration; dependencies supplied by the existing app."""
from datetime import datetime, timedelta, timezone

from .ticket import build_ticket, quote_values
from .service import persist_review, sync_execution_fills, approve_entry, approve_exit
from .ledger import NiftyStrategyRepository
from .analytics import monthly_analytics
from .risk_validator import calculate_nifty_portfolio_risk
from trade_protected_execution import (ProtectedExecutionRepository, submit_basket_hedges,
    reconcile_basket, confirm_basket_shorts, submit_basket_exit)
from trade_environment import require_test_safe_execution


def selection_from_form(form):
    get = lambda key, default='': str((form.get(key) or [default])[0])
    return dict(include_pe=get('structure', 'PE') in {'PE', 'BOTH'},
                include_ce=get('structure', 'PE') in {'CE', 'BOTH'}, lots=get('lots', '2'),
                expiry=get('expiry'), short_pe=get('short_pe'), hedge_pe=get('hedge_pe'),
                short_ce=get('short_ce'), hedge_ce=get('hedge_ce'), mode=get('mode', 'PAPER'))


def execute_action(path, form, account, db_path, config, context_loader, broker_factory, test_mode=False):
    """Only a persisted review authorizes actions; browser prices are ignored."""
    get = lambda key, default='': str((form.get(key) or [default])[0])
    if path == '/nifty-2/review':
        selection = selection_from_form(form)
        context = context_loader(selection)
        ticket = build_ticket(selection, context, config)
        if not ticket['eligible']:
            return None, ticket
        return persist_review(db_path, account, ticket), ticket
    repo = ProtectedExecutionRepository(db_path)
    record = repo.get(account, get('execution_id'))
    if record.get('kind') != 'BASKET':
        raise PermissionError('This execution does not belong to NIFTY 2.0.')
    require_test_safe_execution(record['mode'], test_mode)
    if record['mode'] == 'LIVE':
        if path != '/nifty-2/reconcile' and get('live_ack') != 'PLACE LIVE ORDERS':
            raise PermissionError('Type PLACE LIVE ORDERS to confirm a real broker submission.')
        current = context_loader(record['preview']['selection'])
        if path != '/nifty-2/reconcile' and not current.get('live_ack_enabled'):
            raise PermissionError('Enable the existing Kite live-order acknowledgement in Kite Setup.')
        if (not current.get('session_fingerprint') or current['session_fingerprint'] !=
                record['preview'].get('session_fingerprint')):
            raise PermissionError('Broker account changed since review. Build a new review.')
    broker = broker_factory(record['mode'])
    ack = get('ack') == 'yes'

    def validate(current, stage):
        sync_execution_fills(db_path, current)
        context = context_loader(current['preview']['selection'])
        if current['mode'] == 'LIVE' and (not context.get('live_ack_enabled') or
                context.get('session_fingerprint') != current['preview'].get('session_fingerprint')):
            raise PermissionError('Broker account or live acknowledgement changed since review.')
        if stage.startswith('EXIT'):
            return approve_exit(current, context, close_hedges=stage == 'EXIT_HEDGES')
        return approve_entry(current, context, config)

    if path == '/nifty-2/start':
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(record['reviewed_at'])).total_seconds()
        if age < config['countdown_seconds']:
            raise PermissionError('The configured review countdown has not finished.')
        record = submit_basket_hedges(repo, account, record['id'], broker, validate, ack)
    elif path == '/nifty-2/reconcile':
        record = reconcile_basket(repo, account, record['id'], broker)
    elif path == '/nifty-2/confirm-sell':
        record = confirm_basket_shorts(repo, account, record['id'], broker, validate, ack)
    elif path in {'/nifty-2/close-shorts', '/nifty-2/close-hedges'}:
        record = reconcile_basket(repo, account, record['id'], broker)
        close_hedges = path.endswith('close-hedges')
        prices = validate(record, 'EXIT_HEDGES' if close_hedges else 'EXIT_SHORTS')
        record = submit_basket_exit(repo, account, record['id'], broker, validate, prices, ack, close_hedges)
    else:
        raise ValueError('Unknown NIFTY execution action.')
    sync_execution_fills(db_path, record)
    return record, record['preview']


def page_data(account, db_path, config, context_loader, form=None):
    form = form or {}
    selection = selection_from_form(form)
    context = context_loader(selection)
    master = [row for row in context['instruments'] if row.get('name') == 'NIFTY'
              and row.get('instrument_type') in {'PE', 'CE'}
              and str(row.get('expiry'))[:10] > context['now'].date().isoformat()]
    expiries = sorted({str(row['expiry'])[:10] for row in master})
    if not selection['expiry'] and expiries:
        preferred = [expiry for expiry in expiries if config['preferred_entry_dte_min'] <=
                     (datetime.fromisoformat(expiry).date() - context['now'].date()).days <= config['preferred_entry_dte_max']]
        selection['expiry'] = (preferred or expiries)[0]
    spot = float(context.get('spot') or 0)
    for kind in ('PE', 'CE'):
        contracts = sorted([row for row in master if row['instrument_type'] == kind
                            and str(row['expiry'])[:10] == selection['expiry']], key=lambda row: float(row['strike']))
        if contracts and not selection['short_' + kind.lower()]:
            target = spot * (.98 if kind == 'PE' else 1.02)
            short = min(contracts, key=lambda row: abs(float(row['strike']) - target))
            selection['short_' + kind.lower()] = short['tradingsymbol']
            target = float(short['strike']) + config['default_hedge_width_points'] * (-1 if kind == 'PE' else 1)
            eligible = [row for row in contracts if (float(row['strike']) - float(short['strike'])) * (-1 if kind == 'PE' else 1) > 0]
            if eligible:
                selection['hedge_' + kind.lower()] = min(eligible, key=lambda row: abs(float(row['strike']) - target))['tradingsymbol']
    context = context_loader(selection)
    ledger = NiftyStrategyRepository(db_path)
    ledger.ensure_schema()
    month = str((form.get('month') or [context['now'].strftime('%Y-%m')])[0])
    marks = {key.removeprefix('NFO:'): quote_values(value) for key, value in context['quotes'].items()}
    return dict(account=account, selection=selection, context=context, instruments=master, expiries=expiries,
                ticket=build_ticket(selection, context, config), config=config,
                executions=ProtectedExecutionRepository(db_path).recent_baskets(account),
                risk=calculate_nifty_portfolio_risk(context['positions'], config=config,
                     strategy_allocations=context['allocations'], pending_orders=context['orders']),
                analytics=monthly_analytics(ledger.strategies(account, selection['mode']), month, marks))
