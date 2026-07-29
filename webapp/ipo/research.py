from __future__ import annotations

import csv
import json
import math
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ipo.peers.peer_selector import infer_research_theme, select_sector_leaders, select_top_peers
from ipo.symbol_resolution.symbol_resolver import clean_company_name, normalize_symbol, resolve_symbol

try:
    from ipo_data_service import _enrich_simple_ipo_decision
except Exception:  # pragma: no cover - app can still run if the IPO service changes.
    _enrich_simple_ipo_decision = None


IPO_RESEARCH_CUSTOM_GPT_URL = (
    "https://chatgpt.com/g/g-6a031ff323688191872d730b281c71f0-next-multi-bagger-of-indian-market"
)

RESEARCH_INDEX_FIELDS = [
    "research_id",
    "research_date",
    "symbols_key",
    "company_names",
    "peer_names",
    "sector",
    "final_action",
    "value_score",
    "html_path",
    "json_path",
    "created_at",
    "notes",
]

FINANCIAL_FIELDS = {
    "latest_revenue_growth_yoy",
    "revenue_growth_yoy",
    "sales_growth_yoy",
    "latest_quarter_revenue_growth",
    "latest_pat_growth_yoy",
    "pat_growth_yoy",
    "profit_growth_yoy",
    "latest_quarter_pat_growth",
    "cfo_pat",
    "cfo",
    "free_cash_flow",
    "roce",
    "roe",
    "opm",
    "operating_margin",
    "pe",
    "pe_ratio",
    "peer_median_pe",
}

SHAREHOLDING_FIELDS = {
    "promoter_holding",
    "promoter_pledge",
    "pledge_pct",
    "promoter_change_qoq",
    "pledge_change_qoq",
    "fii_holding",
    "dii_holding",
}


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value in {None, "", "N/A", "NA", "-", "--"}:
        return default
    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").replace("₹", "").strip()
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _has_value(value: Any) -> bool:
    if value in {None, "", "N/A", "NA", "-", "--"}:
        return False
    return str(value).strip() != ""


def _now() -> datetime:
    return datetime.now()


def today_key(as_of: datetime | None = None) -> str:
    return (as_of or _now()).strftime("%Y%m%d")


def _safe_key_part(value: Any) -> str:
    text = normalize_symbol(value) or clean_company_name(value).upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    return text.strip("_") or "IPO"


def symbols_key_for_rows(rows: list[dict[str, Any]], as_of: datetime | None = None) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for row in rows:
        part = _safe_key_part(row.get("symbol") or row.get("company_name"))
        if part and part not in seen:
            seen.add(part)
            parts.append(part)
    return f"{'_'.join(parts[:8])}_{today_key(as_of)}"


def financial_data_available(row: dict[str, Any]) -> bool:
    status = str(row.get("financial_data_status") or "").strip().lower()
    if status.startswith("financial data available"):
        return True
    return any(_has_value(row.get(field)) for field in FINANCIAL_FIELDS)


def shareholding_data_available(row: dict[str, Any]) -> bool:
    return any(_has_value(row.get(field)) for field in SHAREHOLDING_FIELDS)


def data_quality_score(row: dict[str, Any], has_peer_data: bool = False) -> dict[str, Any]:
    resolution = row.get("resolution") or {}
    symbol_confidence = safe_float(
        resolution.get("resolution_confidence") or row.get("symbol_resolution_confidence"),
        0,
    ) or 0
    score = 0
    missing: list[str] = []

    if _has_value(row.get("listing_date")) and _has_value(row.get("ipo_price")):
        score += 15
    else:
        missing.append("IPO/listing data")

    if symbol_confidence >= 85:
        score += 20
    else:
        missing.append("verified symbol")

    if _has_value(row.get("current_price") or row.get("ltp")):
        score += 15
    else:
        missing.append("current price")

    if financial_data_available(row):
        score += 25
    else:
        missing.append("quarterly/financial data")

    if shareholding_data_available(row):
        score += 10
    else:
        missing.append("shareholding data")

    if has_peer_data:
        score += 10
    else:
        missing.append("peer data")

    if _has_value(row.get("liquidity_score") or row.get("average_volume") or row.get("volume")):
        score += 5
    else:
        missing.append("liquidity data")

    if score < 60:
        status = "RESEARCH_ONLY"
    elif score < 80:
        status = "WATCHLIST_ONLY"
    elif score < 90:
        status = "FULL_SCORE"
    else:
        status = "PEER_ADJUSTED"
    return {"score": int(score), "status": status, "missing_fields": missing}


