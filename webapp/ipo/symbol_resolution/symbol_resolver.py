from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote_plus

from ipo.security_map.resolver import resolve_security
from ipo.utils.company_name_cleaner import clean_ipo_company_name


PLACEHOLDER_SYMBOLS = {
    "",
    "-",
    "--",
    "NA",
    "N/A",
    "NONE",
    "PENDING",
    "SYMBOL PENDING",
    "SYMBOLPENDING",
    "TO BE UPDATED",
}

VERIFIED_EXCHANGES = {"NSE", "BSE", "NSE SME", "BSE SME", "SME"}
BAD_SCREENER_MARKERS = (
    "Listed%3A",
    "Listed:",
    "Symbol+pending",
    "Symbol%20pending",
    "Symbol pending",
)


def clean_company_name(value: Any) -> str:
    """Clean noisy IPO tracker names before symbol lookup."""

    return clean_ipo_company_name(value)


def normalize_company_key(value: Any) -> str:
    text = clean_company_name(value).upper()
    text = re.sub(r"\b(LIMITED|LTD|LTD\.|PRIVATE|PVT|PVT\.|INDIA|THE)\b", " ", text)
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def normalize_symbol(value: Any) -> str:
    symbol = re.sub(r"[^A-Z0-9-]", "", str(value or "").upper())
    return "" if symbol in PLACEHOLDER_SYMBOLS else symbol


def normalize_isin(value: Any) -> str:
    isin = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    if isin in PLACEHOLDER_SYMBOLS:
        return ""
    # Real Indian ISINs are 12 characters. A few legacy tests/local trackers
    # have shortened mock values, so keep plausible source IDs instead of
    # dropping the row into an unverified state.
    return isin if 10 <= len(isin) <= 12 else ""


def _default_overrides_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "symbol_overrides.yaml"


def _override_record(symbol: str, exchange: str = "NSE", isin: str = "", source: str = "manual_override") -> dict[str, Any]:
    return {
        "symbol": normalize_symbol(symbol),
        "tradingsymbol": normalize_symbol(symbol),
        "exchange": str(exchange or "NSE").strip().upper(),
        "isin": normalize_isin(isin),
        "verified": True,
        "source": source,
    }


def _flush_structured_override(block: dict[str, Any], records: dict[str, dict[str, Any]]) -> None:
    if not block:
        return
    verified = str(block.get("verified", "")).strip().lower() == "true"
    symbol = normalize_symbol(block.get("tradingsymbol") or block.get("symbol"))
    if not verified or not symbol:
        return
    exchange = str(block.get("exchange") or block.get("preferred_exchange") or "NSE").strip().upper()
    record = _override_record(symbol, exchange, block.get("isin") or "", "structured_override")
    names = [str(block.get("name") or "")]
    names.extend(str(alias) for alias in block.get("aliases", []) if alias)
    for name in names:
        key = normalize_company_key(name)
        if key:
            records[key] = record


