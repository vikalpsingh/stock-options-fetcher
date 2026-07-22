from pathlib import Path

import app


def _unitdspr_top3_item():
    return {
        "stock": "UNITDSPR",
        "option_symbol": "UNITDSPR26JUL1520CE",
        "lots_to_sell": 1,
        "active_lot_size": 400,
        "holding_qty": 1522,
        "kite_holding_qty": 27,
        "income_growth_holding_qty": 1522,
        "holding_source": "Income Growth holding record",
        "cmp": 1404.2,
        "selected_ce_strike": 1520,
        "expiry": "2026-07-28",
        "premium": 18.05,
        "sell_limit_price": 21.70,
        "max_profit": 8680.0,
        "premium_yield_percent": 1.55,
        "otm_percent": 8.25,
        "final_ce_score": 100,
        "event_risk": "CHECK",
        "breakout_risk": "N/A",
        "next_result_date": "No result in next 5 days",
        "event_risk_reason": "Result calendar is clear for the next 5 trading days.",
    }


def _install_unitdspr_ce_popup_fakes(monkeypatch):
    class FakeKiteOrders:
        def kite_client(self):
            return object()

    candidate = {
        "symbol": "UNITDSPR",
        "decision": "SELL_NOW",
        "decision_color": "green",
        "candidate_ce": "UNITDSPR26JUL1520CE",
        "recommended_lots": 2,
        "quantity": 1522,
        "lot_size": 400,
        "cmp": 1404.2,
        "selected_call_strike": 1520,
        "selected_expiry": "2026-07-28",
        "cc_capacity_score": 100,
        "corporate_action_risk": "CHECK",
        "breakout_risk": "N/A",
        "next_result_date": "No result in next 5 days",
        "event_risk_reason": (
            "SELL 1 covered lot(s): shares are available, expiry risk is "
            "acceptable, and premium yield is 1.29%."
        ),
    }

    def fake_quotes(_kite, keys, ttl_seconds=0):
        assert "NFO:UNITDSPR26JUL1520CE" in keys
        assert "NSE:UNITDSPR" in keys
        return {
            "NFO:UNITDSPR26JUL1520CE": {"last_price": 18.05},
            "NSE:UNITDSPR": {"last_price": 1404.2},
        }

    monkeypatch.setattr(app, "kite_orders", FakeKiteOrders())
    monkeypatch.setattr(app, "ce_sell_dashboard", lambda _force=False: ([], [], {}))
    monkeypatch.setattr(app, "income_growth_candidates", lambda: ([candidate], {}))
    monkeypatch.setattr(app, "cached_kite_positions", lambda _kite, ttl_seconds=0: [])
    monkeypatch.setattr(
        app,
        "active_short_option_sell_info_from_positions",
        lambda _underlying, _positions: {
            "summary": "No active PE/CE SELL position found for this stock.",
            "has_short_pe": False,
            "has_short_ce": False,
        },
    )
    monkeypatch.setattr(
        app,
        "covered_ce_holding_source",
        lambda _kite, _underlying: {
            "holding_qty": 1522,
            "holding_source": "Income Growth holding record",
            "kite_holding_qty": 27,
            "income_growth_holding_qty": 1522,
            "average_price": 0.0,
        },
    )
    monkeypatch.setattr(app, "cached_kite_quote", fake_quotes)
    monkeypatch.setattr(app, "load_ce_sell_settings", lambda: {"price_markup_percent": 20.0})
    monkeypatch.setattr(
        app,
        "ce_sell_event_context",
        lambda current_candidate: {
            "next_result_date": current_candidate.get("next_result_date"),
            "result_event_risk": current_candidate.get("event_risk"),
            "result_event_detail": current_candidate.get("event_risk_reason"),
        },
    )


def test_ce_sell_snapshot_uses_income_growth_candidate_and_fresh_quote(monkeypatch):
    _install_unitdspr_ce_popup_fakes(monkeypatch)

    snapshot = app.ce_sell_order_snapshot("UNITDSPR")

    assert snapshot["underlying"] == "UNITDSPR"
    assert snapshot["symbol"] == "UNITDSPR26JUL1520CE"
    assert snapshot["ltp"] == 18.05
    assert snapshot["limit_price"] == 21.70
    assert snapshot["lots_to_sell"] == 1
    assert snapshot["quantity"] == 400
    assert snapshot["holding_qty"] == 1522
    assert snapshot["holding_source"] == "Income Growth holding record"
    assert snapshot["candidate_source"] == "Income Growth ready candidate"
    assert round(snapshot["premium_yield_percent"], 2) == 1.55
    assert round(snapshot["otm_percent"], 2) == 8.25
    assert snapshot["score"] == 100
    assert snapshot["next_result_date"] == "No result in next 5 days"


