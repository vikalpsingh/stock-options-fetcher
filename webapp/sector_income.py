"""Sector-income sell-on-rise evaluation helpers.

The SECTOR-Income page reuses the DHAN-IT spread/order components, but keeps
sector configuration, FII flow classification, and top-candidate ranking out of
the UI layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable


SECTOR_INCOME_UNIVERSE: dict[str, list[str]] = {
    "INFORMATION_TECHNOLOGY": ["TCS", "INFY", "HCLTECH", "TECHM", "WIPRO", "LTM"],
    "FINANCIAL_SERVICES": ["BAJFINANCE", "BAJAJFINSV", "SHRIRAMFIN", "CHOLAFIN", "SBICARD", "JIOFIN"],
    "BANKING": ["HDFCBANK", "ICICIBANK", "AXISBANK", "SBIN", "KOTAKBANK", "INDUSINDBK"],
    "AUTOMOBILE_AUTO_COMPONENTS": ["MARUTI", "M&M", "TATAMOTORS", "EICHERMOT", "BAJAJ-AUTO", "HEROMOTOCO"],
    "HEALTHCARE_PHARMA": ["SUNPHARMA", "DRREDDY", "CIPLA", "LUPIN", "AUROPHARMA", "DIVISLAB"],
    "METALS_MINING": ["HINDALCO", "TATASTEEL", "JSWSTEEL", "VEDL", "NATIONALUM", "SAIL"],
    "OIL_GAS": ["RELIANCE", "ONGC", "IOC", "BPCL", "GAIL", "OIL"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "MARICO"],
    "POWER": ["NTPC", "POWERGRID", "TATAPOWER", "ADANIPOWER", "JSWENERGY", "NHPC"],
    "CAPITAL_GOODS": ["LT", "SIEMENS", "ABB", "BHEL", "BEL", "CUMMINSIND"],
    "TELECOMMUNICATION": ["BHARTIARTL", "INDUSTOWER", "TATACOMM", "IDEA"],
    "CONSUMER_DURABLES": ["TITAN", "HAVELLS", "VOLTAS", "DIXON", "CROMPTON", "BLUESTARCO"],
    "REALTY": ["DLF", "GODREJPROP", "LODHA", "OBEROIRLTY", "PRESTIGE"],
    "CONSTRUCTION_MATERIALS": ["ULTRACEMCO", "GRASIM", "AMBUJACEM", "ACC", "SHREECEM", "DALBHARAT"],
    "CONSUMER_SERVICES": ["ETERNAL", "INDHOTEL", "IRCTC", "TRENT", "NAUKRI", "DMART"],
}


SECTOR_LABELS: dict[str, str] = {
    "INFORMATION_TECHNOLOGY": "Information Technology",
    "FINANCIAL_SERVICES": "Financial Services",
    "BANKING": "Banking",
    "AUTOMOBILE_AUTO_COMPONENTS": "Automobile & Auto Components",
    "HEALTHCARE_PHARMA": "Healthcare & Pharmaceuticals",
    "METALS_MINING": "Metals & Mining",
    "OIL_GAS": "Oil, Gas & Consumable Fuels",
    "FMCG": "Fast Moving Consumer Goods",
    "POWER": "Power",
    "CAPITAL_GOODS": "Capital Goods",
    "TELECOMMUNICATION": "Telecommunication",
    "CONSUMER_DURABLES": "Consumer Durables",
    "REALTY": "Realty",
    "CONSTRUCTION_MATERIALS": "Construction Materials / Cement",
    "CONSUMER_SERVICES": "Consumer Services",
}


FII_SECTOR_SNAPSHOT_DATE = "2026-08-30"
FII_SECTOR_SNAPSHOT_SOURCE = "Supplied Screener FII sector report"
FII_SECTOR_SNAPSHOT: dict[str, dict[str, float]] = {
    "FINANCIAL_SERVICES": {"fii_aum_pct": 27.1, "fortnight_flow_cr": 6950, "one_year_flow_cr": -135301},
    "AUTOMOBILE_AUTO_COMPONENTS": {"fii_aum_pct": 7.1, "fortnight_flow_cr": 4393, "one_year_flow_cr": -28630},
    "HEALTHCARE_PHARMA": {"fii_aum_pct": 6.8, "fortnight_flow_cr": 2910, "one_year_flow_cr": -24869},
    "CAPITAL_GOODS": {"fii_aum_pct": 6.5, "fortnight_flow_cr": -1556, "one_year_flow_cr": 16914},
    "OIL_GAS": {"fii_aum_pct": 6.0, "fortnight_flow_cr": 492, "one_year_flow_cr": -15517},
    "INFORMATION_TECHNOLOGY": {"fii_aum_pct": 5.1, "fortnight_flow_cr": 2530, "one_year_flow_cr": -52281},
    "TELECOMMUNICATION": {"fii_aum_pct": 5.0, "fortnight_flow_cr": -3322, "one_year_flow_cr": -7789},
    "FMCG": {"fii_aum_pct": 3.9, "fortnight_flow_cr": -189, "one_year_flow_cr": -48177},
    "METALS_MINING": {"fii_aum_pct": 3.8, "fortnight_flow_cr": 720, "one_year_flow_cr": 25344},
    "CONSUMER_SERVICES": {"fii_aum_pct": 3.7, "fortnight_flow_cr": 3398, "one_year_flow_cr": -14766},
    "POWER": {"fii_aum_pct": 3.4, "fortnight_flow_cr": -2216, "one_year_flow_cr": -17292},
    "CONSUMER_DURABLES": {"fii_aum_pct": 2.6, "fortnight_flow_cr": 1472, "one_year_flow_cr": -2192},
    "REALTY": {"fii_aum_pct": 1.9, "fortnight_flow_cr": -1206, "one_year_flow_cr": -13202},
    "CONSTRUCTION_MATERIALS": {"fii_aum_pct": 1.4, "fortnight_flow_cr": 384, "one_year_flow_cr": -9604},
}

DEFAULT_SECTOR_PRIORITY = [
    "INFORMATION_TECHNOLOGY",
    "FINANCIAL_SERVICES",
    "AUTOMOBILE_AUTO_COMPONENTS",
    "HEALTHCARE_PHARMA",
]

SECTOR_SCORE_WEIGHTS: dict[str, int] = {
    "trend_structure": 20,
    "rise_into_resistance": 15,
    "relative_weakness": 12,
    "breadth_weakness": 12,
    "iv_premium_quality": 10,
    "options_liquidity": 10,
    "fii_flow_regime": 8,
    "event_risk": 5,
    "rebound_risk": 5,
    "portfolio_capacity": 3,
}

SECTOR_INDEX_CONFIG: dict[str, dict[str, str]] = {
    "INFORMATION_TECHNOLOGY": {"display_name": "Information Technology", "kite_symbol": "NSE:NIFTY IT", "public_symbol": "^CNXIT"},
    "BANKING": {"display_name": "Banking", "kite_symbol": "NSE:NIFTY BANK", "public_symbol": "^NSEBANK"},
    "AUTOMOBILE_AUTO_COMPONENTS": {"display_name": "Automobile & Auto Components", "kite_symbol": "NSE:NIFTY AUTO", "public_symbol": "^CNXAUTO"},
    "FINANCIAL_SERVICES": {"display_name": "Financial Services", "kite_symbol": "NSE:NIFTY FIN SERVICE", "public_symbol": "DATA_UNAVAILABLE"},
    "HEALTHCARE_PHARMA": {"display_name": "Healthcare & Pharmaceuticals", "kite_symbol": "NSE:NIFTY PHARMA", "public_symbol": "^CNXPHARMA"},
    "METALS_MINING": {"display_name": "Metals & Mining", "kite_symbol": "NSE:NIFTY METAL", "public_symbol": "^CNXMETAL"},
    "OIL_GAS": {"display_name": "Oil, Gas & Consumable Fuels", "kite_symbol": "DATA_UNAVAILABLE", "public_symbol": "DATA_UNAVAILABLE"},
    "FMCG": {"display_name": "Fast Moving Consumer Goods", "kite_symbol": "NSE:NIFTY FMCG", "public_symbol": "^CNXFMCG"},
    "POWER": {"display_name": "Power", "kite_symbol": "DATA_UNAVAILABLE", "public_symbol": "DATA_UNAVAILABLE"},
    "CAPITAL_GOODS": {"display_name": "Capital Goods", "kite_symbol": "DATA_UNAVAILABLE", "public_symbol": "DATA_UNAVAILABLE"},
    "TELECOMMUNICATION": {"display_name": "Telecommunication", "kite_symbol": "DATA_UNAVAILABLE", "public_symbol": "DATA_UNAVAILABLE"},
    "CONSUMER_DURABLES": {"display_name": "Consumer Durables", "kite_symbol": "NSE:NIFTY CONSR DURBL", "public_symbol": "DATA_UNAVAILABLE"},
    "REALTY": {"display_name": "Realty", "kite_symbol": "NSE:NIFTY REALTY", "public_symbol": "^CNXREALTY"},
    "CONSTRUCTION_MATERIALS": {"display_name": "Construction Materials / Cement", "kite_symbol": "DATA_UNAVAILABLE", "public_symbol": "DATA_UNAVAILABLE"},
    "CONSUMER_SERVICES": {"display_name": "Consumer Services", "kite_symbol": "DATA_UNAVAILABLE", "public_symbol": "DATA_UNAVAILABLE"},
}


@dataclass(frozen=True)
class SectorIncomeSnapshot:
    snapshot_date: str = FII_SECTOR_SNAPSHOT_DATE
    source_label: str = FII_SECTOR_SNAPSHOT_SOURCE
    imported_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    freshness_status: str = "STATIC_SUPPLIED_SNAPSHOT"
    rows: dict[str, dict[str, float]] = field(default_factory=lambda: dict(FII_SECTOR_SNAPSHOT))


def sector_options() -> list[dict[str, str]]:
    return [{"key": key, "label": SECTOR_LABELS.get(key, key.replace("_", " ").title())} for key in SECTOR_INCOME_UNIVERSE]


def normalize_sector_key(value: str | None) -> str:
    key = str(value or "").strip().upper()
    return key if key in SECTOR_INCOME_UNIVERSE else "INFORMATION_TECHNOLOGY"


def configured_sector_symbols(sector_key: str) -> list[str]:
    return list(SECTOR_INCOME_UNIVERSE.get(normalize_sector_key(sector_key), []))


def load_fii_sector_snapshot() -> SectorIncomeSnapshot:
    return SectorIncomeSnapshot()


def classify_fii_flow_regime(one_year_flow_cr: Any, fortnight_flow_cr: Any) -> str:
    try:
        one_year = float(one_year_flow_cr)
        fortnight = float(fortnight_flow_cr)
    except (TypeError, ValueError):
        return "DATA_UNAVAILABLE"
    if one_year < 0 and fortnight > 0:
        return "RELIEF_RALLY_SELL_ON_RISE"
    if one_year < 0 and fortnight <= 0:
        return "STRUCTURAL_WEAKNESS"
    if one_year >= 0 and fortnight < 0:
        return "PROFIT_BOOKING_ONLY"
    return "ACCUMULATION - AVOID SYSTEMATIC CALL SELLING"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def validate_sector_fno_symbols(
    sector_key: str,
    available_underlyings: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    symbols = configured_sector_symbols(sector_key)
    available = {str(item or "").strip().upper() for item in available_underlyings or [] if str(item or "").strip()}
    check_availability = bool(available)
    return [
        {
            "symbol": symbol,
            "fno_eligible": (symbol in available) if check_availability else True,
            "status": "F&O ELIGIBLE" if (symbol in available or not check_availability) else "F&O UNAVAILABLE - ORDER BLOCKED",
        }
        for symbol in symbols
    ]


def calculate_sector_sell_on_rise_score(
    sector_key: str,
    *,
    sector_technical: dict[str, Any] | None = None,
    valid_fno_count: int = 0,
    active_sector_exposure: int = 0,
) -> dict[str, Any]:
    snapshot = load_fii_sector_snapshot()
    key = normalize_sector_key(sector_key)
    fii = snapshot.rows.get(key, {})
    fii_regime = classify_fii_flow_regime(fii.get("one_year_flow_cr"), fii.get("fortnight_flow_cr"))
    technical = sector_technical or {}
    sector_regime = str(technical.get("sector_regime") or technical.get("trend") or "DATA_UNAVAILABLE").upper()
    dist_50 = _float(technical.get("distance_50_pct"))
    component_scores = calculate_sector_component_scores(
        key,
        sector_technical=technical,
        valid_fno_count=valid_fno_count,
        active_sector_exposure=active_sector_exposure,
    )
    score = sum(_float(item.get("score")) for item in component_scores.values())
    reasons: list[str] = []
    if fii_regime == "RELIEF_RALLY_SELL_ON_RISE":
        reasons.append("negative one-year FII flow with current relief inflow")
    elif fii_regime == "STRUCTURAL_WEAKNESS":
        reasons.append("negative one-year and fortnight FII flow")
    elif fii_regime == "PROFIT_BOOKING_ONLY":
        reasons.append("positive one-year FII flow with recent profit booking")
    else:
        reasons.append("FII accumulation regime avoids systematic call selling")
    if sector_regime in {"BEARISH", "BEARISH_RALLY"}:
        reasons.append("sector DMA regime supports sell-on-rise scan")
    elif sector_regime == "MIXED" or sector_regime == "BULLISH_PULLBACK":
        reasons.append("sector DMA regime is mixed; confirmation needed")
    elif sector_regime == "BULLISH":
        reasons.append("sector trend is bullish; call selling needs caution")
    else:
        reasons.append("sector DMA data unavailable")
    if dist_50 <= -8:
        reasons.append("sector is deeply below 50 DMA; rebound risk")
    if active_sector_exposure >= 3:
        reasons.append("sector exposure cap already near/full")
    score = max(0.0, min(100.0, score))
    decision = "GREEN - SCAN TOP 4" if score >= 65 else "AMBER - SELECTIVE / CONFIRM" if score >= 45 else "RED - NO NEW CALL SPREAD"
    return {
        "sector_key": key,
        "sector_label": SECTOR_LABELS.get(key, key),
        "sector_score": round(score, 2),
        "fii_aum_pct": fii.get("fii_aum_pct"),
        "fortnight_flow_cr": fii.get("fortnight_flow_cr"),
        "one_year_flow_cr": fii.get("one_year_flow_cr"),
        "fii_regime": fii_regime,
        "sector_regime": sector_regime,
        "valid_fno_count": valid_fno_count,
        "active_sector_exposure": active_sector_exposure,
        "decision": decision,
        "status": "GREEN" if decision.startswith("GREEN") else "AMBER" if decision.startswith("AMBER") else "RED",
        "orderable": not decision.startswith("RED"),
        "confidence": sector_confidence(component_scores),
        "component_scores": component_scores,
        "rebound_risk": classify_rebound_risk(technical, fii),
        "liquidity_status": "GREEN" if valid_fno_count >= 4 else "RED" if valid_fno_count == 0 else "AMBER",
        "reasons": reasons,
        "snapshot_date": snapshot.snapshot_date,
        "source_label": snapshot.source_label,
        "imported_at": snapshot.imported_at,
        "freshness_status": snapshot.freshness_status,
    }


def calculate_sector_component_scores(
    sector_key: str,
    *,
    sector_technical: dict[str, Any] | None = None,
    valid_fno_count: int = 0,
    active_sector_exposure: int = 0,
) -> dict[str, dict[str, Any]]:
    key = normalize_sector_key(sector_key)
    snapshot = load_fii_sector_snapshot()
    fii = snapshot.rows.get(key, {})
    technical = sector_technical or {}
    regime = str(technical.get("sector_regime") or technical.get("trend") or "DATA_UNAVAILABLE").upper()
    day_change = _float(technical.get("today_change_pct"))
    distance_50 = _float(technical.get("distance_50_pct"))
    relative_20 = _float(technical.get("relative_strength_20d"))
    breadth_50 = technical.get("breadth_above_50dma_pct")
    liquidity = str(technical.get("liquidity_status") or ("GREEN" if valid_fno_count >= 4 else "AMBER" if valid_fno_count else "RED")).upper()
    event_risk = bool(technical.get("event_risk"))
    rebound_risk = classify_rebound_risk(technical, fii)
    fii_regime = classify_fii_flow_regime(fii.get("one_year_flow_cr"), fii.get("fortnight_flow_cr"))

    def item(key_name: str, score: float, detail: str, missing: bool = False) -> dict[str, Any]:
        weight = SECTOR_SCORE_WEIGHTS[key_name]
        return {
            "score": round(max(0.0, min(float(weight), score)), 2),
            "weight": weight,
            "detail": detail,
            "missing": missing,
        }

    trend_score = 0.0
    if regime == "BEARISH_RALLY":
        trend_score = 18
    elif regime == "BEARISH":
        trend_score = 15
    elif regime in {"MIXED", "BULLISH_PULLBACK"}:
        trend_score = 10
    elif regime == "BULLISH":
        trend_score = 2
    rise_score = 12 if 0.75 <= day_change <= 3.5 and -2 <= distance_50 <= 1 else 7 if 0.5 <= day_change <= 4.5 else 0
    relative_score = 10 if relative_20 < 0 else 4 if relative_20 == 0 else 0
    breadth_missing = breadth_50 in {None, ""}
    breadth_value = _float(breadth_50)
    breadth_score = 10 if not breadth_missing and breadth_value < 45 else 4 if not breadth_missing and breadth_value <= 65 else 2 if breadth_missing else 0
    liquidity_score = 10 if liquidity == "GREEN" else 5 if liquidity == "AMBER" else 0
    fii_score = 8 if fii_regime == "RELIEF_RALLY_SELL_ON_RISE" else 6 if fii_regime == "STRUCTURAL_WEAKNESS" else 3 if fii_regime == "PROFIT_BOOKING_ONLY" else 0
    return {
        "trend_structure": item("trend_structure", trend_score, f"Sector regime {regime}", regime == "DATA_UNAVAILABLE"),
        "rise_into_resistance": item("rise_into_resistance", rise_score, f"Today {day_change:.2f}%, 50DMA dist {distance_50:.2f}%"),
        "relative_weakness": item("relative_weakness", relative_score, f"20D relative strength {relative_20:.2f}%"),
        "breadth_weakness": item("breadth_weakness", breadth_score, "Breadth unavailable" if breadth_missing else f"{breadth_value:.2f}% above 50DMA", breadth_missing),
        "iv_premium_quality": item("iv_premium_quality", 5, "IV percentile unavailable; using spread premium checks"),
        "options_liquidity": item("options_liquidity", liquidity_score, f"{valid_fno_count} configured F&O candidate(s); {liquidity} liquidity"),
        "fii_flow_regime": item("fii_flow_regime", fii_score, fii_regime),
        "event_risk": item("event_risk", 0 if event_risk else 5, "EVENT RISK - NO NEW SECTOR TRADE" if event_risk else "No configured sector event risk"),
        "rebound_risk": item("rebound_risk", 0 if rebound_risk == "EXTREME" else 2 if rebound_risk == "HIGH" else 4 if rebound_risk == "MODERATE" else 5, rebound_risk),
        "portfolio_capacity": item("portfolio_capacity", 0 if active_sector_exposure >= 3 else 3, f"{active_sector_exposure}/3 sector CE spreads used"),
    }


def classify_rebound_risk(sector_technical: dict[str, Any] | None, fii: dict[str, Any] | None = None) -> str:
    technical = sector_technical or {}
    flow = fii or {}
    distance_50 = _float(technical.get("distance_50_pct"))
    rsi = _float(technical.get("rsi"), 50.0)
    fortnight = _float(flow.get("fortnight_flow_cr"))
    one_year = _float(flow.get("one_year_flow_cr"))
    if distance_50 <= -12 or rsi < 25:
        return "EXTREME"
    if distance_50 <= -8 or (one_year < 0 and fortnight > 6000):
        return "HIGH"
    if distance_50 <= -5 or rsi < 35:
        return "MODERATE"
    return "LOW"


def sector_confidence(component_scores: dict[str, dict[str, Any]]) -> str:
    total = len(component_scores)
    available = sum(1 for item in component_scores.values() if not item.get("missing"))
    ratio = available / total if total else 0
    if ratio >= 0.9:
        return "HIGH"
    if ratio >= 0.75:
        return "MEDIUM"
    if ratio > 0:
        return "LOW"
    return "UNUSABLE"


def rank_all_sectors(
    sector_technicals: dict[str, dict[str, Any]] | None = None,
    fno_counts: dict[str, int] | None = None,
    active_exposure: dict[str, int] | None = None,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    technicals = sector_technicals or {}
    counts = fno_counts or {}
    exposure = active_exposure or {}
    rows = [
        calculate_sector_sell_on_rise_score(
            sector,
            sector_technical=technicals.get(sector, {}),
            valid_fno_count=int(counts.get(sector, len(configured_sector_symbols(sector)))),
            active_sector_exposure=int(exposure.get(sector, 0)),
        )
        for sector in SECTOR_INCOME_UNIVERSE
    ]
    confidence_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNUSABLE": 0}
    status_rank = {"GREEN": 3, "AMBER": 2, "RED": 1}
    rows.sort(
        key=lambda row: (
            status_rank.get(str(row.get("status")), 0),
            confidence_rank.get(str(row.get("confidence")), 0),
            _float(row.get("sector_score")),
            0 if row.get("rebound_risk") in {"HIGH", "EXTREME"} else 1,
        ),
        reverse=True,
    )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        row["sector"] = row.get("sector_key")
        row["display_name"] = row.get("sector_label")
        row["score"] = row.get("sector_score")
        row["regime"] = row.get("sector_regime")
        row["decision"] = "SCAN_TOP_4" if str(row.get("status")) == "GREEN" else "CONFIRM_REQUIRED" if str(row.get("status")) == "AMBER" else "BLOCKED"
    selected = choose_default_sector(rows)
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market_state": "CLOSED",
        "benchmark": "NIFTY 50",
        "selected_sector": selected,
        "top_sectors": rows[:3],
        "all_sectors": rows,
        "message": "NO SECTOR CURRENTLY QUALIFIES" if not selected else "",
    }


def choose_default_sector(ranked_sectors: list[dict[str, Any]]) -> str:
    for row in ranked_sectors:
        if row.get("decision") in {"SCAN_TOP_4", "CONFIRM_REQUIRED"}:
            return str(row.get("sector_key") or row.get("sector") or "")
    return ""


def calculate_stock_sell_on_rise_score(row: dict[str, Any], sector_score: dict[str, Any]) -> dict[str, Any]:
    score = 0.0
    reasons: list[str] = []
    if not row.get("fno_eligible", True):
        return {"stock_score": 0.0, "final_decision": "BLOCKED", "reasons": ["F&O UNAVAILABLE - ORDER BLOCKED"]}
    regime = str(row.get("stock_regime") or row.get("trend_view") or "").upper()
    day_change = _float(row.get("day_change_pct"))
    dist_50 = _float(row.get("distance_from_50dma_pct") or row.get("distance_50_pct"))
    dist_200 = _float(row.get("distance_from_200dma_pct") or row.get("distance_200_pct"))
    liquidity = str(row.get("liquidity_view") or row.get("pair_liquidity_condition") or "UNKNOWN").upper()
    event_risk = str(row.get("event_risk") or "").upper() == "YES"
    if regime in {"BEARISH", "BEARISH_RALLY"}:
        score += 35
        reasons.append("stock below key DMA / sell-on-rise zone")
    elif regime in {"MIXED", "BULLISH_PULLBACK"}:
        score += 18
        reasons.append("mixed DMA setup")
    elif regime == "BULLISH":
        score -= 15
        reasons.append("bullish breakout risk")
    if 1.0 <= day_change <= 4.5:
        score += 15
        reasons.append("controlled rise suitable for review")
    elif day_change > 4.5:
        score -= 8
        reasons.append("large rise may be breakout/short-covering")
    if abs(dist_50) <= 2.0:
        score += 10
    if dist_50 <= -8:
        score -= 10
        reasons.append("deep below 50 DMA; rebound-risk amber")
    if dist_200 < 0:
        score += 10
    if liquidity in {"GREEN", "AMBER", "UNKNOWN"}:
        score += 10 if liquidity == "GREEN" else 5
    if not event_risk:
        score += 5
    sector_component = _float(sector_score.get("sector_score")) * 0.15
    score += sector_component
    score = max(0.0, min(100.0, score))
    if event_risk:
        decision = "BLOCKED"
        reasons.append("event/result risk")
    elif str(sector_score.get("decision") or "").startswith("RED"):
        decision = "BLOCKED"
        reasons.append("sector gate is red")
    elif score >= 70:
        decision = "ALLOWED"
    elif score >= 50:
        decision = "CONFIRM_REQUIRED"
    else:
        decision = "BLOCKED"
    return {"stock_score": round(score, 2), "final_decision": decision, "reasons": reasons}


def rank_sector_candidates(
    rows: list[dict[str, Any]],
    sector_score: dict[str, Any],
    *,
    top_n: int = 4,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for row in rows:
        scored = calculate_stock_sell_on_rise_score(row, sector_score)
        ranked.append({**row, **scored})
    ranked.sort(key=lambda item: (_float(item.get("stock_score")), _float(item.get("day_change_pct"))), reverse=True)
    return ranked[:top_n]
