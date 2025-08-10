# otm_premiums_batch.py
# Reads symbols from input.txt with header: #Symbol LOT_SIZE OTM%
# Computes CE & PE for nearest + next 2 monthly expiries and writes to CSV

from nsepython import nse_fno, nsefetch
import pandas as pd
from math import isfinite
from datetime import datetime, timedelta
from calendar import monthrange
import argparse
import sys
import os
import time

DATE_FMT = "%d-%b-%Y"
INPUT_FILE_DEFAULT = "input.txt"
OUTPUT_CSV_DEFAULT = "otm_premiums_batch.csv"

# ----------------------------- Input parser -----------------------------
def read_symbols_with_params(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Symbols file not found: {path}")
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                raise ValueError(f"Invalid line in {path}: {line}")
            sym = parts[0].upper()
            try:
                lot = int(parts[1])
            except:
                lot = 0
            try:
                pct = float(parts[2]) / 100.0  # convert to decimal
            except:
                pct = 0.10
            out.append((sym, lot, pct))
    return out

# ----------------------------- Lot size fetcher -----------------------------
def _pick_lot_from_json(obj):
    if not isinstance(obj, dict):
        return None
    if isinstance(obj.get("marketLot"), (int, float)) and obj["marketLot"] > 0:
        return int(obj["marketLot"])
    rec = obj.get("records") or {}
    if isinstance(rec.get("marketLot"), (int, float)) and rec["marketLot"] > 0:
        return int(rec["marketLot"])
    info = obj.get("info") or {}
    if isinstance(info.get("marketLot"), (int, float)) and info["marketLot"] > 0:
        return int(info["marketLot"])
    return None

def get_lot_size(symbol: str, override: int | None = None):
    if override and override > 0:
        return override
    sym = symbol.upper()
    # Try nse_fno
    try:
        d = nse_fno(sym)
        lot = _pick_lot_from_json(d)
        if lot:
            return lot
    except:
        pass
    # Try quote-derivative
    try:
        qd = nsefetch(f"https://www.nseindia.com/api/quote-derivative?symbol={sym}")
        lot = _pick_lot_from_json(qd)
        if lot:
            return lot
    except:
        pass
    raise RuntimeError(f"Could not determine lot size for {sym} (no override).")

# ----------------------------- Date helpers -----------------------------
def to_date(s: str) -> datetime:
    return datetime.strptime(s, DATE_FMT)

def is_last_thursday(dt: datetime) -> bool:
    last_day = monthrange(dt.year, dt.month)[1]
    last_dt  = datetime(dt.year, dt.month, last_day)
    while last_dt.weekday() != 3:
        last_dt -= timedelta(days=1)
    return dt.date() == last_dt.date()

def nearest_expiry(records) -> str:
    exps = records.get("expiryDates", [])
    if not exps:
        raise RuntimeError("No expiries available.")
    return exps[0]

def next_two_monthlies(records, start_exp: str) -> list[str]:
    exps = records.get("expiryDates", [])
    dates = sorted((to_date(e), e) for e in exps)
    start_dt = to_date(start_exp)
    monthlies = [e for (d, e) in dates if d > start_dt and is_last_thursday(d)]
    if len(monthlies) >= 2:
        return monthlies[:2]
    after = [e for (d, e) in dates if d > start_dt]
    picks = monthlies[:]
    for e in after:
        if len(picks) >= 2:
            break
        if e not in picks:
            picks.append(e)
    return picks[:2]

# ----------------------------- Option chain helpers -----------------------------
def fetch_records(symbol: str):
    try:
        d = nse_fno(symbol.upper())
        rec = d.get("records", {})
        if rec.get("data") and rec.get("expiryDates"):
            return rec
    except:
        pass
    url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol.upper()}"
    d2 = nsefetch(url)
    rec2 = d2.get("records", {})
    if not rec2.get("data") or not rec2.get("expiryDates"):
        raise RuntimeError(f"No option chain found for {symbol}.")
    return rec2

