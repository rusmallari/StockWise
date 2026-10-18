import os
import sqlite3
from datetime import date
from services import stocks_data

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "stockwise.db")
# When the user asks for semi-reliable stocks from companies, the model can just look
# through this candidates list so it doesn't recompute a large amount of data
CANDIDATES = [
    ("SPY",  "S&P 500 index ETF"),
    ("VTI",  "Total US stock market ETF"),
    ("BND",  "US bond market ETF"),
    ("SCHD", "Dividend stock ETF"),
    ("AAPL", "Technology"),
    ("MSFT", "Technology"),
    ("NVDA", "Semiconductors"),
    ("JNJ",  "Healthcare"),
    ("PG",   "Consumer staples"),
    ("KO",   "Consumer staples"),
    ("JPM",  "Banking"),
    ("XOM",  "Energy"),
]


def build_budget_context(user_id):
    # find the current month
    month_prefix = date.today().strftime("%Y-%m")
    month_label = date.today().strftime("%B %Y")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # get all the categories and the monthly budget limit for each
    categories = conn.execute(
        "SELECT name, monthly_limit FROM categories WHERE user_id = ?", (
            user_id,)
    ).fetchall()

    # get the sum of spending for each category from the transactions table that matches the current
    # month
    spending_rows = conn.execute(
        """
        SELECT category, SUM(amount) AS spent
        FROM transactions
        WHERE user_id = ? and DATE LIKE ?
        GROUP BY category
        """, (user_id, month_prefix + "%")
    ).fetchall()

    conn.close()

    spent_by_category = {}
    for row in spending_rows:
        spent_by_category[row["category"]] = row["spent"]

    # build the budget context for the model to use -- how much we have spent, the budget limit
    # and the amount remaining
    lines = [f"Budget for {month_label} (spent/ limit / remaining):"]
    total_left = 0

    for category in categories:
        limit = category["monthly_limit"] or 0
        if limit <= 0:
            continue
        spent = spent_by_category.get(category["name"], 0)
        remaining = limit - spent

        if remaining >= 0:
            lines.append(
                f"- {category['name']}: ${spent:.2f} / ${limit:.2f} / ${remaining:.2f} left")
            total_left += remaining
        else:
            lines.append(
                f"- {category['name']}: ${spent:.2f} / ${limit:.2f} / ${abs(remaining):.2f} over")
    if len(lines) == 1:
        return "User has not set any budget limits yet."
    lines.append(f"Total unspent budget this month: ${total_left:.2f}")
    return "\n".join(lines)


def build_stock_context():
    lines = [
        "Investment options in StockWise (1-year return, volatility, risk):"]
    for symbol, description in CANDIDATES:
        standing = stocks_data.get_roi_and_risk(symbol)
        if standing is None:
            continue

        roi = standing["roi"] * 100
        volatility = standing["volatility"] * 100
        risk = standing["risk"]

        line = (f"- {symbol} ({description}): {roi:+.1f}% return, "
                f"{volatility:.1f}% volatility, {risk} risk")
        lines.append(line)
    if len(lines) == 1:
        return "Stock data isn't available right now"
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_budget_context(2))
