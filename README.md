# StockWise (A personal finance and expense tracker)

This app allows users to manage their monthly expenses, as well as look into investing into stock with resources such as AI chatbot/articles from NY Times API.
When stocks are search it displays, performance of the stock within the last year, theoretical ROI and Risk assessment.

## Features
- User signup/login (password hashing via Werkzeug)
- Add, edit, delete transactions (name, amount, category, date)
- Default + custom expense categories
- Monthly budget limits per category with over/near-limit alerts
- Transaction history table
- Spending-by-category pie chart (Chart.js)
- Stock search (ROI, performance over the past year, and risk assessment)
- Article Search gives validation on why to choose a stock
- AI chatbot (answers all finance related questions)

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

## User Settings

Open **User Settings** in the navigation while logged in. Profile Information changes
both the displayed username and the name used to log in; passwords are unchanged.
The appearance, assistant, and notification switches take effect when you select
**Save Changes** at the top, below your signed-in username. Dark Mode is the default (Light Mode off).
Logout is in Account Actions.

Start locally from PowerShell:

```powershell
.\.venv\Scripts\python.exe stockwise_app.py
```

Startup automatically adds `theme`, `assistant_enabled`, and
`notifications_enabled` to the existing SQLite `users` table if missing. This
migration is repeatable and retains accounts, password hashes, transactions, and
categories. Existing and new users default to dark mode with the assistant and
notifications enabled. No new dependencies or manual SQL commands are needed.
Back up `stockwise.db` before applying database changes to an important deployment.

All POST routes now require a session CSRF token. Existing forms include it, and
the chatbot sends it in `X-CSRF-Token`. Logout now requires POST rather than GET.
Pages opened before this update should be refreshed before submitting forms.

Local verification:

1. Log in and open User Settings. Confirm the current username and five sections.
   Open `/settings` while logged out to confirm it redirects to login.
2. Change the username and save. Try a blank name or an already used username;
   confirm the error. Log out and sign in with the updated username and original
   password. Usernames are unique and case-sensitive, matching existing auth.
3. Enable Light Mode and save preferences. Visit Dashboard, Add Transaction,
   Budget Settings, Stocks, Stock Movers, and Articles; confirm light surfaces,
   readable text, themed forms/charts, and navigation. Refresh and log back in to
   confirm persistence. Turn Light Mode off and save to restore Dark Mode.
4. Open the assistant, then disable Enable Stock Assistant and save. Its button
   and panel should disappear. Re-enable and save, then test opening, closing,
   and sending a message. Sending requires the existing AI service configuration.
5. Set a category limit and add spending at or above 80% of it. Confirm dashboard
   warnings appear with notifications enabled and disappear when disabled and
   saved. Budget progress and transactions remain visible. This controls existing
   in-app budget warnings only; no email or push delivery was added.
6. Log in as another user. Confirm the other user's username, theme, assistant,
   and notifications were not changed. Confirm both users retain their finance data.
7. Check the layout and keyboard-operated switches on desktop and mobile widths.

Run the automated suite (temporary test database, mocked external services):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite checks legacy migration, defaults, saving and login persistence,
user isolation, username validation, CSRF rejection, chat availability, budget
warnings, transaction operations, and authenticated navigation. Real market,
NYT, and AI responses still depend on the existing services and credentials.
