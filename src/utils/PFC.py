# otm_premiums.py
# pip install nsepython pandas python-dateutil

from nsepython import nse_fno, nsefetch
import pandas as pd
from math import isfinite
from datetime import datetime, timedelta
from calendar import monthrange
import argparse
import sys

DATE_FMT = "%d-%b-%Y"  # e.g., "28-Aug-2025"

# ----------------------------- Fetchers -----------------------------
def fetch_records(symbol: str):
    """Try nse_fno first, then raw option-chain API as fallback."""
    # Attempt 1: nse_fno
    try:
        d = nse_fno(symbol.upper())
        rec = d.get("records", {})
        if rec.get("data") and rec.get("expiryDates"):
            return rec
    except Exception:
        pass
    # Attempt 2: option-chain endpoint
    url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol.upper()}"
    d2 = nsefetch(url)
    rec2 = d2.get("records", {})
    if not rec2.get("data") or not rec2.get("expiryDates"):
        raise RuntimeError(f"No option chain found for {symbol}.")
    return rec2

def get_lot_size(symbol: str, fallback: int | None = None) -> int:
    """Best-effort fetch of derivatives lot size. Falls back to provided value if needed."""
    # 1) Try nse_fno root or records.marketLot
    try:
        d = nse_fno(symbol.upper())
        if isinstance(d.get("marketLot"), (int, float)) and d["marketLot"] > 0:
            return int(d["marketLot"])
        rec = d.get("records", {})
        if isinstance(rec.get("marketLot"), (int, float)) and rec["marketLot"] > 0:
            return int(rec["marketLot"])
    except Exception:
        pass

    # 2) Try quote-derivative endpoint (and nested info.marketLot)
    try:
        qd = nsefetch(f"https://www.nseindia.com/api/quote-derivative?symbol={symbol.upper()}")
        if isinstance(qd.get("marketLot"), (int, float)) and qd["marketLot"] > 0:
            return int(qd["marketLot"])
        info = qd.get("info") or {}
        if isinstance(info.get("marketLot"), (int, float)) and info["marketLot"] > 0:
            return int(info["marketLot"])
    except Exception:
        pass

    # 3) Fallback (PFC commonly 2700; you can override via --lot)
    if fallback:
        return int(fallback)
    raise RuntimeError(f"Could not determine lot size for {symbol}. Pass --lot manually.")

# ----------------------------- Date helpers -----------------------------
def to_date(s: str) -> datetime:
    return datetime.strptime(s, DATE_FMT)

def is_last_thursday(dt: datetime) -> bool:
    last_day = monthrange(dt.year, dt.month)[1]
    last_dt  = datetime(dt.year, dt.month, last_day)
    while last_dt.weekday() != 3:  # Thursday == 3
        last_dt -= timedelta(days=1)
    return dt.date() == last_dt.date()

def nearest_expiry(records) -> str:
    exps = records.get("expiryDates", [])
    if not exps:
        raise RuntimeError("No expiries available.")
    return exps[0]  # NSE already orders nearest first

def next_two_monthlies(records, start_exp: str) -> list[str]:
    exps = records.get("expiryDates", [])
    dates = sorted((to_date(e), e) for e in exps)
    start_dt = to_date(start_exp)

    # Prefer true monthlies (last Thursday)
    monthlies = [e for (d, e) in dates if d > start_dt and is_last_thursday(d)]
    if len(monthlies) >= 2:
        return monthlies[:2]

    # Fallback to next available expiries
    after = [e for (d, e) in dates if d > start_dt]
    picks = monthlies[:]
    for e in after:
        if len(picks) >= 2:
            break
        if e not in picks:
            picks.append(e)
    return picks[:2]

# ----------------------------- Option-chain helpers -----------------------------
def available_strikes(records, expiry: str) -> list[float]:
    rows = records.get("data", [])
    strikes = sorted({float(r.get("strikePrice")) for r in rows if r.get("expiryDate") == expiry})
    if not strikes:
        raise RuntimeError(f"No strikes for expiry {expiry}.")
    return strikes

