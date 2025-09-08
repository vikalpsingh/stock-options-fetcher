import requests
import time
import pandas as pd
import numpy as np
from datetime import datetime
import os
from nsepython import equity_history

# -------- PARAMETERS --------
shares = [
    ("PGEL", "PG Electroplast Ltd", 700),
    ("ETERNAL", "Eternal Ltd", 2450),
    ("BAJFINANCE", "Bajaj Finance Ltd", 750),
    ("UNITDSPR", "United Spirits Ltd", 375),
    ("PFC", "Power Finance Corporation Ltd", 1300),
    ("MAZDOCK", "Mazagon Dock Shipbuilders Ltd", 175),
    ("TATACONSUM", "Tata Consumer Products Ltd", 550),
    ("TITAN", "Titan", 350),
    ("NTPC", "NTPC Ltd", 1500),
    ("NAUKRI", "Info edge", 375),
    ("HAVELLS", "HAVELLS Ltd ", 500),
    ("CYIENT", "CYIENT Ltd ", 425)
]

series = "EQ"
alpha = 0.85
months_back = 24
weight_scheme = "exp"
iqr_k = 1.5
expiry_input = "30-Sep-2025"
output_dir = "analysis_outputs"
output_excel = "merged_option_direction_output.xlsx"

os.makedirs(output_dir, exist_ok=True)
end_date = datetime.today()
start_date = end_date - pd.DateOffset(months=months_back)

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

    call_premium = put_premium = call_premium_total = put_premium_total = None

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

def remove_outliers_iqr(data, column, k=1.5):
    q1 = data[column].quantile(0.25)
    q3 = data[column].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - k * iqr
    upper = q3 + k * iqr
    return data[(data[column] >= lower) & (data[column] <= upper)].reset_index(drop=True)

def write_excel(df, path):
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="MergedOutput")
        workbook = writer.book
        worksheet = writer.sheets["MergedOutput"]
        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#FFFF00",
            "border": 1,
            "align": "center"
        })
        cell_format = workbook.add_format({
            "border": 1,
            "align": "center"
        })
        # Format header row
        for col_num, col_name in enumerate(df.columns.values):
            worksheet.write(0, col_num, col_name, header_format)
        # Format data cells
        for row in range(1, len(df) + 1):
            for col in range(len(df.columns)):
                worksheet.write(row, col, df.iat[row - 1, col], cell_format)
        # Auto-adjust column widths
        for i, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).apply(len).max(), len(str(col))) + 2
            worksheet.set_column(i, i, max_len)

results = []

for symbol, name, lot in shares:
    try:
        # Direction/probability analysis
        data_hist = equity_history(
            symbol, series,
            start_date.strftime("%d-%m-%Y"),
            end_date.strftime("%d-%m-%Y")
        )
        if data_hist is None or data_hist.empty:
            print(f"\nNo historical data for {symbol}, skipping...")
            continue

        data_hist["YearMonth"] = pd.to_datetime(data_hist["CH_TIMESTAMP"]).dt.to_period("M")
        data_hist["log_return"] = np.log(data_hist["CH_CLOSING_PRICE"] / data_hist["CH_CLOSING_PRICE"].shift(1))

        monthly = data_hist.groupby("YearMonth").agg(
            close=("CH_CLOSING_PRICE", "last"),
            vol=("log_return", lambda x: np.std(x.dropna(), ddof=1) * np.sqrt(21))
        ).reset_index()
        monthly["pct_change"] = monthly["close"].pct_change() * 100
        monthly.dropna(subset=["pct_change"], inplace=True)
        monthly.reset_index(drop=True, inplace=True)
        data_trimmed = remove_outliers_iqr(monthly, "pct_change", k=iqr_k)
        if len(data_trimmed) < 3:
            print(f"Not enough historical data after outlier removal for {symbol}, skipping...")
            continue

        n = len(data_trimmed)
        weights = np.array([alpha**(n-1-i) for i in range(n)])
        weights /= weights.sum()

        weighted_pct_change = np.sum(weights * data_trimmed["pct_change"])
        weighted_vol = np.sum(weights * data_trimmed["vol"])
        weighted_positive = np.sum(w for w, chg in zip(weights, data_trimmed["pct_change"]) if chg > 0)
        weighted_negative = np.sum(w for w, chg in zip(weights, data_trimmed["pct_change"]) if chg < 0)
        total_weight = weighted_positive + weighted_negative

        prob_increase = weighted_positive / total_weight if total_weight else 0
        prob_decrease = weighted_negative / total_weight if total_weight else 0

        max_upside = data_trimmed.loc[data_trimmed["pct_change"] > 0, "pct_change"].max()
        max_downside = data_trimmed.loc[data_trimmed["pct_change"] < 0, "pct_change"].min()
        direction = "Increase" if prob_increase > prob_decrease else "Decrease"
        max_prob = max(prob_increase, prob_decrease)
        last_vol = data_trimmed["vol"].iloc[-1]

        # Option chain analysis for this expiry
        option_data = fetch_option_chain(symbol)
        if not option_data:
            print(f"No option chain data for {symbol}, skipping options part.")
            results.append({
                "Symbol": symbol,
                "Name": name,
                "Lot Size": lot,
                "Underlying": None,
                "Expiry": expiry_input,
                "Direction": direction,
                "Probability of Direction": max_prob,
                "Predicted % Change": weighted_pct_change,
                "Weighted Volatility (Monthly %)": weighted_vol * 100,
                "Max Upside (trimmed)": max_upside,
                "Max Downside (trimmed)": max_downside,
                "10% OTM Call Premium": None,
                "10% OTM Put Premium": None,
                "Premium Type": None
            })
            continue

        records = option_data.get("records", {})
        underlying = records.get("underlyingValue")

        # Get both premiums
        call_strike, call_prem, call_prem_total, put_strike, put_prem, put_prem_total = get_otm_option_premiums(
            records, underlying, expiry_input, lot
        )

        # Pick premium depending on predicted direction
        if direction == "Increase":
            show_premium = call_prem_total if call_prem_total else None
            premium_type = "CALL"
        else:
            show_premium = put_prem_total if put_prem_total else None
            premium_type = "PUT"

        results.append({
            "Symbol": symbol,
            "Name": name,
            "Lot Size": lot,
            "Underlying": underlying,
            "Expiry": expiry_input,
            "Direction": direction,
            "Probability of Direction": max_prob,
            "Predicted % Change": weighted_pct_change,
            "Weighted Volatility (Monthly %)": weighted_vol * 100,
            "Max Upside (trimmed)": max_upside,
            "Max Downside (trimmed)": max_downside,
            "10% OTM Call Premium": call_prem_total,
            "10% OTM Put Premium": put_prem_total,
            "Premium Type": premium_type,
            "Chosen Premium": show_premium
        })

    except Exception as e:
        print(f"{name} ({symbol}) - Error: {e}")

# Output to Excel
df = pd.DataFrame(results)
excel_path = os.path.join(output_dir, output_excel)
write_excel(df, excel_path)
print(f"\n✓ Merged output saved to {excel_path}")
