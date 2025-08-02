import requests
from bs4 import BeautifulSoup
from utils.fetch_options import *


def get_call_options(symbol):
    url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9"
    }
    session = requests.Session()
    session.headers.update(headers)
    session.get("https://www.nseindia.com")
    response = session.get(url)
    data = response.json()
    calls = [item['CE'] for item in data['records']['data'] if 'CE' in item]
    return [
        f"Strike: {call['strikePrice']}, Premium: {call['lastPrice']}"
        for call in calls[:3]
    ]

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