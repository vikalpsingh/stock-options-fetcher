"""Scoring engine for DHAN F&O sheet candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DhanFnoSheetFilters:
    min_wheel_score: float = 75.0
    max_itm_risk_pct: float = 10.0
    min_total_premium: float = 2500.0
    preferred_otm_lower: float = 5.0
    preferred_otm_upper: float = 12.0
    only_prime_selective: bool = False
    allowed_liquidity_tags: tuple[str, ...] = ("High", "Medium")


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return str(value or "").strip()


class DhanFnoSheetScoringEngine:
    """Scores sheet rows before live DHAN/Kite validation."""

    def __init__(self, filters: DhanFnoSheetFilters | None = None) -> None:
        self.filters = filters or DhanFnoSheetFilters()

    def score_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        reasons: list[str] = []
        wheel = _num(candidate.get("wheel_score"))
        total_premium = _num(candidate.get("total_premium"))
        otm = _num(candidate.get("otm_pct"))
        itm_risk = _num(candidate.get("itm_risk_pct"))
        liquidity = _text(candidate.get("liquidity_tag")).title()

        if wheel < self.filters.min_wheel_score:
            reasons.append("WHEEL_SCORE_BELOW_MIN")
        if itm_risk > self.filters.max_itm_risk_pct:
            reasons.append("ITM_RISK_ABOVE_MAX")
        if total_premium < self.filters.min_total_premium:
            reasons.append("TOTAL_PREMIUM_BELOW_MIN")
        if liquidity not in {tag.title() for tag in self.filters.allowed_liquidity_tags}:
            reasons.append("LIQUIDITY_NOT_ALLOWED")
        if self.filters.only_prime_selective and _text(candidate.get("wheel_action")).title() not in {"Prime", "Selective"}:
            reasons.append("NOT_PRIME_OR_SELECTIVE")
        if candidate.get("sheet_data_status") == "SHEET_DATA_MISSING":
            reasons.append("SHEET_DATA_MISSING")

        score = (
            self._wheel_score(wheel)
            + self._premium_score(total_premium)
            + self._otm_score(otm)
            + self._itm_risk_score(itm_risk)
            + self._liquidity_score(liquidity)
            + self._technical_score(candidate, reasons)
            + self._completeness_score(candidate)
        )
        if _text(candidate.get("wheel_action")).title() not in {"Prime", "Selective"}:
            score -= 2
            reasons.append("WHEEL_ACTION_NOT_PRIME_SELECTIVE")
        if _text(candidate.get("safety_band")).title() not in {"", "High"}:
            score -= 2
            reasons.append("SAFETY_BAND_NOT_HIGH")
        if _text(candidate.get("volatility_tag")).title() == "High":
            score -= 2
            reasons.append("HIGH_VOLATILITY")
        final_score = max(0.0, min(100.0, score))
        decision = "SHEET_PASS" if final_score >= 75 else "SHEET_WATCH" if final_score >= 60 else "SHEET_REVIEW"
        return {
            **candidate,
            "sheet_score": round(final_score, 2),
            "final_sheet_score": round(final_score, 2),
            "sheet_decision": decision,
            "decision": decision,
            "reason_codes": reasons,
            "sheet_reason": "; ".join(reasons) if reasons else "Sheet candidate scored successfully.",
            "trader_comment": self._comment(candidate, decision, reasons, final_score),
        }

    def filter_and_score(self, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        scored = [self.score_candidate(row) for row in candidates]
        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        rejected: list[dict[str, Any]] = []
        for row in scored:
            key = (str(row.get("symbol")), str(row.get("dhan_strategy")))
            existing = deduped.get(key)
            if existing is None or _num(row.get("final_sheet_score")) > _num(existing.get("final_sheet_score")):
                if existing is not None:
                    rejected.append({**existing, "sheet_decision": "SHEET_REVIEW", "reason_codes": [*existing.get("reason_codes", []), "DUPLICATE_LOWER_SCORE"]})
                deduped[key] = row
            else:
                rejected.append({**row, "sheet_decision": "SHEET_REVIEW", "reason_codes": [*row.get("reason_codes", []), "DUPLICATE_LOWER_SCORE"]})
        kept = list(deduped.values())
        kept.sort(key=lambda item: _num(item.get("final_sheet_score")), reverse=True)
        return kept, rejected

    def _wheel_score(self, wheel: float) -> float:
        if wheel >= 90:
            return 25
        if wheel >= 80:
            return 20
        if wheel >= 70:
            return 15
        if wheel >= 60:
            return 10
        if wheel <= 0:
            return 8
        return 5

    def _premium_score(self, total_premium: float) -> float:
        if total_premium >= 5000:
            return 15
        if total_premium >= 3000:
            return 11
        if total_premium >= 1500:
            return 7
        return 3

    def _otm_score(self, otm: float) -> float:
        if 5 <= otm <= 12:
            return 15
        if 3 <= otm < 5:
            return 9
        if 12 < otm <= 18:
            return 10
        if otm <= 0:
            return 6
        return 3 if otm < 3 else 5

    def _itm_risk_score(self, itm_risk: float) -> float:
        if itm_risk <= 0:
            return 6
        if itm_risk <= 3:
            return 15
        if itm_risk <= 7:
            return 12
        if itm_risk <= 10:
            return 8
        if itm_risk <= 15:
            return 4
        return 2

    def _liquidity_score(self, liquidity: str) -> float:
        tag = liquidity.upper()
        if tag == "HIGH":
            return 10
        if tag == "MEDIUM":
            return 7
        if tag == "ACCEPTABLE":
            return 6
        if tag == "LOW":
            return 2
        return 4

    def _technical_score(self, candidate: dict[str, Any], reasons: list[str]) -> float:
        strategy = _text(candidate.get("dhan_strategy"))
        rsi = _num(candidate.get("rsi_14"))
        rel = _num(candidate.get("relative_strength_3m"))
        one_m = _num(candidate.get("ret_1m_pct"))
        three_m = _num(candidate.get("ret_3m_pct"))
        score = 8.0
        if strategy == "BEAR_CALL_SPREAD":
            score += 5 if 40 <= rsi <= 60 else -3 if 60 < rsi <= 65 else -6 if rsi > 65 else 1 if rsi < 40 and rel < -10 else -2 if rsi < 40 else 0
            score += 2 if rel <= 5 else -6 if rel > 8 else -2
            score += -2 if one_m > 8 else 0
            if rsi > 65:
                reasons.append("CE_RSI_ABOVE_65")
        else:
            score += 5 if 45 <= rsi <= 68 else -5 if rsi < 40 else 2 if rsi > 68 else 0
            score += 5 if rel >= 20 else 2 if rel >= -3 else -4 if rel < -10 else 0
            score += -2 if rsi > 70 and rel < 30 else 0
            score += -3 if three_m < -15 else 0
            if rsi < 40:
                reasons.append("PE_RSI_BELOW_40")
        return max(0.0, min(15.0, score))

    def _completeness_score(self, candidate: dict[str, Any]) -> float:
        fields = [
            "spot_price", "strike", "premium", "lot_size", "total_premium", "otm_pct",
            "expiry", "days_to_expiry", "itm_risk_pct", "liquidity_tag", "wheel_score",
            "rsi_14", "relative_strength_3m",
        ]
        present = sum(1 for field in fields if candidate.get(field) not in {None, "", 0})
        return min(5.0, present / len(fields) * 5)

    def _comment(self, candidate: dict[str, Any], decision: str, reasons: list[str], score: float) -> str:
        side = "CE SELL" if candidate.get("dhan_strategy") == "BEAR_CALL_SPREAD" else "PE SELL"
        if decision == "SHEET_PASS":
            return f"{side} candidate looks suitable for DHAN evaluation. Sheet score {score:.1f}."
        if decision == "SHEET_WATCH":
            return f"{side} candidate is watch-only; review risk reasons before adding."
        return f"{side} needs review: {', '.join(reasons) or 'low score'}."
