from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from app import PageState, parse_multipart_form, render_value_stock_panel
from value_stock.models import ParsedValueStock
import value_stock.pdf_parser as pdf_parser
from value_stock.assessment import assess_metric, assess_table
from value_stock.pdf_parser import (
    build_value_score,
    normalize_screener_text,
    parse_screener_pdf_text,
)
from value_stock.repository import ValueStockRepository


SAMPLE_TEXT = """
8/2/26, 2:03 PM Apsis Aerocom Ltd share price | About Apsis Aerocom | Key Insights - Screener
Apsis Aerocom Ltd
A B O U T
Incorporated in 2022, APSIS Aerocom Limited is engaged in precision engineering.
K E Y P O I N T S
Website NSE - ST
Market Cap ₹ 523 Cr.
Current Price ₹ 434
Stock P/E 69.7
Book Value ₹ 40.6
Dividend Yield 0.00 %
ROCE 31.8 %
ROE 25.3 %
Debt ₹ 4.18 Cr.
Price to book value 10.7
Promoter holding 73.0 %
Quick ratio 3.59
Debt to equity 0.09
EVEBITDA 42.4
Sales last year ₹ 30.6 Cr.
NP Ann ₹ 7.51 Cr.
OPM last year 37.4 %
PEG Ratio 0.74
EPS ₹ 6.23
https://www.screener.in/company/APSISAERO/
Profit & Loss
Figures in Rs. Crores
Mar 2023 Mar 2024 Mar 2025 Mar 2026
Sales + 10.37 16.87 20.49 30.65
Operating Profit 1.92 4.17 10.20 11.46
OPM % 18.51% 24.72% 49.78% 37.39%
Net Profit + 1.03 2.55 6.64 7.51
Balance Sheet
Figures in Rs. Crores
Mar 2023 Mar 2024 Mar 2025 Mar 2026
Equity Capital 0.98 0.98 0.98 12.05
Borrowings + 2.44 2.65 2.86 4.18
Cash Flows
Figures in Rs. Crores
Mar 2023 Mar 2024 Mar 2025 Mar 2026
Cash from Operating Activity + 1.29 5.76 1.63 7.04
Free Cash Flow 0.84 0.85 -2.19 0.88
CFO/OP 74% 138% 35% 77%
Ratios
Figures in Rs. Crores
Mar 2023 Mar 2024 Mar 2025 Mar 2026
Debtor Days 63.36 21.42 67.16 47.99
ROCE % 68.46% 91.95% 31.78%
Insights
Mar 2023 Mar 2024 Mar 2025 Mar 2026
Capacity Utilization
81.54 81.01 82.01 100.00
%
Shareholding Pattern
Numbers in percentages
Mar 2026
Promoters + 73.02%
FIIs + 3.02%
Public + 18.72%
"""

PHARMA_BREADCRUMB_TEXT = """
8/2/26, 5:03 PM Corona Remedies Ltd share price | About Corona Remedies | Key Insights - Screener
Corona Remedies Ltd
A B O U T
Incorporated in August 2004, Corona Remedies Limited is a pharmaceutical company.
K E Y P O I N T S
Market Cap ₹ 12,836 Cr.
Current Price ₹ 2,099
Stock P/E 60.6
ROCE 33.3 %
ROE 29.5 %
Debt to equity 0.24
Promoter holding 69.0 %
Peer comparison
Healthcare Healthcare Pharmaceuticals & Biotechnology
Pharmaceuticals EDIT COLUMNS
Part of BSE Healthcare BSE IPO
Shareholding Pattern
Numbers in percentages
Mar 2026 Jun 2026
Promoters + 69.00% 69.00%
FIIs + 2.25% 3.63%
"""


def test_screener_private_digits_are_normalized() -> None:
    assert normalize_screener_text("\ue071\ue072\ue073\ue094\ue074\ue075\ue093\ue076") == "012.34,5"


