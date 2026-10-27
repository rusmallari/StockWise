import os
import sqlite3
import secrets
import hmac
from datetime import datetime, date, timezone
from collections import defaultdict
from services import stocks_data, ai, user_context
from services import nyt_articles
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g, abort
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "stockwise.db")

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

DEFAULT_CATEGORIES = ["Food", "Transportation",
                      "Entertainment", "Bills", "Housing", "Other"]

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            monthly_limit REAL DEFAULT 0,
            UNIQUE(user_id, name),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )
    # Additive, repeatable migration preserves existing accounts and finance data.
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(users)')}
    for name, definition in {
        'theme': "TEXT NOT NULL DEFAULT 'dark' CHECK(theme IN ('dark', 'light'))",
        'assistant_enabled': 'INTEGER NOT NULL DEFAULT 1 CHECK(assistant_enabled IN (0, 1))',
        'notifications_enabled': 'INTEGER NOT NULL DEFAULT 1 CHECK(notifications_enabled IN (0, 1))',
    }.items():
        if name not in columns:
            conn.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
    conn.commit()
    conn.close()


def seed_default_categories(user_id):
    conn = get_db()
    for cat in DEFAULT_CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO categories (user_id, name, monthly_limit) VALUES (?, ?, 0)",
            (user_id, cat),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(func):
    from functools import wraps

    @wraps(func)
    def check_login(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return check_login


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

def csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


@app.before_request
def load_user_and_protect_requests():
    g.user = None
    if session.get('user_id'):
        conn = get_db()
        g.user = conn.execute('SELECT * FROM users WHERE id = ?',
                              (session['user_id'],)).fetchone()
        conn.close()
        if g.user is None:
            session.clear()
        else:
            session['username'] = g.user['username']
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token', '')
        expected = session.get('_csrf_token', '')
        if not expected or not hmac.compare_digest(expected.encode('utf-8'), token.encode('utf-8')):
            if request.is_json:
                return jsonify(error='Session expired. Refresh the page and try again.'), 400
            abort(400, description='Invalid CSRF token. Refresh the page and try again.')


@app.context_processor
def shared_settings():
    return {'current_user': g.user, 'csrf_token': csrf_token}


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def user_settings():
    if request.method == 'POST':
        section = request.form.get('section')
        conn = get_db()
        try:
            if section == 'profile':
                username = request.form.get('username', '').strip()
                if not username or len(username) > 80 or any(not c.isprintable() for c in username):
                    flash('Username must contain 1–80 printable characters.', 'error')
                    return redirect(url_for('user_settings'))
                current_password = request.form.get('current_password', '')
                new_password = request.form.get('new_password', '')
                confirm_password = request.form.get('confirm_password', '')
                if current_password or new_password or confirm_password:
                    if not current_password or not new_password or not confirm_password:
                        flash('To change your password, fill in all three password fields.', 'error')
                        return redirect(url_for('user_settings'))
                    if not check_password_hash(g.user['password_hash'], current_password):
                        flash('Current password is incorrect.', 'error')
                        return redirect(url_for('user_settings'))
                    if new_password != confirm_password:
                        flash('New passwords do not match.', 'error')
                        return redirect(url_for('user_settings'))
                    conn.execute('UPDATE users SET username = ?, password_hash = ? WHERE id = ?',
                                 (username, generate_password_hash(new_password), session['user_id']))
                else:
                    conn.execute('UPDATE users SET username = ? WHERE id = ?',
                                 (username, session['user_id']))
            elif section == 'preferences':
                theme = request.form.get('theme', 'dark')
                assistant = request.form.get('assistant_enabled', '0')
                notifications = request.form.get('notifications_enabled', '0')
                if theme not in ('dark', 'light') or assistant not in ('0', '1') or notifications not in ('0', '1'):
                    abort(400, description='Invalid preference value.')
                conn.execute('UPDATE users SET theme = ?, assistant_enabled = ?, notifications_enabled = ? WHERE id = ?',
                             (theme, int(assistant), int(notifications), session['user_id']))
            else:
                abort(400, description='Invalid settings section.')
            conn.commit()
            flash('Changes saved successfully.', 'success')
        except sqlite3.IntegrityError:
            conn.rollback()
            flash('That username is already taken.', 'error')
        finally:
            conn.close()
        return redirect(url_for('user_settings'))
    return render_template('user_settings.html')


@app.route("/", methods=["GET"])
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if not username or not password:
            flash("Username and password are required.")
            return redirect(url_for("signup"))

        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            conn.close()
            flash("That username is already taken.")
            return redirect(url_for("signup"))

        cur = conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, generate_password_hash(
                password), datetime.now().isoformat()),
        )
        user_id = cur.lastrowid
        conn.commit()
        conn.close()

        seed_default_categories(user_id)

        session["user_id"] = user_id
        session["username"] = username
        return redirect(url_for("dashboard"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return redirect(url_for("dashboard"))

    return render_template("login.html")

# ---------------------------------------------------------------------------
# Logout Button / return to login page
# ---------------------------------------------------------------------------


@app.route("/logout", methods=['POST'])
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard / transaction history + circle charts
# ---------------------------------------------------------------------------

# DEMO 04 | FR6/FR7 | Flask provides spending and transaction data
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    user_id = session["user_id"]

    transactions = conn.execute(
        "SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC, id DESC",
        (user_id,),
    ).fetchall()

    categories = conn.execute(
        "SELECT * FROM categories WHERE user_id = ? ORDER BY name", (user_id,)
    ).fetchall()
    conn.close()

    # Spending totals by category (all-time) for chart + limit alerts

    # this grabs the current month like 2026-09
    month_prefix = date.today().strftime("%Y-%m")
    # this also grabs the month byt like September 2026
    month_label = date.today().strftime("%B %Y")

    totals_by_category = defaultdict(float)
    for t in transactions:
        if t["date"].startswith(month_prefix):
            totals_by_category[t["category"]] += t["amount"]

    total_spent = sum(totals_by_category.values())

    alerts = []
    for cat in categories:
        limit = cat["monthly_limit"] or 0
        spent = totals_by_category.get(cat["name"], 0)
        if limit > 0 and spent >= limit:
            alerts.append(
                f"You've exceeded your {cat['name']} budget (${spent:.2f} / ${limit:.2f}).")
        elif limit > 0 and spent >= 0.8 * limit:
            alerts.append(
                f"You're close to your {cat['name']} budget (${spent:.2f} / ${limit:.2f}).")

    chart_labels = list(totals_by_category.keys())
    chart_values = [round(v, 2) for v in totals_by_category.values()]

    return render_template(
        "dashboard.html",
        transactions=transactions,
        categories=categories,
        total_spent=round(total_spent, 2),
        month_label=month_label,
        alerts=alerts if g.user['notifications_enabled'] else [],
        chart_labels=chart_labels,
        chart_values=chart_values,
    )


# ---------------------------------------------------------------------------
# Transactions
# This is basically, inputting transaction data like, amount, date posted,
# category
# ---------------------------------------------------------------------------

@app.route("/transactions/add", methods=["GET", "POST"])
@login_required
def add_transaction():
    conn = get_db()
    user_id = session["user_id"]
    categories = conn.execute(
        "SELECT * FROM categories WHERE user_id = ? ORDER BY name", (user_id,)
    ).fetchall()

    if request.method == "POST":
        name = request.form["name"].strip()
        amount = request.form["amount"]
        category = request.form["category"]
        today_date = request.form.get("date") or date.today().isoformat()

        try:
            amount = float(amount)
        except ValueError:
            flash("Amount must be a number.")
            conn.close()
            return redirect(url_for("add_transaction"))

        conn.execute(
            "INSERT INTO transactions (user_id, name, amount, category, date) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, amount, category, today_date),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("add_transaction.html", categories=categories, today=date.today().isoformat())


# edit transaction under tranaction history tab on dashboard.
# This is when user wants to edit their transaction, as well as error handling
# User needs to input a valid response, or it will return an error.


@app.route("/transactions/<int:txn_id>/edit", methods=["GET", "POST"])
@login_required
def edit_transaction(txn_id):
    conn = get_db()
    user_id = session["user_id"]
    txn = conn.execute(
        "SELECT * FROM transactions WHERE id = ? AND user_id = ?", (
            txn_id, user_id)
    ).fetchone()
    if txn is None:
        conn.close()
        flash("Transaction not found.")
        return redirect(url_for("dashboard"))

    categories = conn.execute(
        "SELECT * FROM categories WHERE user_id = ? ORDER BY name", (user_id,)
    ).fetchall()

    if request.method == "POST":
        name = request.form["name"].strip()
        try:
            amount = float(request.form["amount"])
        except ValueError:
            flash("Amount must be a number.")
            conn.close()
            return redirect(url_for("edit_transaction", txn_id=txn_id))
        category = request.form["category"]
        date = request.form.get("date") or txn["date"]

        conn.execute(
            "UPDATE transactions SET name = ?, amount = ?, category = ?, date = ? WHERE id = ? AND user_id = ?",
            (name, amount, category, date, txn_id, user_id),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("edit_transaction.html", txn=txn, categories=categories)

# Under Transaction History you can delete transaction on the dashboard.


@app.route("/transactions/<int:txn_id>/delete", methods=["POST"])
@login_required
def delete_transaction(txn_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM transactions WHERE id = ? AND user_id = ?", (
            txn_id, session["user_id"])
    )
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Budget settings
# ---------------------------------------------------------------------------
# DEMO 02 | FR4/FR5 | Flask saves budget changes to the database
@app.route("/budget-settings", methods=["GET", "POST"])
@login_required
def budget_settings():
    conn = get_db()
    user_id = session["user_id"]

    if request.method == "POST":
        # Update limits for existing categories
        for key, value in request.form.items():
            if key.startswith("limit_"):
                cat_id = key.replace("limit_", "")
                try:
                    limit = float(value) if value.strip() != "" else 0
                except ValueError:
                    limit = 0
                conn.execute(
                    "UPDATE categories SET monthly_limit = ? WHERE id = ? AND user_id = ?",
                    (limit, cat_id, user_id),
                )

        # Optionally add a new custom category
        new_category = request.form.get("new_category", "").strip()
        if new_category:
            new_limit = request.form.get("new_category_limit", "0")
            try:
                new_limit = float(new_limit) if new_limit.strip() != "" else 0
            except ValueError:
                new_limit = 0
            conn.execute(
                "INSERT OR IGNORE INTO categories (user_id, name, monthly_limit) VALUES (?, ?, ?)",
                (user_id, new_category, new_limit),
            )

        conn.commit()
        conn.close()
        return redirect(url_for("budget_settings"))

    categories = conn.execute(
        "SELECT * FROM categories WHERE user_id = ? ORDER BY name", (user_id,)
    ).fetchall()
    conn.close()
    return render_template("budget_settings.html", categories=categories)

# ---------------------------------------------------------------------------
# Delete transactions Button
# ---------------------------------------------------------------------------


@app.route("/categories/<int:cat_id>/delete", methods=["POST"])
@login_required
def delete_category(cat_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM categories WHERE id = ? AND user_id = ?", (
            cat_id, session["user_id"])
    )
    conn.commit()
    conn.close()
    return redirect(url_for("budget_settings"))

# ---------------------------------------------------------------------------
# Stock Search Tab
# ---------------------------------------------------------------------------


@app.route("/stocks/search", methods=["GET"])
@login_required
def stock_search():

    query = request.args.get("q", "")
    results = stocks_data.get_search(query)

    if results is None:
        flash("Couldn't reach the market data, try again soon")
        results = []

    return render_template("stock_search.html", query=query, results=results)


@app.route("/stocks/<ticker>")
@login_required
def stock_detail(ticker):

    profile = stocks_data.get_company_profile(ticker)

    if profile is None:
        flash("Couldn't find that stock")
        return redirect(url_for("stock_search"))

    history = stocks_data.get_history(ticker)
    roi_and_risk = stocks_data.get_roi_and_risk(ticker)
    return render_template("stock_detail.html", profile=profile, history=history, risk=roi_and_risk)


# ---------------------------------------------------------------------------
# Stock Movers tab
# ---------------------------------------------------------------------------

@app.route("/stocks/movers")
@login_required
def stock_movers():
    movers = {}
    movers["Top Gainers"] = stocks_data.gainers_losers_mostactive("gainers", 6)
    movers["Top Losers"] = stocks_data.gainers_losers_mostactive("losers", 6)
    movers["Most Active"] = stocks_data.gainers_losers_mostactive(
        "most_active", 6)
    return render_template("stock_movers.html", sections=movers)

# DEMO 08 | FR16 | Flask receives the search and renders articles
# NYT article search page
@app.route("/articles", methods=["GET"])
@login_required
def articles():
    query = request.args.get("q", "").strip()
    article_list = []
    error = None

    # Search NYT when a topic is entered
    if query:
        result = nyt_articles.search_articles(query)
        article_list = result["articles"]
        error = result["error"]

    # Send the articles to the HTML page
    return render_template(
        "articles.html",
        query=query,
        articles=article_list,
        error=error
    )

# Connect the browser with the chatbot. Data is what is received from the browser as json, which
# is the conversation history between the user and the bot.



@app.route("/chat/send", methods=["POST"])
@login_required
def chat_send():
    if not g.user['assistant_enabled']:
        return jsonify(error='Stock Assistant is disabled in User Settings.'), 403
    data = request.get_json(silent=True) or {}
    history = data.get("history", [])
    if not isinstance(history, list):
        return jsonify({"error": "Invalid chat history"}), 400
    clean_messages = []

    # for each message in the chat history, check to make sure its a dictionary, that there is
    # content to be read, and that the message is either from the user or the bot (assistant). Then
    # add that message to the clean messages and return only the last 10 messages to not kill
    # the api bill.
    for message in history:
        if (isinstance(message, dict)
            and isinstance(message.get("content"), str)
            and message.get("content")
                and (message.get("role") == "user" or message.get("role") == "assistant")):

            new_dictionary = {
                "role": message["role"],
                "content": message["content"][:2000]
            }
            clean_messages.append(new_dictionary)
    clean = clean_messages[-10:]
    if not clean:
        return jsonify({"error": "No message received"}), 400

    # if there is context in the session, pass it to get_ai_reply to get more personalized
    # conversation from the chatbot
    user_id = session["user_id"]
    context = user_context.build_budget_context(
        user_id) + "\n\n" + user_context.build_stock_context()

    reply = ai.get_ai_reply(clean, context)
    if reply is None:
        return jsonify({"error": "Assistant not available right now"}), 503
    return jsonify({"reply": reply})

# ---------------------------------------------------------------------------
# JSON API (incase it uses something else ill leave it but if not ill delete everything below)
# ---------------------------------------------------------------------------


@app.route("/api/summary")
@login_required
def api_summary():
    conn = get_db()
    user_id = session["user_id"]
    rows = conn.execute(
        "SELECT category, SUM(amount) as total FROM transactions WHERE user_id = ? GROUP BY category",
        (user_id,),
    ).fetchall()
    conn.close()
    return jsonify({r["category"]: r["total"] for r in rows})


init_db()
if __name__ == "__main__":

    app.run(debug=True)
