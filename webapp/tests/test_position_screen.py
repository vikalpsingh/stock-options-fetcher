from pathlib import Path
import pytest
from position_screen import daily_change,movement_html

@pytest.mark.parametrize('price,close,expected,tone',[(105,100,5,'pnl-positive'),(95,100,-5,'pnl-negative'),(100,100,0,'signal-neutral')])
def test_previous_close_change(price,close,expected,tone):
    assert daily_change(price,close)==pytest.approx(expected)
    assert tone in movement_html(price,close)

@pytest.mark.parametrize('close',[None,0,float('nan'),float('inf')])
def test_unknown_close_is_not_zero(close):
    assert daily_change(100,close) is None
    assert 'unavailable' in movement_html(100,close)

def test_position_only_controls_sorting_and_order():
    source=Path('app.py').read_text(encoding='utf-8-sig')
    start=source.index('    from position_screen import movement_html')
    end=source.index('\ndef ',start)
    view=source[start:end]
    assert view.index('{render_position_close_schedule_panel("intraday")}')<view.index('{table}')
    assert 'id="position-active-analytics"' in view
    for col in (3,4,5):assert f'data-sort-col="{col}"' in view
    for key in ('pnl','otm_distance','sell_pop'):assert f'data-sort-value="{{row.get("{key}")' in view
    assert "enableTableSorting(document.getElementById('position-active-analytics'))" in source