def available_strikes(records, expiry: str) -> list[float]:
    rows = records.get("data", [])
    strikes = sorted({float(r.get("strikePrice")) for r in rows if r.get("expiryDate") == expiry})
    return strikes

def pick_strike(strikes: list[float], target: float, side: str) -> float:
    if side.upper() == "CE":
        cands = [s for s in strikes if s >= target]
        return min(cands) if cands else strikes[-1]
    else:
        cands = [s for s in strikes if s <= target]
        return max(cands) if cands else strikes[0]

def row_for(records, expiry: str, strike: float):
    for r in records.get("data", []):
        if r.get("expiryDate") == expiry and float(r.get("strikePrice")) == float(strike):
            return r
    return None

def extract_leg(row: dict, leg_key: str) -> dict:
    leg = row.get(leg_key, {}) or {}
    bid = leg.get("bidprice") if "bidprice" in leg else leg.get("bidPrice")
    return {
        "LTP": leg.get("lastPrice"),
        "Bid": bid,
        "Ask": leg.get("askPrice"),
        "OI": leg.get("openInterest"),
        "ChgOI": leg.get("changeinOpenInterest") or leg.get("changeInOpenInterest"),
        "IV": leg.get("impliedVolatility"),
        "Volume": leg.get("totalTradedVolume"),
    }

# ----------------------------- Main logic -----------------------------
def compute_for_symbol(symbol: str, lot: int, pct: float):
    records = fetch_records(symbol)
    underlying = records.get("underlyingValue")
    if not (isinstance(underlying, (int, float)) and isfinite(underlying)):
        raise RuntimeError(f"Underlying missing for {symbol}")

    lot_size = get_lot_size(symbol, override=lot)
    near = nearest_expiry(records)
    nxt2 = next_two_monthlies(records, near)
    expiries = [near] + nxt2

    rows_out = []
    for exp in expiries:
        strikes = available_strikes(records, exp)
        if not strikes:
            continue
        target_call = underlying * (1 + pct)
        target_put = underlying * (1 - pct)
        ce_strike = pick_strike(strikes, target_call, "CE")
        pe_strike = pick_strike(strikes, target_put, "PE")
        ce_row = row_for(records, exp, ce_strike)
        pe_row = row_for(records, exp, pe_strike)
        if not ce_row or not pe_row:
            continue
        ce = extract_leg(ce_row, "CE")
        pe = extract_leg(pe_row, "PE")
        ce_prem = (ce["LTP"] or 0) * lot_size
        pe_prem = (pe["LTP"] or 0) * lot_size
        rows_out.append({
            "Symbol": symbol, "Underlying": underlying, "Expiry": exp, "Side": f"CALL (OTM~{pct:.0%})",
            "Strike": ce_strike, "LTP": ce["LTP"], "LotSize": lot_size, "Premium": ce_prem
        })
        rows_out.append({
            "Symbol": symbol, "Underlying": underlying, "Expiry": exp, "Side": f"PUT  (OTM~{pct:.0%})",
            "Strike": pe_strike, "LTP": pe["LTP"], "LotSize": lot_size, "Premium": pe_prem
        })
    return rows_out

# ----------------------------- Runner -----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=INPUT_FILE_DEFAULT, help="Path to input.txt with header #Symbol LOT_SIZE OTM%")
    parser.add_argument("--out", default=OUTPUT_CSV_DEFAULT, help="Output CSV file")
    args = parser.parse_args()

    try:
        sym_data = read_symbols_with_params(args.file)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

    all_rows = []
    for sym, lot, pct in sym_data:
        try:
            rows = compute_for_symbol(sym, lot, pct)
            all_rows.extend(rows)
        except Exception as e:
            print(f"{sym} failed: {e}")

    if not all_rows:
        print("No data fetched.")
        sys.exit(2)

    df = pd.DataFrame(all_rows)
    df.to_csv(args.out, index=False)
    print(f"Saved: {args.out} ({len(df)} rows)")

if __name__ == "__main__":
    main()
