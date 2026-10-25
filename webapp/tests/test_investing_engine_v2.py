from datetime import datetime,timezone
import json
import sqlite3
import pytest
from investing.schemas import Observation
from investing.sector_models import model,REPLACEMENTS
from investing.scoring import evaluate
from investing.ai_review import review,FIELDS
from investing.jobs import prepare,run_job
from investing.ui import enhance

NOW=datetime(2026,10,24,tzinfo=timezone.utc)


def observations(sector='INDUSTRIAL',**changes):
    specs={r[1]:(r[3],r[5]) for r in model(sector)}
    specs.update(market_fresh=('boolean',1),events_reviewed=('boolean',1),thesis_intact=('boolean',1),
                 margin_of_safety=('percent',25),valuation_model_supported=('boolean',1),sector_valuation_ratio=('ratio',0.8))
    specs.update(changes)
    return [Observation.parse(dict(symbol='TEST',isin='INE000A01010',exchange='NSE',sector=sector,metric=k,
        value=v,unit=u,period_end='2026-09-30',filing_date='2026-10-01',source='Verified filing '+k,
        fetched_at='2026-10-20T00:00:00Z',confidence=100,status='VERIFIED')) for k,(u,v) in specs.items()]


@pytest.mark.parametrize('sector',list(REPLACEMENTS))
def test_all_models_bounded_explainable_and_no_pnl_input(sector):
    result=evaluate(observations(sector),sector,NOW,weight=2,sector_weight=10)
    assert 0<=result['score']<=100 and result['data_coverage']==100
    assert sum(r[2] for r in model(sector))==100
    assert result['decision']=='BUY'
    assert result['portfolio_action']=='ADD_SMALL'
    assert not any('pnl' in e['metric'] for e in result['evidence'])


def test_missing_stale_conflicting_and_valuation_do_not_buy():
    assert evaluate([], 'GENERAL',NOW)['score'] is None
    assert evaluate(observations(),'INDUSTRIAL',datetime(2028,1,1,tzinfo=timezone.utc))['decision']=='REVIEW'
    data=observations();data.append(Observation.parse({**data[0].to_dict(),'value':3,'source':'Conflicting filing'}))
    assert evaluate(data,'INDUSTRIAL',NOW)['status']=='NOT_RATABLE'
    assert evaluate(observations(sector_valuation_ratio=('ratio',3)),'INDUSTRIAL',NOW)['decision']!='BUY'
    assert evaluate(observations(valuation_model_supported=('boolean',0)),'INDUSTRIAL',NOW)['decision']!='BUY'


def test_governance_and_concentration_do_not_autosell_strong_stock():
    result=evaluate(observations(),'INDUSTRIAL',NOW,weight=8.2,sector_weight=10)
    assert result['decision']=='BUY' and result['portfolio_action']=='HOLD'
    assert evaluate(observations(governance_allegation=('boolean',1)),'INDUSTRIAL',NOW)['decision']=='REVIEW'
    result=evaluate(observations(fraud_confirmed=('boolean',1)),'INDUSTRIAL',NOW)
    assert result['decision']=='SELL' and result['portfolio_action']=='EXIT'
    assert evaluate(observations(),'INDUSTRIAL',NOW,previous={'score':70})['thesis_status']=='IMPROVING'


def test_gpt_cache_failure_and_disagreement():
    package=evaluate(observations(),'INDUSTRIAL',NOW)
    cache={};calls=[]
    def client(p):
        calls.append(1)
        result={k:[] if t==list else None if t==float else 'Unknown' for k,t in FIELDS.items()}
        result.update(decision='HOLD',portfolio_action='HOLD',evidence_refs=['roce'])
        return result
    result=review(package,cache.get,lambda k,v:cache.update({k:v}),client)
    assert result['disagreement'] and package['decision']=='BUY'
    review(package,cache.get,lambda k,v:cache.update({k:v}),client)
    assert len(calls)==1
    assert review({},lambda _:None,lambda *a:None,lambda _:1/0)['unavailable']