def test_place_approved_ce_sell_order_uses_snapshot_limit_and_quantity(monkeypatch):
    _install_unitdspr_ce_popup_fakes(monkeypatch)
    monkeypatch.setenv("KITE_CONFIRM_LIVE_ORDER", "YES")
    monkeypatch.setattr(app, "invalidate_kite_trade_cache", lambda: None)
    monkeypatch.setattr(app, "clear_app_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "selected_kite_profile_name", lambda: "Shanti")

    sent = {}

    def fake_send(_kite, order, allow_retry):
        sent["order"] = dict(order)
        sent["allow_retry"] = allow_retry
        return "OID123", "placed"

    monkeypatch.setattr(app, "send_order_with_lpp_retry", fake_send)

    result = app.place_approved_ce_sell_order("UNITDSPR")

    assert result["status"] == "LIVE_SENT"
    assert result["order_id"] == "OID123"
    assert sent["allow_retry"] is True
    assert sent["order"]["tradingsymbol"] == "UNITDSPR26JUL1520CE"
    assert sent["order"]["transaction_type"] == "SELL"
    assert sent["order"]["quantity"] == 400
    assert sent["order"]["price"] == 21.70
    assert sent["order"]["tag"] == "TOP3_CE"
    assert "above fresh LTP 18.05" in result["detail"]


def test_ce_sell_dashboard_embeds_page_snapshot(monkeypatch):
    monkeypatch.setattr(app, "load_ce_sell_settings", lambda: {"price_markup_percent": 20.0})
    monkeypatch.setattr(
        app,
        "ce_sell_event_context",
        lambda current_candidate: {
            "next_result_date": current_candidate.get("next_result_date"),
            "result_event_risk": current_candidate.get("event_risk"),
            "result_event_detail": current_candidate.get("event_risk_reason"),
        },
    )
    state = app.PageState(ce_sell_top=[_unitdspr_top3_item()])

    html = app.render_ce_sell_dashboard(state)

    assert "data-ce-snapshot=" in html
    assert "UNITDSPR26JUL1520CE" in html
    assert "&quot;ltp&quot;:18.05" in html
    assert "&quot;limit_price&quot;:21.7" in html


def test_place_approved_ce_sell_order_uses_client_snapshot_fast_path(monkeypatch):
    _install_unitdspr_ce_popup_fakes(monkeypatch)
    monkeypatch.setenv("KITE_CONFIRM_LIVE_ORDER", "YES")
    monkeypatch.setattr(app, "invalidate_kite_trade_cache", lambda: None)
    monkeypatch.setattr(app, "clear_app_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "selected_kite_profile_name", lambda: "Shanti")
    snapshot = app.ce_sell_card_snapshot_payload(_unitdspr_top3_item())
    snapshot["snapshot_created_at"] = app.time.time()

    def fail_if_slow_path(*_args, **_kwargs):
        raise AssertionError("client snapshot should avoid fresh CE scan / quote path")

    monkeypatch.setattr(app, "ce_sell_dashboard", fail_if_slow_path)
    monkeypatch.setattr(app, "income_growth_candidates", fail_if_slow_path)
    monkeypatch.setattr(app, "cached_kite_quote", fail_if_slow_path)
    monkeypatch.setattr(app, "covered_ce_holding_source", fail_if_slow_path)

    sent = {}

    def fake_send(_kite, order, allow_retry):
        sent["order"] = dict(order)
        sent["allow_retry"] = allow_retry
        return "OID456", "placed"

    monkeypatch.setattr(app, "send_order_with_lpp_retry", fake_send)

    result = app.place_approved_ce_sell_order("UNITDSPR", snapshot)

    assert result["status"] == "LIVE_SENT"
    assert result["order_id"] == "OID456"
    assert sent["order"]["tradingsymbol"] == "UNITDSPR26JUL1520CE"
    assert sent["order"]["quantity"] == 400
    assert sent["order"]["price"] == 21.70
    assert "above latest page LTP 18.05" in result["detail"]


def test_ce_sell_modal_uses_wide_metric_layout_hooks():
    source = Path("app.py").read_text(encoding="utf-8-sig")

    assert 'class="income-equity-metrics ce-sell-metrics"' in source
    assert 'class="ce-sell-wide"' in source
    assert 'class="ce-sell-full"' in source
    assert "#ce-sell-order-modal .ce-sell-metrics" in source
    assert 'id="ce-sell-snapshot"' in source
    assert "data-ce-snapshot" in source
    assert "parseCeSellSnapshot" in source
    assert "applyCeSellData" in source
