from datetime import datetime, timedelta, timezone
import html
from pathlib import Path
import pytest

SOURCE=Path('app.py').read_text(encoding='utf-8-sig')
IST=timezone(timedelta(hours=5,minutes=30))

def load(name,scope):
    a=SOURCE.index('def '+name+'('); b=SOURCE.index('\ndef ',a+5)
    exec(compile(SOURCE[a:b],name,'exec'),scope)
    return scope[name]


def fixture():
    stored={}
    jobs={}
    for key in ('position_close_open','income_growth_gpt','intraday_position_close','eod_pnl_snapshot'):
        def save(key=key,**updates):
            stored.setdefault(key,{}).update(updates)
            return stored[key]
        jobs[key]=dict(name=key,purpose='test',schedule='old',load=lambda key=key:stored.get(key,{}),save=save)
    scope=dict(Any=object,datetime=datetime,timedelta=timedelta,INDIA_TIME_ZONE=IST,
               scheduled_job_definitions=lambda:jobs)
    load('validate_schedule_clock',scope)
    return stored,scope


def values():
    return dict(position_close_open_schedule_time='09:25',income_growth_gpt_schedule_time='10:00',
        eod_pnl_snapshot_schedule_time='16:05',intraday_position_close_start_time='09:40',
        intraday_position_close_end_time='15:10',intraday_position_close_interval_minutes='7')


def test_save_roundtrip_and_runtime_slot():
    stored,scope=fixture()
    load('save_scheduled_job_times',scope)(values(),datetime(2026,10,22,12,tzinfo=IST))
    assert stored['position_close_open']['schedule_time']=='09:25'
    state=stored['intraday_position_close']
    assert state['interval_minutes']==7
    assert state['schedule_effective_from']=='2026-10-23'
    scope['intraday_position_close_schedule_state']=lambda:state
    slot=load('intraday_position_close_slot',scope)(datetime(2026,10,23,9,49,tzinfo=IST))
    assert slot[1].strftime('%H:%M')=='09:47'


def test_invalid_schedule_does_not_partially_save():
    stored,scope=fixture()
    for edits in ({'intraday_position_close_interval_minutes':'0'}, {'intraday_position_close_start_time':'16:00'}, {'position_close_open_schedule_time':'25:00'}):
        with pytest.raises(ValueError):
            load('save_scheduled_job_times',scope)(dict(values(),**edits),datetime(2026,10,22,tzinfo=IST))
        assert stored=={}


def test_scheduler_inputs_have_independent_form():
    a=SOURCE.index('def render_scheduler_control_panel(');b=SOURCE.index('\ndef ',a+5)
    panel=SOURCE[a:b]
    assert panel.count('form="scheduler-times-form"')==5
    assert '<form id="scheduler-times-form" method="post" action="/scheduler/save-times"></form>' in SOURCE
    assert 'html.escape(schedule_description)' in panel