def test_background_snapshot_and_ui_preserves_original_columns(tmp_path,monkeypatch):
    path=tmp_path/'research.db';repo=prepare(path);repo.import_batch('A',observations())
    with sqlite3.connect(path) as db:db.execute('INSERT INTO investing_v2_jobs VALUES(?,?,?,?,?)',('j','A','RUNNING','2026-10-24','[]'))
    rows=[dict(symbol='TEST',quote_key='NSE:TEST',sector='Industrial',quantity=1,market_value=100)]
    run_job(path,'A','j',rows)
    assert repo.history('A','INE000A01010','NSE')
    original='<form><section class="panel investing-hero-panel"></section><section class="panel investing-table-panel"><table id="investing-holdings-table"><thead><tr><th>Debt</th><th>Note</th></tr></thead><tbody><tr><td>OLD VALUE</td></tr></tbody></table></form>'
    monkeypatch.delenv('INVESTING_V2_ENABLED',raising=False)
    assert enhance(original,rows,path,'A')==original
    monkeypatch.setenv('INVESTING_V2_ENABLED','true')
    rendered=enhance(original,rows,path,'A')
    assert 'OLD VALUE' in rendered and 'data-sort-col="19">Score</button>' in rendered and '<dialog' in rendered
    assert 'Components and evidence' in rendered and 'DONE' in rendered
    assert 'Verified filing' not in enhance(original,rows,path,'B')


def test_disabled_routes_never_load_jobs_or_place_orders(tmp_path,monkeypatch):
    from investing.integration import handle
    monkeypatch.delenv('INVESTING_V2_ENABLED',raising=False)
    with pytest.raises(PermissionError):handle('/investing/evaluate',{},'A',tmp_path/'db',[])
    assert not (tmp_path/'db').exists()

def test_not_applicable_guidance_does_not_penalize_confidence():
    data=observations()
    data=[Observation.parse({**x.to_dict(),'value':None,'status':'NOT_APPLICABLE'}) if x.metric in {'guidance_growth','order_book_revenue'} else x for x in data]
    result=evaluate(data,'INDUSTRIAL',NOW,weight=2,sector_weight=10)
    assert result['confidence']==100 and result['data_coverage']==100
    assert result['decision']=='BUY'


def test_bounds_missing_essential_unit_and_low_confidence():
    data=observations(sales_cagr_3y=('percent',100000))
    assert evaluate(data,'INDUSTRIAL',NOW)['score']<=100
    assert evaluate(observations(sales_cagr_3y=('rupees',100)),'INDUSTRIAL',NOW)['score'] is None
    low=[Observation.parse({**x.to_dict(),'confidence':20}) for x in observations(fraud_confirmed=('boolean',1))]
    result=evaluate(low,'INDUSTRIAL',NOW)
    assert result['confidence']<65 and result['decision']=='REVIEW'


def test_untrusted_source_is_escaped_and_never_an_order_action(tmp_path,monkeypatch):
    path=tmp_path/'escape.db';repo=prepare(path)
    data=observations();data[0]=Observation.parse({**data[0].to_dict(),'source':'<script>alert(1)</script>'})
    result=evaluate(data,'INDUSTRIAL',NOW);result['symbol']='TEST'
    repo.save_snapshot('A','INE000A01010','NSE',NOW.isoformat(),'v1',result)
    monkeypatch.setenv('INVESTING_V2_ENABLED','true')
    markup='<form><section class="panel investing-hero-panel"></section><table><th>Debt</th><th>Note</th><tbody><tr><td>Old</td></tr></tbody></table></form>'
    rendered=enhance(markup,[{'symbol':'TEST'}],path,'A')
    assert '<script>alert' not in rendered and '&lt;script&gt;' in rendered
    assert '/equity/order' not in rendered and '/trade/' not in rendered
