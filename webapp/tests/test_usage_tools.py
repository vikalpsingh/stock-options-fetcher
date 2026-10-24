import inspect,json
import pytest
from observability import usage_tracker as tracker
from observability.inventory import analyse
from observability.report import report


def test_tracker_preserves_result_signature_and_never_logs_payload(monkeypatch):
    events=[]
    monkeypatch.setenv('USAGE_TRACKING_ENABLED','true')
    monkeypatch.setattr(tracker,'emit',events.append)
    @tracker.tracked('test:boundary')
    def fn(secret, value=2):return value
    assert str(inspect.signature(fn))=='(secret, value=2)'
    assert fn('private-token')==2
    assert 'private-token' not in json.dumps(events)
    assert events[-1]['status']=='SUCCESS'
    @tracker.tracked('test:failure')
    def failure():raise ValueError('private-account')
    with pytest.raises(ValueError):failure()
    assert events[-1]['status']=='FAILURE'
    assert 'private-account' not in json.dumps(events)
    monkeypatch.setattr(tracker,'emit',lambda event:(_ for _ in ()).throw(OSError()))
    assert fn('secret',3)==3


def test_ast_and_report_do_not_import_target(tmp_path):
    root=tmp_path/'src';root.mkdir()
    (root/'sample.py').write_text('raise RuntimeError("must not import")\ndef close_order(): pass\ndef helper(): pass\n')
    data=analyse(root)
    assert any(f['classification']=='SAFETY CRITICAL' for f in data['functions'])
    logs=tmp_path/'logs';logs.mkdir();out=tmp_path/'out'
    (logs/'a.jsonl').write_text(json.dumps(dict(event='FUNCTION_USED',identifier='sample:helper',module='sample',status='SUCCESS',count=1,timestamp='2026-10-24',sample_rate=1))+'\ninvalid\n')
    report(logs,out,root)
    assert len(list(out.glob('*.csv')))==5
    assert 'PROTECTED' in (out/'possible_dead_code.csv').read_text()
    assert '1 malformed' in (out/'usage_summary.md').read_text()
