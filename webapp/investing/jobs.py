"""Explicit background research jobs, isolated from all broker/order schedulers."""
from datetime import datetime,timezone
import json
import math
import logging
import sqlite3
import threading
import time
import uuid
from .repository import InvestingRepository,canonical
from .scoring import evaluate,VERSION
from .schemas import Observation
from .resolution import resolve, EvidenceIssue, review_result

LOG=logging.getLogger(__name__)


def prepare(path):
    repo=InvestingRepository(path);repo.ensure_schema()
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS investing_v2_jobs(
          id TEXT PRIMARY KEY,account TEXT NOT NULL,state TEXT NOT NULL,created_at TEXT NOT NULL,progress TEXT NOT NULL);
          CREATE UNIQUE INDEX IF NOT EXISTS investing_v2_one_job ON investing_v2_jobs(account) WHERE state='RUNNING';
          CREATE TABLE IF NOT EXISTS investing_v2_results(account TEXT NOT NULL,symbol TEXT NOT NULL,exchange TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(account,symbol,exchange));
          CREATE TABLE IF NOT EXISTS investing_v2_ai(account TEXT NOT NULL,key TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(account,key));''')
    return repo


def read_models(repo,account):
    with sqlite3.connect(repo.path) as db:
        rows=db.execute('SELECT data FROM investing_v2_evidence WHERE account=?',(account,)).fetchall()
    return [Observation.parse(json.loads(row[0])) for row in rows]


def run_job(path,account,job_id,rows,ai=False,client=None):
    repo=InvestingRepository(path);progress=[]
    try:
        observations=read_models(repo,account)
        # All portfolio prices must be known; never inflate known weights by dropping unknown holdings.
        complete=bool(rows) and all(isinstance(r.get('market_value'),(int,float)) and math.isfinite(r['market_value']) and r['market_value']>=0 and isinstance(r.get('cmp'),(int,float)) and math.isfinite(r['cmp']) and r['cmp']>0 for r in rows)
        total=sum(r['market_value'] for r in rows) if complete else 0
        for row in rows:
            if not row.get('_evaluate',True):continue
            start=time.monotonic();symbol=str(row.get('symbol','')).strip().upper();exchange=str(row.get('quote_key') or 'NSE:').split(':')[0].strip().upper()
            try:
                matches,isin,sector=resolve(observations,symbol,exchange)
                history=repo.history(account,isin,exchange);previous=history[0]['result'] if history else None
                weight=row['market_value']/total*100 if total else None
                sector_weight=sum(r['market_value'] for r in rows if r.get('sector')==row.get('sector'))/total*100 if total and row.get('sector') else None
                result=evaluate(matches,sector,datetime.now(timezone.utc),weight=weight,sector_weight=sector_weight,previous=previous)
                result['symbol']=symbol
                if ai:
                    from .ai_review import review
                    # Explicit allowlist: never pass account, cost basis, quantities or credentials.
                    package={k:result[k] for k in ('sector_model','score','confidence','evidence','flags','decision','portfolio_action','thesis_status','data_version','model_version','portfolio_weight')}
                    package['symbol']=symbol
                    def lookup(key):
                        with sqlite3.connect(path) as db:found=db.execute('SELECT data FROM investing_v2_ai WHERE account=? AND key=?',(account,key)).fetchone()
                        return json.loads(found[0]) if found else None
                    def save(key,data):
                        with sqlite3.connect(path) as db:db.execute('INSERT OR REPLACE INTO investing_v2_ai VALUES(?,?,?)',(account,key,canonical(data)))
                    result['ai']=review(package,lookup,save,**({'client':client} if client else {}))
                repo.save_snapshot(account,isin,exchange,result['evaluated_at'],VERSION,result)
                progress.append(dict(symbol=symbol,exchange=exchange,status='DONE',decision=result['decision']))
                LOG.info('investing_evaluation correlation_id=%s symbol=%s sector_model=%s data_version=%s score=%s decision=%s portfolio_action=%s duration_ms=%d',job_id,symbol,sector,result['data_version'],result['score'],result['decision'],result['portfolio_action'],(time.monotonic()-start)*1000)
            except EvidenceIssue as exc:
                result=review_result(symbol,exchange,exc.code,exc.reason,datetime.now(timezone.utc))
                progress.append(dict(symbol=symbol,exchange=exchange,status='REVIEW',code=exc.code,reason=exc.reason,result=result))
            except Exception as exc:
                # Report only exception type/location, never provider payloads or credentials.
                import traceback
                frame=traceback.extract_tb(exc.__traceback__)[-1]
                from pathlib import Path
                diagnostic=type(exc).__name__+' / '+Path(frame.filename).name+':'+str(frame.lineno)
                reason='Evaluation failed at '+diagnostic+'. No recommendation was generated.'
                result=review_result(symbol,exchange,'EVALUATION_ERROR',reason,datetime.now(timezone.utc))
                progress.append(dict(symbol=symbol,exchange=exchange,status='ERROR',code='EVALUATION_ERROR',reason=reason,result=result))
                LOG.warning('investing_evaluation_failed correlation_id=%s symbol=%s diagnostic=%s',job_id,symbol,diagnostic)
            with sqlite3.connect(path) as db:
                db.execute('INSERT OR REPLACE INTO investing_v2_results VALUES(?,?,?,?)',(account,symbol,exchange,canonical(result)))
                db.execute('UPDATE investing_v2_jobs SET progress=? WHERE id=? AND account=?',(canonical(progress),job_id,account))
    finally:
        with sqlite3.connect(path) as db:db.execute("UPDATE investing_v2_jobs SET state='DONE',progress=? WHERE id=? AND account=?",(canonical(progress),job_id,account))


def submit(path,account,rows,*,selected=None,ai=False):
    prepare(path);job_id=uuid.uuid4().hex
    rows=[{**r,'_evaluate':not selected or r.get('symbol') in selected} for r in rows]
    with sqlite3.connect(path) as db:
        # Interrupted workers are surfaced as interrupted after a bounded lifetime, never auto-retried.
        db.execute("UPDATE investing_v2_jobs SET state='INTERRUPTED' WHERE account=? AND state='RUNNING' AND created_at<datetime('now','-2 hours')",(account,))
        try:db.execute('INSERT INTO investing_v2_jobs VALUES(?,?,?,?,?)',(job_id,account,'RUNNING',datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),'[]'))
        except sqlite3.IntegrityError:raise ValueError('A research evaluation is already running. Refresh progress.') from None
    threading.Thread(target=run_job,args=(path,account,job_id,rows,ai),daemon=True,name='investing-research').start()
    return job_id
