from __future__ import annotations

import re
from typing import Any

from ipo.utils.company_name_cleaner import clean_ipo_company_name


ALIASES: dict[str, list[str]] = {
    "Apsis Aerocom": ["Apsis Aerocom Limited", "Ap Apsis Aerocom"],
    "Gaudium IVF": ["Gaudium IVF and Women Health", "Gaudium IVF and Women Health Limited"],
    "OnEMI Technology Solutions (KISSHT)": [
        "OnEMI Technology Solutions",
        "OnEMI Technology Solutions Limited",
        "KISSHT",
    ],
    "E to E Transportation Infrastructur...": [
        "E To E Transportation Infrastructure",
        "E To E Transportation Infrastructure Limited",
    ],
    "Central Mine Planning & Design Inst...": [
        "Central Mine Planning & Design Institute",
        "Central Mine Planning & Design Institute Limited",
        "CMPDI",
    ],
    "Sai Parenteral's": ["Sai Parenterals", "Sai Parenterals Limited"],
    "Groww": ["Billionbrains Garage Ventures", "Billionbrains Garage Ventures Limited", "Groww"],
    "ICICI Prudential AMC": [
        "ICICI Prudential Asset Management Company",
        "ICICI Prudential Asset Management Company Limited",
    ],
    "Rubicon Research": ["Rubicon ResearchRUBICON", "Rubicon Research Limited"],
    "Bai Kakaji Polymers": ["Bai-Kakaji Polymers", "Bai-Kakaji Polymers Limited"],
}


FORBIDDEN_FALSE_MATCHES: dict[str, list[str]] = {
    "Indo SMC": ["SMLMAH"],
    "Merritronix": ["MARINETRAN"],
    "Millworks Technologies": ["MACOBSTECH"],
    "Vegorama Punjabi Angithi": ["AGUL"],
    "Accretion Nutraveda": ["JAIPURKURT"],
    "Tipco Engineering India": ["PITTIENG"],
    "GRE Renew Enertech": ["GREENLEAF"],
    "Elfin Agro India": ["ARFIN"],
    "Susan Electricals India": ["RULKA"],
    "Devson Catalyst": ["AVL"],
    "Hannah Joseph Hospital": ["SUPREME"],
    "Highness Microelectronics": ["AIMTRON"],
    "Msafe Equipments": ["RVTH"],
    "Autofurnish": ["OMFURN"],
    "Recode Studios": ["STUDIOLSD"],
    "Crazy Snacks": ["DIAMONDYD"],
    "Nanta Tech": ["TAALTECH"],
    "Groww": ["GKWLIMITED"],
    "Admach Systems": ["RAMCOSYS"],
    "Bai Kakaji Polymers": ["MPEL"],
}


_CORPORATE_SUFFIX_RE = re.compile(
    r"\b(LIMITED|LTD|LTD\.|PRIVATE|PVT|PVT\.|CO|COMPANY|CORPORATION|CORP)\b",
    re.IGNORECASE,
)


def clean_security_company_name(value: Any) -> str:
    """Clean IPO tracker noise without removing meaningful words like India."""

    text = clean_ipo_company_name(value)
    text = re.sub(r"\s+", " ", text).strip(" -:|")
    return text


def normalize_company_name(value: Any) -> str:
    """Stable lookup key for verified company mapping.

    This deliberately keeps words such as ``India`` because many IPO names need
    that word to avoid false matches across similarly named businesses.
    """

    text = clean_security_company_name(value).upper()
    text = _CORPORATE_SUFFIX_RE.sub(" ", text)
    text = re.sub(r"&", " AND ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def normalize_security_symbol(value: Any) -> str:
    return re.sub(r"[^A-Z0-9-]", "", str(value or "").upper())


def build_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, aliases in ALIASES.items():
        index[normalize_company_name(canonical)] = canonical
        for alias in aliases:
            index[normalize_company_name(alias)] = canonical
    return index


def canonical_name_for(value: Any) -> str:
    cleaned = clean_security_company_name(value)
    alias = build_alias_index().get(normalize_company_name(cleaned))
    return alias or cleaned


def forbidden_false_matches_for(company_name: Any) -> list[str]:
    canonical = canonical_name_for(company_name)
    return [normalize_security_symbol(item) for item in FORBIDDEN_FALSE_MATCHES.get(canonical, [])]


def is_forbidden_false_match(company_name: Any, candidate_symbol: Any) -> bool:
    symbol = normalize_security_symbol(candidate_symbol)
    return bool(symbol and symbol in forbidden_false_matches_for(company_name))
