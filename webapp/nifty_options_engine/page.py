"""NIFTY 2.0 page orchestration; dependencies supplied by the existing app."""
from datetime import datetime, timedelta, timezone

from .ticket import build_ticket, quote_values, find_nearby_liquid_spreads, is_hundred_strike, further_otm_contract
from .service import persist_review, sync_execution_fills, approve_entry, approve_exit
from .reconciliation import reconcile_nifty_hedge_allocations
from .ledger import NiftyStrategyRepository
from .analytics import monthly_analytics
from .risk_validator import calculate_nifty_portfolio_risk, get_max_safe_lots
from trade_protected_execution import (ProtectedExecutionRepository, submit_basket_hedges,
    reconcile_basket, confirm_basket_shorts, submit_basket_exit)
from trade_environment import require_test_safe_execution


def selection_from_form(form):
    get = lambda key, default='': str((form.get(key) or [default])[0])
    return dict(include_pe=get('structure', 'PE') in {'PE', 'BOTH'},
                include_ce=get('structure', 'PE') in {'CE', 'BOTH'}, lots=get('lots', '2'),
                expiry=get('expiry'), short_pe=get('short_pe'), hedge_pe=get('hedge_pe'),
                short_ce=get('short_ce'), hedge_ce=get('hedge_ce'), mode=get('mode', 'PAPER'),
                auto_best=get('auto_best', 'yes') == 'yes', base_pe=get('base_pe'), base_ce=get('base_ce'))


def execute_action(path, form, account, db_path, config, context_loader, broker_factory, test_mode=False):
    """Only a persisted review authorizes actions; browser prices are ignored."""
    get = lambda key, default='': str((form.get(key) or [default])[0])
    if path == '/nifty-2/review':
        selection = selection_from_form(form)
        context = context_loader(selection)
        invalidate_changed_lot_reviews(db_path, account, selection)
        ticket = build_ticket(selection, context, config, for_execution=False)
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
        if age > 120:
            raise PermissionError('Review expired after 2 minutes. Refresh details and restart the review.')
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


def invalidate_changed_lot_reviews(db_path, account, selection):
    """Close only unsubmitted reviews; CAS prevents racing an execution claim."""
    repo = ProtectedExecutionRepository(db_path)
    for record in repo.recent_baskets(account):
        old = record['preview'].get('selection') or {}
        if (record['state'] == 'REVIEW' and record['mode'] == selection['mode']
                and any(str(old.get(key)) != str(selection.get(key)) for key in
                    ('lots','expiry','short_pe','hedge_pe','short_ce','hedge_ce','include_pe','include_ce'))):
            record['state'] = 'CLOSED'
            record['note'] = 'Contract, structure or lot selection changed. Create a fresh review and restart the countdown.'
            repo.save(record)


def page_data(account, db_path, config, context_loader, form=None):
    form = form or {}
    selection = selection_from_form(form)
    invalidate_changed_lot_reviews(db_path, account, selection)
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
        for prefix in ('short_', 'hedge_'):
            key = prefix+kind.lower()
            existing = next((row for row in master if row['tradingsymbol']==selection[key]
                and row['instrument_type']==kind and str(row['expiry'])[:10]==selection['expiry']), None)
            if existing and is_hundred_strike(existing):
                continue
            if existing:
                target = float(existing['strike'])
            elif prefix == 'short_':
                target = spot * (.98 if kind=='PE' else 1.02)
            else:
                short = next((row for row in master if row['tradingsymbol']==selection['short_'+kind.lower()]), None)
                if not short:
                    selection[key] = ''
                    continue
                target = float(short['strike']) + config['default_hedge_width_points'] * (-1 if kind=='PE' else 1)
            replacement = further_otm_contract(master, kind, selection['expiry'], target)
            selection[key] = replacement['tradingsymbol'] if replacement else ''
    master = [row for row in master if is_hundred_strike(row)]
    for side in ('pe','ce'):
        if not any(r['tradingsymbol']==selection.get('base_'+side) and str(r['expiry'])[:10]==selection['expiry'] for r in master):
            selection['base_'+side] = selection['short_'+side]
    context = context_loader(selection)
    from .optimizer import optimize_spreads
    optimizer = optimize_spreads(selection, context, config)
    # Reviews/actions keep exact submitted strikes. Only explicit preview refresh (or initial load) auto-selects.
    refresh_action = str((form.get('optimize') or [''])[0])
    auto_refresh = not form.get('short_pe') or refresh_action in {'yes', 'force'}
    if refresh_action in {'yes', 'force'}:
        ProtectedExecutionRepository(db_path).clear_basket_reviews(account=account)
    if (selection['auto_best'] or refresh_action == 'force') and auto_refresh:
        for side in ('PE','CE'):
            row = optimizer['chosen'][side]
            if row is None:
                from .optimizer import maximum_credit_preview
                row = maximum_credit_preview(optimizer['tables'][side])
                if row is not None:
                    optimizer.setdefault('fallback', {})[side] = row
            selection['short_'+side.lower()] = row['short']['tradingsymbol'] if row else ''
            selection['hedge_'+side.lower()] = row['hedge']['tradingsymbol'] if row else ''
        context = context_loader(selection)
    invalidate_changed_lot_reviews(db_path, account, selection)
    ledger = NiftyStrategyRepository(db_path)
    ledger.ensure_schema()
    month = str((form.get('month') or [context['now'].strftime('%Y-%m')])[0])
    marks = {key.removeprefix('NFO:'): quote_values(value) for key, value in context['quotes'].items()}
    ticket = build_ticket(selection, context, config, for_execution=False)
    sizing = get_max_safe_lots(context['positions'], ticket,
        [n for n in config['allowed_lots'] if n <= config['maximum_lots_per_new_trade']],
        config['max_total_nifty_defined_loss_inr'], config=config,
        strategy_allocations=context['allocations'], pending_orders=context['orders'])
    return dict(account=account, selection=selection, context=context, instruments=master, expiries=expiries,
                ticket=ticket, lot_recommendation=sizing, config=config, optimizer=optimizer,
                liquid_alternatives=find_nearby_liquid_spreads(selection, context, config),
                nearer_alternatives=find_nearby_liquid_spreads(selection, context, config, toward_spot=True),
                active_positions=reconcile_nifty_hedge_allocations(context.get("broker_positions",context["positions"]),
                    context.get("broker_allocations",context["allocations"]), context.get("broker_orders",context["orders"])),
                active_positions_mode="LIVE" if "broker_positions" in context else selection['mode'],
                active_positions_risk=calculate_nifty_portfolio_risk(context.get('broker_positions',context['positions']),
                    config=config,strategy_allocations=context.get('broker_allocations',context['allocations']),
                    pending_orders=context.get('broker_orders',context['orders'])),
                executions=ProtectedExecutionRepository(db_path).recent_baskets(account),
                risk=calculate_nifty_portfolio_risk(context['positions'], config=config,
                     strategy_allocations=context['allocations'], pending_orders=context['orders']),
                analytics=monthly_analytics(ledger.strategies(account, selection['mode']), month, marks))
