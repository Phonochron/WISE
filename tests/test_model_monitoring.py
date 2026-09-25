import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app import app
from wise_ai.data_store import list_model_evaluations, list_prediction_summaries, save_analysis, save_model_evaluation
from wise_ai.model_monitoring import evaluate_predictions, model_fingerprint, summarize_predictions


class ModelMonitoringTests(unittest.TestCase):
    def test_evaluation_metrics_and_invalid_labels(self):
        result = evaluate_predictions([0, 0, 1, 1], [.1, .4, .8, .9])
        self.assertEqual(result["roc_auc"], 1.0)
        self.assertEqual(result["brier_score"], .055)
        self.assertEqual(result["confusion"], {"true_negative": 2, "false_positive": 0,
                                               "false_negative": 0, "true_positive": 2})
        self.assertEqual(sum(bin_["count"] for bin_ in result["calibration"]), 4)
        with self.assertRaises(ValueError):
            evaluate_predictions([1, 1], [.7, .8])
        with self.assertRaises(ValueError):
            evaluate_predictions([0, 1], [.2, float("nan")])

    def test_batch_summary_and_branch_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "wise.db")
            frame = pd.DataFrame([
                {"Branch": "Jakarta", "risk_level": "High", "waste_proba": .9},
                {"Branch": "Jakarta", "risk_level": "Low", "waste_proba": .2},
                {"Branch": "Bandung", "risk_level": "Medium", "waste_proba": .5},
            ])
            import_id = save_analysis(database, "test.csv", frame, model_sha256="abc123")
            all_batches = list_prediction_summaries(database)
            self.assertEqual(all_batches[0]["high_count"], 1)
            self.assertEqual(all_batches[0]["average_probability"], .5333)
            self.assertEqual(all_batches[0]["model_sha256"], "abc123")
            scoped = list_prediction_summaries(database, "Jakarta")
            self.assertEqual(scoped[0]["row_count"], 2)
            self.assertEqual(scoped[0]["high_rate"], .5)
            self.assertEqual(scoped[0]["average_probability"], .55)
            self.assertNotIn("filename", scoped[0])
            with patch.dict(app.config, {"DATABASE_PATH": database, "AUTH_REQUIRED": False}):
                response = app.test_client().get("/model-monitoring")
            self.assertEqual(response.status_code, 200)
            self.assertIn(f"Batch #{import_id}".encode(), response.data)
            report = {"file": "holdout.csv", "model_sha256": "abc123",
                      "evaluation_kind": "user_supplied_independence_unverified",
                      "metrics": evaluate_predictions([0, 1], [.1, .9])}
            save_model_evaluation(database, report)
            self.assertEqual(list_model_evaluations(database)[0]["source_name"], "holdout.csv")
            with patch.dict(app.config, {"DATABASE_PATH": database, "AUTH_REQUIRED": False}):
                self.assertIn(b"holdout.csv", app.test_client().get("/model-monitoring").data)

    def test_prediction_summary_and_fingerprint(self):
        summary = summarize_predictions([
            {"risk_level": "High", "waste_proba": .8},
            {"risk_level": "Low", "waste_proba": .2},
        ])
        self.assertEqual(summary["high_rate"], .5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.bin"
            path.write_bytes(b"test model")
            self.assertEqual(model_fingerprint(path), hashlib.sha256(b"test model").hexdigest())
