import requests


def get_call_options(symbol):
    url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        session = requests.Session()
        session.headers.update(headers)
        session.get("https://www.nseindia.com", timeout=5)
        response = session.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        calls = [item["CE"] for item in data["records"]["data"] if "CE" in item]
        return [
            f"Strike: {call['strikePrice']}, Premium: {call['lastPrice']}"
            for call in calls[:3]
        ]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching call options for {symbol}: {e}")
        return []

def main():
    stock_symbol = input("Enter the stock symbol: ")
    call_options = get_call_options(stock_symbol)
    
    if call_options:
        print(f"Call options for {stock_symbol}:")
        for option in call_options:
            print(option)
    else:
        print(f"No call options found for {stock_symbol}.")

if __name__ == "__main__":
    main()