def pick_strike(strikes: list[float], target: float, side: str) -> float:
    """side='CE' => min strike >= target; side='PE' => max strike <= target."""
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
def get_otm_premiums(symbol: str, pct: float = 0.10, lot_size: int | None = None):
    """
    For nearest expiry + next 2 monthly expiries:
      - compute ±pct OTM targets from underlying
      - snap to real listed strikes
      - return CE & PE quotes with LTP, Bid/Ask, OI, IV, Volume, LotSize, Premium=LTP*LotSize
    """
    records = fetch_records(symbol)
    underlying = records.get("underlyingValue")
    if not (isinstance(underlying, (int, float)) and isfinite(underlying)):
        raise RuntimeError("Underlying value missing from NSE response.")

    # Lot size detection with sensible fallback for PFC
    default_fallback = 2700 if symbol.upper() == "PFC" else None
    lot = lot_size if lot_size else get_lot_size(symbol, fallback=default_fallback)

    near = nearest_expiry(records)
    nxt2 = next_two_monthlies(records, near)
    expiries = [near] + nxt2

    rows_out = []
    for exp in expiries:
        strikes = available_strikes(records, exp)
        target_call = underlying * (1 + pct)
        target_put  = underlying * (1 - pct)

        ce_strike = pick_strike(strikes, target_call, side="CE")
        pe_strike = pick_strike(strikes, target_put,  side="PE")

        ce_row = row_for(records, exp, ce_strike)
        pe_row = row_for(records, exp, pe_strike)
        if not ce_row or not pe_row:
            # Skip this expiry if either leg missing
            continue

        ce = extract_leg(ce_row, "CE")
        pe = extract_leg(pe_row, "PE")

        ce_premium = (ce["LTP"] or 0) * lot
        pe_premium = (pe["LTP"] or 0) * lot

        rows_out.append({
            "Symbol": symbol.upper(),
            "Underlying": underlying,
            "Expiry": exp,
            "Side": f"CALL (OTM~{pct:.0%})",
            "Strike": ce_strike,
            "LTP": ce["LTP"],
            "Bid": ce["Bid"],
            "Ask": ce["Ask"],
            "OI": ce["OI"],
            "ChgOI": ce["ChgOI"],
            "IV": ce["IV"],
            "Volume": ce["Volume"],
            "LotSize": lot,
            "Premium": ce_premium
        })
        rows_out.append({
            "Symbol": symbol.upper(),
            "Underlying": underlying,
            "Expiry": exp,
            "Side": f"PUT  (OTM~{pct:.0%})",
            "Strike": pe_strike,
            "LTP": pe["LTP"],
            "Bid": pe["Bid"],
            "Ask": pe["Ask"],
            "OI": pe["OI"],
            "ChgOI": pe["ChgOI"],
            "IV": pe["IV"],
            "Volume": pe["Volume"],
            "LotSize": lot,
            "Premium": pe_premium
        })

    df = pd.DataFrame(rows_out, columns=[
        "Symbol","Underlying","Expiry","Side","Strike","LTP","Bid","Ask","OI","ChgOI","IV","Volume","LotSize","Premium"
    ])
    meta = {
        "symbol": symbol.upper(),
        "underlying": underlying,
        "pct_otm": pct,
        "lot_size": lot,
        "expiries_considered": expiries
    }
    return df, meta

# ----------------------------- CLI -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Fetch ~OTM CE/PE premiums for nearest + next 2 monthly expiries.")
    parser.add_argument("--symbol", required=True, help="F&O trading symbol (e.g., PFC, RELIANCE, BANKNIFTY)")
    parser.add_argument("--pct", type=float, default=0.10, help="OTM percent (e.g., 0.10 for ~10%%)")
    parser.add_argument("--lot", type=int, default=None, help="Force lot size (overrides auto-detection)")
    args = parser.parse_args()

    try:
        df, meta = get_otm_premiums(args.symbol, pct=args.pct, lot_size=args.lot)
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)

    print("Meta:", meta)
    if df.empty:
        print("No rows produced (legs missing for selected expiries).")
        sys.exit(2)

    # Pretty print and also show totals for reference
    with pd.option_context("display.max_columns", None, "display.width", 140):
        print(df.to_string(index=False))

    # Optional: save CSV
    # out = f"otm_premiums_{args.symbol.upper()}.csv"
    # df.to_csv(out, index=False)
    # print(f"\nSaved: {out}")

if __name__ == "__main__":
    main()
