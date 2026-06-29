from datetime import date, timedelta
from pathlib import Path

from position_lifecycle import PositionLifecycleManager
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
        "technical_data": {"close": 440, "ema20": 430, "ema50": 420, "rsi": 55, "volume": 1000, "avg_volume_20d": 1000},
        "market_data": {"nifty_close": 24000, "nifty_ema20": 23900, "nifty_ema50": 23500, "nifty_rsi": 55, "india_vix": 13, "vix_5d_change_pct": 0},
    }
    trade.update(overrides)
    return trade


def test_stop_loss_missing_blocks_trade():
    trade = base_trade(price=0, premium=0, stop_loss=0)
    decision = RiskVetoEngine().evaluate(trade)
    assert decision["decision"] == "BLOCKED"
    assert "STOPLOSS_MISSING" in decision["reason_codes"]


def test_event_within_5_trading_days_blocks_trade():
    trade = base_trade(event_data={"event_type": "earnings", "next_event_date": date.today() + timedelta(days=3)})
    decision = RiskVetoEngine().evaluate(trade)
    assert decision["decision"] == "BLOCKED"
    assert "EVENT_RISK" in decision["reason_codes"]


def test_ce_sell_during_nifty_strong_uptrend_blocks():
    trade = base_trade(
        option_type="CE",
        tradingsymbol="PFC26JUL500CE",
        strike=500,
        market_data={"nifty_close": 24500, "nifty_ema20": 24000, "nifty_ema50": 23500, "nifty_rsi": 62, "india_vix": 13},
    )
    decision = RiskVetoEngine().evaluate(trade)
    assert decision["decision"] in {"BLOCKED", "WATCH_ONLY"}
    assert "NIFTY_STRONG_UPTREND_AVOID_CE" in decision["reason_codes"]


def test_ce_sell_near_stock_breakout_blocks():
    trade = base_trade(
        option_type="CE",
        strike=500,
        technical_data={"close": 490, "high_52w": 500, "high_20d": 500, "rsi": 64, "volume": 1000, "avg_volume_20d": 1000},
    )
    decision = RiskVetoEngine().evaluate(trade)
    assert decision["decision"] == "BLOCKED"
    assert "STOCK_NEAR_BREAKOUT_AVOID_CE" in decision["reason_codes"]


def test_pe_sell_during_breakdown_blocks():
    trade = base_trade(technical_data={"close": 390, "ema20": 410, "ema50": 420, "rsi": 42, "volume": 2000, "avg_volume_20d": 1000})
    decision = RiskVetoEngine().evaluate(trade)
    assert decision["decision"] == "BLOCKED"
    assert "STOCK_BREAKDOWN_AVOID_PE" in decision["reason_codes"]


def test_vix_high_blocks_trade():
    trade = base_trade(market_data={"india_vix": 21})
    decision = RiskVetoEngine().evaluate(trade)
    assert decision["decision"] == "BLOCKED"
    assert "VIX_EXPANSION_BLOCK" in decision["reason_codes"]


def test_vix_moderate_expansion_reduces_size():
    trade = base_trade(
        option_type="CE",
        tradingsymbol="PFC26JUL500CE",
        strike=500,
        quantity=2600,
        market_data={"india_vix": 16},
    )
    decision = RiskVetoEngine().evaluate(trade)
    assert decision["decision"] == "REDUCE_SIZE"
    assert decision["recommended_quantity"] < trade["quantity"]


def test_low_premium_yield_blocks_trade():
    trade = base_trade(premium=0.1, price=0.1)
    decision = RiskVetoEngine().evaluate(trade)
    assert decision["decision"] == "BLOCKED"
    assert "LOW_PREMIUM_YIELD" in decision["reason_codes"]


def test_no_approved_trades_writes_empty_csv_and_reports(tmp_path: Path):
    orders = [base_trade(price=0, premium=0, stop_loss=0)]
    approved, decisions, artifacts = evaluate_and_write_orders(orders, tmp_path)
    assert approved == []
    assert artifacts["approved_count"] == 0
    assert Path(artifacts["approved_orders_path"]).read_text().strip() == "exchange,tradingsymbol,quantity,transaction_type,product,order_type,price,validity"
    assert "STOPLOSS_MISSING" in Path(artifacts["rejected_orders_path"]).read_text()
    assert "NO TRADE DAY" in Path(artifacts["no_trade_summary_path"]).read_text()


def test_profit_target_lifecycle(tmp_path: Path):
    manager = PositionLifecycleManager(tmp_path / "open_positions.csv")
    row = manager.evaluate_position({"option_type": "CE", "entry_premium": 10, "current_premium": 5, "expiry": date.today() + timedelta(days=10)})
    assert row["status"] == "PROFIT_TARGET_HIT"


def test_warning_lifecycle(tmp_path: Path):
    manager = PositionLifecycleManager(tmp_path / "open_positions.csv")
    row = manager.evaluate_position({"option_type": "CE", "entry_premium": 10, "current_premium": 20, "expiry": date.today() + timedelta(days=10)})
    assert row["status"] == "WARNING"


def test_hard_exit_lifecycle(tmp_path: Path):
    manager = PositionLifecycleManager(tmp_path / "open_positions.csv")
    row = manager.evaluate_position({"option_type": "CE", "entry_premium": 10, "current_premium": 30, "expiry": date.today() + timedelta(days=10)})
    assert row["status"] == "EXIT_NOW"
