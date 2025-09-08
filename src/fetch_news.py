from datetime import datetime, timezone
from typing import List

import yfinance as yf

STOCKS: List[str] = [
    "BAJFINANCE",
    "TATACONSUM",
    "PGEL",
    "TITAN",
    "ETERNAL",  # TODO: verify correct ticker symbol
    "MCDOWELL-N",
    "HAVELLS",
    "NAUKRI",
    "PFC",
    "CAMS",
    "CDSL",
    "CYIENT",
    "MAZDOCK",
]


def fetch_news(symbol: str, items: int = 3) -> None:
    """Fetch and print recent news for a given stock symbol."""
    ticker = yf.Ticker(symbol + ".NS")

    try:
        info = ticker.info
        sector = info.get("sector", "Unknown")
    except Exception:
        sector = "Unknown"

    print(f"{symbol} (Sector: {sector})")

    try:
        news_list = ticker.news[:items]
    except Exception as exc:
        print(f"  Failed to load news: {exc}")
        print()
        return

    if not news_list:
        print("  No recent news found.\n")
        return

    for item in news_list:
        publish_time = datetime.fromtimestamp(
            item.get("providerPublishTime", 0), tz=timezone.utc
        )
        time_str = publish_time.strftime("%Y-%m-%d %H:%M UTC")
        title = item.get("title", "No title")
        provider = item.get("provider", "")
        link = item.get("link", "")
        print(f"  - {time_str} | {title} ({provider})")
        if link:
            print(f"    {link}")
    print()


if __name__ == "__main__":
    for sym in STOCKS:
        fetch_news(sym)
