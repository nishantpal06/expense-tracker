#!/usr/bin/env python3
"""Flask web app for the expense tracker.

Run with:  python app.py   then open http://127.0.0.1:5000
"""

import csv
import os
import tempfile
from datetime import date

from flask import Flask, Response, jsonify, render_template, request

from tracker import DEFAULT_DB, ExpenseStore, format_amount


def expense_dict(e):
    return {
        "id": e.id,
        "date": e.date,
        "amount": format_amount(e.amount_cents),
        "amount_cents": e.amount_cents,
        "category": e.category,
        "note": e.note,
    }


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB upload limit
    store = ExpenseStore(db_path or DEFAULT_DB)

    @app.errorhandler(ValueError)
    def bad_request(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(csv.Error)
    def bad_csv(exc):
        return jsonify(error=f"Could not read CSV: {exc}"), 400

    @app.errorhandler(413)
    def too_large(_exc):
        return jsonify(error="File is too large (max 2 MB)"), 413

    @app.get("/")
    def index():
        return render_template("index.html", today=date.today().isoformat())

    # ---- expenses ----
    @app.get("/api/expenses")
    def list_expenses():
        items = store.list(
            category=request.args.get("category") or None,
            month=request.args.get("month") or None,
        )
        return jsonify(expenses=[expense_dict(e) for e in items])

    @app.post("/api/expenses")
    def add_expense():
        data = request.get_json(silent=True) or {}
        e = store.add(
            data.get("amount", ""),
            data.get("category", ""),
            str(data.get("note") or ""),
            data.get("date") or None,
        )
        return jsonify(expense=expense_dict(e)), 201

    @app.delete("/api/expenses/<int:expense_id>")
    def delete_expense(expense_id):
        if not store.delete(expense_id):
            return jsonify(error=f"No expense with id {expense_id}"), 404
        return jsonify(ok=True)

    # ---- reports ----
    @app.get("/api/summary")
    def summary():
        rows = store.summary(request.args.get("month") or None)
        grand = sum(r[1] for r in rows)
        return jsonify(
            total=format_amount(grand),
            total_cents=grand,
            categories=[
                {
                    "category": cat,
                    "total": format_amount(total),
                    "total_cents": total,
                    "count": n,
                    "share": (total / grand) if grand else 0,
                }
                for cat, total, n in rows
            ],
        )

    @app.get("/api/months")
    def months():
        return jsonify(
            months=[
                {"month": m, "total": format_amount(t), "total_cents": t}
                for m, t in store.monthly_totals()
            ]
        )

    # ---- budgets ----
    @app.get("/api/budgets")
    def budgets():
        rows = store.budget_status(request.args.get("month") or None)
        out = []
        for cat, limit, spent, remaining in rows:
            status = "over" if remaining < 0 else ("close" if spent >= 0.8 * limit else "ok")
            out.append(
                {
                    "category": cat,
                    "limit": format_amount(limit),
                    "limit_cents": limit,
                    "spent": format_amount(spent),
                    "spent_cents": spent,
                    "remaining_cents": remaining,
                    "status": status,
                }
            )
        return jsonify(budgets=out)

    @app.put("/api/budgets")
    def set_budget():
        data = request.get_json(silent=True) or {}
        store.set_budget(data.get("category", ""), data.get("amount", ""))
        return jsonify(ok=True)

    @app.delete("/api/budgets/<category>")
    def remove_budget(category):
        if not store.remove_budget(category):
            return jsonify(error=f"No budget for {category!r}"), 404
        return jsonify(ok=True)

    # ---- CSV ----
    @app.get("/api/export.csv")
    def export_csv():
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "expenses.csv")
            store.export_csv(path)
            with open(path, encoding="utf-8") as f:
                body = f.read()
        return Response(
            body,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=expenses.csv"},
        )

    @app.post("/api/import")
    def import_csv():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            raise ValueError("Choose a CSV file to import")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "upload.csv")
            upload.save(path)
            count = store.import_csv(path)
        return jsonify(imported=count)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
