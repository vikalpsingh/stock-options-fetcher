import json
from datetime import datetime
from test_nifty_ticket_service import market
from nifty_options_engine.ticket import build_ticket
from nifty_options_engine.service import persist_review
from nifty_options_engine.ui import saved_ticket_details

def test_sdk_datetimes_survive_paper_review(market, tmp_path):
    selection,context,config=market
    for quote in context['quotes'].values():
        quote['timestamp']=context['now'].replace(tzinfo=None)
        quote['last_trade_time']=context['now']
        quote['last_price']=70
        quote['ohlc']={'close':100}
        quote['unused_sdk_field']=object()
    ticket=build_ticket(selection,context,config)
    json.dumps(ticket)
    record=persist_review(tmp_path/'paper.db','Test',ticket)
    assert record['state']=='REVIEW'
    snapshot=record['preview']['display_legs'][0]['reviewed_quote']
    assert snapshot['timestamp'].endswith('+05:30')
    assert 'last_trade_time' not in snapshot
    assert 'unused_sdk_field' not in snapshot
    assert '-30.00%' in saved_ticket_details(record['preview'])
    assert isinstance(context['quotes']['NFO:NIFTY22000PE']['timestamp'],datetime)

def test_missing_timestamp_remains_missing_for_paper(market,tmp_path):
    selection,context,config=market
    for quote in context['quotes'].values():
        quote.pop('timestamp')
    ticket=build_ticket(selection,context,config)
    record=persist_review(tmp_path/'paper.db','Test',ticket)
    assert record['preview']['display_legs'][0]['reviewed_quote']['timestamp'] is None
