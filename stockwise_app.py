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

# ---------------------------------------------------------------------------
# TEMPLATES (HTML + CSS embedded, single-file build)
# All page markup and styling live here via a Jinja2 DictLoader, so
# render_template("name.html") calls below work exactly as they would
# with a templates/ and static/ folder on disk.
# ---------------------------------------------------------------------------
from jinja2 import DictLoader

TEMPLATES = {
    "base.html": """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}StockWise{% endblock %}</title>
  <style>
/* ========================================================================
   THEME VARIABLES
   ======================================================================== */
:root {
  --primary: #4f7cff;
  --bg: #f5f7fb;
  --card-bg: #ffffff;
  --text: #1f2430;
  --muted: #6b7280;
  --border: #e5e7eb;
  --danger: #e0553f;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
}

/* ========================================================================
   NAVIGATION BAR
   ======================================================================== */
.navbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 32px;
  background: var(--card-bg);
  border-bottom: 1px solid var(--border);
}

.brand { font-weight: 700; font-size: 1.2rem; color: var(--primary); }

.nav-links a {
  margin-left: 20px;
  text-decoration: none;
  color: var(--text);
  font-size: 0.95rem;
}

.nav-links a:hover { color: var(--primary); }

/* ========================================================================
   LAYOUT / CARDS
   ======================================================================== */
.container {
  max-width: 1000px;
  margin: 0 auto;
  padding: 32px 20px;
}

.card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
}

.auth-card, .form-card {
  max-width: 420px;
  margin: 40px auto;
}

h1 { margin-top: 0; }
.subtitle { color: var(--muted); margin-bottom: 24px; }

/* ========================================================================
   FORM ELEMENTS (login, signup, add/edit transaction, budget settings)
   ======================================================================== */
label {
  display: block;
  margin: 14px 0 6px;
  font-size: 0.9rem;
  font-weight: 600;
}

input, select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 1rem;
}

.btn-primary {
  margin-top: 22px;
  width: 100%;
  padding: 12px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
}

.btn-primary:hover { opacity: 0.9; }

.switch-auth { text-align: center; margin-top: 18px; color: var(--muted); }

/* ========================================================================
   DASHBOARD
   ======================================================================== */
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.total-spent { font-size: 1.1rem; }

.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 1.3fr;
  gap: 20px;
}

@media (max-width: 800px) {
  .dashboard-grid { grid-template-columns: 1fr; }
}

/* ========================================================================
   BUDGET ALERTS
   ======================================================================== */
.alerts { margin-bottom: 20px; }

.alert-item {
  background: #fff4e5;
  border: 1px solid #f6c343;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 8px;
  font-size: 0.92rem;
}

/* ========================================================================
   TRANSACTION / LIMIT TABLES
   ======================================================================== */
.txn-table, .limit-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92rem;
}

.txn-table th, .txn-table td,
.limit-table th, .limit-table td {
  text-align: left;
  padding: 8px 6px;
  border-bottom: 1px solid var(--border);
}

.badge {
  background: #eef1ff;
  color: var(--primary);
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.8rem;
}

.row-actions a, .row-actions .link-btn {
  margin-right: 8px;
  font-size: 0.85rem;
}

.link-btn {
  background: none;
  border: none;
  color: var(--danger);
  cursor: pointer;
  padding: 0;
  font-size: 0.85rem;
  text-decoration: underline;
}

.empty-state { color: var(--muted); }

/* ========================================================================
   FLASH MESSAGES
   ======================================================================== */
.flash {
  background: #ffe8e6;
  border: 1px solid var(--danger);
  color: var(--danger);
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.section-heading { margin-top: 28px; font-size: 1rem; }

</style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
</head>
<body>
  {% if session.get('user_id') %}
  <!-- NAVIGATION BAR -->
  <nav class="navbar">
    <div class="brand">StockWise</div>
    <div class="nav-links">
      <a href="{{ url_for('dashboard') }}">Dashboard</a>
      <a href="{{ url_for('add_transaction') }}">Add Transaction</a>
      <a href="{{ url_for('budget_settings') }}">Budget Settings</a>
      <a href="{{ url_for('logout') }}">Logout ({{ session.get('username') }})</a>
    </div>
  </nav>
  {% endif %}

  <!-- MAIN CONTENT AREA -->
  <main class="container">
    <!-- FLASH MESSAGES -->
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        <div class="flash">
          {% for message in messages %}
            <p>{{ message }}</p>
          {% endfor %}
        </div>
      {% endif %}
    {% endwith %}

    {% block content %}{% endblock %}
  </main>
</body>
</html>
""",
    "login.html": """{% extends "base.html" %}
{% block title %}Login - StockWise{% endblock %}
{% block content %}
<!-- LOGIN FORM -->
<div class="card auth-card">
  <h1>Welcome back</h1>
  <p class="subtitle">Log in to your budget dashboard</p>
  <form method="POST">
    <label>Username</label>
    <input type="text" name="username" required autofocus>

    <label>Password</label>
    <input type="password" name="password" required>

    <button type="submit" class="btn-primary">Log In</button>
  </form>
  <p class="switch-auth">No account yet? <a href="{{ url_for('signup') }}">Sign up</a></p>
</div>
{% endblock %}
""",
    "signup.html": """{% extends "base.html" %}
{% block title %}Sign Up - StockWise{% endblock %}
{% block content %}
<!-- SIGNUP FORM -->
<div class="card auth-card">
  <h1>Create your account</h1>
  <p class="subtitle">Start tracking your spending in minutes</p>
  <form method="POST">
    <label>Username</label>
    <input type="text" name="username" required autofocus>

    <label>Password</label>
    <input type="password" name="password" required>

    <button type="submit" class="btn-primary">Sign Up</button>
  </form>
  <p class="switch-auth">Already have an account? <a href="{{ url_for('login') }}">Log in</a></p>
</div>
{% endblock %}
""",
    "dashboard.html": """{% extends "base.html" %}
{% block title %}Dashboard - StockWise{% endblock %}
{% block content %}

<!-- DASHBOARD HEADER -->
<div class="dashboard-header">
  <h1>Your Dashboard</h1>
  <div class="total-spent">Total spent: <strong>${{ "%.2f"|format(total_spent) }}</strong></div>
</div>

<!-- BUDGET ALERTS -->
{% if alerts %}
<div class="alerts">
  {% for alert in alerts %}
    <div class="alert-item">⚠️ {{ alert }}</div>
  {% endfor %}
</div>
{% endif %}

<div class="dashboard-grid">
  <!-- SPENDING CHART -->
  <div class="card">
    <h2>Spending by Category</h2>
    {% if chart_labels %}
      <canvas id="spendingChart" height="220"></canvas>
    {% else %}
      <p class="empty-state">No transactions yet — add one to see your breakdown.</p>
    {% endif %}
  </div>

  <!-- TRANSACTION HISTORY TABLE -->
  <div class="card">
    <h2>Transaction History</h2>
    {% if transactions %}
    <table class="txn-table">
      <thead>
        <tr><th>Date</th><th>Name</th><th>Category</th><th>Amount</th><th></th></tr>
      </thead>
      <tbody>
        {% for t in transactions %}
        <tr>
          <td>{{ t['date'] }}</td>
          <td>{{ t['name'] }}</td>
          <td><span class="badge">{{ t['category'] }}</span></td>
          <td>${{ "%.2f"|format(t['amount']) }}</td>
          <td class="row-actions">
            <a href="{{ url_for('edit_transaction', txn_id=t['id']) }}">Edit</a>
            <form method="POST" action="{{ url_for('delete_transaction', txn_id=t['id']) }}" style="display:inline">
              <button type="submit" class="link-btn" onclick="return confirm('Delete this transaction?')">Delete</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
      <p class="empty-state">No transactions yet.</p>
    {% endif %}
  </div>
</div>

<!-- SPENDING CHART SCRIPT -->
{% if chart_labels %}
<script>
  const ctx = document.getElementById('spendingChart');
  new Chart(ctx, {
    type: 'pie',
    data: {
      labels: {{ chart_labels|tojson }},
      datasets: [{
        data: {{ chart_values|tojson }},
        backgroundColor: ['#4f7cff', '#ff8a5b', '#39c98d', '#f6c343', '#c084fc', '#ff6b9d', '#54c7ec']
      }]
    },
    options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
  });
</script>
{% endif %}

{% endblock %}
""",
    "add_transaction.html": """{% extends "base.html" %}
{% block title %}Add Transaction - StockWise{% endblock %}
{% block content %}
<!-- ADD TRANSACTION FORM -->
<div class="card form-card">
  <h1>Add Transaction</h1>
  <form method="POST">
    <label>Name</label>
    <input type="text" name="name" placeholder="e.g. Groceries" required autofocus>

    <label>Amount ($)</label>
    <input type="number" step="0.01" name="amount" placeholder="0.00" required>

    <label>Category</label>
    <select name="category" required>
      {% for c in categories %}
        <option value="{{ c['name'] }}">{{ c['name'] }}</option>
      {% endfor %}
    </select>

    <label>Date</label>
    <input type="date" name="date" value="{{ today }}">

    <button type="submit" class="btn-primary">Save Transaction</button>
  </form>
</div>
{% endblock %}
""",
    "edit_transaction.html": """{% extends "base.html" %}
{% block title %}Edit Transaction - StockWise{% endblock %}
{% block content %}
<!-- EDIT TRANSACTION FORM -->
<div class="card form-card">
  <h1>Edit Transaction</h1>
  <form method="POST">
    <label>Name</label>
    <input type="text" name="name" value="{{ txn['name'] }}" required autofocus>

    <label>Amount ($)</label>
    <input type="number" step="0.01" name="amount" value="{{ txn['amount'] }}" required>

    <label>Category</label>
    <select name="category" required>
      {% for c in categories %}
        <option value="{{ c['name'] }}" {% if c['name'] == txn['category'] %}selected{% endif %}>{{ c['name'] }}</option>
      {% endfor %}
    </select>

    <label>Date</label>
    <input type="date" name="date" value="{{ txn['date'] }}">

    <button type="submit" class="btn-primary">Save Changes</button>
  </form>
</div>
{% endblock %}
""",
    "budget_settings.html": """{% extends "base.html" %}
{% block title %}Budget Settings - StockWise{% endblock %}
{% block content %}
<div class="card form-card">
  <h1>Budget Settings</h1>
  <p class="subtitle">Set a monthly spending limit per category. You'll get an alert when you're close to or over the limit.</p>

  <form method="POST">
    <!-- CATEGORY LIMITS TABLE -->
    <table class="limit-table">
      <thead><tr><th>Category</th><th>Monthly Limit ($)</th><th></th></tr></thead>
      <tbody>
        {% for c in categories %}
        <tr>
          <td>{{ c['name'] }}</td>
          <td><input type="number" step="0.01" name="limit_{{ c['id'] }}" value="{{ c['monthly_limit'] }}"></td>
          <td>
            <form method="POST" action="{{ url_for('delete_category', cat_id=c['id']) }}" style="display:inline">
              <button type="submit" class="link-btn" onclick="return confirm('Delete this category?')">Delete</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>

    <!-- ADD CUSTOM CATEGORY -->
    <h2 class="section-heading">Add a custom category</h2>
    <label>Category name</label>
    <input type="text" name="new_category" placeholder="e.g. Subscriptions">
    <label>Monthly limit ($)</label>
    <input type="number" step="0.01" name="new_category_limit" placeholder="0.00">

    <button type="submit" class="btn-primary">Save Settings</button>
  </form>
</div>
{% endblock %}
""",
}

app.jinja_loader = DictLoader(TEMPLATES)

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