def value_score_from_row(row: dict[str, Any]) -> float | None:
    existing = safe_float(row.get("value_score") or row.get("lt_score"))
    if existing is not None:
        return round(existing, 2)
    if not financial_data_available(row):
        return None

    score = 0.0
    sector_score = safe_float(row.get("sector_score") or row.get("sector_quality_score"), 55) or 55
    revenue_growth = safe_float(
        row.get("latest_revenue_growth_yoy") or row.get("revenue_growth_yoy") or row.get("sales_growth_yoy"),
        0,
    ) or 0
    pat_growth = safe_float(
        row.get("latest_pat_growth_yoy") or row.get("pat_growth_yoy") or row.get("profit_growth_yoy"),
        0,
    ) or 0
    roce = safe_float(row.get("roce"), 0) or 0
    roe = safe_float(row.get("roe"), 0) or 0
    cfo_pat = safe_float(row.get("cfo_pat"), 0) or 0
    debt_to_equity = safe_float(row.get("debt_to_equity"), 0) or 0
    pe = safe_float(row.get("pe") or row.get("pe_ratio"))
    peer_pe = safe_float(row.get("peer_median_pe"))
    pledge = safe_float(row.get("promoter_pledge") or row.get("pledge_pct"), 0) or 0

    score += min(20, max(0, sector_score / 5))
    score += 15 if sector_score >= 70 else 10 if sector_score >= 55 else 6
    score += min(20, max(0, (max(revenue_growth, 0) + max(pat_growth, 0)) / 4))
    score += min(15, max(0, (max(roce, 0) + max(roe, 0)) / 3))
    score += 15 if cfo_pat >= 0.7 else 10 if cfo_pat >= 0.4 else 5 if cfo_pat > 0 else 0
    if pe is not None and peer_pe is not None:
        score += 10 if pe <= peer_pe else 6 if pe <= peer_pe * 1.25 else 2
    elif pe is not None:
        score += 6
    score += 5 if pledge <= 0 else 2 if pledge <= 5 else 0
    if debt_to_equity > 1.5:
        score -= 5
    return round(max(0.0, min(100.0, score)), 2)


def hard_rule_blocks(row: dict[str, Any], resolution: dict[str, Any], dq: dict[str, Any]) -> list[str]:
    blocks: list[str] = []
    if (safe_float(resolution.get("resolution_confidence"), 0) or 0) < 85:
        blocks.append("SYMBOL_REVIEW_NEEDED")
    if not financial_data_available(row):
        blocks.append("FINANCIAL_DATA_PENDING")
    cfo = safe_float(row.get("cfo"))
    cfo_pat = safe_float(row.get("cfo_pat"))
    debtor_days = safe_float(row.get("debtor_days"))
    debtor_change = safe_float(row.get("debtor_days_change_pct") or row.get("debtor_days_change"))
    if (cfo is not None and cfo < 0) or (cfo_pat is not None and cfo_pat < 0):
        if debtor_days is None or debtor_days > 90 or (debtor_change is not None and debtor_change > 30):
            blocks.append("CFO_DEBTOR_RISK")
    pledge = safe_float(row.get("promoter_pledge") or row.get("pledge_pct"), 0) or 0
    pledge_change = safe_float(row.get("pledge_change_qoq"), 0) or 0
    promoter_change = safe_float(row.get("promoter_change_qoq"), 0) or 0
    if pledge > 5 or pledge_change > 1 or promoter_change < -2:
        blocks.append("PROMOTER_PLEDGE_RISK")
    if "quarterly/financial data" in (dq.get("missing_fields") or []):
        if "QUARTERLY_RESULTS_PENDING" not in blocks:
            blocks.append("QUARTERLY_RESULTS_PENDING")
    current_gain = safe_float(row.get("current_gain_pct"))
    drawdown = safe_float(row.get("drawdown_from_52w_high_pct"), 0) or 0
    pe = safe_float(row.get("pe") or row.get("pe_ratio"))
    peer_pe = safe_float(row.get("peer_median_pe"))
    expensive = pe is not None and peer_pe is not None and pe > peer_pe * 1.4
    if (current_gain is not None and current_gain > 100 and drawdown > -15) or expensive:
        blocks.append("VALUATION_RUNUP_RISK")
    return list(dict.fromkeys(blocks))


