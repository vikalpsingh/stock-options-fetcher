"""Long-term IPO opportunity scoring and ranking.

This module keeps IPO investment logic separate from the web page. It accepts
plain dictionaries so live source adapters, cached rows, tests, and local seed
data can all use the same scoring path.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ipo_screener_config import (
    DEFAULT_IPO_SCREENER_CONFIG,
    IPO_RANKING_VIEWS,
    IPO_SME_POSITION_SIZING,
)


def _num(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        if isinstance(value, str) and value.strip().upper() in {"", "N/A", "NA", "NONE", "#DIV/0!"}:
            return default
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _text(value: Any, default: str = "N/A") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _bounded(value: float, maximum: float) -> float:
    return max(0.0, min(float(value), float(maximum)))


def _pct(current: Any, base: Any) -> float | None:
    current_num = _num(current)
    base_num = _num(base)
    if current_num is None or base_num in {None, 0}:
        return None
    return round(((current_num - float(base_num)) / float(base_num)) * 100.0, 2)


def infer_theme(record: dict[str, Any]) -> str:
    text = " ".join(
        str(record.get(field) or "")
        for field in ("sector", "theme", "company_name", "business_snapshot")
    ).lower()
    checks = [
        ("Power & electrical infra", ("power", "electrical", "energy", "solar", "grid", "transmission")),
        ("EMS/electronics", ("ems", "electronics", "electroplast", "semiconductor", "appliance")),
        ("Defence/aerospace", ("defence", "defense", "aerospace", "shipbuilder", "missile")),
        ("Healthcare/diagnostics", ("health", "diagnostic", "hospital", "pharma", "laborator")),
        ("AMC/financialization", ("amc", "financial", "capital market", "exchange", "depository", "broker", "finance")),
        ("Specialty chemicals", ("chemical", "specialty")),
        ("Consumer premiumization", ("consumer", "premium", "retail", "food", "jewellery", "spirits")),
        ("Data centre infra", ("data centre", "data center", "cloud", "digital infra")),
        ("Industrial automation", ("automation", "robot", "cnc", "industrial")),
        ("Manufacturing capex", ("manufacturing", "capex", "capital goods", "infra", "equipment")),
    ]
    for theme, needles in checks:
        if any(needle in text for needle in needles):
            return theme
    return "Manufacturing capex"


def infer_market_type(record: dict[str, Any]) -> str:
    explicit = _text(record.get("market_type"), "")
    if explicit and explicit.lower() in {"sme", "mainboard"}:
        return explicit.upper() if explicit.lower() == "sme" else "Mainboard"
    text = " ".join(
        str(record.get(field) or "")
        for field in ("symbol", "data_source", "source", "board")
    ).lower()
    return "SME" if "sme" in text else "Mainboard"


def normalize_ipo_record(record: dict[str, Any]) -> dict[str, Any]:
    row = dict(record)
    issue_price = _num(row.get("ipo_price"), _num(row.get("issue_price")))
    current_price = _num(row.get("current_price"))
    listing_price = _num(row.get("listing_price"))
    current_mcap = _num(row.get("current_market_cap"), _num(row.get("market_cap")))
    ipo_mcap = _num(row.get("ipo_market_cap"))
    if ipo_mcap is None and current_mcap is not None and issue_price and current_price:
        ipo_mcap = round(current_mcap * float(issue_price) / float(current_price), 2)
    high_52w = _num(row.get("high_52w"), _num(row.get("week_52_high")))
    drawdown = _num(row.get("drawdown_from_52w_high_pct"))
    if drawdown is None and current_price is not None and high_52w:
        drawdown = _pct(current_price, high_52w)
    gain = _num(row.get("gain_from_ipo_pct"), _num(row.get("return_from_issue_pct")))
    if gain is None:
        gain = _pct(current_price, issue_price)
    row.update(
        {
            "company_name": _text(row.get("company_name")),
            "symbol": _text(row.get("symbol")).upper(),
            "ipo_price": issue_price,
            "issue_price": issue_price,
            "listing_price": listing_price,
            "current_price": current_price,
            "ipo_market_cap": ipo_mcap,
            "current_market_cap": current_mcap,
            "market_cap": current_mcap,
            "gain_from_ipo_pct": gain,
            "return_from_issue_pct": gain,
            "return_from_listing_pct": _num(row.get("return_from_listing_pct"), _pct(current_price, listing_price)),
            "drawdown_from_52w_high_pct": drawdown,
            "theme": row.get("theme") or infer_theme(row),
            "market_type": infer_market_type(row),
            "latest_revenue_growth_yoy": _num(row.get("latest_revenue_growth_yoy"), _num(row.get("revenue_growth_yoy"))),
            "latest_pat_growth_yoy": _num(
                row.get("latest_pat_growth_yoy"),
                _num(row.get("pat_growth_yoy"), _num(row.get("profit_growth_yoy"))),
            ),
            "peer_median_pe": _num(row.get("peer_median_pe"), _num(row.get("industry_pe"))),
        }
    )
    return row


def _sector_tailwind_score(row: dict[str, Any], maximum: float) -> float:
    theme = _text(row.get("theme")).lower()
    premium = {
        "power & electrical infra": 19,
        "ems/electronics": 18,
        "defence/aerospace": 19,
        "data centre infra": 19,
        "industrial automation": 18,
        "manufacturing capex": 17,
        "healthcare/diagnostics": 16,
        "amc/financialization": 16,
        "consumer premiumization": 14,
        "specialty chemicals": 14,
    }
    return _bounded(premium.get(theme, 11), maximum)


def _growth_quality_score(row: dict[str, Any], maximum: float) -> float:
    revenue = _num(row.get("latest_revenue_growth_yoy"))
    ebitda = _num(row.get("ebitda_growth_yoy"))
    pat = _num(row.get("latest_pat_growth_yoy"))
    score = 0.0
    score += 7.0 if (revenue or 0) >= 20 else _bounded(max(revenue or 0, 0) / 20 * 7, 7)
    score += 6.0 if (ebitda or pat or 0) >= 20 else _bounded(max(ebitda or pat or 0, 0) / 20 * 6, 6)
    score += 7.0 if (pat or 0) >= 20 else _bounded(max(pat or 0, 0) / 20 * 7, 7)
    if revenue is None:
        score += 2.0
    if pat is None:
        score += 2.0
    return _bounded(score, maximum)


def _business_quality_score(row: dict[str, Any], maximum: float) -> float:
    opm = _num(row.get("operating_margin"))
    npm = _num(row.get("net_profit_margin"))
    roce = _num(row.get("roce"))
    score = 0.0
    score += 5.0 if (opm or 0) >= 18 else _bounded(max(opm or 0, 0) / 18 * 5, 5)
    score += 4.0 if (npm or 0) >= 10 else _bounded(max(npm or 0, 0) / 10 * 4, 4)
    score += 6.0 if (roce or 0) >= 20 else _bounded(max(roce or 0, 0) / 20 * 6, 6)
    return _bounded(score, maximum)


def _capital_efficiency_score(row: dict[str, Any], maximum: float) -> float:
    roce = _num(row.get("roce"))
    roe = _num(row.get("roe"))
    debt = _num(row.get("debt_to_equity"))
    score = 0.0
    score += 6.0 if (roce or 0) >= 20 else _bounded(max(roce or 0, 0) / 20 * 6, 6)
    score += 5.0 if (roe or 0) >= 18 else _bounded(max(roe or 0, 0) / 18 * 5, 5)
    if debt is None:
        score += 2.0
    elif debt <= 0.5:
        score += 4.0
    elif debt <= 1.0:
        score += 2.0
    return _bounded(score, maximum)


def _cash_flow_quality_score(row: dict[str, Any], maximum: float) -> float:
    cfo_pat = _num(row.get("cfo_pat"))
    fcf = _num(row.get("fcf"))
    debtor_change = _num(row.get("debtor_days_change_pct"), 0.0)
    inventory_change = _num(row.get("inventory_days_change_pct"), 0.0)
    score = 0.0
    if cfo_pat is None:
        score += 5.0
    elif cfo_pat >= 1.0:
        score += 8.0
    elif cfo_pat >= 0.7:
        score += 6.0
    elif cfo_pat >= 0.4:
        score += 3.0
    if fcf is None:
        score += 2.0
    elif fcf >= 0:
        score += 4.0
    else:
        score += 1.0
    score += 2.0 if debtor_change <= 10 else 0.5
    score += 1.0 if inventory_change <= 15 else 0.0
    return _bounded(score, maximum)


def _valuation_comfort_score(row: dict[str, Any], maximum: float) -> float:
    pe = _num(row.get("pe_ratio"))
    peer = _num(row.get("peer_median_pe"))
    drawdown = _num(row.get("drawdown_from_52w_high_pct"))
    score = 0.0
    if pe is None or not peer:
        score += 4.0
    else:
        pe_ratio = pe / peer
        if pe_ratio <= 0.85:
            score += 7.0
        elif pe_ratio <= 1.1:
            score += 5.0
        elif pe_ratio <= 1.4:
            score += 2.5
        else:
            score += 0.5
    if drawdown is not None and drawdown <= -20:
        score += 3.0
    elif drawdown is not None and drawdown <= -10:
        score += 1.5
    else:
        score += 0.5
    return _bounded(score, maximum)


def _governance_ownership_score(row: dict[str, Any], maximum: float) -> float:
    promoter = _num(row.get("promoter_holding"))
    pledge = _num(row.get("pledge_pct"), 0.0)
    promoter_change = _num(row.get("promoter_holding_change"), 0.0)
    score = 0.0
    if promoter is None:
        score += 1.5
    elif promoter >= 50:
        score += 2.5
    elif promoter >= 35:
        score += 1.5
    score += 1.5 if pledge <= 1 else 0.5 if pledge <= 5 else 0.0
    score += 1.0 if promoter_change >= -1 else 0.0
    return _bounded(score, maximum)


def _flag_and_risks(row: dict[str, Any], rules: dict[str, Any]) -> tuple[str, list[str]]:
    revenue = _num(row.get("latest_revenue_growth_yoy"))
    pat = _num(row.get("latest_pat_growth_yoy"))
    roce = _num(row.get("roce"))
    cfo_pat = _num(row.get("cfo_pat"))
    debt_change = _num(row.get("debt_change_pct"), 0.0)
    debtor_change = _num(row.get("debtor_days_change_pct"), 0.0)
    pledge_change = _num(row.get("pledge_change"), 0.0)
    promoter_change = _num(row.get("promoter_holding_change"), 0.0)
    opm_trend_value = _num(row.get("opm_trend_pct"))
    opm_text = _text(row.get("opm_trend"), "").lower()
    risks: list[str] = []
    if cfo_pat is not None and cfo_pat < 0:
        risks.append("CFO negative")
    if debtor_change > float(rules["red_debtor_days_increase"]):
        risks.append("Debtor days up >30%")
    if debt_change > float(rules["red_debt_increase_pct"]):
        risks.append("Debt up >25%")
    if promoter_change < float(rules["red_promoter_selling_pct"]):
        risks.append("Promoter selling")
    if pledge_change > float(rules["red_pledge_increase_pct"]):
        risks.append("Pledge increase")
    if (opm_trend_value is not None and opm_trend_value <= float(rules["red_margin_collapse_pct"])) or "collapse" in opm_text:
        risks.append("Margin collapse")
    if risks:
        return "RED", risks
    green = (
        (revenue or 0) > float(rules["green_revenue_growth_yoy"])
        and (pat or 0) > float(rules["green_pat_growth_yoy"])
        and (roce or 0) > float(rules["green_roce"])
        and (cfo_pat is None or cfo_pat >= float(rules["green_cfo_pat"]))
        and debt_change <= 10
        and debtor_change <= 10
    )
    if green:
        return "GREEN", []
    return "YELLOW", []


def _valuation_below_peer(row: dict[str, Any]) -> bool:
    pe = _num(row.get("pe_ratio"))
    peer = _num(row.get("peer_median_pe"))
    return bool(pe is not None and peer and pe <= peer)


def _cfo_pat_ok_or_improving(row: dict[str, Any], min_cfo_pat: float) -> bool:
    cfo_pat = _num(row.get("cfo_pat"))
    cfo_pat_change = _num(row.get("cfo_pat_change"), 0.0)
    return bool(cfo_pat is not None and (cfo_pat >= min_cfo_pat or cfo_pat_change > 0))


def _is_buy_zone(row: dict[str, Any], lt_score: float, sector_quality_score: float, flag: str, rules: dict[str, Any]) -> bool:
    if row.get("eligible_for_scoring") is False or row.get("is_demo"):
        return False
    drawdown = abs(_num(row.get("drawdown_from_52w_high_pct"), 0.0) or 0.0)
    opm_text = _text(row.get("opm_trend"), "").lower()
    opm_trend_pct = _num(row.get("opm_trend_pct"), 0.0) or 0.0
    debtor_days_known = _num(row.get("debtor_days")) is not None or bool(row.get("debtor_days_not_applicable"))
    return (
        lt_score >= float(rules["min_lt_score"])
        and sector_quality_score >= float(rules["min_sector_score"])
        and (_num(row.get("latest_revenue_growth_yoy"), 0.0) or 0.0) >= float(rules["min_revenue_growth_yoy"])
        and (_num(row.get("latest_pat_growth_yoy"), 0.0) or 0.0) > 0
        and "collapse" not in opm_text
        and opm_trend_pct > -3.0
        and _cfo_pat_ok_or_improving(row, float(rules["min_cfo_pat"]))
        and debtor_days_known
        and flag != "RED"
        and (drawdown >= float(rules["min_drawdown_from_52w_high_pct"]) or _valuation_below_peer(row))
    )


def _action_for(row: dict[str, Any], lt_score: float, buy_zone: bool, flag: str) -> str:
    if flag == "RED" and lt_score < 55:
        return "Remove from Watchlist"
    if flag == "RED":
        return "Avoid"
    if buy_zone:
        return "Buy Zone Reached"
    if lt_score >= 75 and (_num(row.get("latest_revenue_growth_yoy"), 0) or 0) >= 15:
        return "Result Confirmed"
    if lt_score >= 68:
        return "Buy on Correction"
    if lt_score >= 55:
        return "Watchlist"
    return "Avoid"


def _alerts_for(row: dict[str, Any], action: str, flag: str, risks: list[str]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    base = {
        "company_name": row.get("company_name"),
        "symbol": row.get("symbol"),
        "lt_score": row.get("lt_score"),
        "action": action,
    }
    if action == "Buy Zone Reached":
        alerts.append({**base, "alert_type": "Buy-zone alert", "severity": "GREEN", "message": "Quarterly proof and valuation correction are aligned."})
    if action == "Result Confirmed":
        alerts.append({**base, "alert_type": "Result improvement alert", "severity": "BLUE", "message": "Results look confirmed; wait for valuation comfort."})
    if (_num(row.get("drawdown_from_52w_high_pct"), 0.0) or 0.0) <= -20 or _valuation_below_peer(row):
        alerts.append({**base, "alert_type": "Valuation compression alert", "severity": "YELLOW", "message": "Price or valuation has compressed versus peak/peers."})
    if flag == "RED" or risks:
        alerts.append({**base, "alert_type": "Risk deterioration alert", "severity": "RED", "message": ", ".join(risks) or "Risk flags are active."})
    if action == "Remove from Watchlist":
        alerts.append({**base, "alert_type": "Remove-from-watchlist alert", "severity": "RED", "message": "Score and risk flags do not support monitoring."})
    return alerts


def score_ipo_opportunity(
    record: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or DEFAULT_IPO_SCREENER_CONFIG
    row = normalize_ipo_record(record)
    if row.get("eligible_for_scoring") is False or row.get("is_demo"):
        action = row.get("action") or "UNVERIFIED - EXCLUDED"
        flag = row.get("flag") or "RED"
        reason = row.get("exclusion_reason") or "Record is not verified enough for production IPO scoring."
        return {
            **row,
            "lt_score": None,
            "total_score": None,
            "sector_quality_score": None,
            "quality_score": None,
            "growth_score": None,
            "profitability_score": None,
            "valuation_score": None,
            "balance_sheet_score": None,
            "management_score": None,
            "sector_score": None,
            "market_performance_score": None,
            "risk_score": None,
            "flag": flag,
            "risk_flags": row.get("risk_flags") or [reason],
            "action": action,
            "rating": action,
            "buy_zone": None,
            "is_buy_zone": False,
            "alerts": [],
            "final_recommendation": row.get("final_recommendation") or reason,
            "ai_commentary": row.get("final_recommendation") or reason,
        }
    weights = cfg["score_weights"]
    components = {
        "sector_tailwind_score": _sector_tailwind_score(row, weights["sector_tailwind"]),
        "business_quality_score": _business_quality_score(row, weights["business_quality"]),
        "growth_quality_score": _growth_quality_score(row, weights["growth_quality"]),
        "capital_efficiency_score": _capital_efficiency_score(row, weights["capital_efficiency"]),
        "cash_flow_quality_score": _cash_flow_quality_score(row, weights["cash_flow_quality"]),
        "valuation_comfort_score": _valuation_comfort_score(row, weights["valuation_comfort"]),
        "governance_ownership_score": _governance_ownership_score(row, weights["governance_ownership"]),
    }
    lt_score = round(sum(components.values()), 2)
    sector_quality_score = round((components["sector_tailwind_score"] / weights["sector_tailwind"]) * 100, 2)
    flag, risks = _flag_and_risks(row, cfg["flag_rules"])
    buy_zone = _is_buy_zone(row, lt_score, sector_quality_score, flag, cfg["buy_zone_rules"])
    action = _action_for(row, lt_score, buy_zone, flag)
    result = {
        **row,
        **{key: round(value, 2) for key, value in components.items()},
        "lt_score": lt_score,
        "total_score": lt_score,
        "sector_quality_score": sector_quality_score,
        "flag": flag,
        "risk_flags": risks,
        "action": action,
        "rating": action,
        "quality_score": round(
            components["business_quality_score"]
            + components["capital_efficiency_score"]
            + components["cash_flow_quality_score"],
            2,
        ),
        "growth_score": round(components["growth_quality_score"], 2),
        "profitability_score": round(components["business_quality_score"], 2),
        "valuation_score": round(components["valuation_comfort_score"], 2),
        "balance_sheet_score": round(components["capital_efficiency_score"], 2),
        "management_score": round(components["governance_ownership_score"], 2),
        "sector_score": round(components["sector_tailwind_score"], 2),
        "market_performance_score": round(_valuation_comfort_score(row, 10), 2),
        "risk_score": round(100 - lt_score, 2),
        "buy_zone": "Buy Zone Reached" if buy_zone else None,
        "is_buy_zone": bool(buy_zone),
        "sme_position_sizing": IPO_SME_POSITION_SIZING if row.get("market_type") == "SME" else {},
        "business_snapshot": row.get("business_snapshot") or f"{row.get('company_name')} operates in {row.get('sector')} with the {row.get('theme')} theme.",
        "sector_thesis": row.get("sector_thesis") or f"{row.get('theme')} is screened for multi-year earnings durability, not listing-day momentum.",
    }
    result["alerts"] = _alerts_for(result, action, flag, risks)
    result["final_recommendation"] = _final_recommendation(result)
    result["ai_commentary"] = result["final_recommendation"]
    return result


def _final_recommendation(row: dict[str, Any]) -> str:
    action = _text(row.get("action"))
    score = _num(row.get("lt_score"), 0) or 0
    flag = _text(row.get("flag"))
    if action == "Buy Zone Reached":
        return "Buy-zone candidate: quarterly proof, score, and valuation correction are aligned. Use staggered sizing."
    if action == "Result Confirmed":
        return "Result confirmed, but wait for correction or peer-valuation comfort before scaling."
    if action == "Buy on Correction":
        return "Quality is acceptable; add only after a better price or valuation compression."
    if action == "Watchlist":
        return "Watchlist only. Wait for 2-3 more quarters of execution and cleaner cash conversion."
    if flag == "RED":
        return "Avoid for now due to risk flags. Recheck after cash flow, margins, or ownership improve."
    return f"Avoid or wait. Long-term score {score:.0f}/100 is not strong enough yet."


def rank_scored_ipos(records: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    rankable = [
        record
        for record in records
        if record.get("eligible_for_scoring", True) is not False and not record.get("is_demo")
    ]
    ranked = [score_ipo_opportunity(record) for record in rankable]
    ranked.sort(
        key=lambda item: (
            _num(item.get("lt_score"), 0) or 0,
            _num(item.get("sector_quality_score"), 0) or 0,
            _num(item.get("latest_revenue_growth_yoy"), -999) or -999,
        ),
        reverse=True,
    )
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    if limit is not None:
        return ranked[:limit]
    return ranked


def _apply_filters(records: list[dict[str, Any]], market_type: str, theme: str) -> list[dict[str, Any]]:
    market = (market_type or "All").lower()
    selected_theme = theme or "All"
    rows = []
    for row in records:
        if market != "all" and str(row.get("market_type") or "").lower() != market:
            continue
        if selected_theme != "All" and row.get("theme") != selected_theme:
            continue
        rows.append(row)
    return rows


def _ranking_views(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    strong_results_expensive = [
        row
        for row in records
        if (_num(row.get("latest_revenue_growth_yoy"), 0) or 0) >= 20
        and (_num(row.get("latest_pat_growth_yoy"), 0) or 0) >= 20
        and not _valuation_below_peer(row)
    ]
    weak_cash = [
        row
        for row in records
        if (_num(row.get("cfo_pat"), 1) or 0) < 0.7 or (_num(row.get("fcf"), 0) or 0) < 0
    ]
    corrected_strong = [
        row
        for row in records
        if (_num(row.get("lt_score"), 0) or 0) >= 70
        and (_num(row.get("drawdown_from_52w_high_pct"), 0) or 0) <= -20
    ]
    avoid = [row for row in records if row.get("action") in {"Avoid", "Remove from Watchlist"}]
    return {
        "Best IPOs by long-term score": sorted(records, key=lambda row: _num(row.get("lt_score"), 0) or 0, reverse=True),
        "Best IPOs by sector quality": sorted(records, key=lambda row: _num(row.get("sector_quality_score"), 0) or 0, reverse=True),
        "Best corrected IPOs with strong fundamentals": sorted(corrected_strong, key=lambda row: _num(row.get("lt_score"), 0) or 0, reverse=True),
        "IPOs with strong results but expensive valuation": sorted(strong_results_expensive, key=lambda row: _num(row.get("lt_score"), 0) or 0, reverse=True),
        "IPOs with weak cash conversion": sorted(weak_cash, key=lambda row: _num(row.get("cfo_pat"), 99) or 99),
        "IPOs to avoid": sorted(avoid, key=lambda row: _num(row.get("lt_score"), 0) or 0),
    }


def build_ipo_screener_payload(
    listed_records: list[dict[str, Any]],
    upcoming_records: list[dict[str, Any]],
    year: int,
    market_type: str = "All",
    theme: str = "All",
    ranking_view: str = "Best IPOs by long-term score",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scored_all = rank_scored_ipos(listed_records)
    filtered = _apply_filters(scored_all, market_type, theme)
    rankings = _ranking_views(filtered)
    selected_ranking = rankings.get(ranking_view) or rankings[IPO_RANKING_VIEWS[0]]
    for index, item in enumerate(selected_ranking, start=1):
        item["view_rank"] = index
    quarterly = [
        {
            **row,
            "quarter": row.get("quarter") or "Latest Available",
        }
        for row in selected_ranking
    ]
    alerts = [alert for row in filtered for alert in row.get("alerts", [])]
    buy_zone = [row for row in filtered if row.get("action") == "Buy Zone Reached"]
    watchlist = [
        row
        for row in filtered
        if row.get("action") in {"Watchlist", "Result Confirmed", "Buy on Correction", "Buy Zone Reached"}
    ]
    detail = (selected_ranking or scored_all or [{}])[0] if (selected_ranking or scored_all) else {}
    return {
        "year": int(year),
        "market_type": market_type,
        "theme": theme,
        "ranking_view": ranking_view,
        "master": selected_ranking,
        "all_scored": scored_all,
        "quarterly_monitor": quarterly,
        "alerts": alerts,
        "rankings": rankings,
        "detail": detail,
        "exports": {
            "watchlist": watchlist,
            "buy_zone": buy_zone,
            "risk_alerts": alerts,
            "quarterly": quarterly,
        },
        "summary": {
            "listed_total": len(scored_all),
            "listed_filtered": len(filtered),
            "upcoming_count": len(upcoming_records),
            "buy_zone_count": len(buy_zone),
            "risk_alert_count": len([alert for alert in alerts if alert.get("severity") == "RED"]),
            "best_score": max([_num(row.get("lt_score"), 0) or 0 for row in filtered] or [0]),
            "best_action": _text(detail.get("action"), "N/A"),
            "cache_as_of": date.today().isoformat(),
        },
    }
