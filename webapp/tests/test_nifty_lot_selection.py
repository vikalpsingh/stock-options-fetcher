from copy import deepcopy
import pytest
from test_nifty_ticket_service import market
from nifty_options_engine.ticket import build_ticket
from nifty_options_engine.risk_validator import get_max_safe_lots
from nifty_options_engine.ui import saved_ticket_details

@pytest.mark.parametrize('lots', [1,2,3,4])
def test_quantities_risk_and_popup(market, lots):
    selection, context, config = market
    selection['lots'] = str(lots)
    # Future master changes propagate; no assumed 65.
    for row in context['instruments']:
        row['lot_size'] = 75
    ticket = build_ticket(selection, context, config)
    assert all(row['quantity'] == 75*lots for row in ticket['order_payloads'])
    assert ticket['order_payloads'][0]['transaction_type'] == 'BUY'
    assert ticket['max_loss'] == (300-39)*75*lots+500
    assert f'{lots} lots' in saved_ticket_details(ticket)
    assert ticket['eligible'] == (ticket['max_loss'] <= 60000)
    assert ticket['selection']['lots'] == str(lots)

def test_recommendation_uses_canonical_risk(market):
    selection, context, config = market
    ticket = build_ticket(selection, context, config)
    advice = get_max_safe_lots([], ticket, config=config)
    assert advice['allowed_lots'] == [1,2,3]
    assert advice['recommended_lots'] == 3
    assert advice['rejected_lots_with_reasons'][4] == ['MAX_LOSS_CAP_BREACH']
    assert advice['remaining_risk_budget'][4] < 0
    assert selection['lots'] == '2'

def test_condor_uses_larger_width(market):
    selection, context, config = market
    selection.update(include_ce=True, short_ce='NIFTY23700CE', hedge_ce='NIFTY24000CE', lots='3')
    for index, strike in enumerate((24000,23700)):
        row = dict(context['instruments'][index], tradingsymbol=f'NIFTY{strike}CE', instrument_type='CE', strike=strike, instrument_token=10+index)
        context['instruments'].append(row)
        context['quotes']['NFO:'+row['tradingsymbol']] = deepcopy(context['quotes']['NFO:'+context['instruments'][index]['tradingsymbol']])
    ticket = build_ticket(selection, context, config)
    assert len(ticket['order_payloads']) == 4
    assert all(row['quantity'] == 195 for row in ticket['order_payloads'])
    assert ticket['max_loss'] == (300-78)*195+500
    assert ticket['eligible']


def test_changed_lots_invalidates_review_and_resets_countdown(market, tmp_path):
    from datetime import datetime, timedelta, timezone
    from nifty_options_engine.page import invalidate_changed_lot_reviews
    from nifty_options_engine.service import persist_review
    from trade_protected_execution import ProtectedExecutionRepository, submit_basket_hedges
    selection, context, config = market
    path = tmp_path/'orders.db'
    old = persist_review(path, 'A', build_ticket(selection, context, config))
    selection = {**selection, 'lots':'3'}
    invalidate_changed_lot_reviews(path, 'A', selection)
    repo = ProtectedExecutionRepository(path)
    assert repo.get('A', old['id'])['state'] == 'CLOSED'
    new = persist_review(path, 'A', build_ticket(selection, context, config))
    assert new['id'] != old['id']
    class Broker:
        paper_trading = True
        dry_run = False
        def place_order(self, payload):
            pytest.fail('Countdown must prevent broker submission')
    with pytest.raises(PermissionError, match='10 seconds'):
        submit_basket_hedges(repo, 'A', new['id'], Broker(), lambda *a: None, True,
            datetime.fromisoformat(new['reviewed_at'])+timedelta(seconds=9))
