import csv
import io
import os
import tempfile
import unittest

import stockwise_app as stockwise


class ReportsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db = stockwise.DB_PATH
        stockwise.DB_PATH = os.path.join(self.temp_dir.name, "test.db")
        stockwise.init_db()
        conn = stockwise.get_db()
        for user_id in (1, 2):
            conn.execute(
                "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (user_id, f"person{user_id}", "unused", "2026-11-01"),
            )
        conn.execute(
            "INSERT INTO categories (user_id, name, monthly_limit) VALUES (1, 'Food', 100)"
        )
        conn.executemany(
            "INSERT INTO transactions (user_id, name, amount, category, date) VALUES (?, ?, ?, ?, ?)",
            [
                (1, "Lunch", 25.5, "Food", "2026-11-02"),
                (1, "=SUM(1,1)", 10, "Food", "2026-11-03"),
                (1, "October", 100, "Food", "2026-10-02"),
                (2, "Private", 999, "Food", "2026-11-02"),
            ],
        )
        conn.commit()
        conn.close()
        self.client = stockwise.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1

    def tearDown(self):
        stockwise.DB_PATH = self.original_db
        self.temp_dir.cleanup()

    def test_monthly_totals_and_user_isolation(self):
        response = self.client.get("/reports?month=2026-11")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("$35.50", page)
        self.assertIn("Lunch", page)
        self.assertNotIn("Private", page)
        self.assertNotIn("$999", page)

    def test_invalid_month_rejected(self):
        self.assertEqual(self.client.get("/reports?month=2026-13").status_code, 400)
        self.assertEqual(self.client.get("/reports/export?month=abc").status_code, 400)

    def test_csv_export_is_user_scoped_and_safe(self):
        response = self.client.get("/reports/export?month=2026-11")
        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.get_data(as_text=True).lstrip("\ufeff"))))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], ["Date", "Name", "Category", "Amount"])
        self.assertIn("'=SUM(1,1)", [row[1] for row in rows[1:]])
        self.assertNotIn("Private", response.get_data(as_text=True))

    def test_login_required(self):
        anonymous = stockwise.app.test_client()
        self.assertEqual(anonymous.get("/reports").status_code, 302)
        self.assertEqual(anonymous.get("/reports/export").status_code, 302)


if __name__ == "__main__":
    unittest.main()