def final_action_for(row: dict[str, Any], blocks: list[str], value_score: float | None, dq_score: int) -> str:
    if "SYMBOL_REVIEW_NEEDED" in blocks:
        return "Symbol Review Needed"
    if "FINANCIAL_DATA_PENDING" in blocks or "QUARTERLY_RESULTS_PENDING" in blocks or dq_score < 60:
        return "Data Pending"
    if "CFO_DEBTOR_RISK" in blocks or "PROMOTER_PLEDGE_RISK" in blocks:
        return "Watchlist - Hard Rule Blocked"
    score = value_score or 0
    drawdown = safe_float(row.get("drawdown_from_52w_high_pct"), 0) or 0
    cfo_pat = safe_float(row.get("cfo_pat"), 0) or 0
    pat_growth = safe_float(row.get("latest_pat_growth_yoy") or row.get("pat_growth_yoy") or row.get("profit_growth_yoy"), 0) or 0
    if score >= 85 and drawdown <= -20 and cfo_pat >= 0.7 and pat_growth > 0 and not blocks:
        return "Buy Zone Reached"
    if score >= 80 and not {"CFO_DEBTOR_RISK", "PROMOTER_PLEDGE_RISK"}.intersection(blocks):
        return "Staggered Accumulation"
    if score >= 75:
        return "Buy on Correction"
    if score >= 65:
        return "Watchlist"
    return "Avoid"


def _enrich_row(row: dict[str, Any], role: str) -> dict[str, Any]:
    enriched = dict(row)
    if _enrich_simple_ipo_decision is not None:
        try:
            enriched = _enrich_simple_ipo_decision(enriched, enriched.get("ipo_type"))
        except Exception:
            enriched = dict(row)
    enriched["role"] = role
    enriched["company_name"] = clean_company_name(enriched.get("company_name") or enriched.get("company") or "")
    enriched["theme_key"] = infer_research_theme(enriched)
    resolution = resolve_symbol(enriched)
    enriched["resolution"] = resolution
    enriched["symbol"] = resolution.get("symbol") or enriched.get("symbol") or ""
    enriched["exchange"] = resolution.get("exchange") or enriched.get("exchange") or "NSE"
    enriched["screener_url"] = resolution.get("screener_url") or enriched.get("screener_url") or ""
    return enriched


def _metric(row: dict[str, Any], key: str) -> float | None:
    aliases = {
        "pe_ratio": ("pe_ratio", "pe"),
        "revenue_growth_yoy": ("revenue_growth_yoy", "sales_growth_yoy", "latest_revenue_growth_yoy"),
        "profit_growth_yoy": ("profit_growth_yoy", "pat_growth_yoy", "latest_pat_growth_yoy"),
    }
    for field in aliases.get(key, (key,)):
        value = safe_float(row.get(field))
        if value is not None:
            return value
    return None


