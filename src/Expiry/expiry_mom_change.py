# expiry_mom_change.py
# Computes % change in stock close from one monthly F&O expiry to the next.
# Example:
#   python expiry_mom_change.py --symbol PFC --months 6

from nsepython import nse_fno, nsefetch, equity_history
import pandas as pd
from datetime import datetime, timedelta
from calendar import monthrange
import argparse
import sys

DATE_FMT_NSE = "%d-%b-%Y"     # e.g., "28-Aug-2025"
DATE_FMT_HIST = "%d-%m-%Y"    # nsepython equity_history expects dd-mm-YYYY

def is_last_thursday(dt: datetime) -> bool:
    last_day = monthrange(dt.year, dt.month)[1]
    last_dt  = datetime(dt.year, dt.month, last_day)
    # weekday(): Mon=0,...,Thu=3,Sun=6
    while last_dt.weekday() != 3:
        last_dt -= timedelta(days=1)
    return dt.date() == last_dt.date()

def get_expiries(symbol: str) -> list[datetime]:
    """Fetch all expiries for the symbol; return as datetime list."""
    # Try nse_fno first; fall back to option-chain API if needed
    try:
        d = nse_fno(symbol.upper())
        rec = d.get("records", {})
        exps = rec.get("expiryDates", [])
        if exps:
            return [datetime.strptime(e, DATE_FMT_NSE) for e in exps]
    except Exception:
        pass
    oc = nsefetch(f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol.upper()}")
    exps = oc.get("records", {}).get("expiryDates", [])
    if not exps:
        raise RuntimeError(f"No expiries found for {symbol}")
    return [datetime.strptime(e, DATE_FMT_NSE) for e in exps]

def pick_monthly_expiries(expiries: list[datetime], limit: int | None = None) -> list[datetime]:
    """Keep only monthly (last-Thursday) expiries, nearest first, optionally capped."""
    expiries_sorted = sorted(expiries)
    monthlies = [d for d in expiries_sorted if is_last_thursday(d)]
    # Keep only future+recent ones (optional). Here we just keep nearest-first.
    if limit is not None and limit > 0:
        # We want the most recent 'limit' monthlies looking forward from the nearest upcoming
        return monthlies[:limit]
    return monthlies

def nearest_close_on_or_before(symbol: str, target_date: datetime, lookback_days: int = 7) -> tuple[datetime, float]:
    """
    Use equity_history to pull a small window ending on target_date,
    and return (trade_date, close) for the last trading day <= target_date.
    """
    start = (target_date - timedelta(days=lookback_days)).strftime(DATE_FMT_HIST)
    end   = target_date.strftime(DATE_FMT_HIST)

    # equity_history returns a DataFrame with date index or a date column depending on version
    df = equity_history(symbol.upper(), "EQ", start, end)
    if df is None or len(df) == 0:
        raise RuntimeError(f"No equity history for {symbol} in window {start} to {end}")

    # Normalize to DataFrame with a 'DATE' column and 'CLOSE' column
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    # Common column names in nsepython outputs
    # Try to coerce possible column variants
    date_col = None
    for c in ["CH_TIMESTAMP", "TIMESTAMP", "date", "DATE"]:
        if c in df.columns:
            date_col = c
            break
    close_col = None
    for c in ["CH_CLOSING_PRICE", "CLOSE", "close"]:
        if c in df.columns:
            close_col = c
            break
    if date_col is None or close_col is None:
        # Try index as date fallback
        if df.index.name and "date" in df.index.name.lower():
            df = df.reset_index()
            if "index" in df.columns:
                df.rename(columns={"index": "DATE"}, inplace=True)
            date_col = "DATE"
        else:
            raise RuntimeError("Could not locate date/close columns in equity history output.")

    # Parse dates, filter <= target_date, and take the latest
    df["_DT_"] = pd.to_datetime(df[date_col])
    df = df[df["_DT_"] <= target_date].sort_values("_DT_")
    if df.empty:
        raise RuntimeError(f"No trading day on/before {target_date.date()} for {symbol}")
    last_row = df.iloc[-1]
    return (last_row["_DT_"].to_pydatetime(), float(last_row[close_col]))

def month_to_month_changes(symbol: str, months: int = 6) -> pd.DataFrame:
    """
    Compute % change in equity close from one monthly expiry to the next.
    Returns a DataFrame: [FromExpiry, FromClose, ToExpiry, ToClose, PctChange%]
    """
    all_exp = get_expiries(symbol)
    print("DEBUG: All expiries:", [d.strftime(DATE_FMT_NSE) for d in all_exp])  # Add this line
    monthlies = pick_monthly_expiries(all_exp, limit=months + 1)  # need one extra for pairs
    if len(monthlies) < 2:
        raise RuntimeError("Not enough monthly expiries to compute change. Try reducing --months or check the symbol.")

    # For each monthly expiry, get the close on/just before that date
    closes = []
    for exp in monthlies:
        dt, cl = nearest_close_on_or_before(symbol, exp, lookback_days=7)
        closes.append({"Expiry": exp, "TradeDate": dt, "Close": cl})

    # Compute successive % changes
    rows = []
    for i in range(len(closes) - 1):
        e0, d0, c0 = closes[i]["Expiry"], closes[i]["TradeDate"], closes[i]["Close"]
        e1, d1, c1 = closes[i+1]["Expiry"], closes[i+1]["TradeDate"], closes[i+1]["Close"]
        pct = ((c1 - c0) / c0) * 100.0 if c0 else None
        rows.append({
            "Symbol": symbol.upper(),
            "FromExpiry": e0.strftime(DATE_FMT_NSE),
            "FromTradeDate": d0.strftime("%Y-%m-%d"),
            "FromClose": round(c0, 2),
            "ToExpiry": e1.strftime(DATE_FMT_NSE),
            "ToTradeDate": d1.strftime("%Y-%m-%d"),
            "ToClose": round(c1, 2),
            "PctChange%": round(pct, 2) if pct is not None else None
        })

    return pd.DataFrame(rows)

def main():
    ap = argparse.ArgumentParser(description="Month-over-month % change in stock close from one F&O monthly expiry to the next.")
    ap.add_argument("--symbol", default="PFC", help="Equity symbol (e.g., PFC)")
    ap.add_argument("--months", type=int, default=6, help="How many monthly steps to compute (needs +1 expiries internally)")
    args = ap.parse_args()

    try:
        df = month_to_month_changes(args.symbol, months=args.months)
    except Exception as e:
        print("ERROR:", e)
        sys.exit(1)

    if df.empty:
        print("No data produced.")
        sys.exit(2)

    # Print nicely
    with pd.option_context("display.max_columns", None, "display.width", 140):
        print(df.to_string(index=False))

    # Optionally save
    # out = f"mom_expiry_changes_{args.symbol.upper()}.csv"
    # df.to_csv(out, index=False)
    # print(f"\nSaved: {out}")

if __name__ == "__main__":
    main()
