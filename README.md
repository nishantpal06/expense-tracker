# Expense Tracker

A personal expense tracker you can use from the browser or the command line.
Built with Python 3.8+, Flask and SQLite. Money is stored as integer cents, so there are no float
rounding bugs, and everything is covered by a unit test suite.

## Features

- Web dashboard: add expenses, filter by month and category, delete, see totals at a glance
- Spending breakdown by category and month-by-month totals, drawn as bars
- Monthly budgets per category with on track / almost there / over budget status
- CSV export and import (import is all-or-nothing, so a bad row never leaves partial data)
- JSON API behind the dashboard, plus a full command-line interface
- Light and dark theme that follows your system setting, works on phones

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

Settings (all optional environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `EXPENSE_DB` | `~/.expense_tracker.db` | Path of the SQLite database file |
| `HOST` | `127.0.0.1` | Interface to listen on (use `0.0.0.0` to open it to your network) |
| `PORT` | `5000` | Port to listen on |
| `FLASK_DEBUG` | off | Set to `1` for auto-reload while developing |

The built-in Flask server is meant for personal or local use. For a shared deployment, run it behind a
production server, for example `pip install gunicorn && gunicorn app:app`, and add authentication, because
the app has no login.

## JSON API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/expenses?month=YYYY-MM&category=food` | List expenses (filters optional) |
| POST | `/api/expenses` | Add: `{"amount", "category", "note", "date"}` |
| DELETE | `/api/expenses/<id>` | Delete one expense |
| GET | `/api/summary?month=YYYY-MM` | Totals by category |
| GET | `/api/months` | Totals by month |
| GET | `/api/budgets?month=YYYY-MM` | Budget status for a month |
| PUT | `/api/budgets` | Set a budget: `{"category", "amount"}` |
| DELETE | `/api/budgets/<category>` | Remove a budget |
| GET | `/api/export.csv` | Download all expenses as CSV |
| POST | `/api/import` | Upload a CSV (form field `file`; columns `date,amount,category,note`) |

Errors come back as `{"error": "message"}` with status 400 (bad input), 404 (not found) or 413 (file too large).

## Command line

The original CLI still works and shares the same database.

```bash
python cli.py add 12.50 food "lunch with Sam"
python cli.py add 450 travel "train ticket" -d 2026-10-05
python cli.py list -c food -m 2026-10
python cli.py summary -m 2026-10
python cli.py months
python cli.py budget set food 300
python cli.py budget status
python cli.py export my_expenses.csv
python cli.py import my_expenses.csv
python cli.py --help
```

## Project layout

| File | Purpose |
| --- | --- |
| `app.py` | Flask app: page route and JSON API |
| `templates/index.html` | Dashboard page |
| `static/style.css` | Styling (responsive, light and dark) |
| `static/app.js` | Front-end logic (talks to the JSON API) |
| `tracker.py` | Storage layer: `ExpenseStore`, amount and date validation |
| `cli.py` | Command-line interface |
| `test_tracker.py` | Tests for storage and CLI |
| `test_web.py` | Tests for the web app and API |
| `requirements.txt` | Python dependencies (Flask) |

## Running the tests

```bash
python -m unittest -v
```

## Ideas for extending it

- Login and per-user databases
- Recurring expenses (rent, subscriptions)
- Edit existing expenses from the dashboard
- Multiple currencies
