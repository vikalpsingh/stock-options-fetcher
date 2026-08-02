from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ParsedValueStock

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 12 * 1024 * 1024

SCREENER_DIGIT_MAP = str.maketrans(
    {
        "\ue071": "0",
        "\ue072": "1",
        "\ue073": "2",
        "\ue074": "3",
        "\ue075": "4",
        "\ue076": "5",
        "\ue077": "6",
        "\ue078": "7",
        "\ue079": "8",
        "\ue07a": "9",
        "\ue094": ".",
        "\ue093": ",",
        "\ue095": ":",
    }
)

PERIOD_RE = re.compile(r"\b(?:Mar|Jun|Sep|Dec)\s+20\d{2}\b")
NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?%?")

KEY_METRIC_LABELS = (
    "Market Cap",
    "Current Price",
    "High / Low",
    "Stock P/E",
    "Book Value",
    "Dividend Yield",
    "ROCE",
    "ROE",
    "Face Value",
    "Debt",
    "Price to book value",
    "Reserves",
    "ROCE 5Yr",
    "Graham",
    "High price",
    "Up from 52w low",
    "Promoter holding",
    "Quick ratio",
    "Debt to equity",
    "EVEBITDA",
    "Return on equity",
    "Down from 52w high",
    "Profit Var 5Yrs",
    "Sales last year",
    "NP Ann",
    "OPM last year",
    "Mar Cap",
    "PEG Ratio",
    "EPS",
)

TABLE_SECTIONS = {
    "Half Yearly Results": "half_yearly",
    "Profit & Loss": "annual",
    "Balance Sheet": "balance_sheet",
    "Cash Flows": "cash_flow",
    "Ratios": "ratios",
}


class PdfExtractionError(RuntimeError):
    """Raised when a PDF cannot be safely extracted."""


def _extract_text_with_pdfplumber_stream(pdf_content: bytes) -> str:
    import pdfplumber  # type: ignore

    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        return "\n".join(
            page.extract_text(x_tolerance=1, y_tolerance=3) or ""
            for page in pdf.pages
        )


def _bundled_pdf_python_candidates() -> list[Path]:
    configured = os.getenv("VALUE_STOCK_PDF_PYTHON", "").strip()
    candidates: list[Path] = [Path(configured)] if configured else []
    candidates.append(
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "python"
        / ("python.exe" if os.name == "nt" else "bin/python")
    )
    return [path for path in candidates if path and path.exists()]


def _extract_text_with_external_pdfplumber(pdf_content: bytes) -> str:
    helper = (
        "import logging, sys\n"
        "logging.getLogger('pdfminer').setLevel(logging.ERROR)\n"
        "import pdfplumber\n"
        "with pdfplumber.open(sys.argv[1]) as pdf:\n"
        "    text='\\n'.join((page.extract_text(x_tolerance=1, y_tolerance=3) or '') for page in pdf.pages)\n"
        "sys.stdout.write(text)\n"
    )
    last_error = ""
    with tempfile.TemporaryDirectory(prefix="value_stock_pdf_") as tmp_dir:
        pdf_path = Path(tmp_dir) / "upload.pdf"
        pdf_path.write_bytes(pdf_content)
        for python_path in _bundled_pdf_python_candidates():
            if python_path == Path(sys.executable):
                continue
            try:
                env = dict(os.environ)
                env["PYTHONIOENCODING"] = "utf-8"
                result = subprocess.run(
                    [str(python_path), "-c", helper, str(pdf_path)],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env=env,
                    timeout=45,
                )
            except Exception as exc:
                last_error = str(exc)
                continue
            if result.returncode == 0:
                return result.stdout
            last_error = (result.stderr or result.stdout or "").strip()
    raise PdfExtractionError(
        "PDF extraction requires pdfplumber in the app Python environment. "
        "Install requirements or set VALUE_STOCK_PDF_PYTHON to a Python executable with pdfplumber. "
        f"Fallback error: {last_error or 'no fallback runtime found'}"
    )


