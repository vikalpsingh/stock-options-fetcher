from datetime import date, timedelta
from pathlib import Path

from position_lifecycle import PositionLifecycleManager, recommended_action_for_status
from risk_engine import RiskVetoEngine, evaluate_and_write_orders


def base_trade(**overrides):
    trade = {
        "symbol": "PFC",
        "tradingsymbol": "PFC26JUL400PE",
        "option_type": "PE",
        "strike": 400,
        "expiry": date.today() + timedelta(days=20),
        "premium": 5,
        "price": 5,
        "lot_size": 1300,
        "quantity": 1300,
        "transaction_type": "SELL",
        "underlying_spot": 440,
        "available_cash": 1_000_000,
        "cash_data": {"available_cash_for_assignment": 1_000_000},
        "stop_loss": 15,
        "technical_data": {
            "close": 440,
            "ema20": 430,
            "ema50": 420,
            "rsi": 55,
            "volume": 1000,
            "avg_volume_20d": 1000,
        },
        "market_data": {
            "nifty_close": 24000,
            "nifty_ema20": 23900,
            "nifty_ema50": 23500,
            "nifty_rsi": 55,
            "india_vix": 13,
            "vix_5d_change_pct": 0,
        },
    }
    trade.update(overrides)
    return trade


def test_open_exit_now_position_blocks_new_sell():
    trade = base_trade(
        open_positions=[
            {
                "symbol": "CAMS",
                "tradingsymbol": "CAMS26JUL800PE",
                "status": "EXIT_NOW",
            }
        ]
    )
    decision = RiskVetoEngine().evaluate(trade)
    assert decision["decision"] == "BLOCKED"
    assert "EXISTING_POSITION_EXIT_REQUIRED" in decision["reason_codes"]


def test_two_warning_positions_block_new_sell():
    trade = base_trade(
        open_positions=[
            {"symbol": "CAMS", "tradingsymbol": "CAMS26JUL800PE", "status": "WARNING"},
            {"symbol": "HAVELLS", "tradingsymbol": "HAVELLS26JUL1300CE", "status": "WARNING"},
        ]
    )
    decision = RiskVetoEngine().evaluate(trade)
    assert decision["decision"] == "BLOCKED"
    assert "TOO_MANY_WARNING_POSITIONS" in decision["reason_codes"]


def test_same_symbol_open_position_blocks_new_sell():
    trade = base_trade(
        open_positions=[
            {"symbol": "PFC", "tradingsymbol": "PFC26JUL500CE", "status": "OPEN"},
        ]
    )
    decision = RiskVetoEngine().evaluate(trade)
    assert decision["decision"] == "BLOCKED"
    assert "SYMBOL_ALREADY_HAS_OPEN_POSITION" in decision["reason_codes"]


def test_lifecycle_data_missing_is_safe():
    manager = PositionLifecycleManager("unused.csv")
    row = manager.evaluate_position(
        {
            "option_type": "CE",
            "entry_premium": 0,
            "current_premium": 0,
            "expiry": date.today() + timedelta(days=10),
        }
    )
    assert row["status"] == "DATA_MISSING"
    assert row["recommended_action"] == "WAIT_FOR_LTP"


def test_lifecycle_recommended_actions():
    assert recommended_action_for_status("PROFIT_TARGET_HIT") == "BOOK_PROFIT"
    assert recommended_action_for_status("WARNING") == "WATCH_CLOSELY"
    assert recommended_action_for_status("EXIT_NOW") == "EXIT_NOW"
    assert recommended_action_for_status("ROLL_CANDIDATE") == "ROLL_OR_EXIT"


def test_exit_orders_use_buy_transaction_type(tmp_path: Path):
    manager = PositionLifecycleManager(tmp_path / "open_positions.csv")
    manager.save_positions(
        [
            {
                "position_id": "one",
                "entry_date": date.today().isoformat(),
                "symbol": "PFC",
                "tradingsymbol": "PFC26JUL400PE",
                "option_type": "PE",
                "strike": 400,
                "expiry": (date.today() + timedelta(days=20)).isoformat(),
                "quantity": -1300,
                "lot_size": 1300,
                "entry_premium": 10,
                "current_premium": 2,
                "target_exit_premium": 2.5,
                "warning_premium": 20,
                "hard_stop_premium": 30,
                "underlying_entry_price": 440,
                "current_underlying_price": 430,
                "status": "PROFIT_TARGET_HIT",
                "reason": "PE premium decayed 75% or more.",
                "last_checked_at": "",
            }
        ]
    )
    csv_text, report_text = manager.generate_exit_orders(["one"])
    assert "BUY" in csv_text
    assert "PFC26JUL400PE" in csv_text
    assert "BOOK_PROFIT" in report_text


def test_no_approved_trades_writes_empty_outputs(tmp_path: Path):
    orders = [base_trade(price=0, premium=0, stop_loss=0)]
    approved, decisions, artifacts = evaluate_and_write_orders(orders, tmp_path)
    assert approved == []
    assert decisions[0]["decision"] == "BLOCKED"
    assert Path(artifacts["approved_orders_path"]).read_text().strip() == (
        "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity"
    )
    assert "STOPLOSS_MISSING" in Path(artifacts["rejected_orders_path"]).read_text()
    assert "NO TRADE DAY" in Path(artifacts["no_trade_summary_path"]).read_text()
