"""Income Growth F&O universe used by the DHAN paired-spread page.

The rows in this module are intentionally deterministic application data. They
represent the user's current F&O-enabled Income Growth holdings and the maximum
covered CE lots allowed from share coverage. Kite is still the broker used for
option contract resolution and order placement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IncomeGrowthFnoHolding:
    symbol: str
    shares: int
    max_covered_lots: int
    coverage_note: str = ""

    @property
    def ce_sell_allowed(self) -> bool:
        return self.shares > 0 and self.max_covered_lots > 0


INCOME_GROWTH_FNO_HOLDINGS: tuple[IncomeGrowthFnoHolding, ...] = (
    IncomeGrowthFnoHolding("BAJFINANCE", 2310, 1),
    IncomeGrowthFnoHolding("TATACONSUM", 650, 1),
    IncomeGrowthFnoHolding("PGEL", 7350, 3),
    IncomeGrowthFnoHolding("TITAN", 182, 1),
    IncomeGrowthFnoHolding("ETERNAL", 11500, 2),
    IncomeGrowthFnoHolding("UNITDSPR", 1522, 2),
    IncomeGrowthFnoHolding("HAVELLS", 520, 1),
    IncomeGrowthFnoHolding("NAUKRI", 615, 1),
    IncomeGrowthFnoHolding("PFC", 3515, 2),
    IncomeGrowthFnoHolding("CAMS", 410, 1, "CE only if Kite lot size is fully covered."),
    IncomeGrowthFnoHolding("CDSL", 410, 1, "CE only if Kite lot size is fully covered."),
    IncomeGrowthFnoHolding("MAZDOCK", 475, 1),
    IncomeGrowthFnoHolding("NTPC", 927, 1, "CE only if Kite lot size is fully covered."),
    IncomeGrowthFnoHolding("WAAREEENER", 130, 1, "CE only if Kite lot size is fully covered."),
)

DHAN_EXCLUDED_NON_FNO_SYMBOLS = {"NUVAMA"}

INCOME_GROWTH_FNO_BY_SYMBOL: dict[str, IncomeGrowthFnoHolding] = {
    item.symbol: item for item in INCOME_GROWTH_FNO_HOLDINGS
}


def annotate_income_growth_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return a UI/evaluation row enriched with Income Growth holding metadata."""

    symbol = str(row.get("symbol") or "").upper().strip()
    holding = INCOME_GROWTH_FNO_BY_SYMBOL.get(symbol)
    if not holding:
        return row
    enriched = dict(row)
    enriched["stock_bucket"] = "INCOME_GROWTH_FNO"
    enriched["holding_qty"] = holding.shares
    enriched["is_current_holding"] = 1
    enriched["max_covered_lots"] = holding.max_covered_lots
    enriched["ce_sell_allowed"] = 1 if holding.ce_sell_allowed else 0
    enriched["coverage_note"] = holding.coverage_note
    return enriched


def seed_income_growth_fno_watchlist(repository: Any) -> int:
    """Upsert the user's Income Growth F&O holdings into the DHAN watchlist."""

    saved = 0
    for holding in INCOME_GROWTH_FNO_HOLDINGS:
        repository.upsert_watchlist(
            holding.symbol,
            holding.symbol,
            "INCOME_GROWTH",
            is_current_holding=holding.shares > 0,
            holding_qty=holding.shares,
            fno_enabled=True,
            gpt_view="EVALUATE_CE_PE" if holding.shares > 0 else "PE_ONLY",
            gpt_reason=holding.coverage_note or f"Shares: {holding.shares}; max covered CE lots: {holding.max_covered_lots}",
        )
        saved += 1
    return saved


def ce_coverage_reason(symbol: str, requested_lots: int, lot_size: int) -> str:
    """Return a blocking reason when a CE-side sell would exceed share coverage."""

    holding = INCOME_GROWTH_FNO_BY_SYMBOL.get(str(symbol or "").upper().strip())
    if not holding:
        return ""
    if not holding.ce_sell_allowed:
        return "CE_COVERAGE_BLOCKED_NO_SHARES"
    clean_lots = max(int(requested_lots or 0), 0)
    clean_lot_size = max(int(lot_size or 0), 0)
    if clean_lots > holding.max_covered_lots:
        return f"CE_COVERED_LOT_LIMIT_EXCEEDED_MAX_{holding.max_covered_lots}"
    if clean_lot_size <= 0:
        return "CE_LOT_SIZE_UNAVAILABLE_FOR_COVERAGE_CHECK"
    if holding.shares < clean_lots * clean_lot_size:
        return f"CE_NOT_FULLY_COVERED_BY_SHARES_{holding.shares}_LT_{clean_lots * clean_lot_size}"
    return ""


def ce_coverage_context(symbol: str, requested_lots: int, lot_size: int) -> dict[str, Any]:
    """Return advisory CE share-coverage context for hedged DHAN spreads.

    DHAN now places defined-risk CE spreads with a BUY hedge, so equity holding
    is helpful context but no longer a placement blocker. Covered-call-only
    validation remains in the Income/covered CE order flow.
    """

    holding = INCOME_GROWTH_FNO_BY_SYMBOL.get(str(symbol or "").upper().strip())
    clean_lots = max(int(requested_lots or 0), 0)
    clean_lot_size = max(int(lot_size or 0), 0)
    required_shares = clean_lots * clean_lot_size
    if not holding:
        return {
            "ce_share_coverage_status": "NOT_TRACKED",
            "ce_share_coverage_note": "No Income Growth share holding tracked; CE spread remains allowed because it has a BUY hedge.",
            "holding_qty": 0,
            "covered_lots": 0,
            "required_shares": required_shares,
        }
    covered_lots = (holding.shares // clean_lot_size) if clean_lot_size > 0 else 0
    fully_covered = clean_lot_size > 0 and holding.shares >= required_shares and clean_lots <= max(holding.max_covered_lots, covered_lots)
    if fully_covered:
        status = "COVERED_POSITIVE"
        note = f"Positive: you hold {holding.shares} shares; CE spread is additionally covered by stock for {clean_lots} lot(s)."
    elif holding.shares > 0:
        status = "PARTIAL_OR_NOT_COVERED"
        note = (
            f"Shares held: {holding.shares}; required for full stock cover: {required_shares}. "
            "CE spread is still allowed because the BUY hedge defines max loss."
        )
    else:
        status = "NO_SHARES"
        note = "No shares held; CE spread is still allowed because the BUY hedge defines max loss."
    return {
        "ce_share_coverage_status": status,
        "ce_share_coverage_note": note,
        "holding_qty": holding.shares,
        "covered_lots": covered_lots,
        "required_shares": required_shares,
        "max_covered_lots": holding.max_covered_lots,
    }