def normalize_screener_text(text: str) -> str:
    cleaned = text.translate(SCREENER_DIGIT_MAP)
    cleaned = cleaned.replace("\uf8d9", " ").replace("\ue827", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned


def extract_pdf_text(pdf_content: bytes) -> str:
    if not pdf_content:
        raise PdfExtractionError("Uploaded PDF is empty.")
    if len(pdf_content) > MAX_PDF_BYTES:
        raise PdfExtractionError("PDF is too large. Upload a Screener PDF under 12 MB.")
    if not pdf_content.startswith(b"%PDF"):
        raise PdfExtractionError("Uploaded file is not a valid PDF.")

    try:
        text = _extract_text_with_pdfplumber_stream(pdf_content)
    except ImportError:
        text = _extract_text_with_external_pdfplumber(pdf_content)
    except Exception as exc:  # pragma: no cover - library-specific failures
        logger.exception("value_stock_pdf_extract_failed")
        raise PdfExtractionError(f"Could not read PDF text: {exc}") from exc
    return normalize_screener_text(text)


def parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "%"}:
        return None
    match = NUMBER_RE.search(text)
    if not match:
        return None
    token = match.group(0).replace(",", "").replace("%", "")
    try:
        return float(token)
    except ValueError:
        return None


def parse_metric_value(raw: str) -> dict[str, Any]:
    value = parse_number(raw)
    unit = ""
    if "Cr" in raw or "Crore" in raw:
        unit = "Cr"
    elif "%" in raw:
        unit = "%"
    elif "Rs" in raw or "₹" in raw:
        unit = "Rs"
    return {"value": value, "unit": unit, "raw": raw.strip() or None}


def company_key(name: str) -> str:
    key = re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")
    return key or "UNKNOWN"


def _first_non_empty_company_line(lines: list[str], filename: str) -> str:
    ignored = ("share price |", "Summary Chart", "₹ ", "EXPORT TO EXCEL")
    for line in lines[:12]:
        if any(marker in line for marker in ignored):
            continue
        if line and not line.startswith("http") and not re.match(r"\d{1,2}/\d{1,2}/\d{2}", line):
            return line.strip()
    return Path(filename).stem.split(" share price", 1)[0].strip() or "Unknown Company"


def _source_date(lines: list[str]) -> str:
    for line in lines[:5]:
        match = re.match(r"(\d{1,2}/\d{1,2}/\d{2})", line)
        if not match:
            continue
        try:
            return datetime.strptime(match.group(1), "%m/%d/%y").date().isoformat()
        except ValueError:
            return match.group(1)
    return ""


def _business_description(lines: list[str]) -> str:
    start = next((idx for idx, line in enumerate(lines) if line.strip() == "A B O U T"), -1)
    end = next((idx for idx, line in enumerate(lines) if line.strip() == "K E Y P O I N T S"), -1)
    if start >= 0 and end > start:
        return " ".join(lines[start + 1 : end]).strip()
    return ""


def _clean_breadcrumb_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z& /-]+", " ", value)
    token = re.sub(r"\b(EDIT|COLUMNS|Part of|show all)\b.*$", "", token, flags=re.I)
    return re.sub(r"\s+", " ", token).strip(" -/")


def _invalid_metric_label(label: str) -> bool:
    text = str(label or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if "http://" in lowered or "https://" in lowered or "screener.in" in lowered:
        return True
    if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}", text):
        return True
    if re.search(r"\b(?:AM|PM|a\.m\.|p\.m\.)\b", text, flags=re.I):
        return True
    return False


def _parse_peer_breadcrumb(lines: list[str]) -> tuple[str, str]:
    """Extract Screener peer-comparison sector breadcrumbs.

    Screener PDFs render breadcrumbs as text around the "Peer comparison"
    heading, for example:
    Healthcare > Healthcare > Pharmaceuticals & Biotechnology > Pharmaceuticals.
    The first token is the broad sector; the deepest useful token is the
    comparison industry displayed in the Value-Stock table/detail view.
    """
    start = next((idx for idx, line in enumerate(lines) if line.strip() == "Peer comparison"), -1)
    if start < 0:
        return "", ""
    window = " ".join(lines[start + 1 : start + 8])
    window = re.split(r"\b(?:Prom\.|S\.No\.|Detailed Comparison|Figures in)\b", window, maxsplit=1)[0]
    window = re.sub(r"\bEDIT\s+COLUMNS\b.*$", "", window, flags=re.I)
    known_breadcrumbs = [
        "Pharmaceuticals & Biotechnology",
        "Aerospace & Defense",
        "Electrical Equipment",
        "Capital Goods",
        "Healthcare",
        "Pharmaceuticals",
        "Industrials",
        "Information Technology",
        "Financial Services",
        "Consumer Discretionary",
        "Consumer Staples",
        "Energy",
        "Utilities",
        "Materials",
        "Real Estate",
    ]
    found = []
    occupied: list[range] = []
    for token in known_breadcrumbs:
        for match in re.finditer(rf"\b{re.escape(token)}\b", window, flags=re.I):
            span = range(match.start(), match.end())
            if any(match.start() in item or (match.end() - 1) in item for item in occupied):
                continue
            occupied.append(span)
            found.append((match.start(), token))
    if found:
        ordered = []
        for _, token in sorted(found):
            if token not in ordered:
                ordered.append(token)
        return ordered[0], ordered[-1]
    raw_tokens = re.split(r"[\ue820\ue821\ue840\ue83f>|]+", window)
    tokens: list[str] = []
    for raw in raw_tokens:
        token = _clean_breadcrumb_token(raw)
        if not token:
            continue
        if token.lower() in {"peer comparison", "priceonnse", "priceonbse", "emulov"}:
            continue
        if token not in tokens:
            tokens.append(token)
    if not tokens:
        return "", ""
    sector = tokens[0]
    industry = tokens[-1] if len(tokens) > 1 else tokens[0]
    return sector, industry


