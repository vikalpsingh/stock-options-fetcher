import pytest
from test_nifty_ticket_service import market
from nifty_options_engine.ticket import build_ticket
from nifty_options_engine.service import persist_review,approve_entry

@pytest.mark.parametrize('margin,funds',[(50000,1),(None,None),(0,0)])
def test_margin_does_not_veto_fresh_entry(market,tmp_path,margin,funds):
    selection,context,config=market
    ticket=build_ticket(selection,context,config)
    record=persist_review(tmp_path/'paper.db','A',ticket)
    context.update(margin=margin,funds=funds)
    assert build_ticket(selection,context,config)['eligible']
    assert approve_entry(record,context,config)['risk_status']=='PASS'
    assert any(c['status']=='WARNING' and c['name']=='Broker margin estimate' for c in build_ticket(selection,context,config)['checks'])
