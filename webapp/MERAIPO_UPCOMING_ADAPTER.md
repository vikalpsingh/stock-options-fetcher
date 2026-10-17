# MeraIPO Upcoming IPO Adapter

## Purpose

Add MeraIPO as an additional **upcoming IPO discovery source** for the trading
app. The adapter must normalize MeraIPO rows into the same structure already
used by:

- `fetch_nse_upcoming_ipos()`
- `fetch_ipowatch_upcoming_ipos()`
- `_load_research_ready_upcoming_ipos()`
- `_upcoming_ipos_next_7_days()`

This is a market-data ingestion change only. It must not create trade signals,
place orders, or make an IPO application recommendation.

> Naming assumption: “merino” in the request means **MeraIPO**
> (`https://www.meraipo.com/`).

## Important source limitation

MeraIPO currently exposes open, upcoming, and “dates awaited” IPO information
on its public home page. Some MeraIPO issue pages identify IPOALERTS as the
supplier for schedule data. Therefore, MeraIPO is useful as a fallback and
cross-check, but it must not be treated as an independent authoritative source
for every field.

Source priority should remain:

1. NSE/BSE official data for dates, issue status, and subscription data.
2. MeraIPO for missing upcoming rows and display metadata.
3. IPOWatch for GMP/display enrichment when available.
4. Manual CSV upload as the operational fallback.

Conflicts must keep the official exchange value and record a source note.

Reference pages reviewed on 16 October 2026:

