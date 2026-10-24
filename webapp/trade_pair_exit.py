"""Adapt terminal TRADE entry fills to the existing durable basket exit lifecycle."""
from datetime import datetime, timezone
from trade_protected_execution import reconcile_execution, reconcile_basket, submit_basket_exit, basket_remaining
from app_time import is_quote_fresh
from nifty_options_engine.ticket import depth_limit


def prepare_pair_exit(repo, account, eid, broker):
    record=repo.get(account,eid)
    if record.get('kind')=='TRADE_PAIR':
        return reconcile_basket(repo,account,eid,broker)
    record=reconcile_execution(repo,account,eid,broker)
    terminal={'COMPLETE','CANCELLED','REJECTED','NOT_SUBMITTED'}
    if record['hedge_status'] not in terminal or record['short_status'] not in terminal:
        raise PermissionError('Entry orders are pending or uncertain. Reconcile/cancel them before closing.')
    if record['state']=='RECONCILIATION_REQUIRED':
        raise PermissionError('Resolve broker fill identity before closing.')
    legs=[]
    for p,prefix,oid,tag in zip(record['preview']['order_payloads'],('hedge','short'),
            ('hedge_order_id','sell_order_id'),('hedge_tag','short_tag')):
        leg=dict(payload=p,filled=record[prefix+'_filled'],average=record.get(prefix+'_average_price',0),
                 status=record[prefix+'_status'],order_id=record[oid],tag=record[tag])
        # Existing reconciler has already verified these full fills against broker trades.
        if leg['status']=='COMPLETE': leg['trades']=[]
        legs.append(leg)
    record.update(kind='TRADE_PAIR',legs=legs,state='OPEN' if all(x['status']=='COMPLETE' for x in legs) else 'RECOVERY_READY')
    return repo.save(record)


def exit_prices(record, broker, now=None):
    legs=record['legs']
    quotes=broker.get_quote(['NFO:'+x['payload']['tradingsymbol'] for x in legs])
    now=now or datetime.now(timezone.utc)
    positions=broker.get_positions().get('net',[]) if record['mode']=='LIVE' else []
    orders=broker.get_orders() if record['mode']=='LIVE' else []
    prices={}
    for leg in legs:
        remaining=basket_remaining(record,leg)
        if remaining<=0:continue
        p=leg['payload'];symbol=p['tradingsymbol'];side='BUY' if p['transaction_type']=='SELL' else 'SELL'
        if any(o.get('tradingsymbol')==symbol and o.get('status') not in {'COMPLETE','CANCELLED','REJECTED'} for o in orders):
            raise PermissionError('Conflicting pending order for '+symbol+'. Cancel it explicitly in Modify / Cancel, then reconcile; no duplicate close submitted.')
        if record['mode']=='LIVE':
            qty=sum(int(x.get('quantity') or 0) for x in positions if x.get('tradingsymbol')==symbol and x.get('product')==p['product'] and x.get('exchange')==p['exchange'])
            if qty*(1 if side=='SELL' else -1)<remaining:
                raise PermissionError('Broker position does not cover remaining pair quantity.')
        quote=quotes.get('NFO:'+symbol,{})
        depth=depth_limit(quote,side,remaining)
        if not is_quote_fresh(quote,120,now) or depth['shortfall'] or not depth['limit']:
            raise PermissionError('Fresh executable depth required for '+symbol)
        prices[symbol]=depth['limit']
    return prices,quotes


def close_pair(repo,account,eid,broker,acknowledged=False):
    record=prepare_pair_exit(repo,account,eid,broker)
    if not acknowledged:raise PermissionError('Separate close confirmation is required.')
    prices,_=exit_prices(record,broker)
    accepted=(record.get('close_review') or {}).get('prices') or {}
    for leg in record['legs']:
        symbol=leg['payload']['tradingsymbol']
        if symbol not in prices:continue
        old=accepted.get(symbol)
        if old is None or (prices[symbol]>old if leg['payload']['transaction_type']=='SELL' else prices[symbol]<old):
            raise PermissionError('Exit price worsened; refresh the close preview and confirm again.')
    return submit_basket_exit(repo,account,eid,broker,
        lambda current,stage:exit_prices(current,broker)[0],prices,acknowledged=True,
        close_hedges=record['state']=='SHORT_CLOSED_HEDGE_OPEN')
