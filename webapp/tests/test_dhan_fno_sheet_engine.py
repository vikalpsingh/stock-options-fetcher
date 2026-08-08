from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from dhan_fno_sheet_importer import EXPECTED_COLUMNS, parse_fno_opportunities_xlsx
from dhan_fno_sheet_scoring import DhanFnoSheetScoringEngine
from dhan_fno_top10_engine import generate_dhan_top10_from_fno_sheet
from kite_spread_repository import KiteSpreadRepository


def _cell_ref(col_idx: int, row_idx: int) -> str:
    letters = ""
    n = col_idx + 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row_idx}"


def _sheet_xml(rows: list[list[object]]) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
    out.append('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>')
    for r_idx, row in enumerate(rows, start=1):
        out.append(f'<row r="{r_idx}">')
        for c_idx, value in enumerate(row):
            ref = _cell_ref(c_idx, r_idx)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                clean = str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                out.append(f'<c r="{ref}" t="inlineStr"><is><t>{clean}</t></is></c>')
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def make_xlsx(sheets: dict[str, list[dict[str, object]]]) -> bytes:
    bio = BytesIO()
    with ZipFile(bio, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>')
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        sheet_nodes = []
        rel_nodes = []
        for idx, (name, rows) in enumerate(sheets.items(), start=1):
            sheet_nodes.append(f'<sheet name="{name}" sheetId="{idx}" r:id="rId{idx}"/>')
            rel_nodes.append(f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="/xl/worksheets/sheet{idx}.xml"/>')
            values = [EXPECTED_COLUMNS] + [[row.get(col, "") for col in EXPECTED_COLUMNS] for row in rows]
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", _sheet_xml(values))
        zf.writestr("xl/workbook.xml", f'<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{"".join(sheet_nodes)}</sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{"".join(rel_nodes)}</Relationships>')
    return bio.getvalue()


def row(symbol: str, *, wheel=95, tab="CE", liquidity="High", itm=4, total=5000, otm=8, rsi=50, action="Prime", rel=0) -> dict[str, object]:
    data = {
        "Stock": symbol,
        "Spot Price": 1000,
        "Strike": 1100 if tab == "CE" else 900,
        "Premium": 10,
        "Lot Size": 500,
        "Total Premium": total,
        "% OTM": otm,
        "Expiry": "25-Aug-2026",
        "Days to Expiry": 19,
        "ITM Risk %": itm,
        "Premium Yield %": 1.2,
        "Monthly Yield %": 2.0,
        "Move Cover": 1.8,
        "Liquidity Tag": liquidity,
        "Wheel Score": wheel,
        "Wheel Action": action,
        "Safety Band": "High",
        "Volatility Tag": "Low",
        "1M Ret %": 1,
        "3M Ret %": 2,
        "RSI 14": rsi,
        "Rel Str vs Nifty 3M": rel,
        "Dip Signal": "Neutral",
    }
    data.update(
        {
            "symbol": symbol,
            "source_tab": "CE_WHEEL_SHORTLIST" if tab == "CE" else "PE_WHEEL_SHORTLIST",
            "dhan_strategy": "BEAR_CALL_SPREAD" if tab == "CE" else "BULL_PUT_SPREAD",
            "spot_price": data["Spot Price"],
            "strike": data["Strike"],
            "premium": data["Premium"],
            "lot_size": data["Lot Size"],
            "total_premium": data["Total Premium"],
            "otm_pct": data["% OTM"],
            "expiry": "2026-08-25",
            "days_to_expiry": data["Days to Expiry"],
            "itm_risk_pct": data["ITM Risk %"],
            "premium_yield_pct": data["Premium Yield %"],
            "monthly_yield_pct": data["Monthly Yield %"],
            "move_cover": data["Move Cover"],
            "liquidity_tag": data["Liquidity Tag"],
            "wheel_score": data["Wheel Score"],
            "wheel_action": data["Wheel Action"],
            "safety_band": data["Safety Band"],
            "volatility_tag": data["Volatility Tag"],
            "ret_1m_pct": data["1M Ret %"],
            "ret_3m_pct": data["3M Ret %"],
            "rsi_14": data["RSI 14"],
            "relative_strength_3m": data["Rel Str vs Nifty 3M"],
            "dip_signal": data["Dip Signal"],
            "insider_activity": "",
            "block_bulk_activity": "",
        }
    )
    return data


def passing_live(candidate: dict) -> dict:
    return {
        "cmp_kite": 1000,
        "recommended_expiry": "CURRENT_MONTH",
        "sell_leg_tradingsymbol": f"{candidate['symbol']}SELL",
        "buy_leg_tradingsymbol": f"{candidate['symbol']}BUY",
        "sell_strike": 1050,
        "hedge_strike": 1100,
        "sell_premium_live": 12,
        "hedge_premium_live": 4,
        "net_credit": 8,
        "max_gain": 6000,
        "max_loss": 30000,
        "breakeven": 1042,
        "pop_estimate": 75,
        "return_on_risk_pct": 12,
        "pair_liquidity_condition": "GREEN",
        "risk_decision": "APPROVED",
        "risk_reason": "ok",
    }


def test_reads_ce_and_maps_to_call_spread():
    data = make_xlsx({"CE_WHEEL_SHORTLIST": [row("ABC", tab="CE")]})
    parsed = parse_fno_opportunities_xlsx(data)
    assert parsed["ce_rows_read"] == 1
    assert parsed["candidates"][0]["symbol"] == "ABC"
    assert parsed["candidates"][0]["dhan_strategy"] == "BEAR_CALL_SPREAD"


def test_reads_pe_and_maps_to_put_spread():
    data = make_xlsx({"PE_WHEEL_SHORTLIST": [row("XYZ", tab="PE")]})
    parsed = parse_fno_opportunities_xlsx(data)
    assert parsed["pe_rows_read"] == 1
    assert parsed["candidates"][0]["dhan_strategy"] == "BULL_PUT_SPREAD"


def test_missing_tabs_do_not_crash():
    parsed = parse_fno_opportunities_xlsx(make_xlsx({"CE_WHEEL_SHORTLIST": [row("ABC")]}))
    assert parsed["pe_rows_read"] == 0
    assert "PE_WHEEL_SHORTLIST" in parsed["missing_tabs"]


def test_filters_low_wheel_and_high_itm_and_low_liquidity():
    engine = DhanFnoSheetScoringEngine()
    scored, rejected = engine.filter_and_score(
        [row("LOW", wheel=60), row("ITM", itm=15), row("LIQ", liquidity="Low")]
    )
    assert scored == []
    reason_text = " ".join(" ".join(item.get("reason_codes", [])) for item in rejected)
    assert "WHEEL_SCORE_BELOW_MIN" in reason_text
    assert "ITM_RISK_ABOVE_MAX" in reason_text
    assert "LIQUIDITY_NOT_ALLOWED" in reason_text


def test_prime_scores_higher_than_non_prime():
    engine = DhanFnoSheetScoringEngine()
    prime = engine.score_candidate(row("PRIME", action="Prime"))
    weak = engine.score_candidate(row("WEAK", action="Avoid"))
    assert prime["final_sheet_score"] > weak["final_sheet_score"]


def test_ce_rsi_above_65_scores_lower():
    engine = DhanFnoSheetScoringEngine()
    normal = engine.score_candidate(row("NORMAL", tab="CE", rsi=50))
    hot = engine.score_candidate(row("HOT", tab="CE", rsi=72, rel=15))
    assert hot["final_sheet_score"] < normal["final_sheet_score"]
    assert "CE_RSI_ABOVE_65" in hot["reason_codes"]


def test_pe_rsi_below_40_scores_lower():
    engine = DhanFnoSheetScoringEngine()
    normal = engine.score_candidate({**row("NORMAL", tab="PE", rsi=55), "dhan_strategy": "BULL_PUT_SPREAD"})
    weak = engine.score_candidate({**row("WEAK", tab="PE", rsi=35), "dhan_strategy": "BULL_PUT_SPREAD"})
    assert weak["final_sheet_score"] < normal["final_sheet_score"]
    assert "PE_RSI_BELOW_40" in weak["reason_codes"]


def test_deduplicates_same_symbol_strategy_expiry_keeps_best():
    data = make_xlsx({"CE_WHEEL_SHORTLIST": [row("DUP", wheel=80), row("DUP", wheel=99)]})
    result = generate_dhan_top10_from_fno_sheet(data, live_validator=passing_live)
    assert len([item for item in result["top10"] if item["symbol"] == "DUP"]) == 1
    assert result["top10"][0]["wheel_score"] == 99


def test_generates_overall_top10_from_ce_and_pe():
    ce_rows = [row(f"CE{i}", wheel=95 - i, tab="CE") for i in range(8)]
    pe_rows = [row(f"PE{i}", wheel=97 - i, tab="PE") for i in range(8)]
    result = generate_dhan_top10_from_fno_sheet(
        make_xlsx({"CE_WHEEL_SHORTLIST": ce_rows, "PE_WHEEL_SHORTLIST": pe_rows}),
        live_validator=passing_live,
    )
    assert len(result["top10"]) == 10
    assert {item["source_tab"] for item in result["top10"]} == {"CE_WHEEL_SHORTLIST", "PE_WHEEL_SHORTLIST"}


def test_rejects_red_liquidity_after_live_validation():
    def red_live(candidate: dict) -> dict:
        return {**passing_live(candidate), "pair_liquidity_condition": "RED"}

    result = generate_dhan_top10_from_fno_sheet(make_xlsx({"CE_WHEEL_SHORTLIST": [row("RED")]}), live_validator=red_live)
    assert result["top10"] == []
    assert "LIVE_RED_LIQUIDITY" in result["rejected"][0]["reason_codes"]


def test_rejects_when_live_max_gain_below_5000():
    def low_gain(candidate: dict) -> dict:
        return {**passing_live(candidate), "max_gain": 3000}

    result = generate_dhan_top10_from_fno_sheet(make_xlsx({"CE_WHEEL_SHORTLIST": [row("LOWGAIN")]}), live_validator=low_gain)
    assert result["top10"] == []
    assert "LIVE_MAX_GAIN_BELOW_MIN" in result["rejected"][0]["reason_codes"]


def test_repository_saves_run_and_adds_selected_to_watchlist(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    result = generate_dhan_top10_from_fno_sheet(make_xlsx({"CE_WHEEL_SHORTLIST": [row("ADDME")]}), live_validator=passing_live)
    run_id = repo.save_dhan_fno_top10_run(result)
    latest = repo.latest_dhan_fno_top10_run()
    candidate_id = latest["top10"][0]["candidate_id"]
    outcome = repo.add_dhan_fno_top10_to_watchlist([candidate_id])
    watch = repo.list_watchlist(active_only=True)
    assert run_id > 0
    assert outcome["added"] == 1
    assert watch[0]["symbol"] == "ADDME"
    assert watch[0]["source"] == "FNO_SHEET"
    assert watch[0]["gpt_view"] == "CE_SELL"


def test_repository_does_not_duplicate_existing_fno_sheet_watchlist(tmp_path):
    repo = KiteSpreadRepository(tmp_path / "kite.db")
    result = generate_dhan_top10_from_fno_sheet(make_xlsx({"PE_WHEEL_SHORTLIST": [row("EXIST", tab="PE")]}), live_validator=passing_live)
    repo.save_dhan_fno_top10_run(result)
    candidate_id = repo.latest_dhan_fno_top10_run()["top10"][0]["candidate_id"]
    first = repo.add_dhan_fno_top10_to_watchlist([candidate_id])
    second = repo.add_dhan_fno_top10_to_watchlist([candidate_id])
    rows = [item for item in repo.list_watchlist() if item["symbol"] == "EXIST" and item["source"] == "FNO_SHEET"]
    assert first["added"] == 1
    assert second["updated"] == 1
    assert len(rows) == 1
