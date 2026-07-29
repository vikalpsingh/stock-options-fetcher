from __future__ import annotations

from urllib.parse import quote_plus

from .models import SecurityMapping


def build_screener_url(mapping: SecurityMapping | None = None, company_name: str = "") -> tuple[str, str]:
    if mapping:
        if mapping.nse_symbol:
            return f"https://www.screener.in/company/{quote_plus(mapping.nse_symbol)}/", "DIRECT_NSE"
        if mapping.bse_security_code:
            return f"https://www.screener.in/company/{quote_plus(mapping.bse_security_code)}/", "DIRECT_BSE"
        if mapping.canonical_name:
            return f"https://www.screener.in/search/?q={quote_plus(mapping.canonical_name)}", "SEARCH"
    if company_name:
        return f"https://www.screener.in/search/?q={quote_plus(company_name)}", "SEARCH"
    return "https://www.screener.in/", "SEARCH"
