from __future__ import annotations

from dataclasses import dataclass

from ..models.market_snapshot import MarketSnapshot


@dataclass(frozen=True)
class LiquidityResult:
    score: float
    status: str
    maximum_allocation_pct: float
    limit_order_only: bool
    warnings: list[str]


def analyze_liquidity(market: MarketSnapshot, market_type: str) -> LiquidityResult:
    score = 0.0
    warnings: list[str] = []
    traded_value = market.average_traded_value_20d
    if traded_value is not None:
        score += 40 if traded_value >= 50_000_000 else 30 if traded_value >= 10_000_000 else 15
    else:
        warnings.append("20-day traded value missing")
    spread = market.bid_ask_spread_pct
    if spread is not None:
        score += 25 if spread <= 0.5 else 15 if spread <= 1.5 else 5
    else:
        warnings.append("bid/ask spread missing")
    zero_days = market.zero_volume_days_20d
    if zero_days is not None:
        score += 20 if zero_days == 0 else 10 if zero_days <= 2 else 0
    else:
        warnings.append("zero-volume-day history missing")
    circuit_frequency = market.circuit_limit_frequency
    if circuit_frequency is not None:
        score += 15 if circuit_frequency <= 0.05 else 7 if circuit_frequency <= 0.2 else 0
    else:
        warnings.append("circuit frequency missing")
    if market_type.strip().upper() == "SME":
        score = max(0.0, score - 10)
    status = "GOOD" if score >= 80 else "ACCEPTABLE" if score >= 60 else "WEAK" if score >= 40 else "ILLIQUID"
    allocation = 3.0 if status == "GOOD" else 1.5 if status == "ACCEPTABLE" else 0.5 if status == "WEAK" else 0.25
    if market_type.strip().upper() == "SME":
        allocation = min(allocation, 0.5 if status in {"WEAK", "ILLIQUID"} else 1.0)
    return LiquidityResult(score, status, allocation, True, warnings)
