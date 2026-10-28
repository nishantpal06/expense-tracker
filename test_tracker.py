import contextlib
import io
import os
import tempfile
import unittest

import cli
from tracker import ExpenseStore, format_amount, parse_amount, parse_date


class HelperTests(unittest.TestCase):
    def test_parse_amount(self):
        self.assertEqual(parse_amount("12.50"), 1250)
        self.assertEqual(parse_amount("1,000"), 100000)
        self.assertEqual(parse_amount("0.005"), 1)  # rounds half up

    def test_parse_amount_rejects_bad_input(self):
        for bad in ("abc", "0", "-5", "nan", "inf", ""):
            with self.assertRaises(ValueError, msg=bad):
                parse_amount(bad)

    def test_format_amount(self):
        self.assertEqual(format_amount(5), "0.05")
        self.assertEqual(format_amount(123456), "1,234.56")

    def test_parse_date(self):
        self.assertEqual(parse_date("2026-02-03"), "2026-02-03")
        with self.assertRaises(ValueError):
            parse_date("03/02/2026")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ExpenseStore(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_list_delete(self):
        e = self.store.add("10", "Food", "lunch", "2026-01-05")
        self.assertEqual(e.category, "food")
        self.assertEqual(len(self.store.list()), 1)
        self.assertTrue(self.store.delete(e.id))
        self.assertFalse(self.store.delete(e.id))
        self.assertEqual(self.store.list(), [])

    def test_filters(self):
        self.store.add("10", "food", when="2026-01-05")
        self.store.add("20", "travel", when="2026-02-05")
        self.assertEqual(len(self.store.list(category="FOOD")), 1)
        self.assertEqual(len(self.store.list(month="2026-02")), 1)
        with self.assertRaises(ValueError):
            self.store.list(month="2026-13")

    def test_summary_and_months(self):
        self.store.add("10", "food", when="2026-01-05")
        self.store.add("5.50", "food", when="2026-01-06")
        self.store.add("20", "travel", when="2026-02-05")
        self.assertEqual(self.store.summary(), [("travel", 2000, 1), ("food", 1550, 2)])
        self.assertEqual(self.store.monthly_totals(), [("2026-01", 1550), ("2026-02", 2000)])

    def test_budget_status(self):
        self.store.set_budget("food", "100")
        self.store.add("60", "food", when="2026-03-01")
        self.store.add("70", "food", when="2026-04-01")  # other month, ignored
        self.assertEqual(self.store.budget_status("2026-03"), [("food", 10000, 6000, 4000)])
        self.store.set_budget("food", "50")  # update in place
        self.assertEqual(self.store.budget_status("2026-03"), [("food", 5000, 6000, -1000)])
        self.assertTrue(self.store.remove_budget("food"))

    def test_csv_round_trip(self):
        self.store.add("12.34", "food", "a, b", "2026-01-05")
        path = os.path.join(self.tmp.name, "out.csv")
        self.assertEqual(self.store.export_csv(path), 1)
        other = ExpenseStore(os.path.join(self.tmp.name, "other.db"))
        self.assertEqual(other.import_csv(path), 1)
        got = other.list()[0]
        self.assertEqual((got.date, got.amount_cents, got.note), ("2026-01-05", 1234, "a, b"))

    def test_csv_import_is_all_or_nothing(self):
        path = os.path.join(self.tmp.name, "bad.csv")
        with open(path, "w") as f:
            f.write("date,amount,category,note\n2026-01-01,5,food,ok\n2026-01-02,oops,food,bad\n")
        with self.assertRaises(ValueError):
            self.store.import_csv(path)
        self.assertEqual(self.store.list(), [])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "cli.db")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--db", self.db, *args])
        return code, out.getvalue(), err.getvalue()

    def test_full_flow(self):
        self.assertEqual(self.run_cli("add", "9.99", "food", "snack", "-d", "2026-05-01")[0], 0)
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("9.99", out)
        code, out, _ = self.run_cli("summary", "-m", "2026-05")
        self.assertIn("Grand total: 9.99", out)
        self.assertEqual(self.run_cli("budget", "set", "food", "50")[0], 0)
        code, out, _ = self.run_cli("budget", "status", "-m", "2026-05")
        self.assertIn("ok", out)

    def test_errors_return_nonzero(self):
        code, _, err = self.run_cli("add", "-5", "food")
        self.assertEqual(code, 1)
        self.assertIn("Error", err)
        self.assertEqual(self.run_cli("delete", "999")[0], 1)


if __name__ == "__main__":
    unittest.main()
