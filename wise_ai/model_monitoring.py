"""Prediction distribution monitoring and evaluation against external labels."""

from collections import Counter
from hashlib import sha256
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix, precision_recall_fscore_support, roc_auc_score

from .config import RISK_THRESHOLD_HIGH


def model_fingerprint(model_path: str | Path) -> str:
    digest = sha256()
    with Path(model_path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def summarize_predictions(records: list[dict]) -> dict:
    if not records:
        return {"count": 0, "average_probability": None, "high_count": 0, "high_rate": None,
                "risk_counts": {"Low": 0, "Medium": 0, "High": 0}}
    counts = Counter(record["risk_level"] for record in records)
    count = len(records)
    return {
        "count": count,
        "average_probability": round(sum(float(record["waste_proba"]) for record in records) / count, 4),
        "high_count": counts["High"],
        "high_rate": round(counts["High"] / count, 4),
        "risk_counts": {level: counts[level] for level in ("Low", "Medium", "High")},
    }


def evaluate_predictions(labels, probabilities) -> dict:
    y = np.asarray(labels)
    p = np.asarray(probabilities, dtype=float)
    if len(y) < 2 or len(y) != len(p) or not np.isin(y, [0, 1]).all() or len(np.unique(y)) != 2:
        raise ValueError("Evaluation requires matching arrays with both binary label classes")
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Probabilities must be finite values between 0 and 1")
    predicted = (p >= RISK_THRESHOLD_HIGH).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(y, predicted, average="binary", zero_division=0)
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    calibration = []
    for index in range(5):
        lower, upper = index / 5, (index + 1) / 5
        mask = (p >= lower) & (p < upper if upper < 1 else p <= upper)
        if mask.any():
            calibration.append({"range": f"{lower:.1f}-{upper:.1f}", "count": int(mask.sum()),
                                "average_prediction": round(float(p[mask].mean()), 4),
                                "observed_rate": round(float(y[mask].mean()), 4)})
    return {
        "sample_count": len(y), "positive_count": int(y.sum()),
        "threshold": RISK_THRESHOLD_HIGH,
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "average_precision": round(float(average_precision_score(y, p)), 4),
        "brier_score": round(float(brier_score_loss(y, p)), 4),
        "precision": round(float(precision), 4), "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "confusion": {"true_negative": int(tn), "false_positive": int(fp),
                      "false_negative": int(fn), "true_positive": int(tp)},
        "calibration": calibration,
    }
