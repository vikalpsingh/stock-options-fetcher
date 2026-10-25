"""Read-only adapter for configured Investing rows and verified master identities."""
import math
from .schemas import timestamp


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError,ValueError):
        return None


def configured_portfolio(rows, identity_master):
    """Quantities/costs belong to the configured list, not broker holdings."""
    identities = {}
    for item in identity_master:
        key = (item.get('exchange'),item.get('tradingsymbol'))
        if item.get('isin'):
            identities.setdefault(key,set()).add(item['isin'])
    result = []
    for row in rows:
        exchange, _, symbol = str(row.get('quote_key') or '').partition(':')
        matches = identities.get((exchange,symbol),set())
        qty, avg, cmp = (finite(row.get(key)) for key in ('quantity','avg_price','cmp'))
        if qty is not None and qty < 0:qty=None
        if avg is not None and avg < 0:avg=None
        if cmp is not None and cmp <= 0:cmp=None
        market_value = qty*cmp if qty is not None and cmp is not None else None
        result.append(dict(symbol=symbol,exchange=exchange,isin=next(iter(matches)) if len(matches)==1 else None,
            identity_status='VERIFIED' if len(matches)==1 else 'MISSING',quantity=qty,average_cost=avg,
            cmp=cmp,market_value=market_value,sector=row.get('sector'),
            unrealized_pnl=(cmp-avg)*qty if None not in (qty,avg,cmp) else None))
    total = sum(row['market_value'] for row in result) if result and all(row['market_value'] is not None for row in result) else None
    for row in result:
        row['portfolio_weight_pct']=row['market_value']/total*100 if total and row['market_value'] is not None else None
    return result


def adjusted_history_metrics(candles, *, adjusted, as_of):
    """Caller must attest corporate-action adjustment; raw Kite candles are insufficient."""
    keys=('high_52w','low_52w','return_1m_pct','return_3m_pct','return_1y_pct','dma_200')
    result=dict.fromkeys(keys)
    if not adjusted:
        return {**result,'status':'MISSING','reason':'Corporate-action adjusted history unavailable.'}
    cutoff=timestamp(as_of).date()
    by_date={}
    for candle in candles:
        day=timestamp(candle['date']).date()
        close=finite(candle.get('close'));high=finite(candle.get('high'));low=finite(candle.get('low'))
        if day<=cutoff and close is not None and close>0 and high is not None and low is not None and 0<low<=close<=high:
            if day in by_date:raise ValueError('Duplicate historical candle date.')
            by_date[day]=(close,high,low)
    days=sorted(by_date)
    if not days:return {**result,'status':'MISSING','reason':'No valid adjusted observations.'}
    latest=days[-1]
    if (cutoff-latest).days>7:return {**result,'status':'STALE','reason':'Historical series is stale.'}
    from datetime import timedelta
    for name,lag in [('return_1m_pct',30),('return_3m_pct',90),('return_1y_pct',365)]:
        target=latest-timedelta(days=lag)
        earlier=[day for day in days if day<=target and (target-day).days<=7]
        if earlier:result[name]=(by_date[latest][0]/by_date[earlier[-1]][0]-1)*100
    if len(days)>=200:result['dma_200']=sum(by_date[day][0] for day in days[-200:])/200
    if (latest-days[0]).days>=365:
        window=[by_date[day] for day in days if (latest-day).days<=365]
        result.update(high_52w=max(row[1] for row in window),low_52w=min(row[2] for row in window))
    return {**result,'status':'VERIFIED','reason':'Metrics use explicitly adjusted historical candles; insufficient horizons remain null.'}
