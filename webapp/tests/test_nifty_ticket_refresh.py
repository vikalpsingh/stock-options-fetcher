from datetime import datetime, timezone
from copy import deepcopy
from app_time import is_quote_fresh,to_ist
from test_nifty_ticket_service import market
from nifty_options_engine.ticket import build_ticket,nearby_spread_candidates,find_nearby_liquid_spreads
from nifty_options_engine.ui import saved_ticket_details


def test_ist_naive_packet_with_utc_clock():
    now=datetime(2026,10,21,5,0,tzinfo=timezone.utc)
    assert is_quote_fresh({'timestamp':'2026-10-21T10:30:00','last_trade_time':'2026-10-20T10:00:00'},now=now)
    assert not is_quote_fresh({'timestamp':'2026-10-21T10:27:59'},now=now)
    assert not is_quote_fresh({'last_trade_time':'2026-10-21T10:30:00'},now=now)
    assert to_ist(now).hour==10


def test_preview_keeps_final_execution_gates(market):
    selection,context,config=market
    selection['mode']='LIVE';config['live_enabled']=True
    context.update(live_ack_enabled=True,session_fingerprint='test',market_open=False,margin=None,live_risk_gate={'allowed':True})
    preview=build_ticket(selection,context,config,for_execution=False)
    assert preview['eligible']
    final=build_ticket(selection,context,config)
    assert not final['eligible']
    assert {r['name'] for r in final['checks'] if r['status']=='BLOCK'}=={'Market session','Broker margin'}


def test_model_advice_not_duplicate_execution_veto(market):
    selection,context,config=market
    selection['mode']='LIVE';config['live_enabled']=True
    context.update(live_ack_enabled=True,session_fingerprint='test',live_risk_gate={'allowed':False,'reason':'Requested lots exceed the existing confidence sizing allowance'})
    assert build_ticket(selection,context,config)['eligible']


def test_four_rows_preserve_parent_lots(market):
    selection,context,config=market
    selection['lots']='3'
    ticket=build_ticket(selection,context,config)
    assert len(ticket['display_legs'])==4
    assert [r['quantity'] for r in ticket['display_legs']]==[195,195,0,0]
    html=saved_ticket_details(ticket)
    assert html.count('3 lots / 195')==2
    assert html.count('inactive-leg')==2


def test_listed_search_excludes_50(market):
    selection,context,config=market
    template=context['instruments'][0]
    for strike in (21900,22200,21950,22250):
        context['instruments'].append(dict(template,strike=strike,tradingsymbol=f'NIFTY{strike}PE'))
    pairs=nearby_spread_candidates(selection,context['instruments'])['PE']
    assert [p[0]['strike'] for p in pairs]==[22300,22200]
    for short,hedge in pairs:
        for row in (short,hedge):
            context['quotes'].setdefault('NFO:'+row['tradingsymbol'],deepcopy(context['quotes']['NFO:NIFTY22000PE']))
    alternatives=find_nearby_liquid_spreads(selection,context,config)
    assert alternatives['PE'][0]['short']=='NIFTY22200PE'
    assert alternatives['PE'][0]['hedge']=='NIFTY21900PE'
