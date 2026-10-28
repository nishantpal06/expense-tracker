import io
import os
import tempfile
import unittest

from app import create_app


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(os.path.join(self.tmp.name, "web.db"))
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, amount="10", category="food", note="", day="2026-05-01"):
        return self.client.post(
            "/api/expenses",
            json={"amount": amount, "category": category, "note": note, "date": day},
        )

    def test_index_page_and_static_files(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Expense Tracker", res.data)
        for path in ("/static/app.js", "/static/style.css"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200)
            res.close()

    def test_add_list_delete(self):
        res = self.add("12.50", "Food", "lunch")
        self.assertEqual(res.status_code, 201)
        created = res.get_json()["expense"]
        self.assertEqual((created["amount"], created["category"]), ("12.50", "food"))

        listed = self.client.get("/api/expenses?month=2026-05").get_json()["expenses"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(self.client.get("/api/expenses?month=2026-06").get_json()["expenses"], [])

        self.assertEqual(self.client.delete(f"/api/expenses/{created['id']}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/expenses/{created['id']}").status_code, 404)

    def test_validation_errors_return_400(self):
        for payload in (
            {"amount": "-5", "category": "food"},
            {"amount": "abc", "category": "food"},
            {"amount": "5", "category": ""},
            {"amount": "5", "category": "food", "date": "05/01/2026"},
            {},
        ):
            res = self.client.post("/api/expenses", json=payload)
            self.assertEqual(res.status_code, 400, payload)
            self.assertIn("error", res.get_json())
        self.assertEqual(self.client.get("/api/expenses?month=2026-13").status_code, 400)

    def test_summary_and_months(self):
        self.add("10", "food", day="2026-05-01")
        self.add("30", "travel", day="2026-05-02")
        self.add("5", "food", day="2026-06-01")
        data = self.client.get("/api/summary?month=2026-05").get_json()
        self.assertEqual(data["total"], "40.00")
        self.assertEqual(data["categories"][0]["category"], "travel")
        self.assertAlmostEqual(data["categories"][0]["share"], 0.75)
        months = self.client.get("/api/months").get_json()["months"]
        self.assertEqual([m["month"] for m in months], ["2026-05", "2026-06"])

    def test_empty_summary(self):
        data = self.client.get("/api/summary").get_json()
        self.assertEqual((data["total"], data["categories"]), ("0.00", []))

    def test_budgets(self):
        self.add("85", "food")
        self.assertEqual(
            self.client.put("/api/budgets", json={"category": "Food", "amount": "100"}).status_code, 200
        )
        budgets = self.client.get("/api/budgets?month=2026-05").get_json()["budgets"]
        self.assertEqual(budgets[0]["status"], "close")
        self.client.put("/api/budgets", json={"category": "food", "amount": "50"})
        budgets = self.client.get("/api/budgets?month=2026-05").get_json()["budgets"]
        self.assertEqual(budgets[0]["status"], "over")
        self.assertEqual(self.client.delete("/api/budgets/food").status_code, 200)
        self.assertEqual(self.client.delete("/api/budgets/food").status_code, 404)
        self.assertEqual(self.client.put("/api/budgets", json={"category": "x", "amount": "0"}).status_code, 400)

    def test_csv_export_and_import(self):
        self.add("12.34", "food", "a, b")
        exported = self.client.get("/api/export.csv")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("text/csv", exported.content_type)
        self.assertIn(b"12.34", exported.data)

        other = create_app(os.path.join(self.tmp.name, "other.db")).test_client()
        res = other.post(
            "/api/import",
            data={"file": (io.BytesIO(exported.data), "expenses.csv")},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.get_json(), {"imported": 1})
        self.assertEqual(other.get("/api/expenses").get_json()["expenses"][0]["note"], "a, b")

    def test_import_rejects_bad_files(self):
        res = self.client.post("/api/import", data={}, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        bad = io.BytesIO(b"date,amount,category\n2026-01-01,oops,food\n")
        res = self.client.post(
            "/api/import", data={"file": (bad, "bad.csv")}, content_type="multipart/form-data"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.client.get("/api/expenses").get_json()["expenses"], [])


if __name__ == "__main__":
    unittest.main()
