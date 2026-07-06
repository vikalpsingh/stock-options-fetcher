from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


DEFAULT_NIFTY_NO_TRADE_REGIME = {
    "enabled": True,
    "skip_if_vix_below": 11.0,
    "skip_if_vix_above": 24.0,
    "min_premium_yield_on_margin_pct": 0.8,
    "event_risk_enabled": True,
    "event_risk_lookahead_trading_days": 3,
    "event_types": [
        "RBI_POLICY",
        "FED_POLICY",
        "UNION_BUDGET",
        "ELECTION_RESULT",
        "CPI_INFLATION",
        "MAJOR_GEOPOLITICAL_EVENT",
    ],
    "trend_breakout_filter_enabled": True,
    "skip_on_strong_breakout": True,
    "skip_on_strong_breakdown": True,
    "stop_loss_guard_enabled": True,
    "max_consecutive_stop_losses_this_month": 2,
    "monthly_loss_guard_enabled": True,
    "monthly_nifty_loss_limit_pct_of_nifty_margin": 5.0,
    "override_allowed": False,
    "override_requires_manual_confirmation": True,
}


NO_TRADE_MESSAGES = {
    "NO_TRADE_LOW_VIX_POOR_PREMIUM": "India VIX below 11. Premium is not worth selling.",
    "NO_TRADE_HIGH_VIX_UNCERTAINTY": "India VIX above 24. Uncertainty is too high for new income trades.",
    "NO_TRADE_POOR_PREMIUM_YIELD": "Premium yield on margin is below 0.8%.",
    "NO_TRADE_MAJOR_EVENT_WITHIN_3_DAYS": "Major RBI/Fed/Budget/election/event risk within 3 trading days.",
    "NO_TRADE_STRONG_BREAKOUT": "Strong bullish breakout detected. Avoid new CE/strangle/condor income entries.",
    "NO_TRADE_STRONG_BREAKDOWN": "Strong bearish breakdown detected. Avoid new PE/strangle/condor income entries.",
    "NO_TRADE_TWO_CONSECUTIVE_STOP_LOSSES": "Two consecutive NIFTY strategy stop-losses this month. New entries disabled.",
    "NO_TRADE_MONTHLY_LOSS_LIMIT_REACHED": "Monthly NIFTY loss limit reached. New entries disabled until reset.",
}


NO_TRADE_PRIORITY = [
    "NO_TRADE_MONTHLY_LOSS_LIMIT_REACHED",
    "NO_TRADE_TWO_CONSECUTIVE_STOP_LOSSES",
    "NO_TRADE_MAJOR_EVENT_WITHIN_3_DAYS",
    "NO_TRADE_HIGH_VIX_UNCERTAINTY",
    "NO_TRADE_STRONG_BREAKOUT",
    "NO_TRADE_STRONG_BREAKDOWN",
    "NO_TRADE_LOW_VIX_POOR_PREMIUM",
    "NO_TRADE_POOR_PREMIUM_YIELD",
]


@dataclass
class NoTradeDecision:
    allowed: bool
    no_trade: bool
    severity: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocking_reason: str | None = None
    can_manual_override: bool = False
    evaluated_at: datetime = field(default_factory=datetime.now)
    inputs_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evaluated_at"] = self.evaluated_at.isoformat()
        return value


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, "", "N/A", "NA", "--"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _event_is_blocking(event: dict[str, Any], config: dict[str, Any]) -> bool:
    event_type = str(event.get("event_type") or event.get("type") or "").upper()
    if event_type not in {str(item).upper() for item in config.get("event_types", [])}:
        return False
    lookahead = _int_value(config.get("event_risk_lookahead_trading_days") or 3)
    if "trading_days_to_event" in event:
        return _int_value(event.get("trading_days_to_event")) <= lookahead
    event_date = event.get("event_date") or event.get("date")
    current_date = event.get("current_date")
    if isinstance(event_date, str):
        try:
            event_date = date.fromisoformat(event_date[:10])
        except ValueError:
            event_date = None
    if isinstance(current_date, str):
        try:
            current_date = date.fromisoformat(current_date[:10])
        except ValueError:
            current_date = None
    if isinstance(event_date, date):
        current_date = current_date if isinstance(current_date, date) else date.today()
        return 0 <= (event_date - current_date).days <= lookahead
    return False


def next_blocking_event(inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
    events = inputs.get("event_calendar") or []
    if isinstance(events, dict):
        events = [events]
    current_date = inputs.get("current_date")
    candidates: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event = {**event, "current_date": current_date}
        if _event_is_blocking(event, config):
            candidates.append(event)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: _int_value(item.get("trading_days_to_event") or 999))[0]


