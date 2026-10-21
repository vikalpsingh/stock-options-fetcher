from datetime import datetime
import pytest
from test_nifty_ticket_service import market
from nifty_options_engine.ticket import build_ticket
from trade_protected_execution import ProtectedExecutionRepository

def test_manual_cleanup_is_scoped_and_preserves_pending(tmp_path,market):
    selection,context,config=market;repo=ProtectedExecutionRepository(tmp_path/'review.db')
    ticket=build_ticket(selection,context,config)
    old=repo.create_basket_review('A',ticket,'PAPER')
    pending=repo.create_basket_review('A',ticket,'PAPER')
    pending['state']='HEDGE_PENDING';pending['legs'][0]['order_id']='mock-order';repo.save(pending)
    other=repo.create_basket_review('B',ticket,'PAPER')
    assert repo.clear_basket_reviews('A')==1
    assert repo.get('A',old['id'])['review_archived']
    assert repo.get('A',pending['id'])['state']=='HEDGE_PENDING'
    assert repo.get('B',other['id'])['state']=='REVIEW'
    assert len(repo.recent_baskets('A'))==1
    with pytest.raises(PermissionError):repo.claim_basket(old)

def test_daily_cutoff_preserves_new_reviews(tmp_path,market):
    selection,context,config=market;repo=ProtectedExecutionRepository(tmp_path/'review.db')
    ticket=build_ticket(selection,context,config)
    for stamp in ['2026-10-21T08:59:00+05:30','2026-10-21T09:01:00+05:30']:
        row=repo.create_basket_review('A',ticket,'PAPER');row['reviewed_at']=stamp;repo.save(row)
    assert repo.clear_previous_session_reviews(datetime.fromisoformat('2026-10-21T08:59:59+05:30'))==0
    assert repo.clear_previous_session_reviews(datetime.fromisoformat('2026-10-21T03:30:00+00:00'))==1
    assert repo.clear_previous_session_reviews(datetime.fromisoformat('2026-10-21T12:00:00+05:30'))==0
    assert len(repo.recent_baskets('A'))==1
