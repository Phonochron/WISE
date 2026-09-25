import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from app import app
from wise_ai.data_store import get_active_import, list_imports, load_active_analysis
from wise_ai.import_data import read_uploaded_data
from wise_ai.validation import InputValidationError


class FakeModel:
    def predict_proba(self, features):
        return np.tile([0.2, 0.8], (len(features), 1))


def sample_dataframe(product_name="Apple"):
    return pd.DataFrame([{
        "Product_ID": "P-1",
        "Product_Name": product_name,
        "Branch": "Jakarta",
        "Category": "Fruit",
        "Initial_Stock": 100,
        "Sold_Quantity": 60,
        "Remaining_Stock": 40,
        "Expiry_Days_Left": 2,
        "Price": 25000,
        "Discount_Applied": 10,
        "Temperature_(°C)": 27.5,
        "Historical_Avg_Sales": 50,
        "Waste_Amount": 4,
    }])


class ImportFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database_path = str(Path(self.directory.name) / "wise.db")
        database_patch = patch.dict(app.config, {"DATABASE_PATH": self.database_path})
        database_patch.start()
        self.addCleanup(database_patch.stop)
        self.client = app.test_client()

    def upload_csv(self, frame, name="stock.csv"):
        content = frame.to_csv(index=False).encode("utf-8-sig")
        with patch("wise_ai.prediction_engine.load_model", return_value=FakeModel()):
            return self.client.post(
                "/upload",
                data={"data_file": (BytesIO(content), name)},
                content_type="multipart/form-data",
            )

    def test_upload_switches_dashboard_api_and_export_to_active_data(self):
        self.assertEqual(self.client.get("/upload").status_code, 200)
        self.assertIsNone(get_active_import(self.database_path))

        response = self.upload_csv(sample_dataframe())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_active_import(self.database_path)["row_count"], 1)
        self.assertEqual(load_active_analysis(self.database_path)["risk_level"].tolist(), ["High"])
        dashboard = self.client.get("/dashboard")
        self.assertIn(b"Apple", dashboard.data)
        self.assertIn(b"metric-chart-row", dashboard.data)
        self.assertIn(b"Performa Cabang", dashboard.data)
        self.assertIn(b"Risiko per kategori", dashboard.data)
        self.assertNotIn(b"cdn.plot.ly", dashboard.data)
        self.assertEqual(self.client.get("/api/data/critical").json[0]["Product_Name"], "Apple")

        exported = self.client.get("/export")
        self.assertEqual(exported.status_code, 200)
        sheet = pd.read_excel(BytesIO(exported.data))
        self.assertEqual(sheet.loc[0, "Product_Name"], "Apple")
        self.assertEqual(sheet.loc[0, "risk_level"], "High")

        self.assertEqual(self.upload_csv(sample_dataframe("Pear"), "next.csv").status_code, 302)
        self.assertEqual([item["filename"] for item in list_imports(self.database_path)], ["next.csv", "stock.csv"])
        self.assertEqual(self.client.get("/api/data/critical").json[0]["Product_Name"], "Pear")

    def test_invalid_upload_keeps_previous_import_active(self):
        self.upload_csv(sample_dataframe())
        invalid = sample_dataframe().drop(columns=["Price"])
        response = self.upload_csv(invalid, "broken.csv")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Missing columns", response.data)
        self.assertEqual(get_active_import(self.database_path)["filename"], "stock.csv")
        self.assertEqual(len(list_imports(self.database_path)), 1)

    def test_xlsx_upload_and_export_escapes_formula_text(self):
        frame = sample_dataframe()
        workbook = BytesIO()
        frame.to_excel(workbook, index=False)
        workbook.seek(0)
        with patch("wise_ai.prediction_engine.load_model", return_value=FakeModel()):
            response = self.client.post(
                "/upload",
                data={"data_file": (workbook, "stock.xlsx")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.upload_csv(sample_dataframe("=2+2"), "formula.csv").status_code, 302)
        exported = pd.read_excel(BytesIO(self.client.get("/export").data))
        self.assertEqual(exported.loc[0, "Product_Name"], "'=2+2")

    def test_rejects_invalid_format_empty_identity_and_oversize_file(self):
        with self.assertRaisesRegex(InputValidationError, "CSV or XLSX"):
            read_uploaded_data("stock.txt", b"test")
        invalid = sample_dataframe()
        invalid.loc[0, "Branch"] = " "
        with self.assertRaisesRegex(InputValidationError, "Branch"):
            read_uploaded_data("stock.csv", invalid.to_csv(index=False).encode())
        response = self.client.post(
            "/upload",
            data={"data_file": (BytesIO(b"a" * (10 * 1024 * 1024 + 1)), "big.csv")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 413)

    def test_bundled_excel_can_be_imported_with_real_model(self):
        source = Path(__file__).resolve().parents[1] / "data" / "raw" / "dataset_1000.xlsx"
        response = self.client.post(
            "/upload",
            data={"data_file": (BytesIO(source.read_bytes()), "dataset_1000.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_active_import(self.database_path)["row_count"], 1000)
        self.assertEqual(len(load_active_analysis(self.database_path)), 1000)


if __name__ == "__main__":
    unittest.main()