def peer_comparison_highlights(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metrics = {
        "best_roce": ("roce", "max"),
        "worst_roce": ("roce", "min"),
        "best_roe": ("roe", "max"),
        "worst_roe": ("roe", "min"),
        "lowest_pe": ("pe_ratio", "min"),
        "highest_pe": ("pe_ratio", "max"),
        "best_cfo_pat": ("cfo_pat", "max"),
        "weakest_cfo_pat": ("cfo_pat", "min"),
        "lowest_debt": ("debt_to_equity", "min"),
        "highest_debt": ("debt_to_equity", "max"),
        "highest_sales_growth": ("revenue_growth_yoy", "max"),
        "lowest_sales_growth": ("revenue_growth_yoy", "min"),
        "lowest_debtor_days": ("debtor_days", "min"),
        "highest_debtor_days": ("debtor_days", "max"),
        "best_value_score": ("value_score", "max"),
        "weakest_value_score": ("value_score", "min"),
    }
    highlights: dict[str, dict[str, Any]] = {}
    for label, (field, direction) in metrics.items():
        candidates = [(row, _metric(row, field)) for row in rows]
        candidates = [(row, value) for row, value in candidates if value is not None]
        if not candidates:
            continue
        row, value = (max if direction == "max" else min)(candidates, key=lambda item: item[1])
        highlights[label] = {
            "company_name": row.get("company_name"),
            "symbol": row.get("symbol"),
            "metric": field,
            "value": value,
        }
    return highlights


def build_ipo_research_analysis(
    selected_rows: list[dict[str, Any]],
    year: int,
    add_sector_leaders: bool = False,
    as_of: datetime | None = None,
    max_peers_per_company: int = 2,
) -> dict[str, Any]:
    selected = [_enrich_row(row, "Selected") for row in selected_rows]
    peers: list[dict[str, Any]] = []
    if len(selected) == 1:
        peers = [_enrich_row(row, "Peer") for row in select_top_peers(selected[0], max_peers_per_company)]
    elif add_sector_leaders:
        peers = [_enrich_row(row, "Peer") for row in select_sector_leaders(selected, max_peers_per_company)]

    all_rows = selected + peers
    for row in all_rows:
        row["data_quality"] = data_quality_score(row, has_peer_data=bool(peers))
        row["data_quality_score"] = row["data_quality"]["score"]
        row["data_quality_status"] = row["data_quality"]["status"]
        row["value_score"] = value_score_from_row(row)
        row["hard_rule_blocks"] = hard_rule_blocks(row, row["resolution"], row["data_quality"])
        row["final_action"] = final_action_for(
            row,
            row["hard_rule_blocks"],
            row["value_score"],
            int(row["data_quality_score"] or 0),
        )
        row["buy_zone_allowed"] = row["final_action"] == "Buy Zone Reached"

    selected_actions = [str(row.get("final_action") or "") for row in selected]
    if any(action == "Buy Zone Reached" for action in selected_actions):
        final_action = "Buy Zone Reached"
    elif any(action == "Staggered Accumulation" for action in selected_actions):
        final_action = "Staggered Accumulation"
    elif any(action == "Buy on Correction" for action in selected_actions):
        final_action = "Buy on Correction"
    elif any(action == "Watchlist" for action in selected_actions):
        final_action = "Watchlist"
    elif any(action == "Data Pending" for action in selected_actions):
        final_action = "Data Pending"
    elif any(action == "Symbol Review Needed" for action in selected_actions):
        final_action = "Symbol Review Needed"
    else:
        final_action = selected_actions[0] if selected_actions else "Data Pending"

    data_quality_gate = {
        "selected_min_score": min([int(row.get("data_quality_score") or 0) for row in selected], default=0),
        "selected_avg_score": round(
            sum(int(row.get("data_quality_score") or 0) for row in selected) / max(1, len(selected)),
            2,
        ),
        "symbol_review_needed": [row.get("company_name") for row in selected if "SYMBOL_REVIEW_NEEDED" in row.get("hard_rule_blocks", [])],
        "financial_data_pending": [row.get("company_name") for row in selected if "FINANCIAL_DATA_PENDING" in row.get("hard_rule_blocks", [])],
    }
    analysis = {
        "research_date": (as_of or _now()).isoformat(timespec="seconds"),
        "year": int(year),
        "symbols_key": symbols_key_for_rows(selected, as_of),
        "selected_companies": selected,
        "peer_companies": peers,
        "all_companies": all_rows,
        "peer_highlights": peer_comparison_highlights(all_rows),
        "data_quality_gate": data_quality_gate,
        "final_action": final_action,
        "order_safety": (
            "Research only. This module does not place orders. Buy-zone is blocked unless symbol, "
            "financials, cash-flow, governance, and valuation gates pass."
        ),
    }
    return analysis


def build_ipo_research_prompt(analysis: dict[str, Any]) -> str:
    compact = {
        key: analysis.get(key)
        for key in (
            "research_date",
            "year",
            "selected_companies",
            "peer_companies",
            "peer_highlights",
            "data_quality_gate",
            "final_action",
            "order_safety",
        )
    }
    return (
        "Analyze the following verified IPO/company research dataset for long-term Indian value investing. "
        "Use only the JSON data provided. Return JSON only with keys: research_date, selected_companies, "
        "peer_companies, investment_summary, sector_tailwind, business_quality, growth_quality, "
        "profitability_view, cash_flow_view, valuation_view, peer_comparison_view, governance_view, key_risks, "
        "best_candidate, avoid_candidate, buy_zone, suggested_allocation, final_action, investor_conclusion. "
        "Python hard-rule blocks must not be overridden.\n\n"
        f"{json.dumps(compact, ensure_ascii=False, default=str)}"
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.I | re.M).strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def enforce_gpt_research_hard_rules(analysis: dict[str, Any], gpt_output: str) -> str:
    parsed = _extract_json_object(str(gpt_output or ""))
    if parsed is None:
        return str(gpt_output or "")
    blocked = [
        row
        for row in analysis.get("selected_companies", [])
        if not row.get("buy_zone_allowed")
    ]
    gpt_action_text = " ".join(
        str(parsed.get(key) or "")
        for key in ("buy_zone", "final_action", "investment_summary", "investor_conclusion")
    ).lower()
    if blocked and any(term in gpt_action_text for term in ("buy zone", "buy", "accumulate")):
        parsed["buy_zone"] = "BLOCKED_BY_PYTHON_HARD_RULES"
        parsed["final_action"] = "WATCHLIST - HARD RULE BLOCKED"
        parsed["python_hard_rule_override"] = {
            "blocked_companies": [row.get("company_name") for row in blocked],
            "reason_codes": sorted({code for row in blocked for code in row.get("hard_rule_blocks", [])}),
        }
    return json.dumps(parsed, ensure_ascii=False, indent=2, default=str)


def _html_badge(value: Any) -> str:
    text = str(value or "N/A")
    key = text.lower()
    css = "neutral"
    if any(term in key for term in ("buy zone", "staggered", "tracking")):
        css = "good"
    elif any(term in key for term in ("watch", "correction", "data pending", "symbol")):
        css = "warn"
    elif any(term in key for term in ("avoid", "blocked", "risk")):
        css = "bad"
    return f'<span class="badge {css}">{html_escape(text)}</span>'


def html_escape(value: Any) -> str:
    import html

    return html.escape(str(value if value is not None else ""))


def _format_html_metric(value: Any, suffix: str = "") -> str:
    number = safe_float(value)
    if number is None:
        return "N/A"
    formatted = f"{number:.2f}".rstrip("0").rstrip(".")
    return f"{formatted}{suffix}"


def _metric_cell(value: Any, *, suffix: str = "", strong_when: float | None = None, lower_is_better: bool = False) -> str:
    number = safe_float(value)
    css = ""
    if number is not None and strong_when is not None:
        is_strong = number <= strong_when if lower_is_better else number >= strong_when
        if is_strong:
            css = ' class="strong-positive-cell"'
    return f"<td{css}>{html_escape(_format_html_metric(value, suffix))}</td>"


def _strong_positive_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    action = str(row.get("final_action") or "").lower()
    value_score = safe_float(row.get("value_score"))
    revenue_growth = _metric(row, "revenue_growth_yoy")
    pat_growth = _metric(row, "profit_growth_yoy")
    roce = safe_float(row.get("roce"))
    cfo_pat = safe_float(row.get("cfo_pat"))
    drawdown = safe_float(row.get("drawdown_from_52w_high_pct"))
    pe = safe_float(row.get("pe") or row.get("pe_ratio"))
    peer_pe = safe_float(row.get("peer_median_pe"))

    if any(term in action for term in ("buy zone", "staggered", "buy on correction")):
        reasons.append("Action is investment positive")
    if value_score is not None and value_score >= 75:
        reasons.append("Long-term score >= 75")
    if revenue_growth is not None and revenue_growth >= 20:
        reasons.append("Revenue growth >= 20%")
    if pat_growth is not None and pat_growth >= 20:
        reasons.append("PAT growth >= 20%")
    if roce is not None and roce >= 20:
        reasons.append("ROCE >= 20%")
    if cfo_pat is not None and cfo_pat >= 0.7:
        reasons.append("CFO/PAT >= 0.7")
    if drawdown is not None and drawdown <= -20:
        reasons.append("Meaningful correction from 52W high")
    if pe is not None and peer_pe is not None and pe <= peer_pe:
        reasons.append("P/E below peer median")
    return reasons


def _is_strong_positive_row(row: dict[str, Any]) -> bool:
    hard_blocks = set(row.get("hard_rule_blocks") or [])
    severe_blocks = {"CFO_DEBTOR_RISK", "PROMOTER_PLEDGE_RISK", "SYMBOL_REVIEW_NEEDED"}
    if hard_blocks.intersection(severe_blocks):
        return False
    return len(_strong_positive_reasons(row)) >= 4


def _render_summary_cards(analysis: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    selected = list(analysis.get("selected_companies") or [])
    strong_rows = [row for row in rows if _is_strong_positive_row(row)]
    pending_count = sum(1 for row in rows if str(row.get("final_action") or "").lower() == "data pending")
    best_score = max([safe_float(row.get("value_score"), 0) or 0 for row in rows], default=0)
    cards = [
        ("Final Action", _html_badge(analysis.get("final_action")), "Decision from hard-rule gates"),
        ("Companies Reviewed", str(len(rows)), f"{len(selected)} selected, {max(0, len(rows) - len(selected))} peers"),
        ("Strong Positives", str(len(strong_rows)), "Rows with multiple quality signals"),
        ("Best Score", _format_html_metric(best_score), "Long-term score / 100"),
        ("Data Pending", str(pending_count), "Needs quarterly/financial confirmation"),
    ]
    return "".join(
        f"<div class=\"summary-card\"><span>{html_escape(label)}</span><strong>{value}</strong><small>{html_escape(note)}</small></div>"
        for label, value, note in cards
    )


def _render_data_quality_table(analysis: dict[str, Any]) -> str:
    gate = analysis.get("data_quality_gate") or {}
    rows = [
        ("Minimum selected score", gate.get("selected_min_score")),
        ("Average selected score", gate.get("selected_avg_score")),
        ("Symbol review needed", ", ".join(gate.get("symbol_review_needed") or []) or "None"),
        ("Financial data pending", ", ".join(gate.get("financial_data_pending") or []) or "None"),
    ]
    return "".join(
        f"<tr><th>{html_escape(label)}</th><td>{html_escape(value)}</td></tr>"
        for label, value in rows
    )


def _render_positive_notes(row: dict[str, Any]) -> str:
    reasons = _strong_positive_reasons(row)
    if not reasons:
        return '<span class="muted">No strong positive cluster yet</span>'
    items = "".join(f"<li>{html_escape(reason)}</li>" for reason in reasons[:6])
    return f'<div class="positive-list"><strong>Strong positive</strong><ul>{items}</ul></div>'


def _render_peer_highlights_table(highlights: dict[str, dict[str, Any]]) -> str:
    if not highlights:
        return '<p class="muted">Peer comparison needs more comparable financial data.</p>'
    friendly_labels = {
        "best_roce": "Best ROCE",
        "worst_roce": "Weakest ROCE",
        "best_roe": "Best ROE",
        "worst_roe": "Weakest ROE",
        "lowest_pe": "Lowest P/E",
        "highest_pe": "Highest P/E",
        "best_cfo_pat": "Best CFO/PAT",
        "weakest_cfo_pat": "Weakest CFO/PAT",
        "lowest_debt": "Lowest debt/equity",
        "highest_debt": "Highest debt/equity",
        "highest_sales_growth": "Highest sales growth",
        "lowest_sales_growth": "Lowest sales growth",
        "lowest_debtor_days": "Lowest debtor days",
        "highest_debtor_days": "Highest debtor days",
        "best_value_score": "Best value score",
        "weakest_value_score": "Weakest value score",
    }
    positive_keys = {
        "best_roce",
        "best_roe",
        "lowest_pe",
        "best_cfo_pat",
        "lowest_debt",
        "highest_sales_growth",
        "lowest_debtor_days",
        "best_value_score",
    }
    body = ""
    for key, item in highlights.items():
        css = "strong-positive-cell" if key in positive_keys else "risk-cell"
        body += (
            "<tr>"
            f"<td>{html_escape(friendly_labels.get(key, key.replace('_', ' ').title()))}</td>"
            f"<td class=\"{css}\">{html_escape(item.get('company_name'))}<br><small>{html_escape(item.get('symbol'))}</small></td>"
            f"<td>{html_escape(_format_html_metric(item.get('value')))}</td>"
            f"<td>{html_escape(item.get('metric'))}</td>"
            "</tr>"
        )
    return f"<table><thead><tr><th>Signal</th><th>Company</th><th>Value</th><th>Metric</th></tr></thead><tbody>{body}</tbody></table>"


def _render_gpt_section(gpt_output: str) -> str:
    if not str(gpt_output or "").strip():
        return ""
    parsed = _extract_json_object(str(gpt_output))
    if not parsed:
        return f"<section><h2>GPT Research Note</h2><pre>{html_escape(gpt_output)}</pre></section>"
    rows = ""
    for key, value in parsed.items():
        if isinstance(value, (dict, list)):
            display = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        else:
            display = value
        rows += f"<tr><th>{html_escape(str(key).replace('_', ' ').title())}</th><td>{html_escape(display)}</td></tr>"
    return f"<section><h2>GPT Research Note</h2><table class=\"key-table\"><tbody>{rows}</tbody></table></section>"


def render_ipo_research_html(analysis: dict[str, Any], gpt_output: str = "") -> str:
    rows = list(analysis.get("all_companies") or [])
    row_html = ""
    for row in rows:
        row_class = ' class="strong-positive-row"' if _is_strong_positive_row(row) else ""
        hard_rules = ", ".join(row.get("hard_rule_blocks") or []) or "None"
        row_html += (
            f"<tr{row_class}>"
            f"<td>{html_escape(row.get('role'))}</td>"
            f"<td><a href=\"{html_escape(row.get('screener_url'))}\">{html_escape(row.get('company_name'))}</a><br><small>{html_escape(row.get('symbol'))}</small></td>"
            f"<td>{html_escape(row.get('sector') or row.get('theme'))}</td>"
            f"<td>{html_escape(_format_html_metric(row.get('current_price') or row.get('ltp')))}</td>"
            f"<td>{html_escape(_format_html_metric(row.get('market_cap') or row.get('current_market_cap')))}</td>"
            f"{_metric_cell(row.get('latest_revenue_growth_yoy') or row.get('revenue_growth_yoy') or row.get('sales_growth_yoy'), suffix='%', strong_when=20)}"
            f"{_metric_cell(row.get('latest_pat_growth_yoy') or row.get('pat_growth_yoy') or row.get('profit_growth_yoy'), suffix='%', strong_when=20)}"
            f"{_metric_cell(row.get('roce'), suffix='%', strong_when=20)}"
            f"{_metric_cell(row.get('roe'), suffix='%', strong_when=18)}"
            f"{_metric_cell(row.get('cfo_pat'), strong_when=0.7)}"
            f"{_metric_cell(row.get('pe') or row.get('pe_ratio'))}"
            f"{_metric_cell(row.get('drawdown_from_52w_high_pct'), suffix='%', strong_when=-20, lower_is_better=True)}"
            f"{_metric_cell(row.get('value_score'), strong_when=75)}"
            f"<td>{_html_badge(row.get('final_action'))}</td>"
            f"<td>{_render_positive_notes(row)}</td>"
            f"<td>{html_escape(hard_rules)}</td>"
            "</tr>"
        )
    gpt_section = _render_gpt_section(gpt_output)
    summary_cards = _render_summary_cards(analysis, rows)
    data_quality_rows = _render_data_quality_table(analysis)
    peer_highlights = _render_peer_highlights_table(analysis.get("peer_highlights") or {})
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>IPO Long-Term Research - {html_escape(analysis.get('symbols_key'))}</title>
<style>
body{{font-family:Arial,sans-serif;background:linear-gradient(135deg,#edf9f6 0%,#f8fcfb 48%,#eef7ff 100%);color:#0f2940;margin:0;padding:28px;}}
.wrap{{max-width:1280px;margin:auto;}}
.hero,section{{background:rgba(255,255,255,.94);border:1px solid #bce9dc;border-radius:14px;padding:18px;margin:14px 0;box-shadow:0 12px 28px rgba(0,80,70,.08);}}
.hero{{background:linear-gradient(135deg,#0b3142 0%,#0f766e 100%);color:#fff;}}
h1,h2{{margin:0 0 10px;color:#063b45;}}
.hero h1{{color:#fff;}}
.summary-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-top:16px;}}
.summary-card{{background:#f4fbf9;border:1px solid #bce9dc;border-radius:12px;padding:12px;}}
.summary-card span{{display:block;text-transform:uppercase;font-size:11px;font-weight:800;color:#53647d;}}
.summary-card strong{{display:block;font-size:22px;color:#006b5d;margin:6px 0;}}
.summary-card small{{color:#53647d;}}
.badge{{display:inline-block;border-radius:999px;padding:6px 10px;font-weight:800;font-size:12px;}}
.good{{background:#d8fbe6;color:#057244;}}.warn{{background:#fff4bf;color:#905b00;}}.bad{{background:#ffd8d8;color:#9b1717;}}.neutral{{background:#e8f1ff;color:#24456d;}}
table{{width:100%;border-collapse:collapse;font-size:13px;background:#fff;}}th{{background:#0f766e;color:white;text-align:left;}}th,td{{border:1px solid #cde3de;padding:9px;vertical-align:top;}}
.key-table th{{width:260px;}}
.strong-positive-row{{background:#ecfff4;}}
.strong-positive-cell{{background:#d8fbe6;color:#057244;font-weight:800;}}
.risk-cell{{background:#fff1f1;color:#9b1717;font-weight:800;}}
.positive-list strong{{color:#057244;}}
.positive-list ul{{margin:6px 0 0 18px;padding:0;}}
.muted{{color:#62758d;}}
pre{{white-space:pre-wrap;background:#0b1726;color:#d8fff5;border-radius:12px;padding:16px;}}
</style>
</head>
<body><div class="wrap">
<div class="hero">
<h1>IPO Long-Term Research</h1>
<p><strong>Date:</strong> {html_escape(analysis.get('research_date'))}</p>
<p><strong>Final action:</strong> {_html_badge(analysis.get('final_action'))}</p>
<p>{html_escape(analysis.get('order_safety'))}</p>
<div class="summary-grid">{summary_cards}</div>
</div>
<section><h2>Data Quality Gate</h2><table class="key-table"><tbody>{data_quality_rows}</tbody></table></section>
<section><h2>Selected Company vs Sector Leaders</h2><table><thead><tr><th>Role</th><th>Company</th><th>Sector/Theme</th><th>Price</th><th>Market Cap</th><th>Revenue Growth</th><th>PAT Growth</th><th>ROCE</th><th>ROE</th><th>CFO/PAT</th><th>P/E</th><th>52W Drawdown</th><th>Score</th><th>Action</th><th>Strong Positives</th><th>Hard Rules</th></tr></thead><tbody>{row_html}</tbody></table></section>
<section><h2>Peer Highlights</h2>{peer_highlights}</section>
{gpt_section}
<section><h2>Research Discipline</h2><p>Price performance creates interest. Sector creates priority. Financials create confidence. Cash flow creates conviction. Valuation creates entry. Governance controls risk. Peer comparison validates quality.</p></section>
</div></body></html>"""


def _research_base_dir(base_dir: str | Path | None = None) -> Path:
    return Path(base_dir) if base_dir else Path.cwd()


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def save_ipo_research(
    analysis: dict[str, Any],
    html_text: str | None = None,
    gpt_output: str = "",
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = _research_base_dir(base_dir)
    json_dir = root / "research_store" / "json"
    html_dir = root / "research_store" / "html"
    report_dir = root / "reports" / "ipo_research"
    for directory in (json_dir, html_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    symbols_key = str(analysis.get("symbols_key") or symbols_key_for_rows(list(analysis.get("selected_companies") or [])))
    json_path = _unique_path(json_dir / f"{symbols_key}.json")
    html_path = _unique_path(html_dir / f"{symbols_key}.html")
    report_path = report_dir / html_path.name
    html_payload = html_text or render_ipo_research_html(analysis, gpt_output)

    json_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    html_path.write_text(html_payload, encoding="utf-8")
    shutil.copyfile(html_path, report_path)

    selected = list(analysis.get("selected_companies") or [])
    peers = list(analysis.get("peer_companies") or [])
    created_at = _now().isoformat(timespec="seconds")
    row = {
        "research_id": json_path.stem,
        "research_date": str(analysis.get("research_date") or created_at),
        "symbols_key": symbols_key,
        "company_names": ", ".join(str(item.get("company_name") or "") for item in selected),
        "peer_names": ", ".join(str(item.get("company_name") or "") for item in peers),
        "sector": ", ".join(sorted({str(item.get("sector") or item.get("theme") or "") for item in selected if item.get("sector") or item.get("theme")})),
        "final_action": str(analysis.get("final_action") or ""),
        "value_score": max([safe_float(item.get("value_score"), 0) or 0 for item in selected], default=0),
        "html_path": str(html_path),
        "json_path": str(json_path),
        "created_at": created_at,
        "notes": "IPO long-term research",
    }
    index_path = root / "research_store" / "research_index.csv"
    write_header = not index_path.exists()
    with index_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESEARCH_INDEX_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return {**row, "report_path": str(report_path)}


def load_research_index(limit: int = 20, base_dir: str | Path | None = None) -> list[dict[str, str]]:
    index_path = _research_base_dir(base_dir) / "research_store" / "research_index.csv"
    if not index_path.exists():
        return []
    with index_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows.reverse()
    return rows[: max(1, int(limit))]


def find_saved_research(
    company_or_symbol: str,
    date_prefix: str = "",
    base_dir: str | Path | None = None,
) -> dict[str, str] | None:
    needle = str(company_or_symbol or "").strip().lower()
    for row in load_research_index(limit=1000, base_dir=base_dir):
        haystack = " ".join(
            str(row.get(field) or "")
            for field in ("symbols_key", "company_names", "peer_names", "research_date")
        ).lower()
        if needle and needle not in haystack:
            continue
        if date_prefix and not str(row.get("research_date") or "").startswith(date_prefix):
            continue
        return row
    return None
