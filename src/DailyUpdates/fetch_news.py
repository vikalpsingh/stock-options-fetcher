import yfinance as yf
import requests
from bs4 import BeautifulSoup
from time import sleep

STOCKS = [
    "BAJFINANCE", "TATACONSUM", "PGEL", "TITAN",
    "MCDOWELL-N", "HAVELLS", "NAUKRI", "PFC", "CAMS", "CDSL", "CYIENT", "MAZDOCK"
]

def fetch_yfinance_news(symbol, items=3):
    ticker = yf.Ticker(symbol + ".NS")
    try:
        news_list = ticker.news[:items]
    except Exception as ex:
        print(f"\n{symbol} (Yahoo Finance): Failed to fetch news - {ex}")
        return

    print(f"\n{symbol} (Yahoo Finance):")
    if not news_list:
        print("  No recent news found.")
        return

    for news in news_list:
        if isinstance(news, dict):
            title = news.get('title', 'No Title')
            link = news.get('link', '')
            print(f"  - {title}")
            if link:
                print(f"    {link}")
        else:
            print(f"  Unexpected news format: {news}")

def fetch_business_standard_news(symbol, items=3):
    url = f"https://www.business-standard.com/search?type=all&keyword={symbol}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        items_found = 0
        print(f"\n{symbol} (Business Standard):")
        for li in soup.select(".listing li h2 a"):
            if items_found >= items:
                break
            title = li.get_text(strip=True)
            href = li.get('href', '')
            if title and href:
                print(f"  - {title}")
                print(f"    https://www.business-standard.com{href}")
                items_found += 1
        if items_found == 0:
            print("  No recent news found.")
    except Exception as ex:
        print(f"\n{symbol} (Business Standard): Failed to fetch news - {ex}")

def fetch_economictimes_news(symbol, items=3):
    url = f"https://economictimes.indiatimes.com/topic/{symbol}/news"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        items_found = 0
        print(f"\n{symbol} (Economic Times):")
        for a in soup.select(".eachStory a"):
            if items_found >= items:
                break
            title = a.get_text(strip=True)
            href = a.get('href', '')
            if title and href:
                print(f"  - {title}")
                if href.startswith("http"):
                    link = href
                else:
                    link = f"https://economictimes.indiatimes.com{href}"
                print(f"    {link}")
                items_found += 1
        if items_found == 0:
            print("  No recent news found.")
    except Exception as ex:
        print(f"\n{symbol} (Economic Times): Failed to fetch news - {ex}")

if __name__ == "__main__":
    for sym in STOCKS:
        fetch_yfinance_news(sym)
        sleep(1)
        fetch_business_standard_news(sym)
        sleep(1)
        fetch_economictimes_news(sym)
        sleep(1)