def evaluate_nifty_no_trade_regime(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> NoTradeDecision:
    cfg = dict(DEFAULT_NIFTY_NO_TRADE_REGIME)
    if isinstance(config, dict):
        cfg.update(config)
    evaluated_at = inputs.get("evaluated_at")
    if not isinstance(evaluated_at, datetime):
        evaluated_at = datetime.now()
    warnings: list[str] = []
    reasons: list[str] = []
    if not bool(cfg.get("enabled", True)):
        return NoTradeDecision(
            allowed=True,
            no_trade=False,
            severity="INFO",
            warnings=["NIFTY No Trade regime is disabled."],
            evaluated_at=evaluated_at,
            inputs_snapshot=dict(inputs),
        )

    india_vix = _float_or_none(inputs.get("india_vix"))
    premium_yield = _float_or_none(inputs.get("premium_yield_on_margin_pct"))
    trend_regime = str(inputs.get("trend_regime") or "").upper()
    breakout = bool(inputs.get("breakout_status"))
    breakdown = bool(inputs.get("breakdown_status"))
    stop_losses = _int_value(inputs.get("consecutive_stop_losses_this_month"))
    monthly_loss_pct = _float_or_none(inputs.get("monthly_loss_pct_of_nifty_margin"))

    if india_vix is None:
        warnings.append("India VIX missing; VIX no-trade rule not applied.")
    elif india_vix < float(cfg.get("skip_if_vix_below") or 11):
        reasons.append("NO_TRADE_LOW_VIX_POOR_PREMIUM")
    elif india_vix > float(cfg.get("skip_if_vix_above") or 24):
        reasons.append("NO_TRADE_HIGH_VIX_UNCERTAINTY")

    if premium_yield is None:
        warnings.append("Premium yield on margin missing; premium no-trade rule not applied.")
    elif premium_yield < float(cfg.get("min_premium_yield_on_margin_pct") or 0.8):
        reasons.append("NO_TRADE_POOR_PREMIUM_YIELD")

    event = next_blocking_event(inputs, cfg) if bool(cfg.get("event_risk_enabled", True)) else None
    if event:
        reasons.append("NO_TRADE_MAJOR_EVENT_WITHIN_3_DAYS")

    if bool(cfg.get("trend_breakout_filter_enabled", True)):
        if bool(cfg.get("skip_on_strong_breakout", True)) and (trend_regime == "STRONG_BULLISH" or breakout):
            reasons.append("NO_TRADE_STRONG_BREAKOUT")
        if bool(cfg.get("skip_on_strong_breakdown", True)) and (trend_regime == "STRONG_BEARISH" or breakdown):
            reasons.append("NO_TRADE_STRONG_BREAKDOWN")

    if bool(cfg.get("stop_loss_guard_enabled", True)) and stop_losses >= _int_value(cfg.get("max_consecutive_stop_losses_this_month") or 2):
        reasons.append("NO_TRADE_TWO_CONSECUTIVE_STOP_LOSSES")

    if bool(cfg.get("monthly_loss_guard_enabled", True)):
        limit = abs(float(cfg.get("monthly_nifty_loss_limit_pct_of_nifty_margin") or 5.0))
        if monthly_loss_pct is not None and monthly_loss_pct <= -limit:
            reasons.append("NO_TRADE_MONTHLY_LOSS_LIMIT_REACHED")

    ordered_reasons = [reason for reason in NO_TRADE_PRIORITY if reason in set(reasons)]
    blocking_reason = ordered_reasons[0] if ordered_reasons else None
    override_allowed = bool(cfg.get("override_allowed", False))
    if blocking_reason in {
        "NO_TRADE_MONTHLY_LOSS_LIMIT_REACHED",
        "NO_TRADE_TWO_CONSECUTIVE_STOP_LOSSES",
    }:
        override_allowed = False
    if india_vix is not None and india_vix > 30:
        override_allowed = False
    if event:
        event_type = str(event.get("event_type") or event.get("type") or "").upper()
        event_days = _int_value(event.get("trading_days_to_event") or 999)
        if event_type in {"UNION_BUDGET", "ELECTION_RESULT"} and event_days <= 1:
            override_allowed = False

    return NoTradeDecision(
        allowed=not bool(blocking_reason),
        no_trade=bool(blocking_reason),
        severity="BLOCK" if blocking_reason else ("WARNING" if warnings else "INFO"),
        reasons=ordered_reasons,
        warnings=warnings,
        blocking_reason=blocking_reason,
        can_manual_override=override_allowed and bool(blocking_reason),
        evaluated_at=evaluated_at,
        inputs_snapshot={
            **dict(inputs),
            "next_major_event": event,
        },
    )


def no_trade_reason_messages(reasons: list[str]) -> list[str]:
    return [NO_TRADE_MESSAGES.get(reason, reason) for reason in reasons]
