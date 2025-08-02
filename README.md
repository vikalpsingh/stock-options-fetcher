# Stock Options Fetcher

This project is designed to fetch and display call option data for a specified stock symbol using Python. It utilizes the `requests` library to make HTTP requests and `BeautifulSoup` for parsing HTML data.

## Project Structure

```
stock-options-fetcher
├── src
│   ├── main.py          # Entry point of the application
│   └── utils
│       └── fetch_options.py  # Utility functions for fetching option data
├── requirements.txt     # Project dependencies
└── README.md            # Project documentation
```

## Requirements

To run this project, you need to install the following dependencies:

- `requests`
- `beautifulsoup4`

You can install the required packages using pip:

```
pip install -r requirements.txt
```

## Usage

1. Clone the repository or download the project files.
2. Navigate to the project directory.
3. Run the main application:

```
python src/main.py
```

4. Follow the prompts to enter a stock symbol and view the call option data.

## Contributing

If you would like to contribute to this project, please feel free to submit a pull request or open an issue for discussion.

## License

This project is open-source and available under the MIT License.