"""Top-10 DHAN candidate engine for uploaded F&O opportunity sheets."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dhan_fno_sheet_importer import SUPPORTED_SHEETS, parse_fno_opportunities_xlsx
from dhan_fno_sheet_scoring import DhanFnoSheetFilters, DhanFnoSheetScoringEngine


OUTPUT_DIR = Path(__file__).resolve().with_name("dhan_fno_sheet_outputs")


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any, default: str = "") -> str:
    return str(value if value not in {None, ""} else default)


def _liquidity_score(value: Any) -> float:
    tag = str(value or "").strip().upper()
    return 100.0 if tag == "GREEN" else 70.0 if tag == "AMBER" else 0.0 if tag == "RED" else 50.0


def _risk_engine_score(value: Any) -> float:
    decision = str(value or "").strip().upper()
    return 100.0 if decision == "APPROVED" else 70.0 if decision == "REDUCE_SIZE" else 50.0 if decision == "WATCH_ONLY" else 0.0


def _spread_quality_score(row: dict[str, Any]) -> float:
    score = 0.0
    if _num(row.get("max_gain")) >= 5000:
        score += 25
    if _num(row.get("pop_estimate")) >= 70:
        score += 25
    if _num(row.get("return_on_risk_pct")) >= 10:
        score += 20
    if 0 < _num(row.get("max_loss")) <= 40000:
        score += 15
    if _num(row.get("net_credit")) > 0:
        score += 10
    if str(row.get("recommended_expiry") or "").upper() != "NO_TRADE":
        score += 5
    return min(100.0, score)


def _portfolio_fit_score(row: dict[str, Any]) -> float:
    if row.get("event_risk_flag"):
        return 20.0
    if str(row.get("dhan_strategy") or "") == "BEAR_CALL_SPREAD" and _num(row.get("holding_qty")) > 0:
        return 90.0
    return 65.0


def _hard_reject_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if str(row.get("pair_liquidity_condition") or "").upper() == "RED":
        reasons.append("LIVE_RED_LIQUIDITY")
    if _num(row.get("net_credit")) <= 0:
        reasons.append("LIVE_NET_CREDIT_NON_POSITIVE")
    if _num(row.get("max_loss")) <= 0:
        reasons.append("LIVE_MAX_LOSS_INVALID")
    if _num(row.get("max_loss")) > 40000:
        reasons.append("LIVE_MAX_LOSS_ABOVE_LIMIT")
    if _num(row.get("pop_estimate")) < 70:
        reasons.append("LIVE_POP_BELOW_MIN")
    if _num(row.get("max_gain")) < 5000:
        reasons.append("LIVE_MAX_GAIN_BELOW_MIN")
    if str(row.get("risk_decision") or "").upper() == "BLOCKED":
        reasons.append("LIVE_RISK_ENGINE_BLOCKED")
    return reasons


def _default_live_validation(candidate: dict[str, Any]) -> dict[str, Any]:
    # Used by unit tests or offline analysis. App routes pass a validator that
    # calls the existing DHAN/Kite spread builder.
    return {
        "cmp_kite": candidate.get("spot_price"),
        "recommended_expiry": "SHEET_ONLY",
        "sell_leg_tradingsymbol": "",
        "buy_leg_tradingsymbol": "",
        "sell_strike": candidate.get("strike"),
        "hedge_strike": 0,
        "sell_premium_live": candidate.get("premium"),
        "hedge_premium_live": 0,
        "net_credit": candidate.get("premium"),
        "max_gain": candidate.get("total_premium"),
        "max_loss": 30000,
        "breakeven": 0,
        "pop_estimate": max(50.0, min(95.0, 100.0 - _num(candidate.get("itm_risk_pct")) * 4)),
        "return_on_risk_pct": _num(candidate.get("total_premium")) / 30000 * 100,
        "pair_liquidity_condition": "GREEN" if str(candidate.get("liquidity_tag")).title() == "High" else "AMBER",
        "risk_decision": "APPROVED",
        "risk_reason": "Offline sheet validation only.",
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys or ["empty"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def export_dhan_fno_sheet_outputs(result: dict[str, Any], raw_candidates: list[dict[str, Any]], scored: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_csv(OUTPUT_DIR / "dhan_fno_sheet_raw_candidates.csv", raw_candidates)
    _write_csv(OUTPUT_DIR / "dhan_fno_sheet_scored_candidates.csv", scored)
    _write_csv(OUTPUT_DIR / "dhan_fno_sheet_top10.csv", result.get("top10") or [])
    _write_csv(OUTPUT_DIR / "dhan_fno_sheet_rejections.csv", rejected)
    (OUTPUT_DIR / "dhan_fno_sheet_import_summary.json").write_text(
        json.dumps({key: value for key, value in result.items() if key not in {"top10", "rejected"}}, indent=2, default=str),
        encoding="utf-8",
    )


def generate_dhan_top10_from_fno_sheet(
    uploaded_file: bytes,
    repository: Any | None = None,
    broker_adapter: Any | None = None,
    risk_engine: Any | None = None,
    *,
    selected_tabs: list[str] | tuple[str, ...] | None = None,
    min_wheel_score: float = 75,
    min_total_premium: float = 2500,
    max_itm_risk_pct: float = 10,
    allowed_liquidity_tags: tuple[str, ...] = ("High", "Medium"),
    preferred_otm_lower: float = 5,
    preferred_otm_upper: float = 12,
    only_prime_selective: bool = False,
    top_n: int = 10,
    source_file_name: str = "uploaded.xlsx",
    live_validator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tabs = tuple(selected_tabs or SUPPORTED_SHEETS)
    parsed = parse_fno_opportunities_xlsx(uploaded_file, selected_tabs=tabs, source_file_name=source_file_name)
    filters = DhanFnoSheetFilters(
        min_wheel_score=min_wheel_score,
        max_itm_risk_pct=max_itm_risk_pct,
        min_total_premium=min_total_premium,
        preferred_otm_lower=preferred_otm_lower,
        preferred_otm_upper=preferred_otm_upper,
        only_prime_selective=only_prime_selective,
        allowed_liquidity_tags=tuple(allowed_liquidity_tags),
    )
    scorer = DhanFnoSheetScoringEngine(filters)
    scored_candidates, rejected = scorer.filter_and_score(parsed["candidates"])
    strong = [row for row in scored_candidates if row.get("decision") == "PASS" or _num(row.get("final_sheet_score")) >= 75]
    validator = live_validator or _default_live_validation
    live_rows: list[dict[str, Any]] = []
    for row in strong:
        try:
            live = validator(row) or {}
        except Exception as exc:  # pragma: no cover - defensive for live adapters
            rejected.append({**row, "risk_reason": f"Live validation failed: {exc}", "reason_codes": [*row.get("reason_codes", []), "LIVE_VALIDATION_ERROR"]})
            continue
        combined = {
            **row,
            "company_name": row.get("symbol"),
            "spot_price_sheet": row.get("spot_price"),
            "sheet_strike": row.get("strike"),
            "sheet_premium": row.get("premium"),
            "sheet_total_premium": row.get("total_premium"),
            **live,
        }
        hard_reasons = _hard_reject_reasons(combined)
        if hard_reasons:
            rejected.append({**combined, "reason_codes": [*combined.get("reason_codes", []), *hard_reasons], "risk_reason": "; ".join(hard_reasons)})
            continue
        sheet_score = _num(combined.get("final_sheet_score"))
        dhan_eval = _spread_quality_score(combined)
        liquidity = _liquidity_score(combined.get("pair_liquidity_condition"))
        risk = _risk_engine_score(combined.get("risk_decision"))
        fit = _portfolio_fit_score(combined)
        final_score = sheet_score * 0.40 + dhan_eval * 0.20 + liquidity * 0.15 + risk * 0.15 + fit * 0.10
        combined.update(
            {
                "sheet_score": round(sheet_score, 2),
                "dhan_evaluation_score": round(dhan_eval, 2),
                "liquidity_score": round(liquidity, 2),
                "risk_engine_score": round(risk, 2),
                "portfolio_fit_score": round(fit, 2),
                "final_score": round(final_score, 2),
                "risk_reason": _text(combined.get("risk_reason")),
            }
        )
        live_rows.append(combined)
    live_rows.sort(key=lambda item: (_num(item.get("final_score")), _num(item.get("sheet_score"))), reverse=True)
    top10 = []
    for idx, row in enumerate(live_rows[:top_n], start=1):
        top10.append({"rank": idx, **row})
    result = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_file_name": source_file_name,
        "ce_rows_read": parsed["ce_rows_read"],
        "pe_rows_read": parsed["pe_rows_read"],
        "rows_after_basic_filter": len(scored_candidates),
        "rows_after_sheet_score": len(strong),
        "rows_after_live_validation": len(live_rows),
        "top10": top10,
        "rejected": rejected,
    }
    export_dhan_fno_sheet_outputs(result, parsed["candidates"], scored_candidates, rejected)
    return result

