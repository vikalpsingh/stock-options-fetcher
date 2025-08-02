def fetch_call_options(stock_symbol):
    import requests
    from bs4 import BeautifulSoup

    url = f"https://finance.yahoo.com/quote/{stock_symbol}/options"
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch data for {stock_symbol}: {response.status_code}")

    soup = BeautifulSoup(response.text, 'html.parser')
    options_table = soup.find('table', {'class': 'calls'})
    
    if not options_table:
        raise Exception(f"No call options data found for {stock_symbol}")

    call_options = []
    rows = options_table.find_all('tr')[1:]  # Skip header row

    for row in rows:
        cols = row.find_all('td')
        if len(cols) > 0:
            option_data = {
                'strike': cols[2].text,
                'last_price': cols[3].text,
                'bid': cols[4].text,
                'ask': cols[5].text,
                'volume': cols[6].text,
                'open_interest': cols[7].text,
                'expiration': cols[1].text
            }
            call_options.append(option_data)

    return call_options