def test_parse_screener_pdf_text_extracts_summary_tables_and_score() -> None:
    parsed = parse_screener_pdf_text(SAMPLE_TEXT, "Apsis.pdf", "abc")

    assert parsed.company_name == "Apsis Aerocom Ltd"
    assert parsed.company_key == "APSIS-AEROCOM-LTD"
    assert parsed.metrics["Market Cap"]["value"] == 523
    assert parsed.annual["Sales"]["Mar 2026"] == 30.65
    assert parsed.cash_flow["Free Cash Flow"]["Mar 2026"] == 0.88
    assert parsed.operating_metrics["Capacity Utilization"]["values"]["Mar 2026"] == 100
    assert parsed.shareholding["Promoters"]["Mar 2026"] == 73.02
    assert parsed.score["total"] > 0
    assert parsed.score["decision"] in {"ACCUMULATE", "WATCH", "WAIT", "AVOID"}
    assert "Score formula" in parsed.score["explanations"][0]


def test_parse_screener_pdf_text_extracts_peer_breadcrumb_sector() -> None:
    parsed = parse_screener_pdf_text(PHARMA_BREADCRUMB_TEXT, "Corona.pdf", "def")

    assert parsed.company_name == "Corona Remedies Ltd"
    assert parsed.sector == "Healthcare"
    assert parsed.industry == "Pharmaceuticals"


def test_parse_screener_pdf_text_ignores_toolbar_and_uses_business_profile_or_title() -> None:
    text = """
8/2/26, 9:35 PM Indo Farm Equipment Ltd share price | About Indo Farm Equip. | Key Insights - Screener
₹ 161 6.07%
 E X P O R T T O E X C E L  F O L L O W 
31 Jul - close price
A B O U T
Incorporated in 1994, Indo Farm Equipment Limited is engaging in manufacturing Tractors, Pick & Carry Cranes.
K E Y P O I N T S
Market Cap ₹ 775 Cr.
Current Price ₹ 161
https://www.screener.in/company/INDOFARM/consolidated/ 1/11
"""

    parsed = parse_screener_pdf_text(text, "Indo Farm Equipment Ltd share price.pdf", "indo")

    assert parsed.company_name == "Indo Farm Equipment Ltd"
    assert parsed.company_key == "INDO-FARM-EQUIPMENT-LTD"
    assert parsed.screener_url == "https://www.screener.in/company/INDOFARM/"


def test_parse_screener_pdf_text_prefers_business_profile_company_when_it_starts_about() -> None:
    text = """
8/2/26, 9:35 PM Screener company page
 E X P O R T T O E X C E L  F O L L O W 
A B O U T
Park Medi World Ltd is engaged in operating hospitals and healthcare services.
K E Y P O I N T S
Market Cap ₹ 100 Cr.
Current Price ₹ 50
https://www.screener.in/company/PARKHOSPS/ 1/10
"""

    parsed = parse_screener_pdf_text(text, "upload.pdf", "park")

    assert parsed.company_name == "Park Medi World Ltd"
    assert parsed.company_key == "PARK-MEDI-WORLD-LTD"
    assert parsed.screener_url == "https://www.screener.in/company/PARKHOSPS/"


def test_value_stock_repository_upserts_latest_snapshot(tmp_path) -> None:
    parsed = parse_screener_pdf_text(SAMPLE_TEXT, "Apsis.pdf", "abc")
    repo = ValueStockRepository(tmp_path / "value_stock.db")

    first = repo.upsert_parsed(parsed)
    parsed.metrics["Current Price"]["value"] = 450
    second = repo.upsert_parsed(parsed)
    rows = repo.list_companies()
    detail = repo.get_company(parsed.company_key)

    assert first["document_id"] == second["document_id"]
    assert rows[0]["cmp"] == 450
    assert detail is not None
    assert detail["annual"]["Sales"]["Mar 2026"] == 30.65
    assert json.loads(json.dumps(detail["score"]))["decision"]


def test_value_stock_repository_sorts_by_decision_and_score(tmp_path) -> None:
    repo = ValueStockRepository(tmp_path / "value_stock.db")
    high = parse_screener_pdf_text(SAMPLE_TEXT, "Apsis.pdf", "abc")
    high.company_name = "High Score Watch Ltd"
    high.company_key = "HIGH-SCORE-WATCH"
    high.score["decision"] = "WATCH"
    high.score["total"] = 80
    low = parse_screener_pdf_text(PHARMA_BREADCRUMB_TEXT, "Corona.pdf", "def")
    low.score["decision"] = "WATCH"
    low.score["total"] = 55
    accumulate = parse_screener_pdf_text(SAMPLE_TEXT, "Winner.pdf", "ghi")
    accumulate.company_name = "Accumulate Ltd"
    accumulate.company_key = "ACCUMULATE"
    accumulate.score["decision"] = "ACCUMULATE"
    accumulate.score["total"] = 60

    repo.upsert_parsed(low)
    repo.upsert_parsed(high)
    repo.upsert_parsed(accumulate)

    rows = repo.list_companies()

    assert [row["company_name"] for row in rows] == [
        "Accumulate Ltd",
        "High Score Watch Ltd",
        "Corona Remedies Ltd",
    ]


