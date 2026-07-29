from __future__ import annotations

from ipo.config.verified_bse_mappings import VERIFIED_BSE_MAPPINGS
from ipo.config.verified_nse_mappings import VERIFIED_NSE_MAPPINGS
from ipo.security_map.normalizer import (
    clean_security_company_name,
    is_forbidden_false_match,
    normalize_company_name,
)
from ipo.security_map.repository import get_security_mapping, load_security_map, save_security_map
from ipo.security_map.resolver import resolve_security
from ipo.security_map.seed_security_map import build_seed_security_map, run_security_map_audit
from ipo.symbol_resolution.symbol_resolver import resolve_ipo_identity


def test_security_map_seed_counts_and_audit_are_clean():
    seed = build_seed_security_map()
    audit = run_security_map_audit(seed)

    assert len(VERIFIED_NSE_MAPPINGS) == 49
    assert len(VERIFIED_BSE_MAPPINGS) == 19
    assert len(seed) == 68
    assert all(row["status"] == "PASS" for row in audit)


def test_security_map_resolves_known_nse_companies_and_aliases():
    ksh = resolve_security("KSH International")
    apsis = resolve_security("Ap Apsis Aerocom Listed: 18 Mar 2026 Symbol pending")
    groww = resolve_security("Billionbrains Garage Ventures Limited")

    assert ksh and ksh["symbol"] == "KSHINTL"
    assert apsis and apsis["symbol"] == "APSISAERO"
    assert apsis["exchange"] == "NSE"
    assert apsis["resolution_status"] == "SOURCE_VERIFIED"
    assert groww and groww["symbol"] == "GROWW"
    assert groww["legal_name"] == "Billionbrains Garage Ventures Limited"


def test_security_map_resolves_known_bse_companies_without_kite_symbol_assumption():
    indo = resolve_security("In Indo SMC Listed: 01 Jan 2026")

    assert indo
    assert indo["symbol"] == "544681"
    assert indo["exchange"] == "BSE"
    assert indo["bse_security_code"] == "544681"
    assert indo["kite_verified"] is False
    assert indo["kite_key"] == ""
    assert indo["screener_url"] == "https://www.screener.in/company/544681/"


def test_security_map_blocks_forbidden_false_matches():
    assert is_forbidden_false_match("Nanta Tech", "TAALTECH")
    assert is_forbidden_false_match("Indo SMC", "SMLMAH")
    assert is_forbidden_false_match("Groww", "GKWLIMITED")

    nanta = resolve_ipo_identity({"company_name": "Na Nanta Tech Listed: 20 Oct 2025", "symbol": "TAALTECH"})
    assert nanta["symbol"] == "544668"
    assert nanta["exchange"] == "BSE"
    assert nanta["source_symbol"] == "TAALTECH"
    assert nanta["kite_key"] == ""
    assert "Rejected forbidden source symbol TAALTECH" in nanta["resolution_pipeline"]


def test_security_map_exact_kite_validation_is_separate_from_source_verification():
    resolution = resolve_ipo_identity(
        {
            "company_name": "Groww",
            "symbol": "GROWW",
            "instrument_master": [
                {
                    "tradingsymbol": "GROWW",
                    "exchange": "NSE",
                    "instrument_token": 98765,
                    "name": "Billionbrains Garage Ventures Limited",
                }
            ],
        }
    )

    assert resolution["symbol"] == "GROWW"
    assert resolution["kite_verified"] is True
    assert resolution["kite_key"] == "NSE:GROWW"
    assert resolution["instrument_token"] == 98765
    assert resolution["mapping_status"] == "PARTIALLY_VERIFIED"


def test_security_map_normalizer_preserves_india_to_avoid_bad_matches():
    assert normalize_company_name("Tipco Engineering India") != normalize_company_name("Tipco Engineering")
    assert clean_security_company_name("Rubicon Research Listed: 16 Oct 2025 Symbol pending") == "Rubicon Research"


def test_security_map_repository_can_persist_without_losing_seeds(tmp_path):
    path = tmp_path / "company_security_map.json"
    seed = build_seed_security_map()
    save_security_map(seed, path=path, audit_path=tmp_path / "audit.jsonl")
    loaded = load_security_map(path=path)

    assert len(loaded) == 68
    assert get_security_mapping("Rubicon Research Limited", path=path).nse_symbol == "RUBICON"
