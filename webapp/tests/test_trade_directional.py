"""TRADE directional validation with mocked Kite; never import app.py."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
import re
from pathlib import Path
import pytest
from nifty_options_engine.directional_trend import IST,DTV_CONFIG
from nifty_options_engine.config import income_v2_config
from test_nifty_directional_trend import daily_rows,Cache,bars
from trade_directional import load_trade_trends,decision,sector_key,render_trend_panel,table_cell

NOW=datetime(2026,11,6,16,10,tzinfo=IST)


def evidence(ce='ALLOW',pe='ALLOW'):
    return dict(ce_status=ce,pe_status=pe,market_regime='TEST',calculated_at=NOW.isoformat(),
        valid_until=(NOW+timedelta(seconds=30)).isoformat(),reasons={'CE':'Stock trend','PE':'Stock trend'})


def context(ce='ALLOW',pe='ALLOW'):
    return dict(symbol='INFY',stock=evidence(ce,pe),sector=evidence(),market=evidence(),config=DTV_CONFIG)


@pytest.mark.parametrize('ce,pe,side', [('BLOCK','ALLOW','CE'),('ALLOW','BLOCK','PE')])
def test_stock_veto_cannot_be_overridden(ce,pe,side):
    c=context(ce,pe);c.update(rsi=90,mmi=99)
    assert decision(c,'SELL',side,NOW)['status']=='BLOCK'


def test_sideways_and_sector_conflict():
    c=context()
    assert decision(c,'SELL','CE',NOW)['status']=='PASS'
    c['sector']['ce_status']='BLOCK'
    assert decision(c,'SELL','CE',NOW)['status']=='WARNING'
    c['stock']['ce_status']='BLOCK';c['sector']['ce_status']='ALLOW'
    assert decision(c,'SELL','CE',NOW)['status']=='BLOCK'


@pytest.mark.parametrize('kind',['missing','stale'])
def test_missing_stale_blocks_both_sides(kind):
    c=context()
    if kind=='missing':c['stock']={}
    else:c['stock']['valid_until']=(NOW-timedelta(seconds=1)).isoformat()
    assert all(decision(c,'SELL',side,NOW)['status']=='BLOCK' for side in ('CE','PE'))


def test_buys_reductions_shares_and_covered_policy():
    c=context('BLOCK','BLOCK')
    assert decision(c,'BUY','CE',NOW)['status']=='PASS'
    assert decision(c,'SELL','CE',NOW,reducing=True)['status']=='PASS'
    assert decision(c,'SELL','EQ',NOW)['status']=='PASS'
    assert decision(c,'SELL','CE',NOW,verified_covered_call=True)['status']=='BLOCK'
    assert decision(c,'SELL','CE',NOW,verified_covered_call=True,covered_policy='WARNING')['status']=='WARNING'


@pytest.fixture
def feed(monkeypatch):
    import nifty_options_engine.directional_market as shared
    monkeypatch.setattr(shared.time,'sleep',lambda _:None)
    nse=[dict(tradingsymbol=s,exchange='NSE',instrument_type=t,instrument_token=n)
         for s,t,n in [('INFY','EQ',11),('NIFTY IT','INDEX',22),('NIFTY 50','INDEX',33)]]
    class Kite:
        access_token='mock'
        def __init__(self):self.calls=[]
        def quote(self,keys):return {'NSE:NIFTY 50':dict(instrument_token=33,timestamp=NOW.isoformat())}
        def historical_data(self,token,start,end,interval):
            self.calls.append((token,interval))
            rows=daily_rows(direction=1 if token==11 else -1 if token==33 else 0)
            shift=NOW.date()-timedelta(days=1)-rows[-1]['date'].date()
            return [dict(row,date=row['date']+shift,volume=1000 if token==11 else 0) for row in rows]
        def place_order(self,*args,**kw):pytest.fail('No orders allowed')
    return Kite(),nse


def test_actual_stock_sector_market_tokens_and_cache(feed):
    kite,nse=feed;cache=Cache()
    c=load_trade_trends(kite,'A','INFY',NOW,cache=cache,nse=nse,nfo=[],config=income_v2_config())
    assert c['stock']['ce_status']=='BLOCK' and c['market']['pe_status']=='BLOCK'
    assert c['sector_symbol']=='NSE:NIFTY IT'
    assert sorted(kite.calls)==[(11,'day'),(22,'day'),(33,'day')]
    load_trade_trends(kite,'A','INFY',NOW,cache=cache,nse=nse,nfo=[],config=income_v2_config())
    assert len(kite.calls)==3
    assert c['stock']['history'][-1]['adx14']==c['stock']['adx14']
    assert c['stock']['normalized_ema_slope_pct']==pytest.approx(c['stock']['ema_slope']/c['stock']['ema20']*100)


def test_missing_mapping_and_underlying_never_use_nifty(feed):
    kite,nse=feed
    assert sector_key('UNKNOWN') is None
    c=load_trade_trends(kite,'A','UNKNOWN',NOW,cache=Cache(),nse=nse,nfo=[],config=income_v2_config())
    assert c['sector'] is None and c['stock']['ce_status']=='BLOCK' and not c['stock']['history']


def test_nifty_uses_existing_service(feed):
    kite,nse=feed
    c=load_trade_trends(kite,'A','NIFTY',NOW,cache=Cache(),nse=nse,nfo=[],config=income_v2_config())
    assert c['stock']==c['market'] and kite.calls==[(33,'day')]


def test_chart_reads_same_dataset_and_has_isolated_ids(feed):
    kite,nse=feed
    c=load_trade_trends(kite,'A','INFY',NOW,cache=Cache(),nse=nse,nfo=[],config=income_v2_config())
    html=render_trend_panel(c)
    payload=json.loads(re.search(r'<script type="application/json" id="trade-dtv-data">(.*?)</script>',html,re.S).group(1))
    assert payload['data']['history']==c['stock']['history']
    assert payload['data']['data_asof']==c['stock']['data_asof']
    assert 'class="trade-dtv-grid"' in html and 'id="dtv-chart"' not in html
    assert 'NIFTY Trend Strength' not in html and 'INFY' in html
    assert 'BLOCK' in table_cell(c,decision(c,'SELL','CE',NOW))


def test_direct_authorization_rebuilds_review_before_order_reservation():
    # Inspect only the relevant source functions; never import runtime app state.
    source=Path('app.py').read_text(encoding='utf-8-sig')
    review=source[source.index('def build_trade_review('):source.index('def load_trade_workflow_draft(')]
    assert 'symbol, fresh=True)' in review and 'checks.append(dtv_check)' in review
    approval=source[source.index('def validate_protected_trade('):source.index('def render_trade_panel(')] if 'def validate_protected_trade(' in source else source[source.index('Fresh TRADE checks blocked SELL')-500:source.index('Fresh TRADE checks blocked SELL')+100]
    assert 'build_trade_review(state)' in approval and 'trade_has_blocks(checks)' in approval
    submit=source[source.index('fresh_preview, fresh_checks = build_trade_review(state)'):]
    assert submit.index('trade_has_blocks(fresh_checks)')<submit.index('repository.reserve(')


def test_stock_volume_vwap_and_incomplete_session(feed):
    kite,nse=feed
    now=NOW.replace(hour=10,minute=0)
    original=kite.historical_data
    def history(token,start,end,interval):
        if interval=='day':return original(token,start,end,interval)
        return bars(now,[22000+i for i in range(9)],100 if token==11 else 0)
    kite.historical_data=history
    c=load_trade_trends(kite,'A','INFY',now,cache=Cache(),nse=nse,nfo=[],config=income_v2_config())
    assert c['stock']['intraday']['vwap'] is not None
    assert c['sector']['intraday']['vwap'] is None
    def broken(token,start,end,interval):
        return history(token,start,end,interval)[:-2] if interval=='5minute' and token==11 else history(token,start,end,interval)
    kite.historical_data=broken
    c=load_trade_trends(kite,'A','INFY',now,cache=Cache(),nse=nse,nfo=[],config=income_v2_config())
    assert c['stock']['history'] and c['stock']['ce_status']==c['stock']['pe_status']=='BLOCK'


def test_sdk_exception_does_not_expose_credentials(feed):
    kite,nse=feed
    def broken(*args,**kwargs):raise ValueError('secret-token-should-not-appear')
    kite.historical_data=broken
    c=load_trade_trends(kite,'A','INFY',NOW,cache=Cache(),nse=nse,nfo=[],config=income_v2_config())
    assert 'secret-token' not in json.dumps(c)
    assert decision(c,'SELL','CE',NOW)['status']=='BLOCK'


def test_trade_chart_script_syntax(feed):
    import subprocess
    kite,nse=feed
    c=load_trade_trends(kite,'A','INFY',NOW,cache=Cache(),nse=nse,nfo=[],config=income_v2_config())
    html=render_trend_panel(c)
    for script in re.findall(r'<script>(.*?)</script>',html,re.S):
        subprocess.run(['node','--check','-'],input=script.encode('utf-8'),check=True)


def test_renewed_short_authorization_executes_directional_block():
    from types import SimpleNamespace
    from trade_terminal import has_blocks
    source=Path('app.py').read_text(encoding='utf-8-sig')
    start=source.index('def approve_protected_short(')
    end=source.index('\ndef ',start+1)
    calls=[]
    scope={'PageState':SimpleNamespace,'Any':object,'trade_has_blocks':has_blocks,
        'load_trade_terminal_state':lambda state:calls.append(state.trade_symbol),
        'build_trade_review':lambda state:({},[decision(context('BLOCK'),'SELL','CE',NOW)])}
    exec(compile(source[start:end],'<isolated TRADE authorization>','exec'),scope)
    record={'mode':'PAPER','preview':dict(symbol='INFY',short_symbol='INFYCE',hedge_symbol='INFYHEDGE',quantity=100,lot_size=100,
        order_payloads=[{'price':10},{'price':20}])}
    with pytest.raises(PermissionError,match='Hedge remains held'):
        scope['approve_protected_short'](SimpleNamespace(),record)
    assert calls==['INFY']
