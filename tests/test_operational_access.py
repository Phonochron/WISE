import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from werkzeug.security import check_password_hash, generate_password_hash

from app import app
from wise_ai.data_store import get_product_outcome, get_user_by_name, list_signup_requests, save_analysis, save_product_outcome, save_user


class OperationalAccessTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = str(Path(directory.name) / "wise.db")
        configuration = patch.dict(app.config, {"DATABASE_PATH": self.db, "AUTH_REQUIRED": True})
        configuration.start()
        self.addCleanup(configuration.stop)
        save_user(self.db, "admin", generate_password_hash("strong-password-123"), "admin", None)
        save_user(self.db, "jakarta", generate_password_hash("branch-password-123"), "branch", "Jakarta")
        frame = pd.DataFrame([
            {"Product_ID": "J1", "Product_Name": "Apel", "Branch": "Jakarta", "Category": "Fruit",
             "Initial_Stock": 20, "Sold_Quantity": 10, "Remaining_Stock": 10, "Expiry_Days_Left": 1,
             "Price": 10000, "Discount_Applied": 0, "Temperature_(Â°C)": 25,
             "Historical_Avg_Sales": 2, "waste_proba": .9, "risk_level": "High",
             "action_discount": 40, "action_redistribute": False, "action_donate": True, "action_recipe": False},
            {"Product_ID": "B1", "Product_Name": "Roti", "Branch": "Bandung", "Category": "Bakery",
             "Initial_Stock": 20, "Sold_Quantity": 10, "Remaining_Stock": 10, "Expiry_Days_Left": 1,
             "Price": 10000, "Discount_Applied": 0, "Temperature_(Â°C)": 25,
             "Historical_Avg_Sales": 2, "waste_proba": .9, "risk_level": "High",
             "action_discount": 40, "action_redistribute": False, "action_donate": True, "action_recipe": False},
        ])
        self.import_id = save_analysis(self.db, "batch.csv", frame)
        save_product_outcome(self.db, self.import_id, 1, {
            "outcome_date": date.today().isoformat(), "sold_units": 3, "donated_units": 0,
            "redistributed_units": 0, "wasted_units": 1,
            "revenue_value": None, "waste_value": None, "note": "Bandung",
        })
        self.client = app.test_client()

    def login(self, username, password):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            token = session["login_token"]
        return self.client.post("/login", data={"login_token": token, "username": username, "password": password})

    def test_login_branch_scope_and_logout(self):
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.assertEqual(self.client.get("/api/data/critical").status_code, 401)
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})
        self.assertEqual(self.login("jakarta", "wrong").status_code, 401)
        self.assertEqual(self.login("jakarta", "branch-password-123").status_code, 302)
        self.assertEqual(self.client.get("/admin").status_code, 403)
        self.assertEqual(self.client.post("/admin/users", data={}).status_code, 403)
        products = self.client.get("/products")
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertNotIn(b'href="/admin"', dashboard.data)
        self.assertIn(b'href="/account"', dashboard.data)
        self.assertNotIn(b"Roti", dashboard.data)
        self.assertIn(b"Apel", products.data)
        self.assertNotIn(b"Roti", products.data)
        self.assertEqual(len(self.client.get("/api/data/critical").json), 1)
        self.assertEqual(len(self.client.get("/api/data/branches").json), 1)
        self.assertEqual(len(self.client.get("/api/data/alerts").json), 1)
        monitoring = self.client.get("/model-monitoring")
        self.assertEqual(monitoring.status_code, 200)
        self.assertIn(b"1 produk", monitoring.data)
        self.assertEqual(self.client.get(f"/products/{self.import_id}/1").status_code, 404)
        self.assertEqual(self.client.get("/upload").status_code, 403)
        self.assertEqual(self.client.get("/export").status_code, 403)
        detail = self.client.get(f"/products/{self.import_id}/0")
        self.assertEqual(detail.status_code, 200)
        with self.client.session_transaction() as session:
            token = session["review_token"]
        endpoint = f"/products/{self.import_id}/0/outcome"
        outcome = {"review_token": token, "outcome_date": date.today().isoformat(),
                   "sold_units": "5", "donated_units": "0", "redistributed_units": "0", "wasted_units": "1"}
        self.assertEqual(self.client.post(endpoint, data=outcome).status_code, 302)
        self.assertEqual(get_product_outcome(self.db, self.import_id, 0)[0]["sold_units"], 5)
        report = self.client.get("/reports")
        self.assertIn(b"Apel", report.data)
        self.assertNotIn(b"Roti", report.data)
        other_batch = save_analysis(self.db, "bandung-only.csv", pd.DataFrame([{
            "Product_ID": "B2", "Product_Name": "Kue", "Branch": "Bandung", "Category": "Bakery",
            "Initial_Stock": 10, "Sold_Quantity": 5, "Remaining_Stock": 5, "Expiry_Days_Left": 1,
            "Price": 10000, "Discount_Applied": 0, "Temperature_(Â°C)": 25,
            "Historical_Avg_Sales": 2, "waste_proba": .9, "risk_level": "High",
            "action_discount": 40, "action_redistribute": False, "action_donate": True, "action_recipe": False,
        }]))
        self.assertEqual(self.client.get(f"/reports?import_id={other_batch}").status_code, 404)
        self.assertNotIn(b"bandung-only.csv", self.client.get("/reports").data)
        self.assertEqual(self.client.post("/logout", data={"review_token": token}).status_code, 302)
        self.assertEqual(self.client.get("/api/data/critical").status_code, 401)

    def test_branch_can_change_own_password(self):
        self.assertEqual(self.client.get("/account").status_code, 302)
        self.login("jakarta", "branch-password-123")
        self.assertIn(b"Cabang Jakarta", self.client.get("/account").data)
        with self.client.session_transaction() as session:
            token = session["review_token"]
        data = {"review_token": token, "current_password": "branch-password-123",
                "new_password": "my-better-password-2026", "confirm_password": "my-better-password-2026"}
        self.assertEqual(self.client.post("/account", data={**data, "review_token": "bad"}).status_code, 400)
        self.assertEqual(self.client.post("/account", data={**data, "current_password": "wrong"}).status_code, 400)
        self.assertEqual(self.client.post("/account", data={**data, "confirm_password": "different"}).status_code, 400)
        self.assertEqual(self.client.post("/account", data=data).status_code, 302)
        user = get_user_by_name(self.db, "jakarta")
        self.assertTrue(check_password_hash(user["password_hash"], "my-better-password-2026"))
        self.assertEqual(user["role"], "branch")
        self.assertEqual(user["branch"], "Jakarta")
        self.client.post("/logout", data={"review_token": token})
        self.assertEqual(self.login("jakarta", "branch-password-123").status_code, 401)
        self.assertEqual(self.login("jakarta", "my-better-password-2026").location, "/dashboard")

    def test_public_landing_signup_requires_admin_approval(self):
        landing = self.client.get("/")
        self.assertEqual(landing.status_code, 200)
        self.assertIn(b'href="/signup"', landing.data)
        self.assertIn(b'href="/login"', landing.data)
        self.assertNotIn(b'href="/dashboard"', landing.data)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.assertEqual(self.client.get("/signup").status_code, 200)
        with self.client.session_transaction() as session:
            token = session["signup_token"]
        data = {"signup_token": token, "username": "newstaff", "branch": "Jakarta",
                "password": "chosen-password-2026", "confirm_password": "chosen-password-2026"}
        self.assertEqual(self.client.post("/signup", data={**data, "signup_token": "bad"}).status_code, 400)
        self.assertEqual(self.client.post("/signup", data={**data, "confirm_password": "different"}).status_code, 400)
        self.assertEqual(self.client.post("/signup", data=data).location, "/login?registered=1")
        self.assertIsNone(get_user_by_name(self.db, "newstaff"))
        self.assertEqual(self.login("newstaff", "chosen-password-2026").status_code, 401)
        self.assertEqual(len(list_signup_requests(self.db)), 1)
        self.login("jakarta", "branch-password-123")
        self.client.get("/dashboard")
        with self.client.session_transaction() as session:
            review_token = session["review_token"]
        self.assertEqual(self.client.post("/admin/signup/1", data={"review_token": review_token, "decision": "approve"}).status_code, 403)
        self.client.post("/logout", data={"review_token": review_token})
        self.login("admin", "strong-password-123")
        self.assertIn(b"newstaff", self.client.get("/admin").data)
        with self.client.session_transaction() as session:
            review_token = session["review_token"]
        endpoint = "/admin/signup/1"
        self.assertEqual(self.client.post(endpoint, data={"decision": "approve"}).status_code, 400)
        self.assertEqual(self.client.post(endpoint, data={"review_token": review_token, "decision": "approve"}).status_code, 302)
        self.assertEqual(get_user_by_name(self.db, "newstaff")["branch"], "Jakarta")
        self.assertEqual(list_signup_requests(self.db), [])
        self.client.post("/logout", data={"review_token": review_token})
        self.assertEqual(self.login("newstaff", "chosen-password-2026").location, "/dashboard")
        self.assertEqual(self.client.get("/admin").status_code, 403)


    def test_admin_upload_csrf_and_security_headers(self):
        self.assertEqual(self.client.post("/login", data={"username": "admin", "password": "strong-password-123"}).status_code, 400)
        login = self.login("admin", "strong-password-123")
        self.assertEqual(login.status_code, 302)
        self.assertEqual(login.location, "/admin")
        panel = self.client.get("/admin")
        self.assertEqual(panel.status_code, 200)
        self.assertIn(b"Panel admin", panel.data)
        self.assertNotIn(b"scrypt:", panel.data)
        with self.client.session_transaction() as session:
            token = session["review_token"]
        endpoint = "/admin/users"
        user_data = {"username": "surabaya", "password": "new-password-123", "role": "branch", "branch": "Surabaya"}
        self.assertEqual(self.client.post(endpoint, data=user_data).status_code, 400)
        self.assertEqual(self.client.post(endpoint, data={**user_data, "review_token": token}).status_code, 302)
        self.assertEqual(get_user_by_name(self.db, "surabaya")["branch"], "Surabaya")
        self.assertEqual(self.client.post(endpoint, data={**user_data, "username": "admin", "review_token": token}).status_code, 400)
        self.assertEqual(self.client.post("/upload", data={}).status_code, 400)
        page = self.client.get("/upload")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"review_token", page.data)
        self.assertIn("nosniff", page.headers["X-Content-Type-Options"])
        self.assertIn("script-src", page.headers["Content-Security-Policy"])
        self.assertEqual(self.client.get("/export").status_code, 200)
