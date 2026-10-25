"""Small integration seam with existing HTTP UI, never an execution service."""
from .config import enabled


def handle(action,form,account,path,rows,settings=None):
    if not enabled(settings=settings):raise PermissionError('Investing v2 is disabled. Enable it in Kite Setup and save.')
    get=lambda key: str((form.get(key) or [''])[0])
    if action=='/investing/import':
        if get('invest_identity_ack')!='yes':raise ValueError('Verify the evidence source and ISIN mapping before import.')
        from .repository import InvestingRepository
        from .service import import_fundamentals
        count=import_fundamentals(InvestingRepository(path),account,get('invest_evidence'),get('invest_format'),settings=settings)
        return f'Imported {count} observations. Re-evaluate to apply changes.'
    if action=='/investing/evaluate':
        from .jobs import submit
        symbol=get('invest_symbol')
        if symbol and symbol not in {r.get('symbol') for r in rows}:raise ValueError('Select a configured stock.')
        submit(path,account,rows,selected={symbol} if symbol else None,ai=get('invest_ai')=='yes')
        return 'Research queued. Refresh progress to view per-stock results. No orders are submitted.'
    raise ValueError('Unsupported research action.')
