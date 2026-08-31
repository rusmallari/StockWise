import os
import sqlite3
from datetime import datetime
from collections import defaultdict

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "stockwise.db")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

DEFAULT_CATEGORIES = ["Food", "Transportation", "Entertainment", "Bills", "Housing", "Other"]


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

def login_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

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
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            conn.close()
            flash("That username is already taken.")
            return redirect(url_for("signup"))

        cur = conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), datetime.utcnow().isoformat()),
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
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard / transaction history + charts
# ---------------------------------------------------------------------------

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
    totals_by_category = defaultdict(float)
    for t in transactions:
        totals_by_category[t["category"]] += t["amount"]

    total_spent = sum(totals_by_category.values())

    alerts = []
    for cat in categories:
        limit = cat["monthly_limit"] or 0
        spent = totals_by_category.get(cat["name"], 0)
        if limit > 0 and spent >= limit:
            alerts.append(f"You've exceeded your {cat['name']} budget (${spent:.2f} / ${limit:.2f}).")
        elif limit > 0 and spent >= 0.8 * limit:
            alerts.append(f"You're close to your {cat['name']} budget (${spent:.2f} / ${limit:.2f}).")

    chart_labels = list(totals_by_category.keys())
    chart_values = [round(v, 2) for v in totals_by_category.values()]

    return render_template(
        "dashboard.html",
        transactions=transactions,
        categories=categories,
        total_spent=round(total_spent, 2),
        alerts=alerts,
        chart_labels=chart_labels,
        chart_values=chart_values,
    )


# ---------------------------------------------------------------------------
# Transactions CRUD
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
        date = request.form.get("date") or datetime.utcnow().date().isoformat()

        try:
            amount = float(amount)
        except ValueError:
            flash("Amount must be a number.")
            conn.close()
            return redirect(url_for("add_transaction"))

        conn.execute(
            "INSERT INTO transactions (user_id, name, amount, category, date) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, amount, category, date),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("add_transaction.html", categories=categories, today=datetime.utcnow().date().isoformat())


@app.route("/transactions/<int:txn_id>/edit", methods=["GET", "POST"])
@login_required
def edit_transaction(txn_id):
    conn = get_db()
    user_id = session["user_id"]
    txn = conn.execute(
        "SELECT * FROM transactions WHERE id = ? AND user_id = ?", (txn_id, user_id)
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


@app.route("/transactions/<int:txn_id>/delete", methods=["POST"])
@login_required
def delete_transaction(txn_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM transactions WHERE id = ? AND user_id = ?", (txn_id, session["user_id"])
    )
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Budget settings (limits per category, custom categories)
# ---------------------------------------------------------------------------

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


@app.route("/categories/<int:cat_id>/delete", methods=["POST"])
@login_required
def delete_category(cat_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM categories WHERE id = ? AND user_id = ?", (cat_id, session["user_id"])
    )
    conn.commit()
    conn.close()
    return redirect(url_for("budget_settings"))


# ---------------------------------------------------------------------------
# Simple JSON API (handy if a JS frontend is added later)
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


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
