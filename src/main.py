from nsepython import *
import pandas as pd
from datetime import datetime
import math

# Configuration: Define symbols, lot sizes, and OTM percentage
config = {
    "TATACONSUM": {"lot_size": 550, "otm_percentage": 0.10},  # Tata Consumer
    "PFC": {"lot_size": 1300, "otm_percentage": 0.10},        # Power Finance Corporation
    "ETERNAL": {"lot_size": 2425, "otm_percentage": 0.10},     # Zomato (Eternal Ltd.)
    "RVNL": {"lot_size": 1375, "otm_percentage": 0.10}        # Rail Vikas Nigam Limited
}

# Target expiry date
target_expiry = "28-Aug-2025"

def fetch_option_chain(symbol, lot_size, otm_percentage):
    try:
        # Fetch option chain data
        option_chain_data = nse_optionchain_scrapper(symbol)
        expiry_list = option_chain_data['records']['expiryDates']
        spot_price = option_chain_data['records']['underlyingValue']

        # Select expiry
        expiry = target_expiry if target_expiry in expiry_list else expiry_list[0]
        if expiry != target_expiry:
            print(f"[{symbol}] Target expiry {target_expiry} not found. Using nearest expiry: {expiry}")

        # Filter data for the selected expiry
        data = [row for row in option_chain_data['filtered']['data'] if row['expiryDate'] == expiry]
        if not data:
            print(f"[{symbol}] No data found for expiry {expiry}")
            return None

        # Create DataFrame
        option_chain_df = pd.DataFrame(data)

        # Select relevant columns
        columns = [
            'strikePrice',
            'callOption.lastPrice', 'callOption.openInterest', 'callOption.impliedVolatility',
            'putOption.lastPrice', 'putOption.openInterest', 'putOption.impliedVolatility'
        ]

        # Flatten nested JSON data
        option_chain_df['callOption.lastPrice'] = option_chain_df['CE'].apply(lambda x: x.get('lastPrice', 0))
        option_chain_df['callOption.openInterest'] = option_chain_df['CE'].apply(lambda x: x.get('openInterest', 0))
        option_chain_df['callOption.impliedVolatility'] = option_chain_df['CE'].apply(lambda x: x.get('impliedVolatility', 0))
        option_chain_df['putOption.lastPrice'] = option_chain_df['PE'].apply(lambda x: x.get('lastPrice', 0))
        option_chain_df['putOption.openInterest'] = option_chain_df['PE'].apply(lambda x: x.get('openInterest', 0))
        option_chain_df['putOption.impliedVolatility'] = option_chain_df['PE'].apply(lambda x: x.get('impliedVolatility', 0))

        # Filter relevant columns
        option_chain_df = option_chain_df[columns]

        # Rename columns for clarity
        option_chain_df.columns = [
            'Strike Price', 'Call Last Price', 'Call OI', 'Call IV',
            'Put Last Price', 'Put OI', 'Put IV'
        ]

        # Calculate ~10% OTM call strike
        otm_strike = math.ceil(spot_price * (1 + otm_percentage) / 10) * 10
        filtered_df = option_chain_df[option_chain_df['Strike Price'] == otm_strike]

        if filtered_df.empty:
            print(f"[{symbol}] No data found for ~10% OTM strike ₹{otm_strike}")
            return None

        # Calculate premium per lot
        call_premium = filtered_df['Call Last Price'].iloc[0]
        premium_per_lot = call_premium * lot_size

        return {
            "symbol": symbol,
            "spot_price": spot_price,
            "expiry": expiry,
            "otm_strike": otm_strike,
            "filtered_df": filtered_df,
            "premium_per_lot": premium_per_lot
        }

    except Exception as e:
        print(f"[{symbol}] Error fetching option chain: {e}")
        return None

# Process each symbol
print(f"Fetching Option Chain Data as of {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n")
for symbol, settings in config.items():
    print(f"--- {symbol} ---")
    result = fetch_option_chain(symbol, settings["lot_size"], settings["otm_percentage"])
    if result:
        print(f"Spot Price: ₹{result['spot_price']}")
        print(f"Option Chain for Expiry: {result['expiry']}")
        print(f"Data for ~10% OTM Strike ₹{result['otm_strike']}:")
        print(result['filtered_df'].to_string(index=False))
        print(f"Estimated Premium per Lot: ₹{result['premium_per_lot']:.2f}\n")