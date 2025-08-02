import requests
import time

symbol = "PFC"
base_url = "https://www.nseindia.com"
url = f"{base_url}/api/option-chain-equities?symbol={symbol}"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{base_url}/option-chain"
}

session = requests.Session()
session.headers.update(headers)

# Step 1: Establish session
try:
    r1 = session.get(base_url, timeout=10)
    if r1.status_code != 200:
        raise Exception("Failed to connect to NSE homepage.")
    time.sleep(1)

    # Step 2: Get option chain data
    response = session.get(url, timeout=10)
    if response.status_code != 200:
        raise Exception("Failed to get option chain data.")

    try:
        data = response.json()
    except ValueError:
        print("❌ Response content is not valid JSON.")
        print(response.text[:500])  # Debug output
        raise

except Exception as e:
    print(f"❌ Error: {e}")
    exit()

# Step 3: Extract Spot Price
spot_price = float(data['records']['underlyingValue'])
print(f"\n📈 Spot Price of {symbol}: ₹{spot_price:.2f}")

# Step 4: Calculate 10% OTM strike
otm_strike = round(spot_price * 1.10, -1)
print(f"🎯 Target 10% OTM Strike: ₹{otm_strike}")

# Step 5: Find the call option
target_call = None
for item in data['records']['data']:
    ce = item.get('CE')
    if ce and ce['strikePrice'] == otm_strike:
        target_call = ce
        break

# Step 6: Display result
if target_call:
    print("\n✅ 10% OTM Call Option Found:")
    print(f"  • Strike Price: ₹{target_call['strikePrice']}")
    print(f"  • Expiry Date: {target_call['expiryDate']}")
    print(f"  • Premium (LTP): ₹{target_call['lastPrice']}")
    print(f"  • Open Interest: {target_call['openInterest']}")
    print(f"  • IV: {target_call['impliedVolatility']}%")
else:
    print("\n❌ No matching 10% OTM call strike found.")
