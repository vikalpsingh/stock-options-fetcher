from nsepython import *
import pandas as pd
from datetime import datetime

# Define the symbol
symbol = "PFC"

# Fetch the option chain data
try:
    option_chain_data = nse_optionchain_scrapper(symbol)
except Exception as e:
    print(f"Error fetching option chain: {e}")
    exit()

# Extract expiry dates and select the nearest or specific expiry
expiry_list = option_chain_data['records']['expiryDates']
# Optionally, specify a particular expiry (e.g., "28-Aug-2025")
target_expiry = "28-Aug-2025"  # Adjust based on your needs
if target_expiry in expiry_list:
    latest_expiry = target_expiry
else:
    latest_expiry = expiry_list[0]  # Fallback to nearest expiry
    print(f"Target expiry {target_expiry} not found. Using nearest expiry: {latest_expiry}")

# Filter data for the selected expiry
data = [row for row in option_chain_data['filtered']['data'] if row['expiryDate'] == latest_expiry]
spot_price = option_chain_data['records']['underlyingValue']

# Create a DataFrame
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
    'Strike Price', 
    'Call Last Price', 'Call OI', 'Call IV',
    'Put Last Price', 'Put OI', 'Put IV'
]

# Filter for ~10% OTM call (₹450 strike)
otm_strike = 450
filtered_df = option_chain_df[option_chain_df['Strike Price'] == otm_strike]

# Display results
print(f"PFC Option Chain for Expiry: {latest_expiry}")
print(f"Spot Price: ₹{spot_price}")
print("\nOption Chain Data for Strike ₹450:")
print(filtered_df)

# Calculate premium per lot for ₹450 CE
if not filtered_df.empty:
    call_premium = filtered_df['Call Last Price'].iloc[0]
    lot_size = 1300  # As per your provided data
    premium_per_lot = call_premium * lot_size
    print(f"\nEstimated Premium per Lot for ₹450 CE: ₹{premium_per_lot:.2f}")
else:
    print(f"No data found for strike ₹450 in expiry {latest_expiry}")