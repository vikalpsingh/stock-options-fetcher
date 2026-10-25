"""Pure risk tests: no app import, broker adapters or runtime databases."""
import ast
from pathlib import Path

import pytest

from nifty_options_engine.reconciliation import reconcile_nifty_positions
from nifty_options_engine.risk_validator import calculate_nifty_portfolio_risk, strategy_risk_summary


def leg(strike, qty, price, kind="PE", expiry="2026-11-24", strategy="S1", account="A"):
    return dict(tradingsymbol=f"NIFTY{expiry}{strike}{kind}", strike=strike,
                quantity=qty, average_price=price, option_type=kind,
                expiry=expiry, strategy_id=strategy, account_id=account)


def vertical(expiry="2026-11-24", kind="PE", strategy="S1"):
    return [leg(23000, -130, 100, kind, expiry, strategy),
            leg(22700 if kind == "PE" else 23300, 130, 40, kind, expiry, strategy)]


def proposed(rows):
    return {"legs": [
        {**row, "quantity": abs(row["quantity"]),
         "transaction_type": "SELL" if row["quantity"] < 0 else "BUY",
         "bid": row["average_price"], "ask": row["average_price"], "price": 9999}
        for row in rows]}


def test_two_lots_live_size_width_exposure():
    rows = vertical()
    assert 300 * abs(rows[0]["quantity"]) == 39000
    result = calculate_nifty_portfolio_risk(rows)
    assert result["current_defined_max_loss"] == 31200
    assert result["risk_status"] == "PASS"


@pytest.mark.parametrize("kind", ["PE", "CE"])
def test_unhedged_short_unknown_blocks_entries_but_not_repair_or_exit(kind):
    result = calculate_nifty_portfolio_risk([vertical(kind=kind)[0]], proposed(vertical()))
    assert result["current_defined_max_loss"] is None
    assert result["projected_portfolio_max_loss"] is None
    assert result["risk_remaining"] is None
    assert result["risk_status"] == "BLOCK"
    assert result["allow_exit_orders"] and result["allow_hedge_repair_orders"]


def test_unrelated_positions_are_not_inferred_as_strategy():
    rows = vertical()
    for row in rows:
        row["strategy_id"] = ""
    result = calculate_nifty_portfolio_risk(rows)
    assert result["risk_status"] == "BLOCK"
    assert result["current_defined_max_loss"] is None


@pytest.mark.parametrize("field,value", [("expiry", "2026-12-29"),
                                        ("account_id", "B"), ("strategy_id", "S2"),
                                        ("strike", 23400), ("option_type", "CE")])
def test_incompatible_or_unowned_hedge_cannot_protect_short(field, value):
    rows = vertical()
    rows[1][field] = value
    assert calculate_nifty_portfolio_risk(rows)["risk_status"] == "BLOCK"


def test_hedge_quantity_cannot_be_reused():
    rows = vertical()
    rows.append(leg(23100, -130, 120))
    result = reconcile_nifty_positions(rows)
    assert result["block_new_entries"]
    assert sum(row["hedge_quantity"] for row in result["shorts"]) == 130


def test_partial_fill_is_not_full_protection():
    rows = vertical()
    rows[1]["quantity"] = 65
    result = reconcile_nifty_positions(rows)
    assert result["shorts"][0]["status"] == "PARTIAL_SPREAD"
    assert result["block_new_entries"]


def test_condor_uses_maximum_wing_and_total_credit():
    rows = vertical() + [leg(24000, -130, 100, "CE"), leg(24300, 130, 40, "CE")]
    result = calculate_nifty_portfolio_risk(rows)
    assert result["current_defined_max_loss"] == 23400  # (300 - 60 - 60) * 130


def test_distinct_expiries_are_added_without_calendar_netting():
    result = calculate_nifty_portfolio_risk(vertical() + vertical("2026-12-29", strategy="S2"), config={"max_total_nifty_defined_loss_inr":60000})
    assert result["current_defined_max_loss"] == 62400
    assert result["risk_status"] == "BLOCK"


def test_debit_cost_is_not_clipped_to_zero_credit():
    rows = vertical()
    rows[1]["average_price"] = 110
    assert calculate_nifty_portfolio_risk(rows)["current_defined_max_loss"] == 40300


def test_actual_bid_ask_not_optimistic_limit_drives_proposal():
    result = calculate_nifty_portfolio_risk([], proposed(vertical()))
    assert result["new_strategy_max_loss"] == 31200
    assert result["risk_status"] == "PASS"


