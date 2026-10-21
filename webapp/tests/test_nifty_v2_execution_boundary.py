"""No broker adapter is instantiated by these isolated execution-boundary tests."""
import ast
import logging
from pathlib import Path

import pytest

from nifty_options_engine.config import income_v2_config


@pytest.fixture(scope="module")
def legacy_execute():
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8-sig"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "execute_nifty_orders")
    scope = {"Any": object, "logger": logging.getLogger("test-nifty"),
             "nifty_income_config": lambda: {"nifty_income_v2": income_v2_config()}}
    # No broker or OS globals: reaching those paths would fail the test.
    exec(compile(ast.Module(body=[function], type_ignores=[]), "isolated-execution", "exec"), scope)
    return scope["execute_nifty_orders"]


@pytest.mark.parametrize("mode", ["SUGGESTION_ONLY", "PAPER", "DRY_RUN"])
def test_nonlive_modes_never_reach_a_broker(legacy_execute, mode):
    result = legacy_execute([{"tradingsymbol": "NIFTYTEST23000PE", "transaction_type": "SELL"}],
                            mode, "Entry preview")
    assert result[0]["status"] == mode


@pytest.mark.parametrize("override", [False, True])
def test_legacy_acceptance_only_path_cannot_send_short(legacy_execute, override):
    orders = [{"tradingsymbol": "NIFTYTEST22700PE", "transaction_type": "BUY"},
              {"tradingsymbol": "NIFTYTEST23000PE", "transaction_type": "SELL"}]
    with pytest.raises(PermissionError, match="durable hedge-fill"):
        legacy_execute(orders, "LIVE_CONFIRMED", "New NIFTY entry", override)


def test_defaults_and_nonremovable_safety_requirements():
    config = income_v2_config({"countdown_seconds": 1, "no_naked_nifty_sell": False})
    assert config["default_lots"] == 2 and config["default_hedge_width_points"] == 300
    assert config["entry_mode"] == "SUGGESTION_ONLY" and config["live_enabled"] is False
    assert config["countdown_seconds"] == 10 and config["no_naked_nifty_sell"]


@pytest.mark.parametrize("values", [
    {"max_total_nifty_defined_loss_inr": 60001},
    {"default_lots": 0.5},
    {"live_enabled": "false"},
    {"credit_capture_target_pct": 101},
    {"preferred_entry_dte_min": 40},
    {"allowed_strategies": ["NAKED_SELL"]},
])
def test_invalid_settings_rejected(values):
    with pytest.raises(ValueError):
        income_v2_config(values)
