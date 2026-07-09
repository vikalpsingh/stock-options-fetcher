import app


RESEARCH_CSV = """symbol,exchange,transaction_type,lots,price_markup_percent,product,order_type,validity,tag
BAJFINANCE26JUL1100CE,NFO,SELL,1,20,NRML,LIMIT,DAY,GPT_CC
TATACONSUM26JUL1200CE,NFO,SELL,1,20,NRML,LIMIT,DAY,GPT_CC
UNITDSPR26JUL1500CE,NFO,SELL,1,20,NRML,LIMIT,DAY,GPT_CC
PFC26JUL450CE,NFO,SELL,1,20,NRML,LIMIT,DAY,GPT_CC
"""


def option_quote(ltp=4.05, bid=4.0, ask=4.1):
    return {
        "last_price": ltp,
        "depth": {
            "buy": [{"price": bid}],
            "sell": [{"price": ask}],
        },
    }


def test_sell_limit_uses_twenty_percent_above_fresh_ltp():
    order = {
        "exchange": "NFO",
        "tradingsymbol": "BAJFINANCE26JUL1100CE",
        "transaction_type": "SELL",
        "order_type": "LIMIT",
        "price": 0,
        "price_markup_percent": 20,
        "_tick_size": 0.05,
    }

    validation = app.calculateSafeLimitPrice(order, option_quote())

    assert validation["ok"] is True
    assert validation["price"] == 4.85
    assert validation["auto_adjusted"] is False
    assert "SELL markup 20.00%" in validation["message"]


def test_lpp_retry_can_ignore_markup_and_use_executable_bid():
    order = {
        "exchange": "NFO",
        "tradingsymbol": "BAJFINANCE26JUL1100CE",
        "transaction_type": "SELL",
        "order_type": "LIMIT",
        "price": 0,
        "price_markup_percent": 20,
        "_ignore_markup_price": True,
        "_tick_size": 0.05,
    }

    validation = app.calculateSafeLimitPrice(order, option_quote())

    assert validation["ok"] is True
    assert validation["price"] == 3.95
    assert validation["auto_adjusted"] is True


def test_trading_preview_reprices_zero_csv_sell_from_fresh_ltp(monkeypatch):
    rows = [
        {
            "symbol": "BAJFINANCE26JUL1100CE",
            "exchange": "NFO",
            "transaction_type": "SELL",
            "lots": "1",
            "price_markup_percent": "20",
            "product": "NRML",
            "order_type": "LIMIT",
            "price": "0",
            "validity": "DAY",
            "tag": "GPT_CC",
        }
    ]

    class FakeKite:
        def ltp(self, instrument_key):
            return {instrument_key: {"last_price": 4.05}}

    fake_kite = FakeKite()
    monkeypatch.setattr(app.kite_orders, "kite_client", lambda: fake_kite)
    monkeypatch.setattr(
        app,
        "cap_trading_option_rows_by_otm",
        lambda supplied_rows, _kite: ([dict(row) for row in supplied_rows], {}),
    )
    monkeypatch.setattr(
        app,
        "cached_kite_instruments",
        lambda _kite, _exchange: [
            {"tradingsymbol": "BAJFINANCE26JUL1100CE", "lot_size": 750}
        ],
    )
    monkeypatch.setattr(
        app,
        "cached_kite_quote",
        lambda _kite, _keys, ttl_seconds=5: {
            "NFO:BAJFINANCE26JUL1100CE": option_quote()
        },
    )
    monkeypatch.setattr(app, "apply_risk_engine_to_orders", lambda orders, _override: orders)

    orders = app.build_orders(
        rows,
        no_ltp_price=False,
        keep_existing_orders=True,
    )

    assert len(orders) == 1
    assert orders[0]["lots"] == 1
    assert orders[0]["quantity"] == 750
    assert orders[0]["ltp"] == 4.05
    assert orders[0]["price_markup_percent"] == 20
    assert orders[0]["price"] == 4.85


def test_research_save_fetches_fresh_prices_and_removes_untraded_contracts(
    monkeypatch,
    tmp_path,
):
    requested = {}

    def fake_quotes(_kite, keys, ttl_seconds=5):
        requested["keys"] = list(keys)
        requested["ttl_seconds"] = ttl_seconds
        return {
            "NFO:BAJFINANCE26JUL1100CE": option_quote(4.05, 4.0, 4.1),
            "NFO:TATACONSUM26JUL1200CE": option_quote(10.0, 9.95, 10.05),
            "NFO:UNITDSPR26JUL1500CE": {
                "last_price": 6.0,
                "volume": 0,
                "last_trade_time": None,
                "depth": {"buy": [], "sell": []},
            },
            # PFC deliberately absent: unavailable/untraded contracts are removed.
        }

    today_path = tmp_path / "9Jul2026.csv"
    monkeypatch.setattr(app, "cached_kite_quote", fake_quotes)
    monkeypatch.setattr(app, "dated_income_csv_path", lambda: today_path)

    saved_path, message = app.save_today_csv_text(RESEARCH_CSV, kite=object())
    saved = today_path.read_text(encoding="utf-8")

    assert saved_path == str(today_path)
    assert requested["ttl_seconds"] == 0
    assert len(requested["keys"]) == 4
    assert "BAJFINANCE26JUL1100CE,NFO,SELL,1,20,NRML,LIMIT,4.85" in saved
    assert "TATACONSUM26JUL1200CE,NFO,SELL,1,20,NRML,LIMIT,12.00" in saved
    assert "UNITDSPR26JUL1500CE" not in saved
    assert "PFC26JUL450CE" not in saved
    assert "fresh Kite prices for 2 option contract(s)" in message
    assert "Removed 2 untraded/invalid option contract(s)" in message
