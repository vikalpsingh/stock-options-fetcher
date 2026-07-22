"""Configurable covered-call risk thresholds.

The values are intentionally plain Python constants/dataclasses so the web app
can import them without adding new runtime dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field


CORE_COMPOUNDER = "CORE_COMPOUNDER"
INCOME_STOCK = "INCOME_STOCK"
HIGH_VOLATILITY_GROWTH = "HIGH_VOLATILITY_GROWTH"
NORMAL = "NORMAL"


@dataclass(frozen=True)
class CoveredCallCategoryRule:
    """Per-stock-bucket limits for covered CALL selling."""

    max_total_covered_pct: float
    min_otm_pct: float
    max_otm_pct: float
    atr_multiplier: float
    max_recommended_lots: int


@dataclass(frozen=True)
class CoveredCallConfig:
    """Covered-call strategy configuration.

    target_expiry_min_dte / target_expiry_max_dte:
        Prefer next monthly contracts in this trading-days/calendar-days window.

    min_opening_dte:
        New covered-call entries below this DTE are blocked.

    min_premium_yield_pct:
        Premium divided by stock value covered by one lot. Low yield is blocked
        because it caps upside without paying enough income.
    """

    target_expiry_min_dte: int = 28
    target_expiry_max_dte: int = 42
    min_opening_dte: int = 20
    min_premium_yield_pct: float = 0.60
    stale_quote_after_seconds: int = 60
    default_user_max_lots: int = 1
    category_rules: dict[str, CoveredCallCategoryRule] = field(
        default_factory=lambda: {
            CORE_COMPOUNDER: CoveredCallCategoryRule(
                max_total_covered_pct=20.0,
                min_otm_pct=10.0,
                max_otm_pct=12.5,
                atr_multiplier=2.75,
                max_recommended_lots=1,
            ),
            INCOME_STOCK: CoveredCallCategoryRule(
                max_total_covered_pct=40.0,
                min_otm_pct=8.0,
                max_otm_pct=12.5,
                atr_multiplier=2.00,
                max_recommended_lots=1,
            ),
            HIGH_VOLATILITY_GROWTH: CoveredCallCategoryRule(
                max_total_covered_pct=15.0,
                min_otm_pct=12.0,
                max_otm_pct=12.5,
                atr_multiplier=3.00,
                max_recommended_lots=1,
            ),
            NORMAL: CoveredCallCategoryRule(
                max_total_covered_pct=30.0,
                min_otm_pct=9.0,
                max_otm_pct=12.5,
                atr_multiplier=2.25,
                max_recommended_lots=1,
            ),
        }
    )


COVERED_CALL_CONFIG = CoveredCallConfig()


CORE_SYMBOLS = {"BAJFINANCE", "TATACONSUM", "TITAN", "CAMS", "CDSL", "NAUKRI"}
INCOME_SYMBOLS = {"PFC", "NTPC", "HAVELLS", "UNITDSPR"}
HIGH_VOL_SYMBOLS = {"PGEL", "ETERNAL", "WAAREE", "WAAREEENER", "MAZDOCK"}


def classify_income_symbol_category(
    symbol: str,
    *,
    core: str | bool | None = None,
    sector: str | None = None,
) -> str:
    """Map a holding to a risk bucket used by the covered-call engine."""

    clean = (symbol or "").upper().replace("NSE:", "").replace("BSE:", "").strip()
    if clean in HIGH_VOL_SYMBOLS:
        return HIGH_VOLATILITY_GROWTH
    if clean in INCOME_SYMBOLS:
        return INCOME_STOCK
    if clean in CORE_SYMBOLS or core is True or str(core or "").upper() == "Y":
        return CORE_COMPOUNDER
    sector_text = (sector or "").lower()
    if any(token in sector_text for token in ("defence", "energy", "quick", "growth")):
        return HIGH_VOLATILITY_GROWTH
    return NORMAL

