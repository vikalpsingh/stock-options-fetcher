import json
import sqlite3
from datetime import datetime,timezone
import pytest
from investing.jobs import prepare,run_job
from investing.ui import load
from investing.resolution import resolve,EvidenceIssue
from investing.schemas import Observation
from test_investing_engine_v2 import observations


def run(path,job,rows):
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO investing_v2_jobs VALUES(?,?,?,?,?)',(job,'A','RUNNING',datetime.now(timezone.utc).isoformat(),'[]'))
    run_job(path,'A',job,rows)


def test_missing_fundamentals_results_survive_jobs_and_recover_after_import(tmp_path):
    path=tmp_path/'research.db';repo=prepare(path)
    rows=[dict(symbol=s,quote_key='NSE:'+s,market_value=100,cmp=100,sector='Manufacturing') for s in ('SCHNEIDER','PGEL','SHAILY')]
    run(path,'missing',rows)
    latest,_,_=load(path,'A')
    for row in rows:
        result=latest[row['quote_key']]
        assert result['diagnostic_code']=='FUNDAMENTALS_MISSING'
        assert result['status']=='NOT_RATABLE' and result['score'] is None
        assert result['decision']=='REVIEW' and result['portfolio_action']=='NO_ACTION'
    data=[Observation.parse({**o.to_dict(),'symbol':'PGEL','sector':'industrial'}) for o in observations()]
    repo.import_batch('A',data)
    run(path,'imported',[rows[1]])
    latest,_,_=load(path,'A')
    assert latest['NSE:PGEL']['status']=='RATABLE'
    assert latest['NSE:SCHNEIDER']['diagnostic_code']=='FUNDAMENTALS_MISSING'
    assert not load(path,'B')[0]


def test_resolution_distinguishes_exchange_model_and_identity_conflicts():
    data=observations()
    with pytest.raises(EvidenceIssue) as exc:resolve(data,'TEST','BSE')
    assert exc.value.code=='EXCHANGE_MISMATCH'
    invalid=[Observation.parse({**o.to_dict(),'sector':'Manf'}) for o in data]
    with pytest.raises(EvidenceIssue) as exc:resolve(invalid,'TEST','NSE')
    assert exc.value.code=='SECTOR_MODEL_REQUIRED'
    data.append(Observation.parse({**data[0].to_dict(),'isin':'INE000B01010'}))
    with pytest.raises(EvidenceIssue) as exc:resolve(data,'TEST','NSE')
    assert exc.value.code=='IDENTITY_CONFLICT'


def test_engine_error_is_diagnostic_not_disguised_as_missing_data(tmp_path,monkeypatch):
    path=tmp_path/'research.db';repo=prepare(path);repo.import_batch('A',observations())
    def fail(*a,**kw):raise RuntimeError('secret provider token must never appear')
    monkeypatch.setattr('investing.jobs.evaluate',fail)
    run(path,'failed',[dict(symbol='TEST',quote_key='NSE:TEST')])
    result=load(path,'A')[0]['NSE:TEST']
    assert result['diagnostic_code']=='EVALUATION_ERROR'
    assert 'RuntimeError' in result['warnings'][0]
    assert 'secret' not in json.dumps(result)
