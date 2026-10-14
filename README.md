# StockWise (A personal finance and expense tracker)

This app allows users to manage their monthly expenses, as well as look into investing into stock with resources such as AI chatbot/articles from NY Times API

## Features
- User signup/login (password hashing via Werkzeug)
- Add, edit, delete transactions (name, amount, category, date)
- Default + custom expense categories
- Monthly budget limits per category with over/near-limit alerts
- Transaction history table
- Spending-by-category pie chart (Chart.js)

## Run it

```bash
pip install -r requirements.txt
python stockwise_app.py
```

Then visit http://127.0.0.1:5000 — the SQLite database (`stockwise.db`) is
created automatically on first run.

## Structure
- `app.py` — routes, models (raw SQLite), auth
- `templates/` — Jinja2 templates
- `static/style.css` — styling
