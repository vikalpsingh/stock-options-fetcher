from datetime import datetime, timedelta
from math import sin
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_nifty_ticket_service import market

from nifty_options_engine.directional_trend import (
    IST, DTV_CONFIG, completed_candles, efficiency, daily_indicators,
    daily_status, intraday_status, settings, entry_checks)
from nifty_options_engine.directional_market import load_directional_context, historical
from nifty_options_engine.config import income_v2_config


def daily_rows(count=300, direction=0):
    day = datetime(2025,1,1,tzinfo=IST)
    rows=[]
    while len(rows)<count:
        if day.weekday()<5:
            i=len(rows)
            close=22000+30*sin(i*2.3)
            if direction and i>=count-7:
                close=22000*(1+direction*.009*(i-(count-8)))
            rows.append(dict(date=day,open=close-5,high=close+20,low=close-20,close=close,volume=0))
        day+=timedelta(days=1)
    return rows


def bars(now, closes, volume=10):
    return [dict(date=now.replace(hour=9,minute=15,second=0,microsecond=0)+timedelta(minutes=5*i),
                 open=price,high=price+1,low=price-1,close=price,volume=volume) for i,price in enumerate(closes)]


@pytest.mark.parametrize('direction,side',[(1,'ce_status'),(-1,'pe_status')])
def test_persistent_trend_veto_is_causal(direction,side):
    rows=daily_rows(direction=direction)
    points=daily_indicators(rows,DTV_CONFIG)
    assert points[-1][side]=='BLOCK'
    assert points[-1]['er5']>=.7
    assert points[-1]['previous_high']==max(r['close'] for r in rows[-6:-1])
    for size in range(len(rows)-7,len(rows)):
        prefix=daily_indicators(rows[:size],DTV_CONFIG)
        assert prefix[-1]==points[size-100]
    assert any(p[side]=='BLOCK' for p in points[-6:-1])


def test_er_flat_and_wilder_direction():
    assert efficiency([1]*11,10,10)==0
    assert efficiency([1,2,3,4,5,6],5,5)==1
    assert efficiency([1,2],1,5) is None
    rows=daily_rows(direction=1)
    p=daily_indicators(rows,DTV_CONFIG)[-1]
    p.update(adx14=30,plus_di=10,minus_di=40,er5=.1)
    assert daily_status(p,DTV_CONFIG)['pe_status']=='BLOCK'
    assert daily_status(p,DTV_CONFIG)['ce_status']=='ALLOW'
    p.update(adx14=22,previous_adx=21,plus_di=40,minus_di=10)
    assert daily_status(p,DTV_CONFIG)['ce_status']=='CAUTION'
    flat=[dict(r,open=100,close=100,high=100,low=100) for r in rows]
    last=daily_indicators(flat,DTV_CONFIG)[-1]
    assert last['adx14']==last['atr14']==last['er5']==0


def test_daily_and_intraday_completed_only():
    now=datetime(2026,11,6,10,2,tzinfo=IST)
    rows=daily_rows()
    rows.append(dict(rows[-1],date=now,close=1e6,high=1e6))
    assert completed_candles(rows,now,'day')[-1]['date'].date()<now.date()
    intraday=bars(now,[100]*11)
    assert completed_candles(intraday,now,'5minute')[-1]['date'].minute==55
    with pytest.raises(ValueError): daily_indicators(rows[:99],DTV_CONFIG)


@pytest.mark.parametrize('direction,side',[(1,'ce_status'),(-1,'pe_status')])
def test_gap_continuation_and_no_future_opening_range(direction,side):
    now=datetime(2026,11,6,9,40,tzinfo=IST)
    closes=[100+direction*x for x in (1,1.1,1.2,2,3)]
    spot=bars(now,closes,0)
    futures=bars(now,[x+5 for x in closes],100)
    result=intraday_status(spot,futures,100,1,now,DTV_CONFIG)
    assert result[side]=='BLOCK'
    assert 'confirmed' in result['continuation']
    assert result['vwap'] is not None
    opening=now.replace(minute=25)
    early=intraday_status(spot[:2],futures[:2],100,1,opening,DTV_CONFIG)
    assert early[side]=='BLOCK' and 'incomplete' in early['continuation']
    zero=intraday_status(spot,bars(now,closes,0),100,1,now,DTV_CONFIG)
    assert zero['vwap'] is None and zero[side]=='BLOCK'
    # A reversal after confirmation retains the session veto by inspecting prior completed bars.
    reversed_spot=spot+[dict(spot[-1],date=now,open=100,high=101,low=99,close=100)]
    reversed_future=futures+[dict(futures[-1],date=now,open=105,high=106,low=104,close=105)]
    assert 'confirmed' in intraday_status(reversed_spot,reversed_future,100,1,now+timedelta(minutes=5),DTV_CONFIG)['continuation']


