import unittest
from datetime import date, timedelta

from test_product_workflow import ProductWorkflowTests
from wise_ai.data_store import get_product_outcome, list_outcomes
from wise_ai.outcome_reporting import OutcomeValidationError, summarize_outcomes, validate_outcome


class OutcomeValidationTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "outcome_date": date.today().isoformat(), "sold_units": "5",
            "donated_units": "2", "redistributed_units": "0", "wasted_units": "1",
            "revenue_value": "125000", "waste_value": "25000", "note": "Dihitung di toko",
        }

    def test_valid_and_invalid_outcomes(self):
        self.assertEqual(validate_outcome(self.data, 40)["sold_units"], 5)
        for change in (
            {"sold_units": "-1"}, {"sold_units": "1.5"}, {"sold_units": "50"},
            {"outcome_date": (date.today() + timedelta(days=1)).isoformat()},
            {"waste_value": "NaN"}, {"wasted_units": "0"},
            {"note": "x" * 501},
        ):
            with self.subTest(change=change), self.assertRaises(OutcomeValidationError):
                validate_outcome({**self.data, **change}, 40)


class OutcomeFlowTests(unittest.TestCase):
    setUp = ProductWorkflowTests.setUp
    import_rows = ProductWorkflowTests.import_rows
    def test_outcome_edit_history_report_and_batch_isolation(self):
        import_id = self.import_rows()
        self.assertEqual(self.client.get("/reports").status_code, 200)
        self.client.get(f"/products/{import_id}/0")
        with self.client.session_transaction() as session:
            token = session["review_token"]
        url = f"/products/{import_id}/0/outcome"
        data = {"review_token": token, "outcome_date": date.today().isoformat(),
                "sold_units": "5", "donated_units": "2", "redistributed_units": "0",
                "wasted_units": "1", "revenue_value": "125000", "waste_value": "25000", "note": "Catatan"}
        self.assertEqual(self.client.post(url, data={**data, "review_token": "bad"}).status_code, 400)
        self.assertEqual(self.client.post(url, data={**data, "sold_units": "45"}, follow_redirects=True).status_code, 200)
        self.assertIsNone(get_product_outcome(self.database_path, import_id, 0)[0])
        self.assertEqual(self.client.post(url, data=data).status_code, 302)
        self.assertEqual(self.client.post(url, data={**data, "sold_units": "4", "wasted_units": "2"}).status_code, 302)
        current, history = get_product_outcome(self.database_path, import_id, 0)
        self.assertEqual(current["sold_units"], 4)
        self.assertEqual(len(history), 2)
        rows, completed = list_outcomes(self.database_path, import_id)
        self.assertEqual(completed, 0)
        self.assertEqual(summarize_outcomes(rows)["totals"]["sold_units"], 4)
        report = self.client.get(f"/reports?import_id={import_id}")
        self.assertIn(b"Apel Merah", report.data)
        self.assertIn(b"25,000", report.data)
        self.assertEqual(self.client.get("/reports?import_id=99999").status_code, 404)
        newer = self.import_rows()
        self.assertEqual(self.client.post(url, data=data).status_code, 404)
        self.assertIn(b"Belum ada hasil operasional", self.client.get("/reports").data)
        self.assertIn(b"Apel Merah", self.client.get(f"/reports?import_id={import_id}").data)
        self.assertEqual(list_outcomes(self.database_path, newer)[0], [])
