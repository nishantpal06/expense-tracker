#!/usr/bin/env python3
"""Command-line interface for the expense tracker.

Run `python cli.py --help` for usage.
"""

import argparse
import sys
from datetime import date

from tracker import DEFAULT_DB, ExpenseStore, format_amount

BAR_WIDTH = 24


def table(headers, rows, right=()):
    """Print a simple aligned text table. `right` lists column indexes to right-align."""
    cells = [[str(c) for c in row] for row in rows]
    widths = [max(len(h), *(len(r[i]) for r in cells)) if cells else len(h) for i, h in enumerate(headers)]

    def fmt(row):
        return "  ".join(
            c.rjust(widths[i]) if i in right else c.ljust(widths[i]) for i, c in enumerate(row)
        )

    print(fmt(headers))
    print("  ".join("-" * w for w in widths))
    for row in cells:
        print(fmt(row))


def cmd_add(store, args):
    e = store.add(args.amount, args.category, args.note or "", args.date)
    print(f"Added #{e.id}: {e.date}  {format_amount(e.amount_cents)}  {e.category}  {e.note}".rstrip())


def cmd_list(store, args):
    items = store.list(category=args.category, month=args.month, limit=args.limit)
    if not items:
        print("No expenses found.")
        return
    table(
        ["ID", "Date", "Amount", "Category", "Note"],
        [(e.id, e.date, format_amount(e.amount_cents), e.category, e.note) for e in items],
        right=(0, 2),
    )
    print(f"\n{len(items)} expense(s), total {format_amount(sum(e.amount_cents for e in items))}")


def cmd_delete(store, args):
    if store.delete(args.id):
        print(f"Deleted expense #{args.id}.")
    else:
        raise ValueError(f"No expense with id {args.id}")


def cmd_summary(store, args):
    rows = store.summary(args.month)
    if not rows:
        print("No expenses found.")
        return
    grand = sum(r[1] for r in rows)
    table_rows = []
    for cat, total, n in rows:
        share = total / grand
        bar = "#" * max(1, round(share * BAR_WIDTH))
        table_rows.append((cat, n, format_amount(total), f"{share:5.1%}", bar))
    title = f"Spending summary for {args.month}" if args.month else "Spending summary (all time)"
    print(title + "\n")
    table(["Category", "Count", "Total", "Share", ""], table_rows, right=(1, 2, 3))
    print(f"\nGrand total: {format_amount(grand)}")


def cmd_months(store, args):
    rows = store.monthly_totals()
    if not rows:
        print("No expenses found.")
        return
    peak = max(t for _, t in rows)
    table(
        ["Month", "Total", ""],
        [(m, format_amount(t), "#" * max(1, round(t / peak * BAR_WIDTH))) for m, t in rows],
        right=(1,),
    )


def cmd_budget(store, args):
    if args.budget_cmd == "set":
        store.set_budget(args.category, args.amount)
        print(f"Monthly budget for {args.category.strip().lower()} set to {format_amount(store_amount(args.amount))}.")
    elif args.budget_cmd == "remove":
        if not store.remove_budget(args.category):
            raise ValueError(f"No budget for {args.category!r}")
        print(f"Removed budget for {args.category.strip().lower()}.")
    else:
        month = args.month or date.today().strftime("%Y-%m")
        rows = store.budget_status(month)
        if not rows:
            print("No budgets set. Try: python cli.py budget set food 300")
            return
        out = []
        for cat, limit, spent, remaining in rows:
            status = "OVER BUDGET" if remaining < 0 else ("close" if spent >= 0.8 * limit else "ok")
            sign = "-" if remaining < 0 else ""
            out.append((cat, format_amount(limit), format_amount(spent), sign + format_amount(abs(remaining)), status))
        print(f"Budget status for {month}\n")
        table(["Category", "Budget", "Spent", "Left", "Status"], out, right=(1, 2, 3))


def store_amount(text):
    from tracker import parse_amount
    return parse_amount(text)


def cmd_export(store, args):
    print(f"Exported {store.export_csv(args.file)} expense(s) to {args.file}")


def cmd_import(store, args):
    print(f"Imported {store.import_csv(args.file)} expense(s) from {args.file}")


def build_parser():
    p = argparse.ArgumentParser(prog="expenses", description="A small personal expense tracker.")
    p.add_argument("--db", default=str(DEFAULT_DB), help="database file (default: %(default)s)")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="record an expense")
    a.add_argument("amount")
    a.add_argument("category")
    a.add_argument("note", nargs="?", default="")
    a.add_argument("-d", "--date", help="YYYY-MM-DD (default: today)")
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("list", help="list expenses")
    l.add_argument("-c", "--category")
    l.add_argument("-m", "--month", help="YYYY-MM")
    l.add_argument("-n", "--limit", type=int)
    l.set_defaults(func=cmd_list)

    d = sub.add_parser("delete", help="delete an expense by id")
    d.add_argument("id", type=int)
    d.set_defaults(func=cmd_delete)

    s = sub.add_parser("summary", help="totals by category")
    s.add_argument("-m", "--month", help="YYYY-MM")
    s.set_defaults(func=cmd_summary)

    sub.add_parser("months", help="totals by month").set_defaults(func=cmd_months)

    b = sub.add_parser("budget", help="manage monthly category budgets")
    bsub = b.add_subparsers(dest="budget_cmd", required=True)
    bs = bsub.add_parser("set", help="set a monthly budget")
    bs.add_argument("category")
    bs.add_argument("amount")
    br = bsub.add_parser("remove", help="remove a budget")
    br.add_argument("category")
    bst = bsub.add_parser("status", help="show spending against budgets")
    bst.add_argument("-m", "--month", help="YYYY-MM (default: this month)")
    b.set_defaults(func=cmd_budget)

    e = sub.add_parser("export", help="export all expenses to CSV")
    e.add_argument("file")
    e.set_defaults(func=cmd_export)

    i = sub.add_parser("import", help="import expenses from CSV (date,amount,category,note)")
    i.add_argument("file")
    i.set_defaults(func=cmd_import)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        store = ExpenseStore(args.db)
        args.func(store, args)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
