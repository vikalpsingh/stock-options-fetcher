import requests
import time
import pandas as pd
from datetime import datetime

shares = [
    ("PGEL", "PG Electroplast Ltd", 700),
    ("ETERNAL", "Eternal Ltd", 2450),
    ("BAJFINANCE", "Bajaj Finance Ltd", 750),
    ("UNITDSPR", "United Spirits Ltd", 375),
    ("PFC", "Power Finance Corporation Ltd", 1300),
    ("NAZARA", "Nazara tech", 420),
    ("MAZDOCK", "Mazagon Dock Shipbuilders Ltd", 150),
    ("TATACONSUM", "Tata Consumer Products Ltd", 550),
    ("TITAN", "Titan", 505),
    ("NTPC", "NTPC Ltd", 1500)
]

def fetch_option_chain(symbol):
    url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Referer': f'https://www.nseindia.com/get-quotes/derivatives?symbol={symbol}'
    }

    with requests.Session() as session:
        session.get("https://www.nseindia.com", headers=headers)
        time.sleep(2)
        session.get(headers['Referer'], headers=headers)
        time.sleep(2)
        response = session.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

def get_otm_option_premiums(records, underlying, expiry, lot_size):
    strikes = sorted({float(item["strikePrice"]) for item in records.get("data", []) if item.get("expiryDate") == expiry})
    # ~10% OTM CALL: nearest strike >= underlying*1.10
    target_call_strike = underlying * 1.10
    otm_call_strikes = [strike for strike in strikes if strike >= target_call_strike]
    call_strike = min(otm_call_strikes) if otm_call_strikes else None
    # ~10% OTM PUT: nearest strike <= underlying*0.90
    target_put_strike = underlying * 0.90
    otm_put_strikes = [strike for strike in strikes if strike <= target_put_strike]
    put_strike = max(otm_put_strikes) if otm_put_strikes else None

    call_premium = None
    put_premium = None
    call_premium_total = None
    put_premium_total = None

    if call_strike:
        call_option = next((item.get("CE") for item in records.get("data", []) if item.get("expiryDate") == expiry and float(item.get("strikePrice")) == call_strike and item.get("CE")), None)
        if call_option:
            call_premium = call_option.get("lastPrice")
            call_premium_total = call_premium * lot_size if call_premium else None

    if put_strike:
        put_option = next((item.get("PE") for item in records.get("data", []) if item.get("expiryDate") == expiry and float(item.get("strikePrice")) == put_strike and item.get("PE")), None)
        if put_option:
            put_premium = put_option.get("lastPrice")
            put_premium_total = put_premium * lot_size if put_premium else None

    return call_strike, call_premium, call_premium_total, put_strike, put_premium, put_premium_total

def expiry_to_filename(expiry):
    # e.g. "30-Sep-2025" → "Sep_2025_options.csv"
    dt = datetime.strptime(expiry, "%d-%b-%Y")
    return f"{dt.strftime('%b_%Y')}_options.csv"

def main():
    expiry_input = input("Enter NSE expiry date (e.g. 30-Sep-2025): ").strip()
    results = []

    print(f"\nFetching ~10% OTM Call and Put option prices for expiry {expiry_input}\n")
    for symbol, name, lot in shares:
        try:
            data = fetch_option_chain(symbol)
            records = data.get("records", {})
            underlying = records.get("underlyingValue")
            print(f"{name} ({symbol}): Underlying price = {underlying}")

            expiries = records.get("expiryDates", [])
            if expiry_input not in expiries:
                print(f"  --> Expiry {expiry_input} not found. Skipping.\n")
                continue

            (call_strike, call_prem, call_prem_total,
             put_strike, put_prem, put_prem_total) = get_otm_option_premiums(records, underlying, expiry_input, lot)

            results.append({
                "Symbol": symbol,
                "Name": name,
                "Lot Size": lot,
                "Underlying": underlying,
                "Expiry": expiry_input,
                "Call 10% OTM Strike": call_strike,
                "Call LTP": call_prem,
                "Call Premium (Lot)": call_prem_total,
                "Put 10% OTM Strike": put_strike,
                "Put LTP": put_prem,
                "Put Premium (Lot)": put_prem_total
            })

        except Exception as e:
            print(f"{name} ({symbol}) - Error fetching data: {e}\n")

    # Save results to CSV
    df = pd.DataFrame(results)
    out_csv = expiry_to_filename(expiry_input)
    df.to_csv(out_csv, index=False)
    print(f"\n✓ Results saved to {out_csv}")

if __name__ == "__main__":
    main()
