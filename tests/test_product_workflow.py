import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from app import app
from wise_ai.data_store import get_active_import, get_product_reviews
from wise_ai.product_workflow import filter_products, recommended_actions


class FakeModel:
    def predict_proba(self, features):
        probabilities = [0.8 if days <= 2 else 0.2 for days in features["Expiry_Days_Left"]]
        return np.array([[1 - probability, probability] for probability in probabilities])


def sample_rows():
    base = {
        "Initial_Stock": 100, "Sold_Quantity": 60, "Remaining_Stock": 40,
        "Price": 25000, "Discount_Applied": 0,
        "Temperature_(°C)": 27.5, "Historical_Avg_Sales": 50,
    }
    return pd.DataFrame([
        {**base, "Product_ID": "P-1", "Product_Name": "Apel Merah", "Branch": "Jakarta", "Category": "Fruit", "Expiry_Days_Left": 1},
        {**base, "Product_ID": "P-2", "Product_Name": "Roti Gandum", "Branch": "Bandung", "Category": "Bakery", "Expiry_Days_Left": 6},
        {**base, "Product_ID": "P-3", "Product_Name": "Apel Hijau", "Branch": "Bandung", "Category": "Fruit", "Expiry_Days_Left": 2},
    ])


class ProductWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database_path = str(Path(self.directory.name) / "wise.db")
        configuration = patch.dict(app.config, {"DATABASE_PATH": self.database_path})
        configuration.start()
        self.addCleanup(configuration.stop)
        self.client = app.test_client()

    def import_rows(self):
        content = sample_rows().to_csv(index=False).encode("utf-8-sig")
        with patch("wise_ai.prediction_engine.load_model", return_value=FakeModel()):
            response = self.client.post("/upload", data={"data_file": (BytesIO(content), "products.csv")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        return get_active_import(self.database_path)["id"]

    def test_browse_search_filter_and_detail(self):
        import_id = self.import_rows()
        listing = self.client.get("/products?q=apel&category=Fruit&risk=High")
        self.assertEqual(listing.status_code, 200)
        self.assertIn(b"2 produk ditemukan", listing.data)
        self.assertIn(b"Apel Merah", listing.data)
        self.assertNotIn(b"Roti Gandum", listing.data)
        attention_listing = self.client.get("/products?attention=1")
        self.assertIn(b"2 produk ditemukan", attention_listing.data)
        self.assertNotIn(b"Roti Gandum", attention_listing.data)
        branch_listing = self.client.get("/products?branch=Jakarta")
        self.assertIn(b"1 produk ditemukan", branch_listing.data)
        detail = self.client.get(f"/products/{import_id}/0")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"Diskon 40%", detail.data)
        self.assertIn(b"Donasi", detail.data)
        self.assertEqual(self.client.get(f"/products/{import_id}/99").status_code, 404)

    def test_review_is_recorded_and_scoped_to_import(self):
        import_id = self.import_rows()
        self.client.get(f"/products/{import_id}/0")
        with self.client.session_transaction() as session:
            token = session["review_token"]
        endpoint = f"/products/{import_id}/0/review"
        self.assertEqual(self.client.post(endpoint, data={"action_key": "discount", "status": "approved", "note": "Tes"}).status_code, 400)
        self.assertEqual(self.client.post(endpoint, data={"review_token": token, "action_key": "unknown", "status": "approved"}).status_code, 400)
        self.assertEqual(self.client.post(endpoint, data={"review_token": token, "action_key": "discount", "status": "completed"}).status_code, 400)
        response = self.client.post(endpoint, data={"review_token": token, "action_key": "discount", "status": "completed", "note": "Diskon sudah diterapkan manual"})
        self.assertEqual(response.status_code, 302)
        reviews, history = get_product_reviews(self.database_path, import_id, 0)
        self.assertEqual(reviews["discount"]["status"], "completed")
        self.assertEqual(len(history), 1)
        self.assertIn(b"Diskon sudah diterapkan manual", self.client.get(f"/products/{import_id}/0").data)
        self.assertEqual(self.client.post(endpoint, data={"review_token": token, "action_key": "donate", "status": "rejected", "note": "Tidak ada penerima"}).status_code, 302)
        reviews, history = get_product_reviews(self.database_path, import_id, 0)
        self.assertEqual(reviews["discount"]["status"], "completed")
        self.assertEqual(reviews["donate"]["status"], "rejected")
        self.assertEqual(len(history), 2)

        newer_id = self.import_rows()
        self.assertNotEqual(import_id, newer_id)
        self.assertEqual(self.client.post(endpoint, data={"review_token": token, "action_key": "discount", "status": "approved"}).status_code, 404)
        self.assertIn(b"batch lama", self.client.get(f"/products/{import_id}/0").data)
        self.assertEqual(get_product_reviews(self.database_path, newer_id, 0)[0], {})

    def test_filter_treats_search_text_literally_and_action_fallback(self):
        frame = sample_rows()
        frame["waste_proba"] = [0.8, 0.2, 0.8]
        frame["risk_level"] = ["High", "Low", "High"]
        self.assertEqual(len(filter_products(frame, query=".*")), 0)
        self.assertEqual(len(filter_products(frame, query="apel", branch="Bandung")), 1)
        self.assertEqual(len(filter_products(frame, attention=True)), 2)
        self.assertEqual(recommended_actions({"action_discount": 0, "action_redistribute": False, "action_donate": False, "action_recipe": False})[0]["key"], "monitor")

    def test_product_list_paginates_after_filtering(self):
        frame = pd.concat([sample_rows().iloc[[0]].assign(Product_ID=f"P-{index}", Product_Name=f"Produk {index}") for index in range(27)], ignore_index=True)
        with patch("wise_ai.prediction_engine.load_model", return_value=FakeModel()):
            response = self.client.post("/upload", data={"data_file": (BytesIO(frame.to_csv(index=False).encode()), "many.csv")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        first = self.client.get("/products?page=1")
        second = self.client.get("/products?page=2")
        self.assertIn(b"halaman 1 dari 2", first.data)
        self.assertIn(b"halaman 2 dari 2", second.data)
        self.assertEqual(first.data.count(b'class="product-name-link"'), 25)
        self.assertEqual(second.data.count(b'class="product-name-link"'), 2)
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.data.count(b'class="product-name-link"'), 27)
        self.assertNotIn(b"Lihat semua produk", dashboard.data)


if __name__ == "__main__":
    unittest.main()
