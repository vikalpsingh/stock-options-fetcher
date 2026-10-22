from copy import deepcopy
import pytest
from test_nifty_ticket_service import market
from nifty_options_engine.optimizer import generate_nifty_short_strike_candidates, candidate_contracts, optimize_spreads, candidate_quote_keys
from nifty_options_engine.ui import spread_comparison


def test_five_strikes_and_normalization():
    assert [r['strike'] for r in generate_nifty_short_strike_candidates(22250,'PE')]==[22400,22300,22200,22100,22000]
    assert [r['strike'] for r in generate_nifty_short_strike_candidates(23150,'CE')]==[23000,23100,23200,23300,23400]


@pytest.mark.parametrize('lots',[1,2,3,4])
def test_actual_lots_credit_and_cap(market,lots):
    selection,ctx,cfg=market
    selection['lots']=str(lots)
    result=optimize_spreads(selection,ctx,cfg)
    base=next(r for r in result['tables']['PE'] if r['label']=='BASE')
    assert base['hedge']['strike']==22000
    assert base['ticket']['net_credit']==39*65*lots
    assert base['ticket']['max_loss']==(300-39)*65*lots+500
    assert bool(result['chosen']['PE']) == (lots<=3)
    assert 'Best PE' in spread_comparison('PE',result['tables']['PE'],selection,ctx)


def test_missing_bid_and_depth_cannot_win(market):
    selection,ctx,cfg=market
    ctx['quotes']['NFO:NIFTY22300PE']['depth']['buy']=[]
    assert optimize_spreads(selection,ctx,cfg)['chosen']['PE'] is None
    assert 'NFO:NIFTY22000PE' in candidate_quote_keys(selection,ctx['instruments'],300)


def test_combined_uses_shared_max_width_payoff(market):
    selection,ctx,cfg=market
    selection.update(include_ce=True,short_ce='NIFTY23400CE',hedge_ce='NIFTY23700CE')
    for strike,price in ((23400,60),(23700,20)):
        row=dict(ctx['instruments'][0],tradingsymbol=f'NIFTY{strike}CE',strike=strike,instrument_type='CE',instrument_token=strike)
        ctx['instruments'].append(row)
        q=deepcopy(ctx['quotes']['NFO:NIFTY22300PE' if price==60 else 'NFO:NIFTY22000PE'])
        ctx['quotes']['NFO:'+row['tradingsymbol']]=q
    result=optimize_spreads(selection,ctx,cfg)
    assert result['combination_count']==1
    from nifty_options_engine.ticket import build_ticket
    ticket=build_ticket(selection,ctx,cfg,for_execution=False)
    assert ticket['max_loss']==300*130-78*130+500
    assert len(ticket['legs'])==4


def test_page_refresh_manual_selection_and_review_reset(market,tmp_path):
    from nifty_options_engine.page import page_data, invalidate_changed_lot_reviews
    from nifty_options_engine.service import persist_review
    from nifty_options_engine.ticket import build_ticket
    from trade_protected_execution import ProtectedExecutionRepository
    selection,ctx,cfg=market
    path=str(tmp_path/'optimizer.db')
    form={k:[str(v)] for k,v in selection.items() if k not in {'include_pe'}}
    form.update(structure=['PE'],auto_best=['no'],base_pe=['NIFTY22300PE'])
    data=page_data('test',path,cfg,lambda s:deepcopy(ctx),form)
    assert data['selection']['short_pe']=='NIFTY22300PE'
    assert data['ticket']['net_credit']==5070
    record=persist_review(path,'test',build_ticket(selection,ctx,cfg,for_execution=False))
    changed=dict(selection,hedge_pe='NIFTY21900PE')
    invalidate_changed_lot_reviews(path,'test',changed)
    assert ProtectedExecutionRepository(path).get('test',record['id'])['state']=='CLOSED'
    form.update(auto_best=['yes'],optimize=['yes'])
    ctx['quotes']['NFO:NIFTY22300PE']['depth']['buy']=[]
    refreshed=page_data('test',path,cfg,lambda s:deepcopy(ctx),form)
    assert refreshed['selection']['short_pe']==''
    assert not refreshed['ticket']['eligible']


def test_maximum_credit_fallback_keeps_risk_blocks(market):
    from nifty_options_engine.optimizer import maximum_credit_preview
    selection,ctx,cfg=market
    selection['lots']='4'
    result=optimize_spreads(selection,ctx,cfg)
    assert result['chosen']['PE'] is None
    row=maximum_credit_preview(result['tables']['PE'])
    assert row['label']=='BASE'
    assert not row['ticket']['eligible']
    assert row['ticket']['net_credit']==39*260
    ctx['quotes']['NFO:NIFTY22300PE']['depth']['buy']=[]
    assert maximum_credit_preview(optimize_spreads(selection,ctx,cfg)['tables']['PE']) is None


def test_fallback_picks_highest_credit_but_prefers_eligible(market):
    from nifty_options_engine.optimizer import maximum_credit_preview
    selection,ctx,cfg=market
    row=optimize_spreads(selection,ctx,cfg)['chosen']['PE']
    higher=deepcopy(row)
    higher['ticket']['net_credit']+=100
    assert maximum_credit_preview([row,higher]) is higher
    higher['eligible']=False
    assert maximum_credit_preview([row,higher]) is row
