"""Data foundation checks: temporary SQLite, no app import, network or credentials."""
from datetime import datetime, timedelta, timezone
import json
import pytest
from investing.config import enabled
from investing.schemas import Observation
from investing.fundamentals import import_observations
from investing.market_data import configured_portfolio, adjusted_history_metrics
from investing.repository import InvestingRepository
from investing.service import import_fundamentals


def evidence(**changes):
    return dict(symbol='EXAMPLE',isin='INE000A01010',exchange='NSE',sector='INDUSTRIAL',metric='roce',
        value=18,unit='percent',period_end='2026-03-31',filing_date='2026-05-01',
        source='Manual import: annual filing reference example',fetched_at='2026-06-01T12:00:00+05:30',
        confidence=90,status='VERIFIED',**changes) if not changes else {**evidence(),**changes}


def test_flag_is_off_and_disabled_import_has_no_database_side_effect(tmp_path):
    path=tmp_path/'data.db'
    assert not enabled({})
    with pytest.raises(PermissionError):import_fundamentals(InvestingRepository(path),'A','[]','json',environ={})
    assert not path.exists()


@pytest.mark.parametrize('changes',[{'value':float('nan')},{'value':None},{'isin':''},{'confidence':101},
    {'fetched_at':'2026-06-01T12:00:00'},{'period_end':'2027-01-01'},{'status':'NOT_APPLICABLE','value':1}])
def test_invalid_metadata_rejected(changes):
    with pytest.raises(ValueError):Observation.parse(evidence(**changes))


def test_missing_stale_not_applicable_and_point_in_time():
    current=Observation.parse(evidence())
    assert current.state_at('2026-06-02T00:00:00Z')=='VERIFIED'
    assert current.state_at('2027-06-02T00:00:00Z')=='STALE'
    assert current.state_at('2026-05-02T00:00:00Z')=='MISSING'
    for status in ('MISSING','NOT_APPLICABLE'):
        record=Observation.parse(evidence(status=status,value=None))
        assert record.value is None and record.state_at('2026-06-02T00:00:00Z')==status


def test_import_idempotency_account_identity_and_history(tmp_path):
    repo=InvestingRepository(tmp_path/'data.db')
    text=json.dumps([evidence()]);flags={'INVESTING_V2_ENABLED':'true'}
    assert import_fundamentals(repo,'A',text,'json',environ=flags)==1
    assert import_fundamentals(repo,'A',text,'json',environ=flags)==0
    assert repo.observations('B','INE000A01010','NSE')==[]
    assert repo.observations('A','INE000A01010','BSE')==[]
    assert len(repo.observations('A','INE000A01010','NSE'))==1
    args=('A','INE000A01010','NSE','2026-06-02T00:00:00Z','v1',{'status':'NOT_RATABLE'})
    assert repo.save_snapshot(*args)==repo.save_snapshot(*args)
    assert len(repo.history('A','INE000A01010','NSE'))==1
    assert repo.history('B','INE000A01010','NSE')==[]
    restarted=InvestingRepository(repo.path)
    assert len(restarted.observations('A','INE000A01010','NSE'))==1


def test_invalid_batch_is_atomic(tmp_path):
    path=tmp_path/'data.db'
    with pytest.raises(ValueError):
        import_fundamentals(InvestingRepository(path),'A',json.dumps([evidence(),evidence(value=None)]),'json',environ={'INVESTING_V2_ENABLED':'true'})
    assert not path.exists()


def test_csv_and_json_equivalent():
    import csv,io
    row=evidence();buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=list(row));writer.writeheader();writer.writerow(row)
    assert import_observations(buffer.getvalue(),'csv')==import_observations(json.dumps([row]),'json')


def test_configured_quantities_and_unknown_prices_preserved():
    rows=[dict(quote_key='NSE:EXAMPLE',quantity=10,avg_price=100,cmp=110)]
    master=[dict(exchange='NSE',tradingsymbol='EXAMPLE',isin='INE000A01010')]
    portfolio=configured_portfolio(rows,master)
    assert portfolio[0]['quantity']==10 and portfolio[0]['unrealized_pnl']==100
    assert portfolio[0]['portfolio_weight_pct']==100
    assert configured_portfolio(rows,[])[0]['identity_status']=='MISSING'
    assert configured_portfolio(rows,master+[dict(master[0],isin='INE000B01010')])[0]['isin'] is None
    rows.append(dict(quote_key='NSE:UNKNOWN',quantity=1,avg_price=100,cmp=None))
    assert all(row['portfolio_weight_pct'] is None for row in configured_portfolio(rows,master))


def test_raw_candles_never_claim_adjusted_returns():
    now=datetime(2026,10,24,tzinfo=timezone.utc)
    candles=[dict(date=(now-timedelta(days=i)).isoformat(),close=100,high=101,low=99) for i in range(366)]
    assert adjusted_history_metrics(candles,adjusted=False,as_of=now)['return_1y_pct'] is None
    result=adjusted_history_metrics(candles,adjusted=True,as_of=now)
    assert result['dma_200']==100 and result['return_1y_pct']==0 and result['high_52w']==101
