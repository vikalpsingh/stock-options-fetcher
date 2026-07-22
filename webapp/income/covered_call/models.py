"""Data models for covered-call recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class ExpiryChoice:
    expiry: date | None
    dte: int | None
    decision: str
    reason: str


@dataclass(frozen=True)
class CoveredCallInput:
    symbol: str
    holding_qty: int
    lot_size: int
    spot_price: float
    strike: float | None = None
    expiry: date | None = None
    premium: float | None = None
    user_max_lots: int | None = None
    category: str = "NORMAL"
    today_change_pct: float | None = None
    week_change_pct: float | None = None
    month_change_pct: float | None = None
    existing_short_ce_qty: int = 0


@dataclass(frozen=True)
class CoveredCallCapacity:
    symbol: str
    holding_qty: int
    lot_size: int
    capacity_lots: int
    existing_short_ce_lots: int
    unencumbered_shares: int
    max_lots_by_coverage_pct: int
    recommended_lots: int
    recommended_quantity: int
    max_total_covered_pct: float
    current_covered_pct: float
    recommended_covered_pct: float
    reason_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CoveredCallRecommendation:
    symbol: str
    decision: str
    score: int
    capacity: CoveredCallCapacity
    recommended_lots: int
    recommended_quantity: int
    strike: float | None
    expiry: date | None
    dte: int | None
    premium: float | None
    max_profit: float
    premium_yield_pct: float
    otm_pct: float | None
    reason_codes: list[str]
    explanation: str
    category: str
    risk_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

