"""Evaluate the current model on a separately supplied labeled stock file."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from wise_ai.config import BASE_DIR, MODEL_PATH, RAW_DATA_PATH
from wise_ai.import_data import read_uploaded_data
from wise_ai.data_store import save_model_evaluation
from wise_ai.model_monitoring import evaluate_predictions, model_fingerprint
from wise_ai.prediction_engine import predict_waste_risk


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate WISE AI on a labeled CSV/XLSX file")
    parser.add_argument("data", type=Path, help="Labeled stock file with a binary Waste_Flag column")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    parser.add_argument("--save-to-db", action="store_true", help="Record this evaluation in the model monitoring page")
    parser.add_argument("--allow-bundled-smoke-test", action="store_true",
                        help="Allow bundled training/source files for smoke testing only")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Output file already exists; choose a new path")
    source = args.data.resolve()
    bundled_files = {RAW_DATA_PATH.resolve(), (BASE_DIR / "data" / "processed" / "dataset_with_risk_reco.xlsx").resolve()}
    bundled = source in bundled_files
    if bundled and not args.allow_bundled_smoke_test:
        parser.error("Bundled source data may overlap model training; use a separate labeled file")
    if bundled and args.save_to_db:
        parser.error("Bundled smoke tests cannot be saved as evaluation history")
    if not source.is_file() or source.stat().st_size > 10 * 1024 * 1024:
        parser.error("Data file must exist and be at most 10 MB")
    try:
        data = read_uploaded_data(source.name, source.read_bytes())
    except ValueError as exc:
        parser.error(str(exc))
    if "Waste_Flag" not in data:
        parser.error("Waste_Flag column is required")
    labels = pd.to_numeric(data["Waste_Flag"], errors="coerce")
    if labels.isna().any() or not labels.isin([0, 1]).all():
        parser.error("Waste_Flag must contain only 0 and 1")
    scored = predict_waste_risk(data)
    try:
        metrics = evaluate_predictions(labels.astype(int), scored["waste_proba"])
    except ValueError as exc:
        parser.error(str(exc))
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "file": source.name,
        "evaluation_kind": "bundled_smoke_test_not_independent" if bundled else "user_supplied_independence_unverified",
        "model_sha256": model_fingerprint(MODEL_PATH),
        "label_definition": "Waste_Flag=1 indicates a recorded waste case in the supplied file",
        "metrics": metrics,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.save_to_db:
        database = os.getenv("WISE_DATABASE_PATH", str(BASE_DIR / "instance" / "wise.db"))
        report_id = save_model_evaluation(database, report)
        print(f"Evaluation #{report_id} saved to model monitoring history")
    if args.output:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
        print(f"Evaluation report saved to {args.output}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