def test_value_stock_repository_delete_company_removes_comparison_row_permanently(tmp_path) -> None:
    parsed = parse_screener_pdf_text(SAMPLE_TEXT, "Apsis.pdf", "abc")
    repo = ValueStockRepository(tmp_path / "value_stock.db")
    repo.upsert_parsed(parsed)

    assert repo.delete_company(parsed.company_key) is True

    assert repo.list_companies() == []
    assert repo.get_company(parsed.company_key) is None
    assert repo.delete_company(parsed.company_key) is False


def test_score_stays_low_confidence_when_critical_data_is_missing() -> None:
    parsed = ParsedValueStock(
        company_name="Sparse Ltd",
        company_key="SPARSE-LTD",
        checksum="x",
        filename="Sparse.pdf",
        metrics={},
    )

    score = build_value_score(parsed)

    assert score["decision"] == "WATCH"
    assert score["confidence"] == "Low"
    assert "Sales" in score["critical_missing"]


def test_parse_multipart_form_reads_pdf_file() -> None:
    boundary = "----codex-boundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="value_stock_search"\r\n\r\n'
        "apsis\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="value_stock_pdf"; filename="Apsis.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8") + b"%PDF-1.7 sample" + f"\r\n--{boundary}--\r\n".encode("utf-8")

    form, files = parse_multipart_form(body, f"multipart/form-data; boundary={boundary}")

    assert form["value_stock_search"] == ["apsis"]
    assert files["value_stock_pdf"]["filename"] == "Apsis.pdf"
    assert files["value_stock_pdf"]["content"].startswith(b"%PDF")


def test_value_stock_panel_keeps_pdf_upload_without_screener_helper() -> None:
    html = render_value_stock_panel(
        PageState(
            active_tab="value-stock",
            value_stock_rows=[],
        )
    )

    assert "Save Screener page as PDF" not in html
    assert "value-stock-open-screener" not in html
    assert "Upload PDF" in html


def test_value_stock_panel_shows_screener_link_and_delete_action() -> None:
    html = render_value_stock_panel(
        PageState(
            active_tab="value-stock",
            value_stock_rows=[
                {
                    "company_key": "PARK-MEDI-WORLD-LTD",
                    "company_name": "Park Medi World Ltd",
                    "sector": "Healthcare",
                    "industry": "Hospitals",
                    "exchange": "NSE",
                    "screener_url": "https://www.screener.in/company/PARKHOSPS/",
                    "score": 65,
                    "decision": "WATCH",
                    "confidence": "Medium",
                    "freshness": "2026-08-02",
                    "warnings": [],
                }
            ],
        )
    )

    assert "Screener" in html
    assert "https://www.screener.in/company/PARKHOSPS/" in html
    assert 'formaction="/value-stock/delete"' in html
    assert "Delete this Value-Stock row permanently" in html


def test_value_stock_detail_hides_empty_statement_cards_and_shows_kpis() -> None:
    detail = {
        "company_name": "Corona Remedies Ltd",
        "sector": "Healthcare",
        "industry": "Pharmaceuticals",
        "business_description": "Pharma company.",
        "filename": "Corona.pdf",
        "source_date": "2026-08-02",
        "metrics": {
            "Current Price": {"value": 2099},
            "Market Cap": {"value": 12836},
            "Stock P/E": {"value": 60.6},
            "ROCE": {"value": 33.3},
            "Debt to equity": {"value": 0.24},
            "Promoter holding": {"value": 69.0},
        },
        "score": {
            "total": 59.5,
            "decision": "WATCH",
            "confidence": "Low",
            "components": {"business_quality": 80.9, "growth": 45.0},
            "explanations": ["Score formula: test"],
        },
        "shareholding": {"Promoters": {"Mar 2026": 69.0}},
    }
    html = render_value_stock_panel(
        PageState(active_tab="value-stock", value_stock_rows=[], value_stock_detail=detail)
    )

    assert "value-stock-kpi-strip" in html
    assert "Healthcare · Pharmaceuticals" in html
    assert "Annual Profit &amp; Loss" not in html
    assert "Shareholding" in html


