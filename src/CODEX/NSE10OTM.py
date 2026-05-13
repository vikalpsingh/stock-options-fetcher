import requests
import time
import pandas as pd
import numpy as np
from datetime import datetime
from nsepython import equity_history
import os

# List of shares with (symbol, name, lot size)
SHARES = [
    ("PGEL", "PG Electroplast Ltd", 700),
    ("ETERNAL", "Eternal Ltd", 2450),
    ("BAJFINANCE", "Bajaj Finance Ltd", 750),
    ("UNITDSPR", "United Spirits Ltd", 375),
    ("PFC", "Power Finance Corporation Ltd", 1300),
    ("MAZDOCK", "Mazagon Dock Shipbuilders Ltd", 175),
    ("TATACONSUM", "Tata Consumer Products Ltd", 550),
    ("TITAN", "Titan", 350),
    ("NTPC", "NTPC Ltd", 1500),
    ("NAUKRI", "Info Edge", 375),
    ("HAVELLS", "Havells Ltd", 500),
    ("CYIENT", "Cyient Ltd", 425),
]

# ----- Option chain helpers -----

def fetch_option_chain(symbol: str):
    url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": f"https://www.nseindia.com/get-quotes/derivatives?symbol={symbol}",
    }
    with requests.Session() as session:
        session.get("https://www.nseindia.com", headers=headers)
        time.sleep(1)
        session.get(headers["Referer"], headers=headers)
        time.sleep(1)
        resp = session.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()

def get_otm_option_premiums(records: dict, underlying: float, expiry: str, lot_size: int):
    strikes = sorted({float(item["strikePrice"]) for item in records.get("data", []) if item.get("expiryDate") == expiry})
    target_call = underlying * 1.10
    target_put = underlying * 0.90
    call_candidates = [s for s in strikes if s >= target_call]
    put_candidates = [s for s in strikes if s <= target_put]
    call_strike = min(call_candidates) if call_candidates else None
    put_strike = max(put_candidates) if put_candidates else None

    call_prem = call_total = None
    put_prem = put_total = None

    if call_strike is not None:
        row = next((r.get("CE") for r in records.get("data", []) if r.get("expiryDate") == expiry and float(r.get("strikePrice")) == call_strike and r.get("CE")), None)
        if row:
            call_prem = row.get("lastPrice")
            call_total = call_prem * lot_size if call_prem else None

    if put_strike is not None:
        row = next((r.get("PE") for r in records.get("data", []) if r.get("expiryDate") == expiry and float(r.get("strikePrice")) == put_strike and r.get("PE")), None)
        if row:
            put_prem = row.get("lastPrice")
            put_total = put_prem * lot_size if put_prem else None

    return call_strike, call_prem, call_total, put_strike, put_prem, put_total

# ----- Probability helpers -----

def remove_outliers_iqr(data: pd.DataFrame, column: str, k: float = 1.5):
    q1 = data[column].quantile(0.25)
    q3 = data[column].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - k * iqr
    upper = q3 + k * iqr
    return data[(data[column] >= lower) & (data[column] <= upper)].reset_index(drop=True)

def compute_probabilities(symbol: str, months_back: int = 24, alpha: float = 0.85, weight_scheme: str = "exp", iqr_k: float = 1.5):
    end_date = datetime.today()
    start_date = end_date - pd.DateOffset(months=months_back)
    data = equity_history(symbol, "EQ", start_date.strftime("%d-%m-%Y"), end_date.strftime("%d-%m-%Y"))
    if data is None or data.empty:
        return None

    data["YearMonth"] = pd.to_datetime(data["CH_TIMESTAMP"]).dt.to_period("M")
    data["log_return"] = np.log(data["CH_CLOSING_PRICE"] / data["CH_CLOSING_PRICE"].shift(1))

    monthly = data.groupby("YearMonth").agg(
        close=("CH_CLOSING_PRICE", "last"),
        vol=("log_return", lambda x: np.std(x.dropna(), ddof=1) * np.sqrt(21)),
    ).reset_index()
    monthly["pct_change"] = monthly["close"].pct_change() * 100
    monthly.dropna(subset=["pct_change"], inplace=True)
    monthly.reset_index(drop=True, inplace=True)

    trimmed = remove_outliers_iqr(monthly, "pct_change", k=iqr_k)
    if len(trimmed) < 3:
        return None

    n = len(trimmed)
    if weight_scheme == "exp":
        weights = np.array([alpha ** (n - 1 - i) for i in range(n)])
    else:
        weights = np.ones(n)
    weights /= weights.sum()

    weighted_positive = np.sum(w for w, chg in zip(weights, trimmed["pct_change"]) if chg > 0)
    weighted_negative = np.sum(w for w, chg in zip(weights, trimmed["pct_change"]) if chg < 0)
    total_weight = weighted_positive + weighted_negative
    prob_inc = weighted_positive / total_weight if total_weight else 0
    prob_dec = weighted_negative / total_weight if total_weight else 0
    direction = "Increase" if prob_inc >= prob_dec else "Decrease"

    return {
        "prob_increase": prob_inc,
        "prob_decrease": prob_dec,
        "direction": direction,
    }

# ----- Main -----

def expiry_to_filename(expiry: str) -> str:
    dt = datetime.strptime(expiry, "%d-%b-%Y")
    return dt.strftime("%b_%Y") + "_predictions.csv"

def main():
    expiry_input = "28-Apr-2026"
    os.makedirs("analysis_outputs", exist_ok=True)
    results = []
    print(f"\nProcessing probability and premium data for expiry {expiry_input}\n")
    for symbol, name, lot in SHARES:
        try:
            prob = compute_probabilities(symbol)
            if prob is None:
                print(f"{symbol}: Not enough data for probability calculation. Skipping.")
                continue
            chain = fetch_option_chain(symbol)
            records = chain.get("records", {})
            underlying = records.get("underlyingValue")
            expiries = records.get("expiryDates", [])
            if expiry_input not in expiries:
                print(f"{symbol}: Expiry {expiry_input} not available. Skipping.")
                continue
            (call_strike, call_prem, call_total,
             put_strike, put_prem, put_total) = get_otm_option_premiums(records, underlying, expiry_input, lot)
            if prob["direction"] == "Increase":
                strike = call_strike
                ltp = call_prem
                premium = call_total
                opt_type = "CALL"
            else:
                strike = put_strike
                ltp = put_prem
                premium = put_total
                opt_type = "PUT"
            results.append({
                "Symbol": symbol,
                "Name": name,
                "Lot Size": lot,
                "Underlying": underlying,
                "Expiry": expiry_input,
                "Probability Increase": prob["prob_increase"],
                "Probability Decrease": prob["prob_decrease"],
                "Predicted Direction": prob["direction"],
                "Option Type": opt_type,
                "OTM Strike": strike,
                "Option LTP": ltp,
                "Premium (Lot)": premium,
            })
            print(f"{symbol}: direction={prob['direction']} strike={strike} premium={premium}")
        except Exception as e:
            print(f"{symbol}: error {e}")

    if results:
        df = pd.DataFrame(results)
        out_csv = os.path.join("analysis_outputs", expiry_to_filename(expiry_input))
        df.to_csv(out_csv, index=False)
        print(f"\n✓ Results saved to {out_csv}")
    else:
        print("\nNo results to save.")

if __name__ == "__main__":
    main()
