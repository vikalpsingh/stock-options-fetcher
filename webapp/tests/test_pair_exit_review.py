from datetime import datetime,timedelta,timezone
from copy import deepcopy
import pytest
from pair_exit_review import save_exit_review,validate_exit_review

class Repo:
    def save(self,r):return r

def test_review_stage_quantity_price_and_expiry_boundaries():
    now=datetime.now(timezone.utc)
    r=dict(legs=[dict(payload=dict(tradingsymbol='S',transaction_type='SELL'),filled=10),dict(payload=dict(tradingsymbol='H',transaction_type='BUY'),filled=10)])
    prices={'S':5,'H':2}
    r=save_exit_review(Repo(),r,prices,40,now)
    validate_exit_review(r,prices,now)
    with pytest.raises(PermissionError):validate_exit_review(r,{'S':6,'H':2},now)
    with pytest.raises(PermissionError):validate_exit_review(r,prices,now+timedelta(seconds=121))
    changed=deepcopy(r);changed['legs'][0]['filled']=9
    with pytest.raises(PermissionError):validate_exit_review(changed,prices,now)
    with pytest.raises(ValueError):save_exit_review(Repo(),r,prices,float('nan'),now)


def test_exit_depth_tick_rounding_and_missing_market_data():
    from pair_exit_review import executable_exit_limit
    now=datetime.now(timezone.utc)
    quote=dict(timestamp=now.isoformat(),depth=dict(buy=[dict(price=2.03,quantity=10)],sell=[dict(price=3.02,quantity=10)]))
    assert executable_exit_limit(quote,'BUY',10,0.05,now)==3.05
    assert executable_exit_limit(quote,'SELL',10,0.05,now)==2.0
    for qty,tick in [(11,0.05),(10,None),(10,0)]:
        with pytest.raises(PermissionError):executable_exit_limit(quote,'BUY',qty,tick,now)
    with pytest.raises(PermissionError):executable_exit_limit({},'BUY',10,0.05,now)
