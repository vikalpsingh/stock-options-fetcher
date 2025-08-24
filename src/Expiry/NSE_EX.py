from nsepython import equity_history
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

# -------- PARAMETERS --------
symbols = ["PFC", "TATACONSUM", "ETERNAL", "RVNL"]  # Your requested stock symbols
series = "EQ"
alpha = 0.8           # Exponential decay factor for weighting recent months
remove_extremes = 1   # Number of top and bottom extreme monthly % changes to remove
years_back = 1        # Number of years history to analyze
output_csv = "stock_predictions.csv"  # Output CSV file if you want to save results
# ----------------------------

# Date range for fetching data
end_date = datetime.today()
start_date = end_date - timedelta(days=365 * years_back)

results = []

for symbol in symbols:
    try:
        # Fetch historical daily data for the symbol
        data = equity_history(symbol, series,
                              start_date.strftime("%d-%m-%Y"),
                              end_date.strftime("%d-%m-%Y"))

        if data is None or data.empty:
            print(f"\nNo data found for {symbol}, skipping...")
            continue

        # Convert date column to year-month period for grouping monthly
        data['YearMonth'] = pd.to_datetime(data['CH_TIMESTAMP']).dt.to_period('M')
        # Group by month and take the last closing price as monthly expiry proxy
        monthly_prices = data.groupby('YearMonth').agg({'CH_CLOSING_PRICE': 'last'}).reset_index()

        # Calculate month-on-month percentage change
        monthly_prices['pct_change'] = monthly_prices['CH_CLOSING_PRICE'].pct_change() * 100
        monthly_prices = monthly_prices.dropna(subset=['pct_change']).reset_index(drop=True)

        if len(monthly_prices) <= 2 * remove_extremes:
            print(f"Not enough data after trimming extremes for {symbol}, skipping...")
            continue

        # Sort by pct_change and remove top and bottom extremes to reduce outlier impact
        sorted_changes = monthly_prices.sort_values('pct_change').reset_index(drop=True)
        truncated_changes = sorted_changes.iloc[remove_extremes:-remove_extremes].reset_index(drop=True)

        # Prepare exponential weights for recent months with decay factor alpha
        n = len(truncated_changes)
        weights = np.array([alpha**(n - 1 - i) for i in range(n)])  # Most recent month weight=1
        weights /= weights.sum()  # Normalize weights to sum to 1

        # Calculate weighted mean monthly % change
        mean_change_weighted = np.sum(weights * truncated_changes['pct_change'])

        # Calculate weighted probabilities of increase and decrease
        weighted_positive = np.sum(w for w, chg in zip(weights, truncated_changes['pct_change']) if chg > 0)
        weighted_negative = np.sum(w for w, chg in zip(weights, truncated_changes['pct_change']) if chg < 0)
        total_weight = weighted_positive + weighted_negative

        prob_increase_weighted = weighted_positive / total_weight if total_weight else 0
        prob_decrease_weighted = weighted_negative / total_weight if total_weight else 0

        # Maximum upside and downside after removing extremes
        max_upside = truncated_changes.loc[truncated_changes['pct_change'] > 0, 'pct_change'].max()
        max_downside = truncated_changes.loc[truncated_changes['pct_change'] < 0, 'pct_change'].min()

        # Determine predicted direction based on max probability
        direction = "Increase" if prob_increase_weighted > prob_decrease_weighted else "Decrease"
        max_prob = max(prob_increase_weighted, prob_decrease_weighted)

        # Append results for each symbol
        results.append({
            "Symbol": symbol,
            "Data Start": start_date.date(),
            "Data End": end_date.date(),
            "Probability Increase": prob_increase_weighted,
            "Probability Decrease": prob_decrease_weighted,
            "Predicted Direction": direction,
            "Probability of Direction": max_prob,
            "Predicted % Change": mean_change_weighted,
            "Max Upside (trimmed)": max_upside,
            "Max Downside (trimmed)": max_downside
        })

        print(f"\n--- {symbol} Prediction (Outliers Removed) ---")
        print(f"Data period: {start_date.date()} to {end_date.date()}")
        print(f"Probability of Increase: {prob_increase_weighted:.2%}")
        print(f"Probability of Decrease: {prob_decrease_weighted:.2%}")
        print(f"Predicted Direction: {direction} (Probability: {max_prob:.2%})")
        print(f"Predicted % Change (Weighted Mean): {mean_change_weighted:.2f}%")
        print(f"Max Upside (trimmed): {max_upside:.2f}%")
        print(f"Max Downside (trimmed): {max_downside:.2f}%")

    except Exception as e:
        print(f"\nError processing {symbol}: {e}")

# Optional: save results to CSV
if results:
    df_results = pd.DataFrame(results)
    df_results.to_csv(output_csv, index=False)
    print(f"\nAll predictions saved to {output_csv}")
else:
    print("\nNo predictions to save.")