class Cache:
    def __init__(self): self.values={}
    def __call__(self,key,fetch,ttl):
        if key not in self.values: self.values[key]=deepcopy(fetch())
        return deepcopy(self.values[key])


@pytest.fixture
def fake_market(monkeypatch):
    import nifty_options_engine.directional_market as module
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    now=datetime(2026,11,6,10,0,tzinfo=IST)
    rows=daily_rows()
    # Align completed fixture with the previous session.
    shift=now.date()-timedelta(days=1)-rows[-1]['date'].date()
    rows=[dict(r,date=r['date']+shift) for r in rows]
    class Kite:
        access_token='mock-session'
        calls=[]
        def historical_data(self,token,start,end,interval):
            self.calls.append((token,interval))
            return rows if interval=='day' else bars(now,[22000+i for i in range(9)],0)
        def quote(self,keys): return {}
        def instruments(self,exchange): return [dict(tradingsymbol='NIFTY 50',exchange='NSE',instrument_token=123)]
    return Kite(),now,dict(timestamp=now.isoformat(),last_price=22008),rows


def test_loader_caches_warmup_and_uses_dynamic_spot(fake_market):
    kite,now,quote,rows=fake_market
    cache=Cache()
    cfg=income_v2_config()
    first=load_directional_context(kite,'A',now,[],quote,cfg,cache,mmi='SELL CALL')
    second=load_directional_context(kite,'A',now,[],quote,cfg,cache,mmi='SELL CALL')
    assert len(first['history'])>=130
    assert first==second
    assert kite.calls==[(123,'day'),(123,'5minute')]
    assert first['intraday']['vwap'] is None


@pytest.mark.parametrize('code',[401,403,429])
def test_kite_errors_fail_closed(fake_market,code):
    kite,now,quote,_=fake_market
    class ApiError(Exception): pass
    error=ApiError('sensitive token must not appear');error.code=code
    def fail(*a,**kw): raise error
    kite.historical_data=fail
    result=load_directional_context(kite,'A',now,[],quote,income_v2_config(),Cache())
    assert result['ce_status']==result['pe_status']=='BLOCK'
    assert 'sensitive' not in str(result)


def test_stale_missing_and_config_off(fake_market):
    kite,now,quote,_=fake_market
    quote['timestamp']=(now-timedelta(minutes=5)).isoformat()
    result=load_directional_context(kite,'A',now,[],quote,income_v2_config(),Cache())
    assert result['ce_status']=='BLOCK'
    assert entry_checks(dict(include_ce=True),dict(now=now),income_v2_config())[0]['status']=='BLOCK'
    cfg=income_v2_config({'directional_trend_veto':{'enabled':False}})
    assert entry_checks(dict(include_ce=True),dict(now=now),cfg)==[]
    with pytest.raises(ValueError): income_v2_config({'directional_trend_veto':{'er_veto_threshold':1.5}})


def test_ticket_veto_preserves_prices_and_cannot_be_overridden_by_mmi(market):
    from nifty_options_engine.ticket import build_ticket
    selection, context, config = market
    baseline = build_ticket(selection, context, config)
    context['dtv'].update(pe_status='BLOCK', mmi_recommendation='SELL PUT')
    blocked = build_ticket(selection, context, config)
    assert not blocked['eligible']
    assert blocked['net_credit'] == baseline['net_credit']
    assert blocked['max_loss'] == baseline['max_loss']
    assert any(c['name']=='Directional Trend Veto PE' and c['status']=='BLOCK' for c in blocked['checks'])


