"""Central risk veto engine for option-income trades."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import risk_config as cfg


KITE_ORDER_HEADERS = [
    "exchange",
    "tradingsymbol",
    "quantity",
    "transaction_type",
    "product",
    "order_type",
    "price",
    "validity",
]

REJECTED_ORDER_HEADERS = [
    "symbol",
    "tradingsymbol",
    "option_type",
    "strike",
    "expiry",
    "premium",
    "original_quantity",
    "decision",
    "risk_score",
    "reason_codes",
    "human_reason",
]


@dataclass
class RiskDecision:
    symbol: str = ""
    tradingsymbol: str = ""
    decision: str = "APPROVED"
    risk_score: int = 100
    reason_codes: list[str] = field(default_factory=list)
    human_reason: str = "Risk checks passed."
    recommended_quantity: int = 0
    stop_loss: float = 0.0
    target_price: float = 0.0
    risk_action_plan: str = ""
    target_exit_premium: float = 0.0
    warning_premium: float = 0.0
    hard_stop_premium: float = 0.0
    stop_loss_defined: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "tradingsymbol": self.tradingsymbol,
            "decision": self.decision,
            "risk_score": self.risk_score,
            "reason_codes": list(self.reason_codes),
            "human_reason": self.human_reason,
            "recommended_quantity": self.recommended_quantity,
            "stop_loss": self.stop_loss,
            "target_price": self.target_price,
            "entry_premium": None,
            "target_exit_premium": self.target_exit_premium,
            "warning_premium": self.warning_premium,
            "hard_stop_premium": self.hard_stop_premium,
            "stop_loss_defined": self.stop_loss_defined,
            "risk_action_plan": self.risk_action_plan,
        }


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def trading_days_between(start: date, end: date) -> int:
    if end <= start:
        return 0
    days = 0
    current = start
    while current < end:
        current = date.fromordinal(current.toordinal() + 1)
        if current.weekday() < 5:
            days += 1
    return days


def load_stock_buckets(path: str | Path | None = None) -> dict[str, str]:
    bucket_path = Path(path) if path else Path(__file__).with_name("stock_buckets.json")
    try:
        data = json.loads(bucket_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    mapping: dict[str, str] = {}
    for bucket, details in data.items():
        for symbol in details.get("symbols", []):
            mapping[str(symbol).upper()] = bucket
    return mapping


def add_stop_loss_plan(trade: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(trade)
    premium = _to_float(
        enriched.get("option_premium", enriched.get("premium", enriched.get("price")))
    )
    option_type = str(enriched.get("option_type") or "").upper()
    transaction_type = str(enriched.get("transaction_type") or "").upper()
    enriched["entry_premium"] = premium
    if transaction_type != "SELL" or option_type not in {"CE", "PE"} or premium <= 0:
        enriched["target_exit_premium"] = 0.0
        enriched["warning_premium"] = 0.0
        enriched["hard_stop_premium"] = 0.0
        enriched["stop_loss_defined"] = False
        enriched["risk_action_plan"] = ""
        return enriched
    if option_type == "CE":
        target = premium * (1 - cfg.CE_PROFIT_BOOKING_PCT / 100)
        warning = premium * cfg.CE_WARNING_MULTIPLIER
        hard_stop = premium * cfg.CE_HARD_EXIT_MULTIPLIER
        plan = (
            f"Book profit at {cfg.CE_PROFIT_BOOKING_PCT}% premium decay. "
            "Warning if premium doubles. Hard exit if premium triples or stock "
            "breaks out above resistance."
        )
    else:
        target = premium * (1 - cfg.PE_PROFIT_BOOKING_PCT / 100)
        warning = premium * cfg.PE_WARNING_MULTIPLIER
        hard_stop = premium * cfg.PE_HARD_EXIT_MULTIPLIER
        plan = (
            f"Book profit at {cfg.PE_PROFIT_BOOKING_PCT}% premium decay. "
            "Warning if premium doubles. Hard exit if premium triples or stock "
            "closes below EMA50 with high volume."
        )
    enriched["target_exit_premium"] = round(max(target, 0.05), 2)
    enriched["warning_premium"] = round(warning, 2)
    enriched["hard_stop_premium"] = round(hard_stop, 2)
    enriched["stop_loss"] = round(hard_stop, 2)
    enriched["stop_loss_defined"] = True
    enriched["risk_action_plan"] = plan
    return enriched


def evaluate_ce_sell_risk(
    trade: dict[str, Any],
    market_data: dict[str, Any] | None = None,
    technical_data: dict[str, Any] | None = None,
    portfolio_data: dict[str, Any] | None = None,
) -> list[str]:
    market = market_data or {}
    tech = technical_data or {}
    portfolio = portfolio_data or {}
    reasons: list[str] = []
    nifty_close = _to_float(market.get("nifty_close") or market.get("nifty_spot"))
    nifty_ema20 = _to_float(market.get("nifty_ema20"))
    nifty_ema50 = _to_float(market.get("nifty_ema50"))
    nifty_rsi = _to_float(market.get("nifty_rsi"))
    if (
        cfg.CE_AVOID_IF_NIFTY_STRONG_UPTREND
        and nifty_close > 0
        and nifty_close > nifty_ema20 > nifty_ema50 > 0
        and nifty_rsi > 60
    ):
        reasons.append("NIFTY_STRONG_UPTREND_AVOID_CE")
    close = _to_float(tech.get("close") or trade.get("underlying_spot"))
    rsi = _to_float(tech.get("rsi") or tech.get("RSI"))
    high_52w = _to_float(tech.get("high_52w") or tech.get("52_week_high"))
    high_20d = _to_float(tech.get("high_20d") or tech.get("20_day_high"))
    near_52 = high_52w > 0 and close > 0 and (high_52w - close) / high_52w * 100 <= cfg.CE_AVOID_IF_STOCK_NEAR_BREAKOUT_PCT
    near_20 = high_20d > 0 and close > 0 and (high_20d - close) / high_20d * 100 <= cfg.CE_AVOID_IF_STOCK_NEAR_BREAKOUT_PCT
    if (near_52 or near_20) and rsi > 60:
        reasons.append("STOCK_NEAR_BREAKOUT_AVOID_CE")
    ema20 = _to_float(tech.get("ema20"))
    ema50 = _to_float(tech.get("ema50"))
    volume = _to_float(tech.get("volume"))
    avg_volume = _to_float(tech.get("avg_volume_20d") or tech.get("20_day_average_volume"))
    if close > ema20 > ema50 > 0 and rsi > cfg.CE_AVOID_IF_RSI_ABOVE and volume > 1.5 * avg_volume > 0:
        reasons.append("STRONG_MOMENTUM_AVOID_CE")
    premium_yield = _to_float(trade.get("premium_yield_pct"))
    if premium_yield and premium_yield < cfg.CE_MIN_PREMIUM_YIELD_PCT:
        reasons.append("LOW_PREMIUM_YIELD")
    bucket = str(portfolio.get("bucket") or trade.get("bucket") or "").upper()
    strike = _to_float(trade.get("strike"))
    delta = abs(_to_float(trade.get("delta")))
    otm_pct = ((strike - close) / close * 100) if strike > 0 and close > 0 else _to_float(trade.get("otm_pct"))
    if bucket == "CORE_COMPOUNDER" and not (otm_pct >= 8 or (0 < delta <= 0.20)):
        reasons.append("CORE_HOLDING_UPSIDE_PROTECTION")
    return reasons


def evaluate_pe_sell_risk(
    trade: dict[str, Any],
    market_data: dict[str, Any] | None = None,
    technical_data: dict[str, Any] | None = None,
    portfolio_data: dict[str, Any] | None = None,
    cash_data: dict[str, Any] | None = None,
) -> list[str]:
    market = market_data or {}
    tech = technical_data or {}
    cash = cash_data or {}
    reasons: list[str] = []
    close = _to_float(tech.get("close") or trade.get("underlying_spot"))
    ema20 = _to_float(tech.get("ema20"))
    ema50 = _to_float(tech.get("ema50"))
    rsi = _to_float(tech.get("rsi") or tech.get("RSI"))
    volume = _to_float(tech.get("volume"))
    avg_volume = _to_float(tech.get("avg_volume_20d") or tech.get("20_day_average_volume"))
    high_volume = volume > 1.5 * avg_volume > 0
    if ((cfg.PE_AVOID_IF_STOCK_BELOW_EMA20 and close > 0 and ema20 > 0 and close < ema20) or (cfg.PE_AVOID_IF_STOCK_BELOW_EMA50 and close > 0 and ema50 > 0 and close < ema50)) and (high_volume or cfg.PE_AVOID_IF_HIGH_SELL_VOLUME):
        reasons.append("STOCK_BREAKDOWN_AVOID_PE")
    if ema20 > 0 and ema50 > 0 and ema20 < ema50 and rsi and rsi < 45:
        reasons.append("DOWNTREND_AVOID_PE")
    nifty_close = _to_float(market.get("nifty_close") or market.get("nifty_spot"))
    nifty_ema50 = _to_float(market.get("nifty_ema50"))
    vix = _to_float(market.get("india_vix") or market.get("vix"))
    if nifty_close > 0 and nifty_ema50 > 0 and nifty_close < nifty_ema50 and vix > cfg.VIX_BLOCK_NEW_TRADES_ABOVE:
        reasons.append("MARKET_RISK_AVOID_PE")
    strike = _to_float(trade.get("strike"))
    lot_size = _to_int(trade.get("lot_size"), 1)
    quantity = abs(_to_int(trade.get("quantity"), lot_size))
    lots = max(quantity / lot_size, 1) if lot_size > 0 else 1
    assignment_value = strike * lot_size * lots
    if assignment_value > _to_float(cash.get("available_cash_for_assignment") or trade.get("available_cash"), 0):
        reasons.append("NOT_CASH_SECURED")
    if assignment_value > cfg.MAX_ASSIGNMENT_VALUE_PER_STOCK:
        reasons.append("ASSIGNMENT_LIMIT_EXCEEDED")
    premium_yield = _to_float(trade.get("premium_yield_pct"))
    if premium_yield and premium_yield < cfg.PE_MIN_PREMIUM_YIELD_PCT:
        reasons.append("LOW_PREMIUM_YIELD")
    return reasons


def evaluate_open_position_portfolio_risk(
    trade: dict[str, Any],
    open_positions: list[dict[str, Any]],
) -> list[str]:
    """Block fresh income entries when existing positions need attention."""
    reasons: list[str] = []
    transaction_type = str(trade.get("transaction_type") or "").upper()
    if transaction_type != "SELL":
        return reasons
    symbol = str(trade.get("symbol") or "").upper()
    tradingsymbol = str(trade.get("tradingsymbol") or "").upper()
    warning_count = 0
    for row in open_positions or []:
        status = str(row.get("status") or "").upper()
        row_symbol = str(row.get("symbol") or "").upper()
        row_tradingsymbol = str(row.get("tradingsymbol") or "").upper()
        if status == "EXIT_NOW" and cfg.BLOCK_NEW_SELL_IF_ANY_EXIT_NOW:
            reasons.append("EXISTING_POSITION_EXIT_REQUIRED")
        if status == "WARNING":
            warning_count += 1
        if symbol and row_symbol == symbol and status not in {"", "CLOSED"}:
            reasons.append("SYMBOL_ALREADY_HAS_OPEN_POSITION")
        elif tradingsymbol and row_tradingsymbol == tradingsymbol and status not in {"", "CLOSED"}:
            reasons.append("SYMBOL_ALREADY_HAS_OPEN_POSITION")
    if warning_count >= cfg.OPEN_POSITION_WARNING_BLOCK_COUNT:
        reasons.append("TOO_MANY_WARNING_POSITIONS")
    return reasons


class RiskVetoEngine:
    """Evaluates proposed option trades and returns approve/block decisions."""

    def __init__(self, stock_buckets: dict[str, str] | None = None):
        self.stock_buckets = stock_buckets if stock_buckets is not None else load_stock_buckets()

    def evaluate(self, trade: dict[str, Any]) -> dict[str, Any]:
        enriched = add_stop_loss_plan(trade)
        symbol = str(enriched.get("symbol") or "").upper()
        tradingsymbol = str(enriched.get("tradingsymbol") or symbol).upper()
        option_type = str(enriched.get("option_type") or "").upper()
        transaction_type = str(enriched.get("transaction_type") or "").upper()
        quantity = abs(_to_int(enriched.get("quantity"), 0))
        lot_size = max(_to_int(enriched.get("lot_size"), quantity or 1), 1)
        premium = _to_float(enriched.get("entry_premium"))
        spot = _to_float(enriched.get("underlying_spot") or enriched.get("spot"))
        strike = _to_float(enriched.get("strike"))
        market = dict(enriched.get("market_data") or {})
        tech = dict(enriched.get("technical_data") or {})
        event = dict(enriched.get("event_data") or {})
        portfolio = dict(enriched.get("portfolio_data") or {})
        cash = dict(enriched.get("cash_data") or {})
        open_positions = list(enriched.get("open_positions") or portfolio.get("open_positions") or [])
        if symbol and "bucket" not in portfolio:
            portfolio["bucket"] = self.stock_buckets.get(symbol)
        reason_codes: list[str] = []
        warnings: list[str] = []
        decision = "APPROVED"
        recommended_quantity = quantity

        if transaction_type == "SELL" and option_type in {"CE", "PE"}:
            reason_codes.extend(evaluate_open_position_portfolio_risk(enriched, open_positions))
            if cfg.BLOCK_ORDER_IF_STOPLOSS_MISSING and not enriched.get("stop_loss_defined"):
                reason_codes.append("STOPLOSS_MISSING")
            expiry = _parse_date(enriched.get("expiry"))
            today = _parse_date(enriched.get("as_of_date")) or date.today()
            if expiry:
                days_to_expiry = trading_days_between(today, expiry)
                if days_to_expiry < cfg.BLOCK_NEW_TRADES_IF_DAYS_TO_EXPIRY_LESS_THAN:
                    reason_codes.append("EXPIRY_WEEK_RISK")
            else:
                warnings.append("MISSING_EXPIRY")
            event_type = str(event.get("event_type") or enriched.get("event_type") or "").lower()
            event_date = _parse_date(event.get("next_event_date") or enriched.get("next_event_date"))
            event_days = trading_days_between(today, event_date) if event_date else None
            if event_type in cfg.EVENT_TYPES_TO_BLOCK and event_days is not None and event_days <= cfg.BLOCK_IF_EVENT_WITHIN_TRADING_DAYS:
                reason_codes.append("EVENT_RISK")
            if not tech:
                warnings.append("MISSING_TECHNICAL_DATA")
            if not market:
                warnings.append("MISSING_MARKET_DATA")
            capital_at_risk = 0.0
            lots = max(quantity / lot_size, 1) if lot_size > 0 else 1
            if option_type == "CE":
                capital_at_risk = spot * lot_size * lots
            elif option_type == "PE":
                capital_at_risk = strike * lot_size * lots
            premium_received = premium * quantity
            premium_yield_pct = premium_received / capital_at_risk * 100 if capital_at_risk > 0 else 0.0
            enriched["premium_yield_pct"] = premium_yield_pct
            if option_type == "CE" and premium_yield_pct < cfg.CE_MIN_PREMIUM_YIELD_PCT:
                reason_codes.append("LOW_PREMIUM_YIELD")
            if option_type == "PE" and premium_yield_pct < cfg.PE_MIN_PREMIUM_YIELD_PCT:
                reason_codes.append("LOW_PREMIUM_YIELD")
            vix = _to_float(market.get("india_vix") or market.get("vix"))
            vix_change = _to_float(market.get("vix_5d_change_pct") or market.get("vix_5day_change"))
            if vix > cfg.VIX_BLOCK_NEW_TRADES_ABOVE or vix_change > cfg.VIX_5D_EXPANSION_BLOCK_PCT:
                reason_codes.append("VIX_EXPANSION_BLOCK")
            elif vix > cfg.VIX_REDUCE_SIZE_ABOVE or vix_change > cfg.VIX_5D_EXPANSION_REDUCE_PCT:
                decision = "REDUCE_SIZE"
                recommended_quantity = max(lot_size, int(quantity * 0.5 // lot_size * lot_size)) if quantity >= lot_size else max(1, int(quantity * 0.5))
                reason_codes.append("VIX_EXPANSION_REDUCE_SIZE")
            monthly_loss_pct = _to_float(enriched.get("monthly_loss_pct") or market.get("monthly_loss_pct"))
            if monthly_loss_pct >= cfg.MAX_OPTION_LOSS_PER_MONTH_PCT:
                reason_codes.append("MONTHLY_LOSS_LIMIT_REACHED")
            elif monthly_loss_pct >= cfg.MAX_OPTION_LOSS_PER_MONTH_PCT * 0.75:
                decision = "REDUCE_SIZE"
                recommended_quantity = max(lot_size, int(quantity * 0.5 // lot_size * lot_size)) if quantity >= lot_size else max(1, int(quantity * 0.5))
                reason_codes.append("MONTHLY_LOSS_LIMIT_NEAR")
            if option_type == "CE":
                ce_reasons = evaluate_ce_sell_risk(enriched, market, tech, portfolio)
                reason_codes.extend(ce_reasons)
            elif option_type == "PE":
                pe_reasons = evaluate_pe_sell_risk(enriched, market, tech, portfolio, cash)
                reason_codes.extend(pe_reasons)
            bucket = str(portfolio.get("bucket") or "").upper()
            if bucket == "HIGH_VOLATILITY_GROWTH" and not any(code.endswith("BLOCK") for code in reason_codes):
                decision = "REDUCE_SIZE"
                recommended_quantity = max(lot_size, int(quantity * 0.5 // lot_size * lot_size)) if quantity >= lot_size else max(1, int(quantity * 0.5))
                reason_codes.append("HIGH_VOLATILITY_BUCKET_REDUCE_SIZE")

        reason_codes = list(dict.fromkeys(reason_codes + warnings))
        hard_blocks = [
            code for code in reason_codes
            if code not in {"VIX_EXPANSION_REDUCE_SIZE", "MONTHLY_LOSS_LIMIT_NEAR", "HIGH_VOLATILITY_BUCKET_REDUCE_SIZE", "MISSING_TECHNICAL_DATA", "MISSING_MARKET_DATA", "MISSING_EXPIRY"}
        ]
        if hard_blocks:
            decision = "BLOCKED"
            recommended_quantity = 0
        if decision == "APPROVED" and any(code in reason_codes for code in ("MISSING_TECHNICAL_DATA", "MISSING_MARKET_DATA")):
            # Missing optional data should be visible but should not block by itself.
            pass
        risk_score = max(0, 100 - 15 * len(hard_blocks) - 5 * (len(reason_codes) - len(hard_blocks)))
        if decision == "BLOCKED":
            risk_score = min(risk_score, 40)
        elif decision == "REDUCE_SIZE":
            risk_score = min(risk_score, 70)
        human_reason = (
            "Risk engine blocked trade: " + ", ".join(reason_codes)
            if decision == "BLOCKED"
            else "Risk engine recommends smaller size: " + ", ".join(reason_codes)
            if decision == "REDUCE_SIZE"
            else "Risk checks passed." + (f" Warnings: {', '.join(warnings)}." if warnings else "")
        )
        result = RiskDecision(
            symbol=symbol,
            tradingsymbol=tradingsymbol,
            decision=decision,
            risk_score=int(risk_score),
            reason_codes=reason_codes,
            human_reason=human_reason,
            recommended_quantity=int(recommended_quantity),
            stop_loss=_to_float(enriched.get("stop_loss")),
            target_price=_to_float(enriched.get("target_exit_premium")),
            risk_action_plan=str(enriched.get("risk_action_plan") or ""),
            target_exit_premium=_to_float(enriched.get("target_exit_premium")),
            warning_premium=_to_float(enriched.get("warning_premium")),
            hard_stop_premium=_to_float(enriched.get("hard_stop_premium")),
            stop_loss_defined=bool(enriched.get("stop_loss_defined")),
        ).to_dict()
        result["entry_premium"] = premium
        result["premium_yield_pct"] = enriched.get("premium_yield_pct")
        return result


def kite_order_from_trade(order: dict[str, Any], quantity: int | None = None) -> dict[str, Any]:
    return {
        "exchange": order.get("exchange", "NFO"),
        "tradingsymbol": order.get("tradingsymbol") or order.get("symbol"),
        "quantity": quantity if quantity is not None else order.get("quantity"),
        "transaction_type": order.get("transaction_type"),
        "product": order.get("product", "NRML"),
        "order_type": order.get("order_type", "LIMIT"),
        "price": order.get("price", 0),
        "validity": order.get("validity", "DAY"),
    }


def write_risk_outputs(
    proposed_orders: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    approved_path = output_path / "approved_orders.csv"
    rejected_path = output_path / "rejected_orders.csv"
    summary_path = output_path / "no_trade_summary.txt"
    approved_count = 0
    rejected_count = 0
    with approved_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=KITE_ORDER_HEADERS, lineterminator="\n")
        writer.writeheader()
        for order, decision in zip(proposed_orders, decisions):
            if decision.get("decision") in {"APPROVED", "REDUCE_SIZE"}:
                quantity = int(decision.get("recommended_quantity") or order.get("quantity") or 0)
                if quantity <= 0:
                    continue
                writer.writerow(kite_order_from_trade(order, quantity))
                approved_count += 1
    with rejected_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REJECTED_ORDER_HEADERS, lineterminator="\n")
        writer.writeheader()
        for order, decision in zip(proposed_orders, decisions):
            if decision.get("decision") == "BLOCKED":
                writer.writerow(
                    {
                        "symbol": decision.get("symbol") or order.get("symbol"),
                        "tradingsymbol": decision.get("tradingsymbol") or order.get("tradingsymbol"),
                        "option_type": order.get("option_type", ""),
                        "strike": order.get("strike", ""),
                        "expiry": order.get("expiry", ""),
                        "premium": order.get("premium", order.get("price", "")),
                        "original_quantity": order.get("quantity", ""),
                        "decision": decision.get("decision"),
                        "risk_score": decision.get("risk_score"),
                        "reason_codes": "|".join(decision.get("reason_codes") or []),
                        "human_reason": decision.get("human_reason"),
                    }
                )
                rejected_count += 1
    if approved_count == 0:
        reasons = []
        for decision in decisions:
            reasons.extend(decision.get("reason_codes") or [])
        reason_labels = {
            "EVENT_RISK": "Event risk",
            "LOW_PREMIUM_YIELD": "Low premium yield",
            "NIFTY_STRONG_UPTREND_AVOID_CE": "Nifty strong uptrend",
            "STOCK_NEAR_BREAKOUT_AVOID_CE": "Stock near breakout",
            "VIX_EXPANSION_BLOCK": "VIX expansion",
            "STOPLOSS_MISSING": "Stop-loss missing",
            "EXPIRY_WEEK_RISK": "Expiry week risk",
        }
        lines = ["NO TRADE DAY", ""]
        seen = set()
        for code in reasons:
            label = reason_labels.get(code)
            if label and label not in seen:
                lines.append(f"- {label}")
                seen.add(label)
        if len(lines) == 2:
            lines.append("- Risk engine blocked all proposed trades")
        summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        summary_path.write_text(
            f"Approved trades: {approved_count}\nRejected trades: {rejected_count}\n",
            encoding="utf-8",
        )
    return {
        "approved_orders_path": str(approved_path),
        "rejected_orders_path": str(rejected_path),
        "no_trade_summary_path": str(summary_path),
        "approved_count": approved_count,
        "rejected_count": rejected_count,
    }


def evaluate_and_write_orders(
    orders: list[dict[str, Any]],
    output_dir: str | Path,
    engine: RiskVetoEngine | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    engine = engine or RiskVetoEngine()
    decisions = [engine.evaluate(order) for order in orders]
    artifacts = write_risk_outputs(orders, decisions, output_dir)
    approved: list[dict[str, Any]] = []
    for order, decision in zip(orders, decisions):
        if decision.get("decision") in {"APPROVED", "REDUCE_SIZE"}:
            updated = dict(order)
            updated["quantity"] = int(decision.get("recommended_quantity") or order.get("quantity") or 0)
            updated["risk_decision"] = decision
            approved.append(updated)
    return approved, decisions, artifacts
