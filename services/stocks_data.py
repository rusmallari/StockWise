"""This file contains the function definitions for interacting with yfinance
   to get the data from Yahoo Finance. These functions are going to be called
   from other files in the project, hence this file is in the 'services' folder."""

import os               # db path routing
import yfinance as yf   # where all the stock data is coming from -- Yahoo Finance
import statistics       # calculate stdev to find volatility
import math             # for sqrt(252) --> number of trading days in a year
import sqlite3          # the db
import json             # used to turn some results into text
import time             # used to calculate the current time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "stockwise.db")
SCREENS = {"gainers": "day_gainers",
           "losers": "day_losers", "most_active": "most_actives"}
VALID_TIME_LEFT_SEARCH = 24 * 3600
VALID_TIME_LEFT_PROFILE = 24 * 3600
VALID_TIME_LEFT_HISTORY = 12 * 3600
VALID_TIME_LEFT_GAINERS_LOSERS = 15 * 60

# this is to return a result when the user searches for company stocks such as "apple",
# which would be the query parameter


def _search(query: str) -> list:

    filtered = []
    try:
        # returns a list of dictionaries
        matches = yf.Search(query, max_results=20).quotes
    except Exception:
        return None

    # for every dictionary in the list, build a new dictionary only for the ones that have
    # an equity quotetype; insert the name, symbol, and the exchange name into the new dictionary
    # and add it to the filtered list
    for match in matches:
        if match.get("quoteType") == "EQUITY" and "." not in match.get("symbol", ""):
            each_item = {}
            each_item["symbol"] = match.get("symbol")
            each_item["name"] = match.get("longname") or match.get(
                "shortname") or match.get("symbol")
            each_item["exchange"] = match.get(
                "exchDisp") or match.get("exchange")
            filtered.append(each_item)

    return filtered


