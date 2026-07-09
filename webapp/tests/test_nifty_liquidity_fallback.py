from datetime import date
from unittest.mock import patch

import app


def _symbol(strike: int, option_type: str) -> str:
    return f"NIFTYTEST{strike}{option_type}"


def test_ce_zero_ltp_moves_inward_up_to_two_hundred_points():
    quotes = {
        _symbol(25100, "CE"): {"last_price": 0, "oi": 50_000, "volume": 500},
        _symbol(25000, "CE"): {"last_price": 0, "oi": 50_000, "volume": 500},
        _symbol(24900, "CE"): {"last_price": 12.0, "oi": 50_000, "volume": 500},
    }

    adjusted = app.adjust_nifty_preview_sell_order_for_liquidity(
        {
            "tradingsymbol": _symbol(25100, "CE"),
            "transaction_type": "SELL",
            "strike": 25100,
            "option_type": "CE",
        },
        lambda symbol: quotes.get(symbol, {}),
        _symbol,
    )

    assert adjusted["strike"] == 24900
    assert adjusted["tradingsymbol"] == _symbol(24900, "CE")
    assert adjusted["original_strike"] == 25100
    assert adjusted["original_tradingsymbol"] == _symbol(25100, "CE")
    assert adjusted["liquidity_shift_points"] == 200


def test_pe_zero_ltp_moves_inward_toward_spot():
    quotes = {
        _symbol(22000, "PE"): {"last_price": 0, "oi": 50_000, "volume": 500},
        _symbol(22100, "PE"): {"last_price": 8.0, "oi": 50_000, "volume": 500},
    }

    adjusted = app.adjust_nifty_preview_sell_order_for_liquidity(
        {
            "tradingsymbol": _symbol(22000, "PE"),
            "transaction_type": "SELL",
            "strike": 22000,
            "option_type": "PE",
        },
        lambda symbol: quotes.get(symbol, {}),
        _symbol,
    )

    assert adjusted["strike"] == 22100
    assert adjusted["tradingsymbol"] == _symbol(22100, "PE")
    assert adjusted["liquidity_shift_points"] == 100


def test_fallback_never_moves_more_than_two_hundred_points():
    adjusted = app.adjust_nifty_preview_sell_order_for_liquidity(
        {
            "tradingsymbol": _symbol(25100, "CE"),
            "transaction_type": "SELL",
            "strike": 25100,
            "option_type": "CE",
        },
        lambda _symbol_name: {"last_price": 0, "oi": 50_000, "volume": 500},
        _symbol,
    )

    assert adjusted["strike"] == 24900
    assert adjusted["liquidity_shift_points"] == 200


def test_manual_ce_order_uses_adjusted_tradable_symbol_and_markup():
    quote_map = {
        f"NFO:{_symbol(25100, 'CE')}": {"last_price": 0, "oi": 50_000, "volume": 500},
        f"NFO:{_symbol(25000, 'CE')}": {"last_price": 0, "oi": 50_000, "volume": 500},
        f"NFO:{_symbol(24900, 'CE')}": {"last_price": 12.0, "oi": 50_000, "volume": 500},
    }

    with patch.object(app, "nifty_symbol_for_leg", side_effect=lambda _items, _expiry, strike, option_type: _symbol(int(strike), option_type)):
        orders, previews = app.nifty_income_pair_orders_from_otm(
            [],
            date(2026, 8, 4),
            spot=24000,
            pe_otm_pct=5.5,
            ce_otm_pct=4.5,
            config={
                "lot_size": 65,
                "strike_rounding": 100,
                "manual_pair_sell_markup_percent": 20.0,
            },
            quote_map=quote_map,
            lots=1,
            include_pe=False,
            include_ce=True,
            include_cover=False,
        )

    assert len(orders) == 1
    assert orders[0]["tradingsymbol"] == _symbol(24900, "CE")
    assert orders[0]["strike"] == 24900
    assert orders[0]["option_ltp"] == 12.0
    assert orders[0]["price"] == 14.4
    assert orders[0]["liquidity_shift_points"] == 200
    assert previews[0]["original_strike"] == 25100