def _parse_identity(lines: list[str], filename: str) -> dict[str, str]:
    text = "\n".join(lines)
    url_match = re.search(r"https://www\.screener\.in/company/[^ \n]+", text)
    exchange = ""
    for candidate in ("NSE - ST", "NSE", "BSE"):
        if candidate in text:
            exchange = candidate
            break
    sector, industry = _parse_peer_breadcrumb(lines)
    for line in lines:
        if sector and industry:
            break
        if "Capital Goods" in line or "Industrials" in line:
            clean = re.sub(r"[^A-Za-z& /-]+", " ", line)
            parts = [part.strip() for part in re.split(r"\s{2,}|\s+EDIT\s+COLUMNS", clean) if part.strip()]
            joined = " ".join(parts)
            if "Industrials" in joined:
                sector = "Industrials"
            if "Aerospace" in joined:
                industry = "Aerospace & Defense"
            elif "Electrical" in joined:
                industry = "Electrical Equipment"
    return {
        "company_name": _first_non_empty_company_line(lines, filename),
        "source_date": _source_date(lines),
        "exchange": exchange,
        "screener_url": url_match.group(0) if url_match else "",
        "sector": sector,
        "industry": industry,
        "business_description": _business_description(lines),
    }


def _parse_key_metrics(lines: list[str]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    label_pattern = "|".join(re.escape(label) for label in sorted(KEY_METRIC_LABELS, key=len, reverse=True))
    row_re = re.compile(rf"^({label_pattern})\s+(.+)$")
    for line in lines:
        match = row_re.match(line.strip())
        if not match:
            continue
        label = match.group(1)
        raw = match.group(2).strip()
        metrics[label] = parse_metric_value(raw)
    if "Mar Cap" in metrics and "Market Cap" not in metrics:
        metrics["Market Cap"] = metrics["Mar Cap"]
    return metrics


def _extract_table(lines: list[str], section_title: str) -> dict[str, dict[str, Any]]:
    start = next((idx for idx, line in enumerate(lines) if line.strip() == section_title), -1)
    if start < 0:
        return {}
    header_idx = -1
    periods: list[str] = []
    for idx in range(start + 1, min(len(lines), start + 8)):
        periods = PERIOD_RE.findall(lines[idx])
        if periods:
            header_idx = idx
            break
    if header_idx < 0 or not periods:
        return {}

    stop_titles = {title for title in TABLE_SECTIONS if title != section_title} | {
        "Insights",
        "Shareholding Pattern",
        "Documents",
        "Compounded Compounded Stock Price Return on",
    }
    table: dict[str, dict[str, Any]] = {}
    for line in lines[header_idx + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in stop_titles:
            break
        if PERIOD_RE.search(stripped) or stripped.startswith("Figures in"):
            continue
        matches = list(NUMBER_RE.finditer(stripped))
        if len(matches) < 2:
            continue
        value_count = min(len(matches), len(periods))
        value_matches = matches[-value_count:]
        row_periods = periods[-value_count:]
        label = stripped[: value_matches[0].start()].replace("+", "").strip()
        if _invalid_metric_label(label):
            continue
        row: dict[str, Any] = {}
        for period, match in zip(row_periods, value_matches):
            row[period] = parse_number(match.group(0))
        table[label] = row
    return table


def _parse_operating_metrics(lines: list[str]) -> dict[str, dict[str, Any]]:
    start = next((idx for idx, line in enumerate(lines) if line.strip() == "Insights"), -1)
    if start < 0:
        return {}
    periods: list[str] = []
    header_idx = -1
    for idx in range(start + 1, min(len(lines), start + 12)):
        periods = PERIOD_RE.findall(lines[idx])
        if periods:
            header_idx = idx
            break
    if header_idx < 0:
        return {}
    metrics: dict[str, dict[str, Any]] = {}
    idx = header_idx + 1
    while idx < len(lines):
        name = lines[idx].strip()
        if name in {"Shareholding Pattern", "Documents"}:
            break
        value_line = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
        unit_line = lines[idx + 2].strip() if idx + 2 < len(lines) else ""
        values = [parse_number(match.group(0)) for match in NUMBER_RE.finditer(value_line)]
        if name and values:
            if _invalid_metric_label(name):
                idx += 1
                continue
            row_periods = periods[-len(values) :]
            metrics[name] = {
                "unit": unit_line if unit_line and not PERIOD_RE.search(unit_line) else "",
                "values": dict(zip(row_periods, values)),
            }
            idx += 3
        else:
            idx += 1
    return metrics


def _parse_shareholding(lines: list[str]) -> dict[str, dict[str, Any]]:
    start = next((idx for idx, line in enumerate(lines) if line.strip() == "Shareholding Pattern"), -1)
    if start < 0:
        return {}
    periods: list[str] = []
    header_idx = -1
    for idx in range(start + 1, min(len(lines), start + 12)):
        periods = PERIOD_RE.findall(lines[idx])
        if periods:
            header_idx = idx
            break
    if header_idx < 0:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for line in lines[header_idx + 1 :]:
        stripped = line.strip()
        if stripped.startswith("* ") or stripped == "Documents":
            break
        matches = list(NUMBER_RE.finditer(stripped))
        if len(matches) < 1:
            continue
        values = matches[-len(periods) :]
        label = stripped[: values[0].start()].replace("+", "").strip()
        if _invalid_metric_label(label):
            continue
        rows[label] = {
            period: parse_number(match.group(0))
            for period, match in zip(periods[-len(values) :], values)
        }
    return rows


def _latest(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    for key in sorted(row.keys(), key=lambda item: item[-4:] + item[:3], reverse=True):
        value = row.get(key)
        if value is not None:
            return float(value)
    return None


def _previous_and_latest(row: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not row:
        return None, None
    values = [row[key] for key in sorted(row.keys(), key=lambda item: item[-4:] + item[:3]) if row.get(key) is not None]
    if not values:
        return None, None
    if len(values) == 1:
        return None, float(values[-1])
    return float(values[-2]), float(values[-1])


def _growth_score(previous: float | None, latest: float | None) -> tuple[float, str]:
    if previous is None or latest is None or previous <= 0:
        return 45.0, "Insufficient comparable history; kept conservative."
    growth = ((latest - previous) / previous) * 100
    score = max(0.0, min(100.0, 50.0 + growth))
    return score, f"Latest period growth is {growth:.1f}% vs prior comparable period."


def _score_linear(value: float | None, low: float, high: float, missing: float = 45.0) -> float:
    if value is None:
        return missing
    return max(0.0, min(100.0, ((value - low) / (high - low)) * 100.0))


def build_value_score(parsed: ParsedValueStock) -> dict[str, Any]:
    annual = parsed.annual
    metrics = parsed.metrics
    sales_prev, sales_latest = _previous_and_latest(annual.get("Sales"))
    pat_prev, pat_latest = _previous_and_latest(annual.get("Net Profit"))
    fcf_latest = _latest(parsed.cash_flow.get("Free Cash Flow"))
    cfo_op_latest = _latest(parsed.cash_flow.get("CFO/OP"))
    opm_latest = _latest(annual.get("OPM %")) or (metrics.get("OPM last year") or {}).get("value")
    roce_latest = _latest(parsed.ratios.get("ROCE %")) or (metrics.get("ROCE") or {}).get("value")
    roe_latest = (metrics.get("ROE") or metrics.get("Return on equity") or {}).get("value")
    debt_equity = (metrics.get("Debt to equity") or {}).get("value")
    pe = (metrics.get("Stock P/E") or {}).get("value")
    ev_ebitda = (metrics.get("EVEBITDA") or {}).get("value")
    peg = (metrics.get("PEG Ratio") or {}).get("value")
    promoter_latest = _latest(parsed.shareholding.get("Promoters")) or (metrics.get("Promoter holding") or {}).get("value")

    sales_growth_score, sales_reason = _growth_score(sales_prev, sales_latest)
    pat_growth_score, pat_reason = _growth_score(pat_prev, pat_latest)
    growth = (sales_growth_score + pat_growth_score) / 2

    quality = (
        _score_linear(roce_latest, 8, 35) * 0.45
        + _score_linear(roe_latest, 8, 35) * 0.35
        + (100 - _score_linear(debt_equity, 0.0, 1.2, missing=45.0)) * 0.20
    )
    profitability = _score_linear(opm_latest, 8, 35) * 0.45 + _score_linear(roce_latest, 8, 35) * 0.55
    cash_flow = (
        _score_linear(cfo_op_latest, 40, 120) * 0.60
        + (75.0 if fcf_latest is not None and fcf_latest > 0 else 30.0 if fcf_latest is not None else 45.0) * 0.40
    )
    balance_sheet = 100 - _score_linear(debt_equity, 0.0, 1.5, missing=45.0)
    valuation = (
        (100 - _score_linear(pe, 12, 70, missing=45.0)) * 0.45
        + (100 - _score_linear(ev_ebitda, 8, 45, missing=45.0)) * 0.35
        + (100 - _score_linear(peg, 0.5, 2.0, missing=55.0)) * 0.20
    )
    governance = _score_linear(promoter_latest, 35, 75) * 0.70 + 55.0 * 0.30

    components = {
        "business_quality": round(quality, 1),
        "growth": round(growth, 1),
        "profitability": round(profitability, 1),
        "cash_flow_quality": round(cash_flow, 1),
        "balance_sheet": round(balance_sheet, 1),
        "valuation": round(valuation, 1),
        "governance_ownership": round(governance, 1),
    }
    weighted = (
        components["business_quality"] * 0.20
        + components["growth"] * 0.20
        + components["profitability"] * 0.15
        + components["cash_flow_quality"] * 0.15
        + components["balance_sheet"] * 0.10
        + components["valuation"] * 0.10
        + components["governance_ownership"] * 0.10
    )
    critical_missing = [
        label
        for label, value in {
            "Sales": sales_latest,
            "Net Profit": pat_latest,
            "ROCE": roce_latest,
            "Debt/Equity": debt_equity,
        }.items()
        if value is None
    ]
    if critical_missing:
        decision = "WATCH"
        confidence = "Low"
    elif weighted >= 75:
        decision = "ACCUMULATE"
        confidence = "Medium"
    elif weighted >= 60:
        decision = "WATCH"
        confidence = "Medium"
    elif weighted >= 45:
        decision = "WAIT"
        confidence = "Medium"
    else:
        decision = "AVOID"
        confidence = "Medium"

    explanations = [
        "Score formula: quality 20%, growth 20%, profitability 15%, cash flow 15%, balance sheet 10%, valuation 10%, governance 10%.",
        sales_reason,
        pat_reason,
    ]
    if debt_equity is not None:
        explanations.append(f"Debt/equity is {debt_equity:.2f}; lower leverage improves balance-sheet score.")
    if pe is not None:
        explanations.append(f"P/E is {pe:.1f}; valuation is treated contextually, not simply red/green.")
    if critical_missing:
        explanations.append("Critical missing data prevents a high-confidence decision: " + ", ".join(critical_missing) + ".")

    return {
        "total": round(weighted, 1),
        "components": components,
        "decision": decision,
        "confidence": confidence,
        "critical_missing": critical_missing,
        "explanations": explanations,
    }


def parse_screener_pdf_text(text: str, filename: str, checksum: str) -> ParsedValueStock:
    normalized = normalize_screener_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    identity = _parse_identity(lines, filename)
    parsed = ParsedValueStock(
        company_name=identity["company_name"],
        company_key=company_key(identity["company_name"]),
        checksum=checksum,
        filename=filename,
        source_date=identity["source_date"],
        exchange=identity["exchange"],
        sector=identity["sector"],
        industry=identity["industry"],
        screener_url=identity["screener_url"],
        business_description=identity["business_description"],
        metrics=_parse_key_metrics(lines),
        operating_metrics=_parse_operating_metrics(lines),
        shareholding=_parse_shareholding(lines),
        raw_text=normalized,
    )
    for title, attr in TABLE_SECTIONS.items():
        setattr(parsed, attr, _extract_table(lines, title))
    if not parsed.company_name or parsed.company_name == "Unknown Company":
        parsed.warnings.append("Company name could not be extracted confidently.")
    if not parsed.annual:
        parsed.warnings.append("Annual profit-and-loss table was not extracted.")
    if not parsed.metrics:
        parsed.warnings.append("Key valuation metrics were not extracted.")
    parsed.score = build_value_score(parsed)
    return parsed


def parse_pdf_content(filename: str, pdf_content: bytes) -> ParsedValueStock:
    checksum = hashlib.sha256(pdf_content).hexdigest()
    text = extract_pdf_text(pdf_content)
    return parse_screener_pdf_text(text, filename, checksum)