- [MeraIPO primary-market page](https://www.meraipo.com/)
- [Example MeraIPO issue guide showing schedule provenance](https://www.meraipo.com/ipo/hdfire)
- [NSE upcoming IPO page](https://www.nseindia.com/market-data/all-upcoming-issues-ipo)

## Existing integration point

The current upcoming source registry is inside
`ipo_data_service._load_research_ready_upcoming_ipos()`:

```python
for label, fetcher in (
    ("NSE upcoming IPO API", fetch_nse_upcoming_ipos),
    ("IPOWatch GMP/upcoming table", fetch_ipowatch_upcoming_ipos),
):
    ...
```

Add MeraIPO to this registry without removing the existing adapters:

```python
for label, fetcher in (
    ("NSE upcoming IPO API", fetch_nse_upcoming_ipos),
    ("MeraIPO upcoming IPO table", fetch_meraipo_upcoming_ipos),
    ("IPOWatch GMP/upcoming table", fetch_ipowatch_upcoming_ipos),
):
    ...
```

## Configuration

Add these defaults beside the current upcoming-source constants:

```python
DEFAULT_MERAIPO_UPCOMING_URL = "https://www.meraipo.com/"
MERAIPO_SOURCE_LABEL = "MeraIPO upcoming IPO table"
```

Allow a server override:

```text
IPO_MERAIPO_UPCOMING_URL=https://www.meraipo.com/
```

Do not commit cookies, session headers, credentials, downloaded responses, or
anti-bot tokens. The adapter should use the existing `_http_get_text()` timeout
and headers.

## Canonical row contract

Every MeraIPO record returned by the adapter must use this shape:

| Field | Required | Normalized value |
|---|---:|---|
| `company_name` | Yes | Clean company display name |
| `symbol` | No | Exchange symbol only when explicitly available |
| `ipo_date` | Yes for scheduled rows | Opening date or `N/A` |
| `ipo_close_date` | No | Closing date or `N/A` |
| `sector` | No | Industry/sector, otherwise `N/A` |
| `market_type` | Yes | `Mainboard`, `SME`, or `N/A` |
| `ipo_type` | No | Security/issue type, otherwise `N/A` |
| `issue_size` | No | Display value without inventing zero |
| `price_band` | No | Full band such as `₹258–₹271` |
| `lot_size` | No | Minimum lot size |
| `gmp` | No | Unofficial GMP display value |
| `gmp_pct` | No | Numeric percentage when calculable |
| `source` | Yes | `MeraIPO upcoming IPO table` |
| `source_url` | Yes | MeraIPO page used for the row |
| `source_status` | Yes | `LIVE_HTML`, `MANUAL_UPLOAD`, or `STALE_CACHE` |
| `last_updated_at` | Yes | App ingestion timestamp |

Missing data must remain `N/A` or `None`. Never convert missing issue size,
price, lot size, GMP, or subscription figures to zero.

## Field mapping

MeraIPO’s public table currently presents fields similar to the following:

| MeraIPO display field | Canonical field |
|---|---|
| Company / bidding dates | `company_name`, `ipo_date`, `ipo_close_date` |
| Security type | `ipo_type` and `market_type` |
| Issue size (₹ crore) | `issue_size` |
| Price band | `price_band` |
| Lot size | `lot_size` |
| GMP · unofficial | `gmp` |
| GMP % | `gmp_pct` |
| Status | source metadata only |

Do not ingest subscription percentages into the existing upcoming row contract
until a separate verified subscription schema is introduced.

## Adapter skeleton

Implement in `ipo_data_service.py` near `fetch_ipowatch_upcoming_ipos()`:

```python
def fetch_meraipo_upcoming_ipos(today: date | None = None) -> dict[str, Any]:
    """Fetch and normalize public MeraIPO open/upcoming issue rows."""
    url = os.getenv("IPO_MERAIPO_UPCOMING_URL", DEFAULT_MERAIPO_UPCOMING_URL)
    markup = _http_get_text(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Referer": "https://www.meraipo.com/",
        },
    )
    now = _now_text()
    records: list[dict[str, Any]] = []

    for raw in _records_from_html_tables(markup):
        company = _first_present(
            raw,
            ["company_bidding_dates", "company", "company_name", "issuer", "name"],
        )
        if not company:
            continue

        # Keep parsing in small testable helpers. MeraIPO may combine company and
        # dates in one cell, so split dates without treating them as company text.
        company_name, open_date, close_date = _parse_meraipo_company_and_dates(
            company,
            default_year=(today or date.today()).year,
        )
        if not company_name:
            continue

        security_type = _first_present(raw, ["security_type", "type", "board"])
        price_band = _first_present(raw, ["price_band", "price"])
        gmp = _first_present(raw, ["gmp_unofficial", "gmp", "premium"])

        records.append(
            {
                "company_name": clean_ipo_company_name(company_name),
                "symbol": "",  # Resolve later; do not guess from company words.
                "ipo_date": open_date or "N/A",
                "ipo_close_date": close_date or "N/A",
                "sector": "N/A",
                "market_type": _ipo_market_type_from_text(security_type, "N/A"),
                "ipo_type": _clean_text(security_type or "N/A"),
                "issue_size": _first_present(raw, ["issue_size_crore", "issue_size"]) or "N/A",
                "price_band": price_band or "N/A",
                "lot_size": _first_present(raw, ["lot_size", "lot"]) or "N/A",
                "gmp": gmp or "N/A",
                "gmp_pct": _number(_first_present(raw, ["gmp_pct", "gmp_percent"]))
                or _gmp_percent(gmp, price_band),
                "source": MERAIPO_SOURCE_LABEL,
                "source_url": url,
                "source_status": "LIVE_HTML",
                "last_updated_at": now,
            }
        )

    return {
        "records": _deduplicate_meraipo_rows(records),
        "source": url,
        "error": "",
    }
```

The code above is an integration template. Confirm the actual normalized HTML
headers with a saved test fixture before finalizing the aliases.

## Parser requirements

Create focused helpers rather than embedding regular expressions in the fetcher:

```python
def _parse_meraipo_company_and_dates(
    value: Any,
    default_year: int,
) -> tuple[str, str | None, str | None]:
    ...


def _deduplicate_meraipo_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ...
```

Rules:

- Support `13 Oct 2026 – 15 Oct 2026` and equivalent hyphen variants.
- Keep `To be announced` rows only for the broader announced watchlist.
- Do not place undated rows in “Next 7 Days”. Existing date filtering will
  naturally exclude them.
- Deduplicate by normalized company name plus open date, not by guessed symbol.
- Preserve the source URL and ingestion timestamp.
- Reject navigation text, modal headings, repeated snapshots, and header rows.
- Cap records to a defensive maximum such as 100 rows.

## Manual upload fallback

Add a MeraIPO CSV upload option only if live HTML remains unreliable. Accept
UTF-8 CSV with these headers:

```csv
company_name,ipo_open_date,ipo_close_date,market_type,issue_size,price_band,lot_size,gmp,gmp_pct,source_url
Example Industries Limited,2026-10-21,2026-10-23,Mainboard,1450,660-693,21,95,13.71,https://www.meraipo.com/ipo/example
```

Upload behavior:

1. Validate extension, MIME type, UTF-8 decoding, and a reasonable size limit.
2. Normalize every row into the canonical contract.
3. Reject rows without a company name.
4. Reject invalid dates instead of silently changing them.
5. Set `source="MeraIPO manual upload"` and
   `source_status="MANUAL_UPLOAD"`.
6. Save through the existing IPO cache/snapshot layer, never beside broker or
   runtime credential files.
7. Show accepted, rejected, duplicate, and undated row counts in the UI.
8. Manual upload must not trigger any broker/order operation.

## Merge policy

The existing `_merge_by_symbol()` is weak for pre-listing companies because a
real exchange symbol may not exist. Introduce an upcoming-specific key:

```python
def _upcoming_identity_key(row: dict[str, Any]) -> str:
    symbol = _clean_text(row.get("symbol")).upper()
    if symbol:
        return f"SYMBOL:{symbol}"
    company = _ipo_company_lookup_key(row.get("company_name") or "")
    return f"COMPANY:{company}"
```

Merge precedence per field:

- NSE/BSE official non-empty value wins.
- MeraIPO fills only missing official fields.
- IPOWatch may fill missing GMP fields.
- Manual upload may fill missing fields but must not overwrite newer official
  values.
- `0` must not be treated as a valid replacement for unavailable market data.

Record provenance either as `field_sources` or at minimum:

```python
{
    "source": "NSE upcoming IPO API + MeraIPO upcoming IPO table",
    "source_urls": ["..."],
    "source_conflicts": ["ipo_close_date"],
}
```

## Caching and operational safety

- Use the existing IPO cache abstraction and a source-specific cache key.
- Recommended TTL: 30 minutes while an issue is open; 4 hours for announced
  issues with dates awaited.
- On network/parser failure, return the last valid cached snapshot with
  `source_status="STALE_CACHE"` and a visible warning.
- Never replace a non-empty cache with an empty scrape.
- Log counts and error categories, not full page content.
- Do not retry more than once in a foreground request.
- Respect MeraIPO terms, robots policy, and rate limits. If automated access is
  disallowed, retain only the manual CSV upload path.

## Tests

All tests must use local fixtures and mocks—never call MeraIPO, NSE, IPOWatch,
or broker APIs.

Required cases:

1. Open Mainboard issue with full dates and price band.
2. Open SME issue with comma-formatted lot size.
3. Announced issue with dates awaited.
4. Missing GMP remains `N/A`, not zero.
5. GMP percentage is calculated from the upper price band.
6. Duplicate modal/table representation becomes one record.
7. Invalid/no-company rows are rejected.
8. MeraIPO failure does not prevent NSE rows from loading.
9. Official NSE dates win when MeraIPO dates conflict.
10. Manual CSV upload reports accepted/rejected/duplicate counts.
11. “Next 7 Days” includes open issues and scheduled openings only.
12. No test performs live network or broker calls.

Suggested fixtures:

```text
tests/fixtures/meraipo/upcoming_open.html
tests/fixtures/meraipo/upcoming_announced.html
tests/fixtures/meraipo/upcoming_changed_headers.html
tests/fixtures/meraipo/upcoming_upload.csv
```

## Acceptance criteria

- IPO page loads when IPOWatch is unavailable.
- MeraIPO rows appear through the same normalized upcoming-IPO table.
- Official exchange data retains priority.
- Undated announced IPOs do not incorrectly appear in “Next 7 Days”.
- Missing values stay missing and are never displayed as zero.
- Source and freshness are visible for every imported row.
- Empty or malformed MeraIPO output cannot erase the last good snapshot.
- All existing IPO tests plus the new adapter/upload tests pass.
- No broker credentials, page dumps, uploaded CSVs, or runtime databases are
  committed.

## Recommended delivery sequence

1. Save representative sanitized MeraIPO HTML fixtures.
2. Implement parser helpers and fixture tests.
3. Implement `fetch_meraipo_upcoming_ipos()`.
4. Add source registry and source-priority merge tests.
5. Add cache/fallback behavior.
6. Add optional manual CSV upload only if automated access is unreliable or
   disallowed.
7. Run `py_compile` and the full IPO test suite.

