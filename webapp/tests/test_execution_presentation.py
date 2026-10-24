from execution_presentation import margin_estimate_status, render_discipline_cards
from trade_execution_ui import render_execution_monitor


def test_only_local_defined_risk_margin_becomes_warning():
    assert margin_estimate_status(100,200,defined_risk=True)=='PASS'
    assert margin_estimate_status(200,100,defined_risk=True)=='WARNING'
    assert margin_estimate_status(None,None,defined_risk=True)=='WARNING'
    assert margin_estimate_status(float('nan'),100,defined_risk=True)=='WARNING'
    assert margin_estimate_status(200,100,defined_risk=False)=='BLOCK'
    assert margin_estimate_status(200,100,defined_risk=True,verified_insufficient=True)=='BLOCK'


def test_reusable_four_cards_and_mobile_layout():
    markup=render_discipline_cards()
    assert markup.count('<article class="discipline-card ')==4
    for name in ('Emotional Discipline','Market Perspective','Opportunity Mindset','Enter the Zone'):
        assert name in markup
    assert 'grid-template-columns:repeat(2,minmax(0,1fr))' in markup
    assert '@media(max-width:600px)' in markup
    assert markup in render_execution_monitor([], 'test')