@pytest.mark.parametrize("value", [None, 0, float("nan"), float("inf")])
def test_bad_executable_quote_is_blocked(value):
    candidate = proposed(vertical())
    candidate["legs"][0]["bid"] = value
    assert calculate_nifty_portfolio_risk([], candidate)["risk_status"] == "BLOCK"


def test_costs_and_hard_cap_cannot_be_overridden_by_ticket():
    candidate = {**proposed(vertical("2026-12-29")), "max_total_nifty_defined_loss_inr":999999}
    result = calculate_nifty_portfolio_risk(vertical(), candidate,
                                          config={"max_total_nifty_defined_loss_inr": 60000,
                                                  "estimated_execution_costs_inr": 250})
    assert result["risk_cap"] == 60000
    assert result["projected_portfolio_max_loss"] == 62650
    assert result["risk_status"] == "BLOCK"


def test_lone_long_hedge_includes_remaining_cost():
    result = calculate_nifty_portfolio_risk([vertical()[1]])
    assert result["current_defined_max_loss"] == 5200
    assert result["reconciliation"]["groups"][0]["status"] == "LONG_HEDGE_ONLY"


def test_legacy_ticket_summary_uses_explicit_quantity_and_executable_credit():
    legs = proposed(vertical())["legs"]
    for row in legs:
        row["lot_size"] = 65
    summary = strategy_risk_summary("BULL_PUT_SPREAD", legs)
    assert summary["gross_risk"] == 39000
    assert summary["max_loss"] == 31200
    assert summary["lots"] == 2
    assert summary["net_credit_value"] == 7800
    legs[1]["expiry"] = "2026-12-29"
    assert strategy_risk_summary("BULL_PUT_SPREAD", legs)["cap_status"] == "FAIL"


def test_missing_leg_quantity_is_not_replaced_by_historical_lot_size():
    legs = proposed(vertical())["legs"]
    del legs[0]["quantity"]
    summary = strategy_risk_summary("BULL_PUT_SPREAD", legs)
    assert summary["max_loss"] is None
    assert summary["cap_status"] == "FAIL"


def test_app_wrappers_preserve_unknown_risk_and_repair_permission():
    # Extract only pure functions. Importing app initializes the user's DB.
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8-sig"))
    names = {"calculate_current_nifty_defined_risk", "calculate_total_nifty_risk_after_order",
             "validate_nifty_risk_cap_after_repair_or_new_spread", "format_nifty_risk"}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    import math
    scope = {"Any": object, "math": math, "calculate_nifty_portfolio_risk": calculate_nifty_portfolio_risk,
             "_nifty_risk_positions": lambda rows: rows, "format_buy_amount": str}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "risk-wrapper", "exec"), scope)
    rows = [vertical()[0]]
    risk = scope["calculate_total_nifty_risk_after_order"](rows, proposed(vertical()))
    assert risk["cap_status"] == "FAIL" and risk["current_defined_risk"] is None
    assert scope["format_nifty_risk"](risk["current_defined_risk"]) == "UNKNOWN / UNCAPPED"
    repair = scope["validate_nifty_risk_cap_after_repair_or_new_spread"](
        rows, {"action_type": "CREATE_HEDGE", "orders": [{"transaction_type": "BUY"}]})
    assert repair["allowed"]
    assert repair["total_projected_max_loss"] is None
    additional = scope["validate_nifty_risk_cap_after_repair_or_new_spread"](
        rows, {"action_type": "SELL_AGAINST_LONG", "hedge_validity": "SAME_EXPIRY_FULL_HEDGE"})
    assert not additional["allowed"]


def test_configurable_loss_cap_controls_same_portfolio():
    from nifty_options_engine.config import income_v2_config
    assert income_v2_config()['max_total_nifty_defined_loss_inr']==100000
    rows=vertical()
    for row in rows:row['quantity']*=3
    assert calculate_nifty_portfolio_risk(rows,config=income_v2_config())['risk_status']=='PASS'
    assert calculate_nifty_portfolio_risk(rows,config=income_v2_config({'max_total_nifty_defined_loss_inr':60000}))['risk_status']=='BLOCK'
    assert calculate_nifty_portfolio_risk(rows,config=income_v2_config({'max_total_nifty_defined_loss_inr':120000}))['risk_status']=='PASS'
