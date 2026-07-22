"""Covered-call income engine.

The package keeps capacity, strike selection, expiry selection, and final
recommendation logic separate from the large web application module.
"""

from .capacity import calculate_covered_call_capacity
from .config import (
    CoveredCallConfig,
    COVERED_CALL_CONFIG,
    classify_income_symbol_category,
)
from .expiry_selector import select_monthly_expiry
from .models import (
    CoveredCallCapacity,
    CoveredCallInput,
    CoveredCallRecommendation,
    ExpiryChoice,
)
from .service import build_covered_call_recommendation
from .strike_selector import select_atr_guarded_call_strike

__all__ = [
    "CoveredCallCapacity",
    "CoveredCallConfig",
    "CoveredCallInput",
    "CoveredCallRecommendation",
    "ExpiryChoice",
    "COVERED_CALL_CONFIG",
    "build_covered_call_recommendation",
    "calculate_covered_call_capacity",
    "classify_income_symbol_category",
    "select_atr_guarded_call_strike",
    "select_monthly_expiry",
]

