import csv
import io

import pytest

import app


LOTS_CSV = """symbol,exchange,transaction_type,lots,price_markup_percent,product,order_type,validity,tag
BAJFINANCE26JUL1100CE,NFO,SELL,1,20,NRML,LIMIT,DAY,GPT_CC
"""

SUPPLIED_TRADING_CSV = """symbol,exchange,transaction_type,lots,price_markup_percent,product,order_type,price,validity,tag
BAJFINANCE26JUL1100CE,NFO,SELL,1,20,NRML,LIMIT,0,DAY,GPT_CC
TATACONSUM26JUL1200CE,NFO,SELL,1,20,NRML,LIMIT,0,DAY,GPT_CC
UNITDSPR26JUL1500CE,NFO,SELL,1,20,NRML,LIMIT,0,DAY,GPT_CC
PFC26JUL450CE,NFO,SELL,1,20,NRML,LIMIT,0,DAY,GPT_CC
"""


def test_lots_csv_does_not_require_or_emit_lot_size():
    normalized = app.canonicalize_kite_csv(LOTS_CSV)
    reader = csv.DictReader(io.StringIO(normalized))
    row = next(reader)

    assert "lot_size" not in reader.fieldnames
    assert "quantity" not in reader.fieldnames
    assert row["lots"] == "1"
    assert row["symbol"] == "BAJFINANCE26JUL1100CE"


def test_supplied_trading_csv_passes_pre_preview_validation():
    normalized = app.canonicalize_kite_csv(SUPPLIED_TRADING_CSV)
    rows = app.parse_csv_text(normalized)

    app.validate_kite_order_rows(rows)

    assert len(rows) == 4
    assert all(row["lots"] == "1" for row in rows)
    assert all("quantity" not in row for row in rows)


def test_legacy_lot_size_is_removed_and_not_trusted():
    legacy = """symbol,exchange,transaction_type,lots,lot_size,price_markup_percent,product,order_type,validity,tag
BAJFINANCE26JUL1100CE,NFO,SELL,1,999,20,NRML,LIMIT,DAY,GPT_CC
"""
    normalized = app.canonicalize_kite_csv(legacy)

    assert "lot_size" not in normalized.splitlines()[0]
    assert ",999," not in normalized


def test_lots_are_resolved_to_kite_unit_quantity(monkeypatch):
    base_args = app.default_args(no_ltp_price=True, keep_existing_orders=True)
    row = next(csv.DictReader(io.StringIO(app.canonicalize_kite_csv(LOTS_CSV))))
    row["price"] = "10"
    order_args = app.kite_orders.args_for_csv_row(base_args, row)

    monkeypatch.setattr(
        app,
        "cached_kite_instruments",
        lambda _kite, exchange: [
            {
                "exchange": exchange,
                "tradingsymbol": "BAJFINANCE26JUL1100CE",
                "lot_size": 750,
            }
        ],
    )
    resolved = app.resolve_order_arg_lot_sizes([order_args], object())
    order = app.kite_orders.build_order(order_args, object())

    assert resolved[("NFO", "BAJFINANCE26JUL1100CE")] == 750
    assert order_args.lot_size == 750
    assert order["quantity"] == 750


def test_final_kite_payload_contains_quantity_not_lot_fields():
    payload = app.kite_order_payload(
        {
            "variety": "regular",
            "exchange": "NFO",
            "tradingsymbol": "BAJFINANCE26JUL1100CE",
            "transaction_type": "SELL",
            "lots": 1,
            "lot_size": 750,
            "quantity": 750,
            "product": "NRML",
            "order_type": "LIMIT",
            "price": 10.0,
            "validity": "DAY",
        }
    )

    assert payload["quantity"] == 750
    assert "lots" not in payload
    assert "lot_size" not in payload


def test_fractional_lots_are_rejected():
    invalid = LOTS_CSV.replace(",1,20,", ",1.5,20,")

    with pytest.raises(ValueError, match="positive whole number"):
        app.canonicalize_kite_csv(invalid)
