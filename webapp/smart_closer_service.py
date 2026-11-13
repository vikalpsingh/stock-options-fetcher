"""Read-only broker reconciliation and dry-run group evaluation.

This module intentionally has no broker mutation methods. Production worker
activation must remain disabled until shared order ownership and the complete
partial-fill coordinator are integrated and verified.
"""
from datetime import datetime
import logging
from smart_closer_engine import reconcile_groups, evaluate_group
from nifty_options_engine.analytics import strategy_performance

logger=logging.getLogger(__name__)


def reconcile_strategy_positions(repository, account, mode, kite, now):
    repository.ensure_schema()
    if mode!='LIVE':
        raise ValueError('Read-only Kite reconciliation requires the LIVE ledger; PAPER uses injected fixtures.')
    try:
        positions=kite.positions()['net']
        orders=kite.orders()
        trades=kite.trades()
        instruments=kite.instruments('NFO')
        master={r['tradingsymbol']:r for r in instruments}
        groups=repository.groups(account,mode)
        # Import only already registered order IDs; never infer entry ownership.
        with repository.connect() as db:
            known={r[0] for r in db.execute('SELECT order_id FROM nifty_order_events WHERE account_id=?',(account,))}
        for trade in trades:
            if str(trade.get('order_id')) not in known: continue
            stamp=trade.get('fill_timestamp')
            if isinstance(stamp,datetime): stamp=stamp.isoformat()
            repository.record_fill(account,{**trade,'price':trade.get('average_price',trade.get('price')),
                                          'filled_at':stamp,'fees':trade.get('fees')})
        groups=repository.groups(account,mode)
        for group in groups:
            for leg in group['strategy']['legs']:
                row=master.get(leg['tradingsymbol'])
                if not row or str(row.get('expiry'))[:10]!=str(leg['expiry'])[:10] or row.get('instrument_token')!=leg.get('instrument_token'):
                    raise ValueError('Instrument metadata requires reconciliation.')
        results,unmatched=reconcile_groups(groups,positions,orders,now)
        repository.save_reconciliation(account,results)
        return dict(results=results,unmatched=unmatched)
    except Exception:
        repository.fail_reconciliation(account,mode)
        # SDK exceptions can contain credentials/URLs; never log raw messages.
        logger.warning('SMART_CLOSER reconciliation failed; automatic eligibility invalidated')
        raise


def preview_strategy_closes(repository, account, mode, quotes, now, exit_charge_estimator):
    """Read-only decisions using the frozen capital and all required group legs."""
    config=repository.config(account)
    results=[]
    for group in repository.groups(account,mode):
        p=strategy_performance(group['strategy'])
        fees=exit_charge_estimator(group,p,quotes)
        result=evaluate_group(group,quotes,now,config=config,estimated_exit_charges=fees)
        results.append(result)
        logger.info('SMART_CLOSER group=%s decision=%s roi=%s',group['strategy_group_id'],result['decision'],result['return_pct'])
    return results
