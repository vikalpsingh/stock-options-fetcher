import requests
import pandas as pd
import time
import math
import os

# List of your stock symbols
symbols = [
    "PRITI", "MEGA", "PAKKA", "MAXINDIA", "PNBGILTS", "JAYKAY", "PROTEANEGOV",
    "EPACK", "MSTC", "MEDIASSIST", "AWFIS", "E2E", "FIEM", "SHAILYENG", "LATENTVIEW",
    "BANCO", "NAZARA", "CYIENT", "CAPLIPOINT", "OLAELEC", "ZENTECH", "NATCOPHARM",
    "SCHNEIDER", "CAMS", "PGELECTRO", "JYOTICNC", "CDSL", "ASTRAL", "JSWINFRA",
    "HDB", "WAAREE", "INFOEDGE", "HAVELLS", "USL", "TATACONSUM", "MAZDOCK",
    "PFC", "ZOMATO", "TITAN", "NTPC", "BAJAJFIN"
]

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

session = requests.Session()

def fetch_option_chain(symbol):
    url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
    session.get("https://www.nseindia.com", headers=headers)  # To set cookies
    time.sleep(0.5)
    resp = session.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"Failed to fetch option chain for {symbol}")
        return None

def round_to_nearest_strike(price, strike_step=50):
    # Round strike to nearest multiple of strike_step
    return int(math.ceil(price / strike_step) * strike_step)

call_results = []
put_results = []

for symbol in symbols:
    try:
        data = fetch_option_chain(symbol)
        if not data:
            continue

        records = data.get("records", {})
        underlying = records.get("underlyingValue")
        lot_size = records.get("marketLot", 1)
        options = records.get("data", [])
        if underlying is None or not options:
            print(f"No underlying or option data for {symbol}, skipping.")
            continue

        # 10% OTM call: strike price >= underlying * 1.10
        target_call_strike = round_to_nearest_strike(underlying * 1.10)
        # 10% OTM put: strike price <= underlying * 0.90
        target_put_strike = int(underlying * 0.90 // 50 * 50)  # Round down to nearest 50

        # Find closest CE strike >= target_call_strike
        ce_candidates = [opt for opt in options if opt["strikePrice"] >= target_call_strike and "CE" in opt]
        if ce_candidates:
            ce_strike = min(ce_candidates, key=lambda x: x["strikePrice"])
            ce_data = ce_strike.get("CE", {})
            call_results.append({
                "Symbol": symbol,
                "Underlying": underlying,
                "LotSize": lot_size,
                "Strike": ce_strike["strikePrice"],
                "LTP": ce_data.get("lastPrice", 0),
                "OpenInterest": ce_data.get("openInterest", 0),
                "Volume": ce_data.get("totalTradedVolume", 0),
                "PremiumValue": ce_data.get("lastPrice", 0) * lot_size
            })

        # Find closest PE strike <= target_put_strike
        pe_candidates = [opt for opt in options if opt["strikePrice"] <= target_put_strike and "PE" in opt]
        if pe_candidates:
            pe_strike = max(pe_candidates, key=lambda x: x["strikePrice"])
            pe_data = pe_strike.get("PE", {})
            put_results.append({
                "Symbol": symbol,
                "Underlying": underlying,
                "LotSize": lot_size,
                "Strike": pe_strike["strikePrice"],
                "LTP": pe_data.get("lastPrice", 0),
                "OpenInterest": pe_data.get("openInterest", 0),
                "Volume": pe_data.get("totalTradedVolume", 0),
                "PremiumValue": pe_data.get("lastPrice", 0) * lot_size
            })

        time.sleep(0.5)  # polite delay

    except Exception as e:
        print(f"Error processing {symbol}: {e}")

# Create DataFrames
df_calls = pd.DataFrame(call_results)
df_puts = pd.DataFrame(put_results)

# Filter to remove zero premium entries (optional)
df_calls = df_calls[df_calls["PremiumValue"] > 0].sort_values(by="PremiumValue", ascending=False).reset_index(drop=True)
df_puts = df_puts[df_puts["PremiumValue"] > 0].sort_values(by="PremiumValue", ascending=False).reset_index(drop=True)

# Write to Excel with formatting
import xlsxwriter

output_file = "10pct_OTM_calls_and_puts.xlsx"
with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
    # Write Calls
    df_calls.to_excel(writer, index=False, sheet_name='Calls')
    # Write Puts
    df_puts.to_excel(writer, index=False, sheet_name='Puts')

    workbook = writer.book
    for sheet_name in ['Calls', 'Puts']:
        worksheet = writer.sheets[sheet_name]
        df = df_calls if sheet_name == 'Calls' else df_puts

        # Header format
        header_fmt = workbook.add_format({
            'bold': True,
            'bg_color': '#FFFF00',
            'border': 1,
            'align': 'center'
        })
        # Cell format
        cell_fmt = workbook.add_format({
            'border': 1,
            'align': 'center'
        })

        # Format header
        for col_num, value in enumerate(df.columns):
            worksheet.write(0, col_num, value, header_fmt)

        # Format data cells
        for row in range(1, len(df) + 1):
            for col in range(len(df.columns)):
                worksheet.write(row, col, df.iat[row-1, col], cell_fmt)

        # Auto-adjust column widths
        for i, col in enumerate(df.columns):
            max_len = max(
                df[col].astype(str).map(len).max(),
                len(col)
            ) + 2
            worksheet.set_column(i, i, max_len)

print(f"Saved output to {output_file}")
