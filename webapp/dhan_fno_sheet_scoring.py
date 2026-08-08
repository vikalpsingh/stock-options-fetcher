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
        reject = False
        wheel = _num(candidate.get("wheel_score"))
        total_premium = _num(candidate.get("total_premium"))
        premium_yield = _num(candidate.get("premium_yield_pct"))
        otm = _num(candidate.get("otm_pct"))
        itm_risk = _num(candidate.get("itm_risk_pct"))
        liquidity = _text(candidate.get("liquidity_tag")).title()
        action = _text(candidate.get("wheel_action")).title()
        safety = _text(candidate.get("safety_band")).title()
        volatility = _text(candidate.get("volatility_tag")).title()

        if wheel < self.filters.min_wheel_score:
            reasons.append("WHEEL_SCORE_BELOW_MIN")
            reject = True
        if itm_risk > self.filters.max_itm_risk_pct:
            reasons.append("ITM_RISK_ABOVE_MAX")
            reject = True
        if total_premium < self.filters.min_total_premium:
            reasons.append("TOTAL_PREMIUM_BELOW_MIN")
        if liquidity not in {tag.title() for tag in self.filters.allowed_liquidity_tags}:
            reasons.append("LIQUIDITY_NOT_ALLOWED")
            reject = True
        if self.filters.only_prime_selective and action not in {"Prime", "Selective"}:
            reasons.append("NOT_PRIME_OR_SELECTIVE")
            reject = True

        score = 0.0
        score += 20 if wheel >= 95 else 17 if wheel >= 90 else 13 if wheel >= 80 else 8 if wheel >= 70 else 0
        score += self._premium_score(total_premium, premium_yield)
        score += self._otm_score(otm)
        score += 15 if itm_risk <= 3 else 11 if itm_risk <= 7 else 6 if itm_risk <= 10 else 0
        score += 10 if liquidity == "High" else 6 if liquidity == "Medium" else 0
        score += self._technical_score(candidate, reasons)

        penalty = self._risk_penalty(candidate, reasons)
        final_score = max(0.0, min(100.0, score - penalty))
        decision = "REJECT" if reject or final_score < 70 else "PASS" if final_score >= 80 else "WATCH_ONLY"
        return {
            **candidate,
            "sheet_score": round(score, 2),
            "risk_penalty": round(penalty, 2),
            "final_sheet_score": round(final_score, 2),
            "decision": decision,
            "reason_codes": reasons,
            "trader_comment": self._comment(candidate, decision, reasons, final_score),
        }

    def filter_and_score(self, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        scored = [self.score_candidate(row) for row in candidates]
        deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
        rejected: list[dict[str, Any]] = []
        for row in scored:
            key = (str(row.get("symbol")), str(row.get("dhan_strategy")), str(row.get("expiry")))
            existing = deduped.get(key)
            if existing is None or _num(row.get("final_sheet_score")) > _num(existing.get("final_sheet_score")):
                if existing is not None:
                    rejected.append({**existing, "decision": "REJECT", "reason_codes": [*existing.get("reason_codes", []), "DUPLICATE_LOWER_SCORE"]})
                deduped[key] = row
            else:
                rejected.append({**row, "decision": "REJECT", "reason_codes": [*row.get("reason_codes", []), "DUPLICATE_LOWER_SCORE"]})
        kept = list(deduped.values())
        rejected.extend([row for row in kept if row.get("decision") == "REJECT"])
        return [row for row in kept if row.get("decision") != "REJECT"], rejected

    def _premium_score(self, total_premium: float, premium_yield: float) -> float:
        base = 10 if total_premium >= 5000 else 7 if total_premium >= 3000 else 3 if total_premium >= self.filters.min_total_premium else 0
        yield_bonus = 5 if 0.5 <= premium_yield <= 3.0 else 3 if 0 < premium_yield <= 5.0 else 0
        return base + yield_bonus

    def _otm_score(self, otm: float) -> float:
        if self.filters.preferred_otm_lower <= otm <= self.filters.preferred_otm_upper:
            return 15
        if 3 <= otm < self.filters.preferred_otm_lower:
            return 8
        if self.filters.preferred_otm_upper < otm <= 15:
            return 10
        if otm > 15:
            return 5
        return 0

    def _technical_score(self, candidate: dict[str, Any], reasons: list[str]) -> float:
        strategy = _text(candidate.get("dhan_strategy"))
        rsi = _num(candidate.get("rsi_14"))
        rel = _num(candidate.get("relative_strength_3m"))
        dip = _text(candidate.get("dip_signal")).lower()
        one_m = _num(candidate.get("ret_1m_pct"))
        three_m = _num(candidate.get("ret_3m_pct"))
        score = 10.0
        if strategy == "BEAR_CALL_SPREAD":
            score += 4 if 40 <= rsi <= 60 else -5 if rsi > 65 else 0
            score += 3 if rel <= 5 else -4 if rel > 12 else 0
            score += -3 if "dip" in dip and "no" not in dip else 1
            score += -3 if one_m > 8 else 0
            if rsi > 65:
                reasons.append("CE_RSI_ABOVE_65")
        else:
            score += 4 if 45 <= rsi <= 65 else -5 if rsi < 40 else 0
            score += 3 if rel >= -3 else -4 if rel < -10 else 0
            score += -3 if "dip" in dip and one_m < -8 else 1
            score += -3 if three_m < -15 else 0
            if rsi < 40:
                reasons.append("PE_RSI_BELOW_40")
        return max(0.0, min(15.0, score))

    def _risk_penalty(self, candidate: dict[str, Any], reasons: list[str]) -> float:
        penalty = 0.0
        if _text(candidate.get("liquidity_tag")).title() == "Low":
            penalty += 8
        if _text(candidate.get("wheel_action")).title() not in {"Prime", "Selective"}:
            penalty += 4
            reasons.append("WHEEL_ACTION_NOT_PRIME_SELECTIVE")
        if _text(candidate.get("safety_band")).title() != "High":
            penalty += 4
            reasons.append("SAFETY_BAND_NOT_HIGH")
        if _text(candidate.get("volatility_tag")).title() == "High":
            penalty += 4
            reasons.append("HIGH_VOLATILITY")
        if _num(candidate.get("days_to_expiry")) < 7:
            penalty += 4
            reasons.append("EXPIRY_TOO_CLOSE")
        for key, code in (("insider_activity", "INSIDER_ACTIVITY_FLAG"), ("block_bulk_activity", "BLOCK_BULK_ACTIVITY_FLAG")):
            value = _text(candidate.get(key)).lower()
            if value and any(word in value for word in ("sell", "negative", "suspicious", "pledge")):
                penalty += 3
                reasons.append(code)
        return min(20.0, penalty)

    def _comment(self, candidate: dict[str, Any], decision: str, reasons: list[str], score: float) -> str:
        side = "CE SELL" if candidate.get("dhan_strategy") == "BEAR_CALL_SPREAD" else "PE SELL"
        if decision == "PASS":
            return f"{side} candidate looks suitable for DHAN evaluation. Sheet score {score:.1f}."
        if decision == "WATCH_ONLY":
            return f"{side} candidate is watch-only; review risk reasons before adding."
        return f"{side} rejected: {', '.join(reasons) or 'low score'}."

