#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
otm_premiums_batch.py
Fetch OTM option premiums (CE & PE) for selected NSE symbols.
"""

import requests
import pandas as pd
import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from calendar import monthrange
from math import isfinite
from typing import List, Tuple, Dict, Any

DATE_FMT = "%d-%b-%Y"
INPUT_FILE_DEFAULT = "input.txt"
OUTPUT_CSV_DEFAULT = "otm_premiums_batch.csv"

# ----------------------------- NSE Fetch Helper -----------------------------
def nsefetch(url: str, max_retries: int = 3, sleep: float = 1.0) -> dict:
    """Fetch NSE data with retries and proper headers."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    sess = requests.Session()
    for attempt in range(max_retries):
        try:
            resp = sess.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        time.sleep(sleep)
    raise RuntimeError(f"Failed to fetch data from NSE after {max_retries} attempts: {url}")

# ----------------------------- Input Parser -----------------------------
def read_symbols_with_params(path: str) -> List[Tuple[str, int, float]]:
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
                pct = float(parts[2]) / 100.0
            except:
                pct = 0.10
            out.append((sym, lot, pct))
    return out

# ----------------------------- Lot Size Helpers -----------------------------
def _pick_lot_from_json(obj: dict) -> int | None:
    if not isinstance(obj, dict):
        return None
    for key in ("marketLot",):
        if isinstance(obj.get(key), (int, float)) and obj[key] > 0:
            return int(obj[key])
    rec = obj.get("records") or {}
    if rec:
        return _pick_lot_from_json(rec)
    info = obj.get("info") or {}
    return _pick_lot_from_json(info) if info else None

def get_lot_size(symbol: str, override: int | None = None) -> int:
    if override and override > 0:
        return override
    try:
        qd = nsefetch(f"https://www.nseindia.com/api/quote-derivative?symbol={symbol.upper()}")
        lot = _pick_lot_from_json(qd)
        if lot:
            return lot
    except Exception as e:
        print(f"[WARN] Lot fetch failed for {symbol}: {e}")
    # Fallback
    print(f"[WARN] Falling back to LotSize=1 for {symbol}")
    return 1

# ----------------------------- Date Helpers -----------------------------
def to_date(s: str) -> datetime:
    return datetime.strptime(s, DATE_FMT)

def is_last_thursday(dt: datetime) -> bool:
    last_day = monthrange(dt.year, dt.month)[1]
    last_dt = datetime(dt.year, dt.month, last_day)
    while last_dt.weekday() != 3:  # Thursday == 3
        last_dt -= timedelta(days=1)
    return dt.date() == last_dt.date()

def nearest_expiry(records: dict) -> str:
    exps = records.get("expiryDates", [])
    if not exps:
        raise RuntimeError("No expiries available.")
    return exps

def next_two_monthlies(records: dict, start_exp: str) -> List[str]:
    exps = records.get("expiryDates", [])
    dates = sorted((to_date(e), e) for e in exps)
    start_dt = to_date(start_exp)
    monthlies = [e for (d, e) in dates if d > start_dt and is_last_thursday(d)]
    if len(monthlies) >= 2:
        return monthlies[:2]
    after = [e for (d, e) in dates if d > start_dt]
    picks = monthlies[:]
    for (_, e) in after:
        if len(picks) >= 2:
            break
        if e not in picks:
            picks.append(e)
    return picks[:2]

# ----------------------------- Option Chain Helpers -----------------------------
def fetch_records(symbol: str) -> dict:
    url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol.upper()}"
    d2 = nsefetch(url)
    rec2 = d2.get("records", {})
    if not rec2.get("data") or not rec2.get("expiryDates"):
        raise RuntimeError(f"No option chain found for {symbol}.")
    return rec2

def available_strikes(records: dict, expiry: str) -> List[float]:
    rows = records.get("data", [])
    return sorted({float(r.get("strikePrice")) for r in rows if r.get("expiryDate") == expiry})

def pick_strike(strikes: List[float], target: float, side: str) -> float:
    if side.upper() == "CE":
        cands = [s for s in strikes if s >= target]
        return min(cands) if cands else strikes[-1]
    else:
        cands = [s for s in strikes if s <= target]
        return max(cands) if cands else strikes[0]

def row_for(records: dict, expiry: str, strike: float) -> dict | None:
    for r in records.get("data", []):
        if r.get("expiryDate") == expiry and float(r.get("strikePrice")) == float(strike):
            return r
    return None

def extract_leg(row: dict, leg_key: str) -> dict:
    leg = row.get(leg_key, {}) or {}
    bid = leg.get("bidPrice") or leg.get("bidprice")
    return {
        "LTP": leg.get("lastPrice"),
        "Bid": bid,
        "Ask": leg.get("askPrice"),
        "OI": leg.get("openInterest"),
        "ChgOI": leg.get("changeInOpenInterest") or leg.get("changeinOpenInterest"),
        "IV": leg.get("impliedVolatility"),
        "Volume": leg.get("totalTradedVolume"),
    }

# ----------------------------- Main Logic -----------------------------
def compute_for_symbol(symbol: str, lot: int, pct: float) -> List[Dict[str, Any]]:
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
            "Symbol": symbol, "Underlying": underlying, "Expiry": exp,
            "Side": f"CALL (OTM~{pct:.0%})",
            "Strike": ce_strike, **ce,
            "LotSize": lot_size, "Premium": ce_prem
        })
        rows_out.append({
            "Symbol": symbol, "Underlying": underlying, "Expiry": exp,
            "Side": f"PUT  (OTM~{pct:.0%})",
            "Strike": pe_strike, **pe,
            "LotSize": lot_size, "Premium": pe_prem
        })
        time.sleep(1)  # avoid NSE rate-limit
    return rows_out

# ----------------------------- Runner -----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=INPUT_FILE_DEFAULT,
                        help="Path to input.txt with header #Symbol LOT_SIZE OTM%")
    parser.add_argument("--out", default=OUTPUT_CSV_DEFAULT,
                        help="Output CSV file")
    parser.add_argument("--skip-sort", action="store_true",
                        help="Skip sorting step")
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
            print(f"[OK] {sym}: {len(rows)} rows")
        except Exception as e:
            print(f"[FAIL] {sym}: {e}")

    if not all_rows:
        print("No data fetched.")
        sys.exit(2)

    df = pd.DataFrame(all_rows)
    before = len(df)
    df = df.drop_duplicates(subset=["Symbol", "Underlying", "Expiry", "Strike", "Side"], keep="first").reset_index(drop=True)
    print(f"Removed {before - len(df)} duplicate rows.")
    df.to_csv(args.out, index=False)
    print(f"Saved: {args.out} ({len(df)} rows)")

    if not args.skip_sort:
        try:
            import subprocess
            subprocess.run(
                ["python", os.path.join(os.path.dirname(__file__), "sort_by_premium.py"), args.out],
                check=True
            )
            print(f"Sorted output saved as 'sorted_output.csv'")
        except Exception as e:
            print(f"[WARN] Sorting failed: {e}")

if __name__ == "__main__":
    main()
