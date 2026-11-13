from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from nifty_options_engine.market_session import get_nse_market_session, validate_market_data_freshness
from nifty_options_engine.readiness import monthly_view, entry_readiness

IST=ZoneInfo('Asia/Kolkata')
def session(day, hour=11, minute=0):
    return get_nse_market_session(datetime.fromisoformat(day).replace(hour=hour,minute=minute,tzinfo=IST))

def test_holiday_and_expected_history():
    s=session('2026-11-10')
    assert s['reason']=='NSE_HOLIDAY'
    assert s['last_trading_date']=='2026-11-09'
    assert s['next_trading_date']=='2026-11-11'
    f=validate_market_data_freshness(s,{'timestamp':'2026-11-09T15:30:00+05:30'},[{'date':'2026-11-09T00:00:00+05:30'}],[])
    assert f['status']=='EXPECTED_PREVIOUS_SESSION'
    assert f['intraday_status']=='SESSION_CLOSED'
    assert f['quote_age_seconds']>3600

@pytest.mark.parametrize('day,reason',[('2026-11-14','WEEKEND'),('2027-01-04','CALENDAR_UNKNOWN')])
def test_closed_unknown(day,reason):
    s=session(day)
    assert s['reason']==reason and not s['new_entries_allowed']

def test_special_and_boundary():
    assert not session('2026-11-08',10)['new_entries_allowed']
    assert session('2026-11-08',14,25)['new_entries_allowed']
    assert not session('2026-11-08',15,40)['new_entries_allowed']
    assert session('2026-11-12',9,15)['new_entries_allowed']
    assert not session('2026-11-12',9,14)['new_entries_allowed']

def test_live_freshness():
    s=session('2026-11-12')
    daily=[{'date':'2026-11-11T00:00:00+05:30'}]
    intra=[{'date':'2026-11-12T10:55:00+05:30'}]
    q={'timestamp':'2026-11-12T10:59:55+05:30','last_price':25000}
    assert validate_market_data_freshness(s,q,daily,intra)['status']=='FRESH'
    q['timestamp']='2026-11-12T10:58:00+05:30'
    assert validate_market_data_freshness(s,q,daily,intra)['status']=='STALE_DURING_MARKET'

@pytest.mark.parametrize('used,state',[(0,'GREEN'),(33000,'AMBER'),(48000,'RED'),(60000,'HARD BLOCK')])
def test_monthly_classification(used,state):
    m=monthly_view(dict(loss_used=used,max_monthly_loss=60000,data_status='CLOSED_TRADE_LEDGER'))
    assert m['display_state']==state
    assert m['remaining_display']==60000-used

def test_missing_and_sticky_lock():
    assert monthly_view({})['display_state']=='UNKNOWN'
    assert monthly_view(dict(loss_used=0,max_monthly_loss=60000,data_status='NO_REALISED_DATA'))['display_state']=='UNKNOWN'
    assert monthly_view(dict(loss_used=0,max_monthly_loss=60000,data_status='KITE_PNL_IMPORT',hard_locked=True))['display_state']=='HARD BLOCK'

def test_readiness_cannot_override_direction():
    context=dict(market_session=session('2026-11-12'),monthly=dict(loss_used=0,max_monthly_loss=60000,data_status='KITE_PNL_IMPORT'),
        dtv=dict(freshness={'status':'FRESH','quote_timestamp':'2026-11-12T11:00:00+05:30'},ce_status='BLOCK',pe_status='ALLOW',reasons={'CE':'Bullish veto'}))
    assert entry_readiness(context,['CE'])[0]=='NO TRADE'
    assert entry_readiness(context,['PE'])[0]=='READY FOR PREVIEW'
    context['market_session']=session('2026-11-10')
    assert entry_readiness(context,['PE'])[0]=='MARKET CLOSED'

def test_holiday_loader_retains_daily_and_does_not_fetch_intraday(monkeypatch):
    from test_nifty_directional_trend import daily_rows
    from nifty_options_engine.directional_market import load_directional_context
    from nifty_options_engine.config import income_v2_config
    from datetime import timedelta
    rows=daily_rows()
    shift=datetime(2026,11,9,tzinfo=IST)-rows[-1]['date']
    rows=[dict(r,date=r['date']+shift) for r in rows]
    calls=[]
    class Kite:
        access_token='mock'
        def historical_data(self,token,start,end,interval):
            calls.append(interval)
            assert interval=='day'
            return rows
    monkeypatch.setattr('nifty_options_engine.directional_market.time.sleep',lambda _:None)
    now=datetime(2026,11,10,11,tzinfo=IST)
    result=load_directional_context(Kite(),'mock',now,[],dict(instrument_token=1,timestamp='2026-11-09T15:30:00+05:30'),income_v2_config(),market_session=get_nse_market_session(now))
    assert calls==['day']
    assert result['history']
    assert result['adx14']==result['history'][-1]['adx14']
    assert result['freshness']['status']=='EXPECTED_PREVIOUS_SESSION'
    assert result['ce_status']==result['pe_status']=='BLOCK'
    assert 'MARKET CLOSED' in result['intraday']['continuation']
    assert result['ema_slope_sessions']==3


def test_final_gate_blocks_manual_override():
    from test_nifty_ticket_service import market as fixture
    # Obtain the pure fixture data without app imports or broker calls.
    from nifty_options_engine.ticket import build_ticket
    selection,context,config=fixture.__wrapped__()
    selection.update(quick_pair='PE',skip_strategy_validation=True)
    context['market_session']=session('2026-11-10')
    ticket=build_ticket(selection,context,config)
    assert not ticket['eligible']
    assert any(c['name']=='Final trade readiness' and c['status']=='BLOCK' for c in ticket['checks'])
