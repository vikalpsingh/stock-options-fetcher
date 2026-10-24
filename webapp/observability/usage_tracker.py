"""Opt-in entrypoint telemetry. Never inspects arguments, results or exception text."""
import functools, os, queue, random, threading, time, json
from datetime import datetime, timezone
from pathlib import Path

_events=queue.Queue(maxsize=2048)
_lock=threading.Lock()
_started=False
_loaded=set()

def _writer():
    while True:
        event=_events.get()
        try:
            folder=Path(os.environ.get('USAGE_TRACKING_LOG_DIR','runtime/usage_logs'))
            folder.mkdir(parents=True,exist_ok=True)
            path=folder/'usage.jsonl'
            if path.exists() and path.stat().st_size>5_000_000:
                for i in range(4,0,-1):
                    src=folder/f'usage.{i}.jsonl'; dst=folder/f'usage.{i+1}.jsonl'
                    if src.exists():src.replace(dst)
                path.replace(folder/'usage.1.jsonl')
            with path.open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
        except Exception:pass
        finally:_events.task_done()

def emit(event):
    global _started
    try:
        if os.environ.get('USAGE_TRACKING_ENABLED','false').lower()!='true':return
        if not _started:
            if not _lock.acquire(blocking=False):return
            try:
                if not _started:
                    threading.Thread(target=_writer,name='usage-writer',daemon=True).start();_started=True
            finally:_lock.release()
        _events.put_nowait(event)
    except Exception:pass

def tracked(identifier=None, *, boundary='', critical=True):
    def decorate(fn):
        stable=identifier or fn.__module__+':'+fn.__qualname__
        module,name=stable.split(':',1)
        @functools.wraps(fn)
        def wrapped(*args,**kwargs):
            selected=False
            rate=1.0
            try:
                enabled=os.environ.get('USAGE_TRACKING_ENABLED','false').lower()=='true'
                level=os.environ.get('USAGE_TRACKING_LEVEL','ENTRYPOINTS').upper()
                rate=1.0 if critical else min(1,max(0,float(os.environ.get('USAGE_TRACKING_SAMPLE_RATE','0.1'))))
                selected=enabled and (critical or level=='ALL') and (critical or random.random()<rate)
            except Exception:pass
            if not selected:return fn(*args,**kwargs)
            start=time.perf_counter();status='SUCCESS'
            try:return fn(*args,**kwargs)
            except BaseException:
                status='FAILURE';raise
            finally:
                try:
                    stamp=datetime.now(timezone.utc).isoformat()
                    env=os.environ.get('USAGE_TRACKING_ENVIRONMENT','UNKNOWN').upper()
                    if env not in {'PROD','PAPER','TEST'}:env='UNKNOWN'
                    event=dict(event='FUNCTION_USED',timestamp=stamp,last_seen=stamp,module=module,function=name,
                        identifier=stable,boundary=boundary,count=1,status=status,duration_ms=round((time.perf_counter()-start)*1000,3),
                        deployment_sha=os.environ.get('DEPLOYMENT_GIT_SHA','UNKNOWN')[:40],environment=env,sample_rate=rate)
                    if module not in _loaded:
                        _loaded.add(module);emit(dict(event,event='MODULE_LOADED',count=0))
                    emit(event)
                except Exception:pass
        return wrapped
    return decorate
