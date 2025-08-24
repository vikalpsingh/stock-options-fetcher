from nsepython import equity_history
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# -------- PARAMETERS --------
symbols = ["PFC", "TATACONSUM", "ETERNAL", "RVNL"]
series = "EQ"
alpha = 0.85             # Decay factor for exponential weights
months_back = 24
weight_scheme = "exp"
output_dir = "analysis_outputs"
iqr_k = 1.5
output_excel = "stock_predictions_24m.xlsx"
# ----------------------------

os.makedirs(output_dir, exist_ok=True)
end_date = datetime.today()
start_date = end_date - pd.DateOffset(months=months_back)
results = []

def remove_outliers_iqr(data, column, k=1.5):
    q1 = data[column].quantile(0.25)
    q3 = data[column].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - k * iqr
    upper = q3 + k * iqr
    return data[(data[column] >= lower) & (data[column] <= upper)].reset_index(drop=True)

def autosize_columns(df, worksheet):
    for i, col in enumerate(df.columns):
        max_len = max(df[col].astype(str).apply(len).max(), len(str(col))) + 2
        worksheet.set_column(i, i, max_len)

def write_excel(df, path):
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Predictions")
        workbook = writer.book
        worksheet = writer.sheets["Predictions"]

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

        # Format header cells
        for col_num, col_name in enumerate(df.columns.values):
            worksheet.write(0, col_num, col_name, header_format)
        # Format data cells with border and center alignment
        for row in range(1, len(df) + 1):
            for col in range(len(df.columns)):
                worksheet.write(row, col, df.iat[row - 1, col], cell_format)
        # Auto-adjust columns
        autosize_columns(df, worksheet)

for symbol in symbols:
    try:
        data = equity_history(
            symbol, series,
            start_date.strftime("%d-%m-%Y"),
            end_date.strftime("%d-%m-%Y")
        )
        if data is None or data.empty:
            print(f"\nNo data found for {symbol}, skipping...")
            continue
        
        data["YearMonth"] = pd.to_datetime(data["CH_TIMESTAMP"]).dt.to_period("M")
        data["log_return"] = np.log(data["CH_CLOSING_PRICE"] / data["CH_CLOSING_PRICE"].shift(1))

        monthly = data.groupby("YearMonth").agg(
            close=("CH_CLOSING_PRICE", "last"),
            vol=("log_return", lambda x: np.std(x.dropna(), ddof=1) * np.sqrt(21))
        ).reset_index()

        monthly["pct_change"] = monthly["close"].pct_change() * 100
        monthly.dropna(subset=["pct_change"], inplace=True)
        monthly.reset_index(drop=True, inplace=True)

        data_trimmed = remove_outliers_iqr(monthly, "pct_change", k=iqr_k)
        if len(data_trimmed) < 3:
            print(f"Not enough data after outlier removal for {symbol}, skipping...")
            continue

        n = len(data_trimmed)
        if weight_scheme == "exp":
            weights = np.array([alpha**(n-1-i) for i in range(n)])
        else:
            weights = np.ones(n)
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

        results.append({
            "Symbol": symbol,
            "Data Start": start_date.date(),
            "Data End": end_date.date(),
            "Probability Increase": prob_increase,
            "Probability Decrease": prob_decrease,
            "Predicted Direction": direction,
            "Probability of Direction": max_prob,
            "Predicted % Change": weighted_pct_change,
            "Weighted Volatility (Monthly %)": weighted_vol * 100,
            "Last Month Vol (%)": last_vol * 100,
            "Max Upside (trimmed)": max_upside,
            "Max Downside (trimmed)": max_downside,
            "Samples": n
        })

        print(f"\n--- {symbol} 24-Month Prediction ---")
        print(f"Period: {start_date.date()} to {end_date.date()} | Samples: {n}")
        print(f"Probability Increase: {prob_increase:.2%} | Decrease: {prob_decrease:.2%}")
        print(f"Predicted Direction: {direction} ({max_prob:.2%})")
        print(f"Predicted Mean % Change: {weighted_pct_change:.2f}%")
        print(f"Weighted Volatility: {weighted_vol * 100:.2f}% | Last Month Vol: {last_vol * 100:.2f}%")
        print(f"Max Upside: {max_upside:.2f}% | Max Downside: {max_downside:.2f}%")

    except Exception as e:
        print(f"\nError processing {symbol}: {e}")

if results:
    df_results = pd.DataFrame(results)
    excel_path = os.path.join(output_dir, output_excel)
    write_excel(df_results, excel_path)
    print(f"\nAll 24-month predictions saved to {excel_path}")
else:
    print("\nNo predictions to save.")
