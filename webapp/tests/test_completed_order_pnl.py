import math
from pathlib import Path

from position_order_display import completed_order_current_pnl as pnl


def test_completed_row_quantity_and_position_direction():
    row = dict(status="COMPLETE", quantity=65, filled_quantity=65,
               position_qty=-260, position_avg_price=100, ltp=80,
               position_pnl=5200, transaction_type="BUY")
    assert pnl(row) == 1300
    assert pnl(dict(row, position_qty=260, transaction_type="SELL")) == -1300
    assert pnl(dict(row, filled_quantity=20)) == 400


def test_cancelled_and_rejected_rows_are_zero_even_with_fills():
    for status in ("CANCELLED", "CANCELED", "REJECTED"):
        assert pnl(dict(status=status, filled_quantity=20, position_pnl=5000)) == 0


def test_missing_or_invalid_inputs_do_not_copy_whole_position_pnl():
    row = dict(status="COMPLETE", quantity=65, position_qty=-260,
               position_avg_price=100, ltp=80, position_pnl=5200)
    for change in ({"ltp": None}, {"ltp": float("nan")},
                   {"position_avg_price": None}, {"position_qty": 0}):
        assert pnl(dict(row, **change)) is None
    assert pnl(dict(row, ltp=0)) == 6500
