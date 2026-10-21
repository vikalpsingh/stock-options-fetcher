import pytest
from nifty_options_engine.ticket import further_otm_contract, build_ticket
from test_nifty_ticket_service import market

@pytest.mark.parametrize('side,target,expected',[('PE',22050,22000),('PE',21750,21700),('CE',23750,23800),('CE',24050,24100)])
def test_all_four_contracts_round_further_otm(side,target,expected):
    rows=[dict(name='NIFTY',instrument_type=side,expiry='2026-11-17',strike=n,tradingsymbol=f'NIFTY26N17{n}{side}') for n in (21700,21750,21800,22000,22050,22100,23700,23750,23800,24000,24050,24100)]
    result=further_otm_contract(rows,side,'2026-11-17',target)
    assert result['strike']==expected
    assert further_otm_contract(rows,side,'2026-11-24',target) is None

def test_server_rejects_off_grid_review(market):
    selection,context,config=market
    context['instruments'][1]['strike']=22350
    ticket=build_ticket(selection,context,config)
    assert not ticket['eligible']
    assert any(c['name']=='SELL PE strike grid' and c['status']=='BLOCK' for c in ticket['checks'])