def test_entry_reapproval_and_expired_evidence(tmp_path, market):
    from nifty_options_engine.ticket import build_ticket
    from nifty_options_engine.service import persist_review, approve_entry
    selection, context, config = market
    record = persist_review(tmp_path/'directional.db', 'A', build_ticket(selection, context, config))
    context['dtv']['pe_status'] = 'BLOCK'
    with pytest.raises(PermissionError, match='Directional Trend Veto'):
        approve_entry(record, context, config)
    context['dtv']['pe_status'] = 'ALLOW'
    context['dtv']['valid_until'] = (context['now']-timedelta(seconds=1)).isoformat()
    assert not build_ticket(selection, context, config)['eligible']


def test_caution_requires_full_depth(market):
    from nifty_options_engine.ticket import build_ticket
    selection, context, config = market
    context['dtv']['pe_status'] = 'CAUTION'
    assert build_ticket(selection, context, config)['eligible']
    context['quotes']['NFO:NIFTY22000PE']['depth']['sell'][0]['quantity'] = 1
    assert not build_ticket(selection, context, config)['eligible']


@pytest.mark.parametrize('stage',['start','confirm-sell'])
def test_route_rechecks_veto_before_submission(tmp_path, market, stage):
    from nifty_options_engine.page import execute_action
    from nifty_options_engine.ticket import build_ticket
    from nifty_options_engine.service import persist_review
    from trade_protected_execution import ProtectedExecutionRepository
    from datetime import timezone
    selection, context, config = market
    path=tmp_path/'route.db'
    record=persist_review(path,'A',build_ticket(selection,context,config))
    record['reviewed_at']=(datetime.now(timezone.utc)-timedelta(seconds=12)).isoformat()
    repo=ProtectedExecutionRepository(path)
    repo.save(record)
    from kite_broker_adapter import KiteBrokerAdapter
    broker=KiteBrokerAdapter(paper_trading=True)
    action={'execution_id':[record['id']], 'ack':['yes']}
    loader=lambda _:context
    factory=lambda _:broker
    if stage=='confirm-sell':
        execute_action('/nifty-2/start',action,'A',path,config,loader,factory)
        execute_action('/nifty-2/reconcile',action,'A',path,config,loader,factory)
        from nifty_options_engine.ledger import NiftyStrategyRepository
        context['allocations']=NiftyStrategyRepository(path).position_allocations('A','PAPER')
        context['positions']=deepcopy(context['allocations'])
    context['dtv']['pe_status']='BLOCK'
    broker.place_order=lambda *a,**kw:pytest.fail('Veto must prevent broker submission')
    with pytest.raises(PermissionError, match='Directional Trend Veto'):
        execute_action('/nifty-2/'+stage,action,'A',path,config,loader,factory)
    form={key:[str(value)] for key,value in selection.items()}
    form['structure']=['PE']
    reviewed,ticket=execute_action('/nifty-2/review',form,'A',path,config,loader,factory)
    assert reviewed is None and not ticket['eligible']


def test_intraday_failure_retains_daily_chart_and_safe_reason(fake_market):
    kite,now,quote,_=fake_market
    quote['timestamp']=(now-timedelta(minutes=5)).isoformat()
    result=load_directional_context(kite,'A',now,[],quote,income_v2_config(),Cache())
    assert len(result['history'])>100 and result['adx14'] is not None
    assert result['ce_status']==result['pe_status']=='BLOCK'
    assert 'Current NIFTY spot quote is stale' in result['reasons']['CE']


def test_missing_index_quote_timestamp_uses_completed_history(fake_market):
    kite,now,quote,_=fake_market
    quote.pop('timestamp')
    result=load_directional_context(kite,'A',now,[],quote,income_v2_config(),Cache())
    assert result['history'] and result['intraday']['asof']
    assert 'UNVERIFIED' not in result['market_regime']


def test_refresh_cache_fetches_once_per_request():
    from nifty_options_engine.directional_market import request_refresh_cache
    calls=[]
    fetch=lambda:calls.append(1) or {'value':len(calls)}
    refresh=request_refresh_cache()
    assert refresh('history',fetch,1800)==refresh('history',fetch,1800)=={'value':1}
    assert request_refresh_cache()('history',fetch,1800)=={'value':2}