def test_apsis_expected_assessment_colours() -> None:
    table = {
        "Sales": {"Mar 2025": 20.49, "Mar 2026": 30.65},
        "Expenses": {"Mar 2025": 10.29, "Mar 2026": 19.19},
        "OPM %": {"Mar 2025": 49.78, "Mar 2026": 37.39},
        "ROCE %": {"Mar 2025": 91.95, "Mar 2026": 31.78},
        "Free Cash Flow": {"Mar 2025": -2.09, "Mar 2026": 0.88},
        "Cash from Financing Activity": {"Mar 2025": 0.01, "Mar 2026": 33.41},
    }
    assessments = assess_table(table)

    assert assessments["Sales"]["trend_status"] == "positive"
    assert round(assessments["Sales"]["delta_value"], 1) == 49.6
    assert assessments["Expenses"]["trend_status"] == "negative"
    assert assessments["OPM %"]["trend_status"] == "negative"
    assert round(assessments["OPM %"]["delta_value"], 2) == -12.39
    assert assessments["ROCE %"]["value_status"] == "positive"
    assert assessments["ROCE %"]["trend_status"] == "negative"
    assert assessments["Free Cash Flow"]["trend_status"] == "positive"
    assert assessments["Cash from Financing Activity"]["value_status"] == "warning"


def test_debt_equity_assessment_is_green_absolute() -> None:
    assessment = assess_metric("Debt to equity", {"Latest": 0.09})

    assert assessment["value_status"] == "positive"
    assert assessment["display_value"] == "0.09x"


def test_parser_rejects_url_and_date_fragment_metric_rows() -> None:
    parsed = parse_screener_pdf_text(
        """
        Fragment Ltd
        Shareholding Pattern
        Numbers in percentages
        Mar 2026 Jun 2026
        Promoters + 69.00% 69.00%
        https://www.screener.in/company/FRAG/ 8.00 10.00
        8/2/26 26.00 5.00
        Documents
        """,
        "Fragment.pdf",
        "frag",
    )

    assert "Promoters" in parsed.shareholding
    assert all("screener" not in key.lower() for key in parsed.shareholding)
    assert all(not key.startswith("8/2") for key in parsed.shareholding)


def test_value_stock_detail_renders_accessible_colour_badges() -> None:
    detail = {
        "company_name": "Apsis Aerocom Ltd",
        "sector": "Industrials",
        "industry": "Aerospace & Defense",
        "business_description": "Precision engineering.",
        "filename": "Apsis.pdf",
        "source_date": "2026-08-02",
        "metrics": {"Current Price": {"value": 434}},
        "score": {
            "total": 74.7,
            "decision": "WATCH",
            "confidence": "Medium",
            "components": {"business_quality": 80.0},
            "explanations": ["Score formula: test"],
        },
        "annual": {
            "Sales": {"Mar 2025": 20.49, "Mar 2026": 30.65},
            "OPM %": {"Mar 2025": 49.78, "Mar 2026": 37.39},
        },
    }

    rendered = render_value_stock_panel(
        PageState(active_tab="value-stock", value_stock_rows=[], value_stock_detail=detail)
    )

    assert "value-stock-legend" in rendered
    assert "vs-positive" in rendered
    assert "vs-negative" in rendered
    assert "aria-label=" in rendered
    assert "↓12.39 pp" in rendered


def test_external_pdf_runtime_uses_utf8_stdout(monkeypatch, tmp_path) -> None:
    fallback_python = tmp_path / "python.exe"
    fallback_python.write_text("placeholder", encoding="utf-8")
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="Apsis \ue071\ue072\ue094\ue073", stderr="")

    monkeypatch.setattr(pdf_parser, "_bundled_pdf_python_candidates", lambda: [fallback_python])
    monkeypatch.setattr(subprocess, "run", fake_run)

    text = pdf_parser._extract_text_with_external_pdfplumber(b"%PDF-1.7 fake")

    assert "Apsis 01.2" in normalize_screener_text(text)
    assert calls
    assert calls[0][1]["env"]["PYTHONIOENCODING"] == "utf-8"
