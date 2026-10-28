"""Storage layer for the expense tracker (SQLite, amounts kept as integer cents)."""

import csv
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

DEFAULT_DB = Path(os.environ.get("EXPENSE_DB", Path.home() / ".expense_tracker.db"))
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT    NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    category     TEXT    NOT NULL,
    note         TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
CREATE TABLE IF NOT EXISTS budgets (
    category     TEXT PRIMARY KEY,
    limit_cents  INTEGER NOT NULL CHECK (limit_cents > 0)
);
"""


@dataclass(frozen=True)
class Expense:
    id: int
    date: str
    amount_cents: int
    category: str
    note: str


# ---------- helpers ----------

def parse_amount(text) -> int:
    """Turn '12.50' into 1250 cents. Raises ValueError for bad or non-positive input."""
    try:
        value = Decimal(str(text).strip().replace(",", ""))
    except InvalidOperation:
        raise ValueError(f"Invalid amount: {text!r}")
    if not value.is_finite() or value <= 0:
        raise ValueError("Amount must be a positive number")
    cents = int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if cents <= 0:
        raise ValueError("Amount is too small")
    return cents


def format_amount(cents: int) -> str:
    return f"{cents // 100:,}.{cents % 100:02d}"


def parse_date(text: Optional[str]) -> str:
    """Return an ISO date string. None means today."""
    if text is None:
        return date.today().isoformat()
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ValueError(f"Invalid date {text!r}, expected YYYY-MM-DD")


def check_month(month: str) -> str:
    if not MONTH_RE.match(month or ""):
        raise ValueError(f"Invalid month {month!r}, expected YYYY-MM")
    return month


def clean_category(name: str) -> str:
    name = (name or "").strip().lower()
    if not name:
        raise ValueError("Category cannot be empty")
    return name


# ---------- store ----------

class ExpenseStore:
    def __init__(self, db_path=DEFAULT_DB):
        self.db_path = str(db_path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- expenses ---
    def add(self, amount, category, note="", when=None) -> Expense:
        cents = parse_amount(amount)
        cat = clean_category(category)
        day = parse_date(when)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO expenses (date, amount_cents, category, note) VALUES (?, ?, ?, ?)",
                (day, cents, cat, note.strip()),
            )
            return Expense(cur.lastrowid, day, cents, cat, note.strip())

    def delete(self, expense_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            return cur.rowcount > 0

    def list(self, category=None, month=None, limit=None) -> List[Expense]:
        sql, params = "SELECT * FROM expenses WHERE 1=1", []
        if category:
            sql += " AND category = ?"
            params.append(clean_category(category))
        if month:
            sql += " AND substr(date, 1, 7) = ?"
            params.append(check_month(month))
        sql += " ORDER BY date DESC, id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._connect() as conn:
            return [Expense(**dict(r)) for r in conn.execute(sql, params)]

    # --- reports ---
    def summary(self, month=None) -> List[Tuple[str, int, int]]:
        """Return (category, total_cents, count), biggest first."""
        sql = "SELECT category, SUM(amount_cents) AS total, COUNT(*) AS n FROM expenses"
        params = []
        if month:
            sql += " WHERE substr(date, 1, 7) = ?"
            params.append(check_month(month))
        sql += " GROUP BY category ORDER BY total DESC, category"
        with self._connect() as conn:
            return [(r["category"], r["total"], r["n"]) for r in conn.execute(sql, params)]

    def monthly_totals(self) -> List[Tuple[str, int]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT substr(date, 1, 7) AS m, SUM(amount_cents) AS total "
                "FROM expenses GROUP BY m ORDER BY m"
            )
            return [(r["m"], r["total"]) for r in rows]

    # --- budgets ---
    def set_budget(self, category, amount) -> None:
        cat, cents = clean_category(category), parse_amount(amount)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO budgets (category, limit_cents) VALUES (?, ?) "
                "ON CONFLICT(category) DO UPDATE SET limit_cents = excluded.limit_cents",
                (cat, cents),
            )

    def remove_budget(self, category) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM budgets WHERE category = ?", (clean_category(category),))
            return cur.rowcount > 0

    def budget_status(self, month=None) -> List[Tuple[str, int, int, int]]:
        """Return (category, limit_cents, spent_cents, remaining_cents) for the month."""
        month = check_month(month) if month else date.today().strftime("%Y-%m")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT b.category, b.limit_cents, "
                "COALESCE((SELECT SUM(e.amount_cents) FROM expenses e "
                "          WHERE e.category = b.category AND substr(e.date, 1, 7) = ?), 0) AS spent "
                "FROM budgets b ORDER BY b.category",
                (month,),
            )
            return [(r["category"], r["limit_cents"], r["spent"], r["limit_cents"] - r["spent"]) for r in rows]

    # --- CSV ---
    def export_csv(self, path) -> int:
        items = list(reversed(self.list()))
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "amount", "category", "note"])
            for e in items:
                writer.writerow([e.date, format_amount(e.amount_cents).replace(",", ""), e.category, e.note])
        return len(items)

    def import_csv(self, path) -> int:
        """Import rows with columns date, amount, category, note. All-or-nothing."""
        parsed = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            missing = {"date", "amount", "category"} - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV is missing columns: {', '.join(sorted(missing))}")
            for line_no, row in enumerate(reader, start=2):
                try:
                    parsed.append((
                        parse_date(row["date"]),
                        parse_amount(row["amount"]),
                        clean_category(row["category"]),
                        (row.get("note") or "").strip(),
                    ))
                except ValueError as exc:
                    raise ValueError(f"Line {line_no}: {exc}")
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO expenses (date, amount_cents, category, note) VALUES (?, ?, ?, ?)", parsed
            )
        return len(parsed)