# gets the company profile information when the user searches for a company
# ticker example --> "AAPL" --> for Apple
def _get_company_profile(ticker: str):
    try:
        # returns a large dictionary of info about the company
        info = yf.Ticker(ticker).info
    except Exception:
        return None

    # if the company's info doesn't have a name return none
    if not (info.get("longName") or info.get("shortName")):
        return None

    # otherwise, create and return a dictionary of part the company's information
    # that we care about
    return {
        "symbol": ticker,
        "name": info.get("longName") or info.get("shortName"),
        "description": info.get("longBusinessSummary"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "website": info.get("website"),
        "market_cap": info.get("marketCap"),
        "beta": info.get("beta"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow")
    }


# gets the one year history of a company's stock daily closing prices
# ticker example --> "AAPL" --> for Apple
def _get_history(ticker: str):
    try:
        # returns a dataFrame, one row per trading day
        history = yf.Ticker(ticker).history(period="1y")
    except Exception:
        return None
    # if the table is empty return none
    if history.empty:
        return None

    # make a list of dates in the table in the form of YYYY-MM-DD
    dates = []
    for date in history.index:
        dates.append(date.strftime("%Y-%m-%d"))

    # make a list where each item is the closing value of the stock for each day
    closes = []
    for close in history["Close"]:
        number = float(close)
        closes.append(round(number, 2))

    # return a dictionary of the company's ID ("symbol"), the list of dates, and the
    # corresponding list of closes
    return {
        "symbol": ticker,
        "dates": dates,
        "closes": closes
    }


# Get roi and risk calls get_history first to get the history of the company's stocks. It returns
# a dictionary of dates and their respective closes.
# ROI: the percent change of a company's stock over 1 year
# Risk: find out how steadily or sharply the company's stock change over the past year
def get_roi_and_risk(ticker):

    # call get_history for the company (ticker) to get the dates and closes
    history = get_history(ticker)
    if not history:
        return None

    # if there are less than 30 prices for a stock, then the numbers won't mean too much,
    # meaning we can't really tell yet.
    closes = history["closes"]
    if len(closes) < 30:
        return None

    roi = (closes[-1] / closes[0]) - 1      # find the roi from the entire year

    # find the daily return percent for a stock which is a percent of how the stock
    # changed each day
    daily_returns = []
    for i in range(1, len(closes)):
        each_day_return_percent = (closes[i] / closes[i - 1]) - 1
        daily_returns.append(each_day_return_percent)

    # By the rules of finance, take the standard deviation of the daily returns to get
    # the daily volatility and then multiply by sqrt(252) to get annual volatility
    volatility = statistics.stdev(daily_returns)
    annual_volatility = volatility * math.sqrt(252)

    # Classify the risk based on very loose criteria (not official)
    if annual_volatility < 0.20:
        risk_label = "Low"
    elif annual_volatility < 0.40:
        risk_label = "Medium"
    else:
        risk_label = "High"

    # return a dictionary of the company's symbol, roi, volatility, and risk label
    return {
        "symbol": history["symbol"],
        "roi": round(roi, 4),
        "volatility": round(annual_volatility, 4),
        "risk": risk_label
    }

# this function is to figure out the most gainers, losers, and mostactives list
# the kind parameter is going to be picked by the user like "gainers" or "losers"


def _gainers_losers_mostactive(kind):
    try:
        # returns a list of dictionaries
        screen = yf.screen(SCREENS[kind])["quotes"]
    except Exception:
        return None

    needed = []
    # for every dictionary (stock) that yfinance returns, we build a dictionary with the company's
    # name, symbol, price, change as a percent, and volume; and then add it to the needed list
    # and return
    for stock in screen:
        each_item = {}
        each_item["symbol"] = stock.get("symbol")
        each_item["name"] = stock.get("longName") or stock.get(
            "shortName") or stock.get("symbol")
        each_item["price"] = stock.get("regularMarketPrice")
        each_item["change_percent"] = stock.get("regularMarketChangePercent")
        each_item["volume"] = stock.get("regularMarketVolume")
        needed.append(each_item)

    return needed


# Cache implementation
# key     = the key needed for the DB lookup which is the company's symbol, Ex: "AAPL" for Apple
# max_age = a hardcoded unofficial value of the maximum amount of time that the data for a
#           compnany can be in the DB before we overwrite it
# fetch   = an alias for the function that we call if there is no row that exists for that key or
#           if the data for that key has already lived in the DB passed the max_age parameter

# this function is called everytime one of the main functions is called like get_history() so
# that way we can check if the database has the information first before we go through the process
# of recomputing the same thing

def cached(key, max_age, fetch):

    conn = get_cache_db()
    try:
        row = conn.execute(
            "SELECT data, fetched_at FROM stock_cache WHERE key = ?", (key, )).fetchone()
        if row:
            entry_age = time.time() - row["fetched_at"]
            if entry_age < max_age:
                return json.loads(row["data"])

        data = fetch()

        if data is None:
            return None
        else:
            conn.execute(
                "INSERT OR REPLACE INTO stock_cache (key, data, fetched_at) VALUES (?, ?, ?)",
                (key, json.dumps(data), time.time())
            )
        conn.commit()
        return data
    finally:
        conn.close()

# this is called by the cached() function which just establishes the connection to the database
# and creates the stock_cache table if it doesn't already exist


def get_cache_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS stock_cache (
            key TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            fetched_at REAL NOT NULL
        );
        """
    )
    conn.commit()
    return conn


# these are the functions that are called when the user interacts with the app. Each function
# gets the ticker (symbol) of the selected company and gets rid of any whitespace and makes
# it uppercase. Each function defines its own fetch() function that calls the actual function
# that gets the data internally. Each function calls the cached() function first to see if the
# data is already in the database or if the data is still valid. If not, then it calls its own
# fetch() function to get the new data.
def get_history(ticker: str):
    usable = ticker.strip().upper()

    def fetch():
        return _get_history(usable)

    return cached(f"history:{usable}", VALID_TIME_LEFT_HISTORY, fetch)


def get_company_profile(ticker: str):
    usable = ticker.strip().upper()

    def fetch():
        return _get_company_profile(usable)

    return cached(f"profile:{usable}", VALID_TIME_LEFT_PROFILE, fetch)


def get_search(query: str):
    ready = query.strip()
    if not ready:
        return []

    def fetch():
        return _search(ready)
    return cached(f"search:{ready.lower()}", VALID_TIME_LEFT_SEARCH, fetch)


def gainers_losers_mostactive(kind: str, limit=10):
    if kind not in SCREENS:
        return None

    def fetch():
        return _gainers_losers_mostactive(kind)

    result = cached(f"movers:{kind}", VALID_TIME_LEFT_GAINERS_LOSERS, fetch)
    if result is None:
        return None
    else:
        return result[:limit]


if __name__ == "__main__":

    # start = time.time()
    # get_history("aapl")
    # print("1st call:", round(time.time() - start, 2), "sec")
    # start = time.time()
    # get_history("aapl")
    # print("2nd call:", round(time.time() - start, 2), "sec")
    get_history("aapl")