def load_symbol_override_records(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load verified manual symbol override records.

    Structured entries with ``verified=false`` are intentionally ignored. This
    prevents pending IPO names from turning into fake production symbols.
    """

    file_path = Path(path) if path else _default_overrides_path()
    if not file_path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    in_flat_overrides = False
    block: dict[str, Any] = {}
    current_list_key = ""
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0 and line.lower() == "overrides:":
            _flush_structured_override(block, records)
            block = {}
            in_flat_overrides = True
            current_list_key = ""
            continue
        if indent == 0 and line.endswith(":"):
            _flush_structured_override(block, records)
            block = {"name": line[:-1].strip()}
            in_flat_overrides = False
            current_list_key = ""
            continue
        if in_flat_overrides and indent > 0 and ":" in line:
            key, value = line.split(":", 1)
            clean_key = normalize_company_key(key)
            clean_value = normalize_symbol(value)
            if clean_key and clean_value:
                records[clean_key] = _override_record(clean_value, "NSE", "", "flat_override")
            continue
        if not block:
            continue
        if line.startswith("- ") and current_list_key:
            block.setdefault(current_list_key, []).append(line[2:].strip().strip('"'))
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"')
            if value:
                block[key] = value
                current_list_key = ""
            else:
                block[key] = []
                current_list_key = key
    _flush_structured_override(block, records)
    return records


def load_symbol_overrides(path: str | Path | None = None) -> dict[str, str]:
    """Backward-compatible override map used by older IPO code/tests."""

    return {
        key: str(record.get("symbol") or "")
        for key, record in load_symbol_override_records(path).items()
        if record.get("symbol")
    }


def screener_url_for(symbol: str, company: str, confidence: int) -> str:
    if symbol and confidence >= 85:
        return f"https://www.screener.in/company/{quote_plus(symbol)}/"
    if company:
        return f"https://www.screener.in/search/?q={quote_plus(company)}"
    return "https://www.screener.in/"


def _bad_screener_url(url: str) -> bool:
    if not url:
        return True
    return any(marker.lower() in url.lower() for marker in BAD_SCREENER_MARKERS)


def _coerce_instrument_master(master: Any) -> list[dict[str, Any]]:
    if not master:
        return []
    if isinstance(master, dict):
        for key in ("instruments", "records", "data"):
            value = master.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [master]
    if isinstance(master, list):
        return [item for item in master if isinstance(item, dict)]
    return []


def _instrument_value(instrument: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in instrument and instrument.get(name) not in {None, ""}:
            return instrument.get(name)
    return ""


def _instrument_candidate(instrument: dict[str, Any], method: str, score: int) -> dict[str, Any]:
    symbol = normalize_symbol(_instrument_value(instrument, "tradingsymbol", "symbol", "ticker"))
    exchange = str(_instrument_value(instrument, "exchange", "segment") or "NSE").strip().upper()
    return {
        "symbol": symbol,
        "tradingsymbol": symbol,
        "exchange": exchange,
        "isin": normalize_isin(_instrument_value(instrument, "isin", "isin_code")),
        "instrument_token": _instrument_value(instrument, "instrument_token", "token"),
        "name": clean_company_name(_instrument_value(instrument, "name", "company_name", "company")),
        "match_method": method,
        "match_score": score,
    }


def search_kite_instrument_master(
    company: str,
    symbol: str = "",
    isin: str = "",
    instrument_master: Any = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Resolve an IPO row against a provided Kite instrument master snapshot.

    The function is intentionally pure and accepts an injected instrument list.
    Production code can pass a cached Kite master; tests can pass small fixtures.
    """

    instruments = _coerce_instrument_master(instrument_master)
    if not instruments:
        return None, []
    company_key = normalize_company_key(company)
    symbol = normalize_symbol(symbol)
    isin = normalize_isin(isin)
    candidates: list[dict[str, Any]] = []
    for instrument in instruments:
        candidate = _instrument_candidate(instrument, "KITE_INSTRUMENT_NAME", 0)
        instrument_symbol = str(candidate.get("symbol") or "")
        instrument_name_key = normalize_company_key(candidate.get("name") or "")
        instrument_isin = str(candidate.get("isin") or "")
        if not instrument_symbol:
            continue
        if isin and instrument_isin and isin == instrument_isin:
            candidates.append({**candidate, "match_method": "KITE_INSTRUMENT_ISIN", "match_score": 100})
            continue
        if symbol and instrument_symbol == symbol:
            candidates.append({**candidate, "match_method": "KITE_INSTRUMENT_SYMBOL", "match_score": 95})
            continue
        if company_key and instrument_name_key and company_key == instrument_name_key:
            candidates.append({**candidate, "match_method": "KITE_INSTRUMENT_COMPANY", "match_score": 88})
            continue
        if company_key and instrument_name_key:
            company_words = set(company_key.split())
            instrument_words = set(instrument_name_key.split())
            if len(company_words) >= 2 and company_words.issubset(instrument_words):
                candidates.append({**candidate, "match_method": "KITE_INSTRUMENT_PARTIAL_COMPANY", "match_score": 78})
    candidates.sort(key=lambda item: int(item.get("match_score") or 0), reverse=True)
    return (candidates[0] if candidates else None), candidates[:5]


def _stringify_pipeline(steps: Iterable[str]) -> str:
    return " -> ".join(step for step in steps if step)


def resolve_ipo_identity(
    row_or_name: dict[str, Any] | str,
    market: str = "NSE",
    instrument_master: Any = None,
) -> dict[str, Any]:
    """Resolve an IPO company into a tradable identity with an audit trail.

    Pipeline:
    IPO company name -> clean name -> saved override -> Kite instrument master
    -> exchange/tradingsymbol -> NSE/BSE/ISIN verification -> Screener URL.
    """

    row: dict[str, Any] = row_or_name if isinstance(row_or_name, dict) else {"company_name": row_or_name}
    raw_company = str(row.get("company_name") or row.get("company") or row.get("ipo_name") or "")
    company = clean_company_name(raw_company)
    steps = [f"Clean company name: {company or 'MISSING'}"]
    raw_symbol = row.get("symbol") or row.get("ticker") or row.get("tradingsymbol") or ""
    source_symbol = normalize_symbol(raw_symbol)
    if source_symbol:
        steps.append(f"Source symbol: {source_symbol}")
    else:
        steps.append("Source symbol: missing/pending")

    master = instrument_master if instrument_master is not None else (
        row.get("instrument_master") or row.get("kite_instruments") or row.get("instruments")
    )
    security_resolution = resolve_security(
        {**row, "company_name": company, "symbol": source_symbol},
        instrument_master=master,
    )
    if security_resolution:
        security_steps = security_resolution.get("resolution_steps") or []
        combined_steps = steps + [str(step) for step in security_steps]
        security_resolution.update(
            {
                "company_name": str(row.get("company_name") or company),
                "raw_company_name": raw_company,
                "clean_company_name": company,
                "source_symbol": source_symbol,
                "resolution_steps": combined_steps,
                "resolution_pipeline": _stringify_pipeline(combined_steps),
            }
        )
        return security_resolution

    overrides = load_symbol_override_records()
    company_key = normalize_company_key(company)
    override = overrides.get(company_key, {})
    override_symbol = normalize_symbol(override.get("symbol") or override.get("tradingsymbol"))
    if override_symbol:
        steps.append(f"Saved override: {override_symbol}")
    else:
        steps.append("Saved override: none")

    initial_symbol = source_symbol or override_symbol
    input_isin = normalize_isin(row.get("isin") or override.get("isin") or "")
    instrument_match, candidates = search_kite_instrument_master(company, initial_symbol, input_isin, master)
    if instrument_match:
        steps.append(
            f"Kite instrument master: {instrument_match.get('symbol')} ({instrument_match.get('match_method')})"
        )
    else:
        steps.append("Kite instrument master: no match/not supplied")

    symbol = normalize_symbol((instrument_match or {}).get("symbol")) or initial_symbol
    exchange = str(
        (instrument_match or {}).get("exchange")
        or override.get("exchange")
        or row.get("exchange")
        or market
        or "NSE"
    ).strip().upper()
    isin = normalize_isin((instrument_match or {}).get("isin")) or input_isin
    instrument_token = (instrument_match or {}).get("instrument_token") or row.get("instrument_token") or ""
    isin_match_status = "MATCHED" if input_isin and instrument_match and input_isin == (instrument_match.get("isin") or "") else ""
    if not isin_match_status:
        isin_match_status = "SOURCE_ISIN" if isin else "MISSING"
    exchange_verified = exchange in VERIFIED_EXCHANGES
    isin_verified = bool(isin)

    if instrument_match and int(instrument_match.get("match_score") or 0) >= 88:
        confidence = 98 if isin_verified else 92
        status = "RESOLVED"
        method = str(instrument_match.get("match_method") or "KITE_INSTRUMENT")
    elif source_symbol:
        confidence = 95 if isin_verified else 90
        status = "RESOLVED"
        method = "SOURCE_SYMBOL"
    elif override_symbol:
        confidence = 92 if isin_verified else 90
        status = "RESOLVED"
        method = "VERIFIED_MANUAL_OVERRIDE"
    elif company:
        confidence = 55
        status = "UNRESOLVED"
        method = "SEARCH_ONLY"
    else:
        confidence = 0
        status = "UNRESOLVED"
        method = "MISSING_COMPANY"

    is_listed_verified = bool(symbol and confidence >= 85 and exchange_verified and (isin_verified or instrument_match))
    if is_listed_verified:
        steps.append(f"NSE/BSE verification: verified on {exchange}")
    elif symbol and confidence >= 85:
        steps.append("NSE/BSE verification: symbol resolved, ISIN/listing data pending")
    else:
        steps.append("NSE/BSE verification: unresolved")
    steps.append(f"ISIN: {isin_match_status}")

    screener_url = str(row.get("screener_url") or "").strip()
    if _bad_screener_url(screener_url):
        screener_url = screener_url_for(symbol, company, confidence)
    screener_status = "DIRECT" if symbol and confidence >= 85 and "/company/" in screener_url else "SEARCH"
    steps.append(f"Screener URL: {screener_status}")

    return {
        "company_name": str(row.get("company_name") or company),
        "raw_company_name": raw_company,
        "clean_company_name": company,
        "validated_company_name": company,
        "source_symbol": source_symbol,
        "override_symbol": override_symbol,
        "symbol": symbol,
        "resolved_tradingsymbol": symbol,
        "exchange": exchange,
        "isin": isin,
        "screener_url": screener_url,
        "screener_url_status": screener_status,
        "nse_url": f"https://www.nseindia.com/get-quotes/equity?symbol={quote_plus(symbol)}" if symbol else "",
        "bse_url": f"https://www.bseindia.com/stock-share-price/{quote_plus(symbol)}/" if symbol else "",
        "kite_symbol": symbol,
        "kite_key": f"{exchange}:{symbol}" if symbol else "",
        "instrument_token": instrument_token,
        "resolution_confidence": confidence,
        "status": status,
        "resolution_status": status,
        "match_method": method,
        "instrument_match_method": str((instrument_match or {}).get("match_method") or ""),
        "top_candidates": candidates,
        "is_listed_verified": is_listed_verified,
        "eligible_identity": is_listed_verified,
        "exchange_verified": exchange_verified,
        "isin_match_status": isin_match_status,
        "verification_status": "VERIFIED" if is_listed_verified else "DATA_PENDING",
        "verification_reasons": [
            reason
            for reason, present in (
                ("symbol", bool(symbol)),
                ("exchange", exchange_verified),
                ("isin_or_kite_match", bool(isin_verified or instrument_match)),
            )
            if not present
        ],
        "resolution_steps": steps,
        "resolution_pipeline": _stringify_pipeline(steps),
    }


def resolve_symbol(
    row_or_name: dict[str, Any] | str,
    market: str = "NSE",
    instrument_master: Any = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the explicit IPO identity pipeline."""

    return resolve_ipo_identity(row_or_name, market=market, instrument_master=instrument_master)
