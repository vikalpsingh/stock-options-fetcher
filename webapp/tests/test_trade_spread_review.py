import ast
import math
from pathlib import Path

import pytest

from trade_execution_ui import render_spread_summary


def preview():
    return dict(strategy_type="BEAR_CALL_SPREAD", symbol="TEST", mode="PAPER",
                expiry="2026-11-24", hedge_revalidated=True, net_credit=80, max_profit=80,
                max_loss=20, spread_pop=75, short_leg_pop=70, breakeven=108,
                spread_width=10, quantity=10, initial_margin=100, final_margin=50,
                credit_margin_pct=160, hedge_symbol="TEST110CE", short_symbol="TEST100CE",
                hedge_bid=1, hedge_ask=2, hedge_limit_price=2, hedge_cost=20,
                short_bid=10, short_ask=11, short_limit_price=10, short_premium=100)


def test_summary_groups_revalidated_metrics_and_both_legs():
    markup = render_spread_summary(preview(), [{"status": "PASS"}])
    for text in ("Revalidated spread", "Net credit", "Maximum profit", "Maximum loss",
                 "Spread POP", "75.00%", "₹80.00", "₹20.00", "₹108.00", "TEST110CE",
                 "TEST100CE", "Initial margin", "before charges", "CHECKS PASSED"):
        assert text in markup
    assert "risk-neutral" in markup
    assert "70.00%" in markup


def test_blocked_selected_hedge_still_displays_candidate_metrics():
    candidate = preview()
    markup = render_spread_summary(
        {"selected_hedge_symbol": candidate["hedge_symbol"], "hedge_alternatives": [candidate]},
        [{"status": "BLOCK", "name": "Margin", "reason": "<unsafe>"}],
    )
    assert "REVIEW BLOCKED" in markup
    assert "₹80.00" in markup
    assert "&lt;unsafe&gt;" in markup
    assert "<unsafe>" not in markup


def test_missing_pop_is_unavailable_not_short_leg_pop():
    data = preview()
    data["spread_pop"] = None
    markup = render_spread_summary(data)
    assert "<strong>Unavailable</strong><small>Model estimate at breakeven" in markup
    assert "No estimate is substituted" in markup


def test_execution_snapshot_does_not_claim_live_values_or_repeat_legs():
    markup = render_spread_summary(preview(), snapshot=True)
    assert "REVIEW SNAPSHOT" in markup
    assert "Values are not live P&amp;L" in markup
    assert "spread-leg-table" not in markup


@pytest.fixture(scope="module")
def probability_model():
    # Reuse the app's model without importing its runtime/database initialization.
    source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in {"normal_cdf", "bs_d1", "calculate_probability_expiry_itm"}]
    namespace = {"math": math}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "model", "exec"), namespace)
    return namespace["calculate_probability_expiry_itm"]


@pytest.mark.parametrize("kind,breakeven,better", [("CE", 108, 109), ("PE", 92, 91)])
def test_pop_changes_with_spread_breakeven(probability_model, kind, breakeven, better):
    def pop(strike):
        return 100 - probability_model(kind, spot=100, strike=strike, dte=30, iv=.3, rate=.065)
    assert 0 < pop(breakeven) < pop(better) < 100


def test_model_does_not_invent_pop_without_iv_or_time(probability_model):
    assert probability_model("CE", spot=100, strike=108, dte=30, iv=None) is None
    assert probability_model("CE", spot=100, strike=108, dte=0, iv=.3) is None
