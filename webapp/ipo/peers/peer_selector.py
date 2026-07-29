from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ipo.symbol_resolution.symbol_resolver import clean_company_name, normalize_company_key


def _default_peer_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "sector_peer_leaders.yaml"


def load_sector_peer_leaders(path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    file_path = Path(path) if path else _default_peer_path()
    if not file_path.exists():
        return {}
    mapping: dict[str, list[dict[str, Any]]] = {}
    current_key = ""
    in_leaders = False
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            current_key = stripped[:-1]
            mapping.setdefault(current_key, [])
            in_leaders = False
            continue
        if stripped == "leaders:":
            in_leaders = True
            continue
        if current_key and in_leaders and stripped.startswith("- "):
            parts = [part.strip() for part in stripped[2:].split("|")]
            symbol = parts[0] if parts else ""
            company = parts[1] if len(parts) > 1 else symbol
            exchange = parts[2] if len(parts) > 2 else "NSE"
            sector = parts[3] if len(parts) > 3 else current_key.replace("_", " ").title()
            theme = parts[4] if len(parts) > 4 else sector
            mapping[current_key].append(
                {
                    "company_name": company,
                    "symbol": symbol,
                    "exchange": exchange,
                    "sector": sector,
                    "theme": theme,
                    "ipo_type": "Peer",
                    "market_type": "Peer",
                    "source": "sector_peer_leaders",
                    "role": "Peer Leader",
                }
            )
    return mapping


def infer_research_theme(row: dict[str, Any]) -> str:
    text = " ".join(
        str(row.get(field) or "")
        for field in ("company_name", "sector", "theme", "industry", "business", "description")
    ).lower()
    checks = [
        ("power_electrical_infra", ("power", "electrical", "grid", "transformer", "cable", "infra")),
        ("ems_electronics", ("ems", "electronics", "electro", "pcb", "semiconductor", "consumer durable")),
        ("defence_aerospace", ("defence", "defense", "aerospace", "shipyard", "missile", "naval")),
        ("diagnostics_healthcare", ("health", "diagnostic", "hospital", "pharma", "laborator")),
        ("financialization_amc", ("amc", "asset management", "depository", "exchange", "capital market", "finance")),
        ("specialty_chemicals", ("chemical", "specialty", "fluoro", "dye", "intermediate")),
        ("fmcg_ingredients", ("consumer", "fmcg", "food", "premium", "beverage")),
        ("data_centre_infra", ("data centre", "data center", "cloud", "network", "server")),
        ("manufacturing_capex", ("manufacturing", "industrial", "automation", "machine", "capex", "engineering")),
    ]
    for theme_key, keywords in checks:
        if any(keyword in text for keyword in keywords):
            return theme_key
    return "general_quality"


def _from_universe(row: dict[str, Any], universe: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    theme_key = infer_research_theme(row)
    selected_company_key = normalize_company_key(row.get("company_name"))
    selected_symbol = str(row.get("symbol") or "").upper()
    peers = []
    for candidate in universe:
        if normalize_company_key(candidate.get("company_name")) == selected_company_key:
            continue
        if selected_symbol and str(candidate.get("symbol") or "").upper() == selected_symbol:
            continue
        if infer_research_theme(candidate) != theme_key:
            continue
        peers.append(dict(candidate, role="Peer Candidate"))
    peers.sort(
        key=lambda item: (
            float(item.get("market_cap") or item.get("current_market_cap") or 0),
            float(item.get("liquidity_score") or 0),
        ),
        reverse=True,
    )
    return peers[:limit]


def select_top_peers(
    row: dict[str, Any],
    limit: int = 2,
    universe: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if universe:
        matched = _from_universe(row, universe, limit)
        if matched:
            return matched
    theme_key = infer_research_theme(row)
    leaders = load_sector_peer_leaders().get(theme_key) or load_sector_peer_leaders().get("manufacturing_capex") or []
    selected_symbol = str(row.get("symbol") or "").upper()
    selected_name = normalize_company_key(row.get("company_name"))
    result = []
    for leader in leaders:
        if selected_symbol and str(leader.get("symbol") or "").upper() == selected_symbol:
            continue
        if normalize_company_key(leader.get("company_name")) == selected_name:
            continue
        result.append(dict(leader, theme_key=theme_key, peer_type="broad sector peer"))
        if len(result) >= limit:
            break
    return result


def select_sector_leaders(rows: list[dict[str, Any]], limit_per_theme: int = 2) -> list[dict[str, Any]]:
    selected_symbols = {str(row.get("symbol") or "").upper() for row in rows}
    selected_names = {normalize_company_key(row.get("company_name")) for row in rows}
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        for peer in select_top_peers(row, limit=limit_per_theme):
            key = str(peer.get("symbol") or clean_company_name(peer.get("company_name"))).upper()
            if key in seen or key in selected_symbols or normalize_company_key(peer.get("company_name")) in selected_names:
                continue
            seen.add(key)
            result.append(peer)
    return result

