import unittest
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from app import app, load_processed_data
from wise_ai.config import FEATURE_COLUMNS, get_server_config
from wise_ai.prediction_engine import predict_single_product, run_full_pipeline
from wise_ai.validation import InputValidationError


SAMPLE = {
    "Initial_Stock": 100,
    "Sold_Quantity": 60,
    "Remaining_Stock": 40,
    "Expiry_Days_Left": 3,
    "Price": 25000,
    "Discount_Applied": 10,
    "Temperature_(°C)": 27.5,
    "Historical_Avg_Sales": 50,
}


class FakeModel:
    def predict_proba(self, features):
        probabilities = [0.8 if days <= 2 else 0.5 for days in features["Expiry_Days_Left"]]
        return np.array([[1 - probability, probability] for probability in probabilities])


class PipelineTests(unittest.TestCase):
    def test_full_pipeline_preserves_input_and_generates_actions(self):
        source = pd.DataFrame([
            {**SAMPLE, "Product_ID": "A", "Category": "Bakery"},
            {**SAMPLE, "Product_ID": "B", "Category": "Fruit", "Remaining_Stock": 60,
             "Expiry_Days_Left": 1},
        ])
        original = source.copy(deep=True)

        with patch("wise_ai.prediction_engine.load_model", return_value=FakeModel()):
            result = run_full_pipeline(source)

        pd.testing.assert_frame_equal(source, original)
        self.assertEqual(result["risk_level"].tolist(), ["Medium", "High"])
        self.assertEqual(result["action_discount"].tolist(), [10, 40])
        self.assertEqual(result["action_redistribute"].tolist(), [False, True])
        self.assertEqual(result["action_donate"].tolist(), [False, True])
        self.assertEqual(result["action_recipe"].tolist(), [True, True])

    def test_invalid_single_product_is_rejected_before_model_load(self):
        changes = [
            {"Price": -1},
            {"Remaining_Stock": 1.5},
            {"Discount_Applied": 101},
            {"Initial_Stock": True},
            {"Temperature_(°C)": float("inf")},
        ]
        with patch("wise_ai.prediction_engine.load_model") as load_model:
            for change in changes:
                with self.subTest(change=change), self.assertRaises(InputValidationError):
                    predict_single_product({**SAMPLE, **change})
            load_model.assert_not_called()

    def test_missing_and_non_object_api_payloads_return_400(self):
        client = app.test_client()
        self.assertEqual(client.post("/api/predict", json={"Price": 12}).status_code, 400)
        self.assertEqual(client.post("/api/predict", json=[SAMPLE]).status_code, 400)
        self.assertEqual(client.post("/api/predict", data="not json").status_code, 400)

    def test_valid_api_prediction(self):
        with patch("wise_ai.prediction_engine.load_model", return_value=FakeModel()):
            response = app.test_client().post("/api/predict", json=SAMPLE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"waste_proba": 0.5, "risk_level": "Medium"})

    def test_batch_rejects_missing_or_nonfinite_values(self):
        incomplete = pd.DataFrame([{key: value for key, value in SAMPLE.items() if key != "Price"}])
        nonfinite = pd.DataFrame([{**SAMPLE, "Price": float("inf")}])
        with patch("wise_ai.prediction_engine.load_model") as load_model:
            with self.assertRaisesRegex(InputValidationError, "Missing columns"):
                run_full_pipeline(incomplete)
            with self.assertRaisesRegex(InputValidationError, "finite"):
                run_full_pipeline(nonfinite)
            load_model.assert_not_called()

    def test_server_config_defaults_and_rejects_invalid_values(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(get_server_config(), {"host": "127.0.0.1", "port": 5000, "debug": False})
        with patch.dict("os.environ", {"WISE_PORT": "70000"}, clear=True):
            with self.assertRaisesRegex(ValueError, "WISE_PORT"):
                get_server_config()
        with patch.dict("os.environ", {"WISE_DEBUG": "maybe"}, clear=True):
            with self.assertRaisesRegex(ValueError, "WISE_DEBUG"):
                get_server_config()

    def test_bundled_dataset_can_run_full_pipeline(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(app.config, {"DATABASE_PATH": str(Path(directory) / "wise.db")}):
            result = load_processed_data()
        self.assertGreater(len(result), 0)
        self.assertTrue(set(FEATURE_COLUMNS).issubset(result.columns))
        self.assertTrue({"waste_proba", "risk_level", "action_discount"}.issubset(result.columns))


if __name__ == "__main__":
    unittest.main()
