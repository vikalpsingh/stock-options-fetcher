#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
otm_scan_fixed.py — NSE 8–10% OTM CALL/PUT scanner (Current & Next Monthly)
Fixed-symbol version — no CLI input needed
Author: ChatGPT
Date: 2025-09-05
"""

import datetime as dt
import math
import random
import time
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

# ------------------------- Settings -------------------------

MIN_OI = 2000          # minimum open interest to pass liquidity
MAX_SPREAD_PCT = 2.0   # maximum bid-ask spread (% of mid)
MIN_VOLUME = 1         # minimum traded volume
SLEEP_BETWEEN_CALLS = 0.8  # seconds

# Hard-coded symbols
SYMBOLS = [
    "BAJFINANCE", "TATACONSUM", "PGEL", "TITAN", "ETERNAL",
    "MCDOWELL-N",  # United Spirits (F&O name)
    "HAVELLS", "NAUKRI", "PFC", "CAMS", "CDSL", "CYIENT", "MAZDOCK"
]

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36",
]

NSE_HOME = "https://www.nseindia.com"
NSE_OC_EQ = "https://www.nseindia.com/api/option-chain-equities?symbol={sym}"

# Lot size fallback (in case API doesn't return it)
FALLBACK_LOTS = {
    "BAJFINANCE": 125,
    "TATACONSUM": 500,
    "PGEL": 350,
    "TITAN": 125,
    "ETERNAL": 0,          # not in F&O likely
    "MCDOWELL-N": 600,
    "HAVELLS": 250,
    "NAUKRI": 200,
    "PFC": 3000,
    "CAMS": 0,
    "CDSL": 500,
    "CYIENT": 200,
    "MAZDOCK": 79,
}


# ------------------------- Session & Fetch -------------------------

def nse_session() -> requests.Session:
    """Create a session with NSE-friendly headers & cookies."""
    ses = requests.Session()
    ua = random.choice(UA_POOL)
    ses.headers.update({
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-GB,en;q=0.9",
        "Referer": NSE_HOME + "/",
        "Connection": "keep-alive",
    })
    # Warm up cookies
    for _ in range(3):
        try:
            r = ses.get(NSE_HOME, timeout=10)
            if r.ok:
                break
        except Exception:
            time.sleep(1.0)
    return ses


def fetch_option_chain(session: requests.Session, symbol: str, retries: int = 4, backoff: float = 1.2) -> Optional[dict]:
    """Fetch option-chain JSON for the given equity symbol."""
    url = NSE_OC_EQ.format(sym=symbol)
    last_exc = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (401, 403):
                # refresh cookies and retry
                session.get(NSE_HOME, timeout=10)
        except Exception as e:
            last_exc = e
        time.sleep(backoff * (attempt + 1))
    if last_exc:
        print(f"[WARN] Failed fetching {symbol}: {last_exc}")
    else:
        try:
            print(f"[WARN] Failed fetching {symbol}: HTTP {r.status_code}")
        except Exception:
            print(f"[WARN] Failed fetching {symbol}")
    return None


# ------------------------- Expiry Utilities -------------------------

def parse_expiries(expiry_list: List[str]) -> List[dt.date]:
    """Parse dd-MMM-yyyy strings to date objects and sort ascending."""
    out = []
    for s in expiry_list:
        try:
            out.append(dt.datetime.strptime(s, "%d-%b-%Y").date())
        except Exception:
            pass
    return sorted(out)


def select_monthlies(expiries: List[dt.date], today: dt.date) -> Tuple[Optional[dt.date], Optional[dt.date]]:
    """
    Pick current-month last expiry and next-month last expiry from provided list.
    Uses calendar months in the API-provided expiryDates list.
    """
    if not expiries:
        return None, None
    cur_month = [d for d in expiries if d.month == today.month and d >= today]
    next_month_num = (today.month % 12) + 1
    nxt_month = [d for d in expiries if (d.year > today.year) or (d.year == today.year and d.month == next_month_num)]
    cur_m = max(cur_month) if cur_month else None
    nxt_m = max(nxt_month) if nxt_month else None
    return cur_m, nxt_m

# ------------------------- Strike & Payload Helpers -------------------------

def nearest_strike(strikes: List[float], target: float, side: str) -> Optional[float]:
    """
    Pick nearest strike meeting OTM condition:
       - Calls: smallest strike >= target
       - Puts : largest  strike <= target
    """
    strikes = sorted(strikes)
    if side == "CALL":
        cands = [s for s in strikes if s >= target]
        return cands[0] if cands else None
    else:
        cands = [s for s in strikes if s <= target]
        return cands[-1] if cands else None


def extract_lot_from_chain(chain: dict) -> Optional[int]:
    """Try to read lot size from the payload if present."""
    try:
        data = chain.get("records", {}).get("data", [])
        for row in data:
            for side in ("CE", "PE"):
                if side in row and "marketLot" in row[side]:
                    ml = int(row[side]["marketLot"])
                    if ml > 0:
                        return ml
    except Exception:
        pass
    try:
        ml = int(chain.get("records", {}).get("marketLot", 0))
        return ml if ml > 0 else None
    except Exception:
        pass
    return None


def fmt_date(d: Optional[dt.date]) -> str:
    return d.strftime("%d-%b-%Y") if d else ""


def pick_leg(rows: List[dict], expiry_str: str, strike: float, side_key: str) -> Optional[dict]:
    """
    From the option-chain `records.data` rows, pick the dict for the given expiry/strike/side.
    side_key = "CE" or "PE"
    """
    if strike is None:
        return None
    for r in rows:
        if r.get("expiryDate") == expiry_str and r.get("strikePrice") == strike and side_key in r:
            return r[side_key]
    return None
# ------------------------- Core Builder -------------------------

def build_tables_for_symbol(symbol: str,
                            chain: dict,
                            min_oi: int, max_spread_pct: float, min_volume: int,
                            fallback_lots: Dict[str, int],
                            today: dt.date):
    """
    For a given symbol payload, return:
      - DataFrame for current-month legs
      - DataFrame for next-month legs
      - Issues list (if any)
    """
    issues = []
    rec = chain.get("records", {})
    under = rec.get("underlyingValue", None)
    expiry_strs = rec.get("expiryDates", [])
    rows = rec.get("data", [])

    if under is None or not expiry_strs or not rows:
        issues.append("No option data / not F&O")
        return pd.DataFrame(), pd.DataFrame(), issues

    expiries = parse_expiries(expiry_strs)
    cur_m, nxt_m = select_monthlies(expiries, today)
    if not cur_m and not nxt_m:
        issues.append("No monthly expiries found")
        return pd.DataFrame(), pd.DataFrame(), issues

    lot = extract_lot_from_chain(chain)
    if not lot:
        lot = fallback_lots.get(symbol, 0)
        if not lot:
            issues.append("Lot size unavailable")

    strikes = sorted({float(r.get("strikePrice")) for r in rows if r.get("strikePrice") is not None})

    def legs_for_exp(exp_date: dt.date) -> List[dict]:
        if not exp_date:
            return []
        exp_str = fmt_date(exp_date)
        out = []

        # Targets
        call8 = under * 1.08
        call10 = under * 1.10
        put8 = under * 0.92
        put10 = under * 0.90

        sel_call8 = nearest_strike(strikes, call8, "CALL")
        sel_call10 = nearest_strike(strikes, call10, "CALL")
        sel_put8  = nearest_strike(strikes, put8,  "PUT")
        sel_put10 = nearest_strike(strikes, put10, "PUT")

        picks = [
            ("CALL_8",  sel_call8,  "CE"),
            ("CALL_10", sel_call10, "CE"),
            ("PUT_8",   sel_put8,   "PE"),
            ("PUT_10",  sel_put10,  "PE"),
        ]

        for tag, strike, side in picks:
            leg = pick_leg(rows, exp_str, strike, side) if strike else None
            if not leg:
                out.append({
                    "Symbol": symbol, "Underlying": under, "Lot": lot,
                    "Expiry": exp_str, "Leg": tag, "Strike": strike,
                    "LTP": None, "Bid": None, "Ask": None, "OI": None, "Volume": None,
                    "Spread%": None, "PremPerLot": None, "Yield%": None, "Status": "NA"
                })
                continue

            bid = float(leg.get("bidprice") or 0.0)
            ask = float(leg.get("askPrice") or 0.0)
            ltp = float(leg.get("lastPrice") or 0.0)
            oi  = int(leg.get("openInterest") or 0)
            vol = int(leg.get("totalTradedVolume") or 0)

            spread_pct = None
            if bid > 0 and ask > 0 and ask >= bid:
                mid = (bid + ask) / 2
                if mid > 0:
                    spread_pct = (ask - bid) / mid * 100.0

            # premium per lot (prefer LTP; fallback to mid if LTP=0 and quotes present)
            price_for_prem = ltp if ltp > 0 else ((bid + ask) / 2 if (bid > 0 and ask > 0) else None)
            prem_per_lot = price_for_prem * lot if (price_for_prem and lot) else None
            yield_pct = (prem_per_lot / (under * lot) * 100.0) if (prem_per_lot and under and lot) else None

            status = "OK"
            if (oi is None or oi < min_oi) or (vol is None or vol < min_volume) or \
               (spread_pct is None or spread_pct > max_spread_pct) or (price_for_prem is None or price_for_prem <= 0):
                status = "ILLQ"

            out.append({
                "Symbol": symbol, "Underlying": under, "Lot": lot,
                "Expiry": exp_str, "Leg": tag, "Strike": strike,
                "LTP": round(price_for_prem, 2) if price_for_prem else None,
                "Bid": bid if bid else None, "Ask": ask if ask else None,
                "OI": oi if oi else None, "Volume": vol if vol else None,
                "Spread%": round(spread_pct, 2) if spread_pct is not None else None,
                "PremPerLot": round(prem_per_lot, 2) if prem_per_lot is not None else None,
                "Yield%": round(yield_pct, 3) if yield_pct is not None else None,
                "Status": status
            })
        return out

    cur_rows = legs_for_exp(cur_m) if cur_m else []
    nxt_rows = legs_for_exp(nxt_m) if nxt_m else []

    return pd.DataFrame(cur_rows), pd.DataFrame(nxt_rows), issues
# ------------------------- Views & Main -------------------------

def best_views(df: pd.DataFrame):
    """
    Return two views:
      A) Max CALL (from CALL_8 vs CALL_10) per symbol
      B) Max PUT  (from PUT_8  vs PUT_10) per symbol
    Only keep rows with Status == 'OK'
    """
    if df.empty:
        return df, df
    ok = df[df["Status"] == "OK"].copy()
    if ok.empty:
        return ok, ok

    calls = ok[ok["Leg"].str.contains("CALL")]
    puts  = ok[ok["Leg"].str.contains("PUT")]

    def pick_max(df_leg: pd.DataFrame) -> pd.DataFrame:
        return (df_leg.sort_values(["Symbol", "PremPerLot"], ascending=[True, False])
                      .groupby("Symbol", as_index=False)
                      .first()
                      .sort_values("PremPerLot", ascending=False))

    calls_best = pick_max(calls) if not calls.empty else pd.DataFrame()
    puts_best  = pick_max(puts)  if not puts.empty else pd.DataFrame()
    return calls_best, puts_best


def main():
    today = dt.date.today()
    session = nse_session()

    df_cur_all, df_nxt_all = [], []
    skipped, notes = [], []

    for sym in SYMBOLS:
        print(f"[SCAN] {sym} ...")
        chain = fetch_option_chain(session, sym)
        if not chain:
            skipped.append((sym, "Fetch failed / not F&O"))
            time.sleep(SLEEP_BETWEEN_CALLS)
            continue

        df_cur, df_nxt, issues = build_tables_for_symbol(
            sym, chain,
            min_oi=MIN_OI, max_spread_pct=MAX_SPREAD_PCT, min_volume=MIN_VOLUME,
            fallback_lots=FALLBACK_LOTS, today=today
        )
        if issues:
            notes.append(f"{sym}: {', '.join(issues)}")
        if df_cur.empty and df_nxt.empty:
            skipped.append((sym, "No valid monthly legs"))
        if not df_cur.empty:
            df_cur_all.append(df_cur)
        if not df_nxt.empty:
            df_nxt_all.append(df_nxt)

        time.sleep(SLEEP_BETWEEN_CALLS)

    df_cur = pd.concat(df_cur_all, ignore_index=True) if df_cur_all else pd.DataFrame()
    df_nxt = pd.concat(df_nxt_all, ignore_index=True) if df_nxt_all else pd.DataFrame()

    cur_calls, cur_puts = best_views(df_cur)
    nxt_calls, nxt_puts = best_views(df_nxt)

    if not cur_calls.empty:
        cur_calls.to_csv("current_month_calls_sorted.csv", index=False)
    if not cur_puts.empty:
        cur_puts.to_csv("current_month_puts_sorted.csv", index=False)
    if not nxt_calls.empty:
        nxt_calls.to_csv("next_month_calls_sorted.csv", index=False)
    if not nxt_puts.empty:
        nxt_puts.to_csv("next_month_puts_sorted.csv", index=False)

    lines = []
    lines.append(f"Run date: {today.isoformat()}")
    lines.append("")

    def top10(title, dfv):
        lines.append(f"== {title} ==")
        if dfv is None or dfv.empty:
            lines.append("  (none)")
            return
        for _, r in dfv.head(10).iterrows():
            strike = int(r['Strike']) if pd.notna(r['Strike']) else 'NA'
            lines.append(
                f"  {r['Symbol']:<12} {r['Expiry']}  {r['Leg']:<7}  K:{strike:>5}  "
                f"LTP:{r['LTP']}  OI:{r['OI']}  Vol:{r['Volume']}  "
                f"Prem/Lot:{r['PremPerLot']}  Yld%:{r['Yield%']}"
            )
        lines.append("")

    top10("Current Monthly — Top CALLs (Prem/Lot)", cur_calls)
    top10("Current Monthly — Top PUTs  (Prem/Lot)", cur_puts)
    top10("Next Monthly — Top CALLs (Prem/Lot)",    nxt_calls)
    top10("Next Monthly — Top PUTs  (Prem/Lot)",    nxt_puts)

    if skipped:
        lines.append("== Skipped / Illiquid ==")
        for s, why in skipped:
            lines.append(f"  {s}: {why}")
        lines.append("")

    if notes:
        lines.append("== Notes / Caveats ==")
        lines += [f"  - {n}" for n in notes]

    with open("scan_summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n".join(lines))
    print("\nSaved CSVs (if any) + scan_summary.txt in the current folder.")


if __name__ == "__main__":
    main()
