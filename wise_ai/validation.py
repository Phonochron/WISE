"""Input contract shared by single-product and dataset prediction."""

import math
from collections.abc import Mapping

import pandas as pd

from .config import FEATURE_COLUMNS


class InputValidationError(ValueError):
    """User-provided prediction data does not meet the model input contract."""


INTEGER_FIELDS = {
    "Initial_Stock",
    "Sold_Quantity",
    "Remaining_Stock",
    "Expiry_Days_Left",
}
NONNEGATIVE_FIELDS = set(FEATURE_COLUMNS) - {"Temperature_(°C)"}


def validate_record(record: Mapping) -> dict[str, int | float]:
    if not isinstance(record, Mapping):
        raise InputValidationError("Expected a JSON object")

    missing = [field for field in FEATURE_COLUMNS if field not in record]
    if missing:
        raise InputValidationError(f"Missing fields: {', '.join(missing)}")

    values = {}
    for field in FEATURE_COLUMNS:
        value = record[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InputValidationError(f"{field} must be a number")
        if not math.isfinite(value):
            raise InputValidationError(f"{field} must be finite")
        if field in INTEGER_FIELDS and not float(value).is_integer():
            raise InputValidationError(f"{field} must be a whole number")
        if field in NONNEGATIVE_FIELDS and value < 0:
            raise InputValidationError(f"{field} must be non-negative")
        if field == "Discount_Applied" and value > 100:
            raise InputValidationError("Discount_Applied must be at most 100")
        values[field] = int(value) if field in INTEGER_FIELDS else float(value)
    return values


def validate_features(df: pd.DataFrame) -> pd.DataFrame:
    """Validate model columns while preserving the source DataFrame."""
    missing = [field for field in FEATURE_COLUMNS if field not in df.columns]
    if missing:
        raise InputValidationError(f"Missing columns: {', '.join(missing)}")
    if df.empty:
        raise InputValidationError("Dataset must contain at least one row")

    features = df[FEATURE_COLUMNS].copy()
    for field in FEATURE_COLUMNS:
        if pd.api.types.is_bool_dtype(features[field]):
            raise InputValidationError(f"{field} must be numeric")
        numeric = pd.to_numeric(features[field], errors="coerce")
        if numeric.isna().any():
            raise InputValidationError(f"{field} contains missing or non-numeric values")
        if not numeric.map(math.isfinite).all():
            raise InputValidationError(f"{field} must contain finite values")
        if field in INTEGER_FIELDS and not (numeric % 1 == 0).all():
            raise InputValidationError(f"{field} must contain whole numbers")
        if field in NONNEGATIVE_FIELDS and (numeric < 0).any():
            raise InputValidationError(f"{field} must contain non-negative values")
        if field == "Discount_Applied" and (numeric > 100).any():
            raise InputValidationError("Discount_Applied must be at most 100")
        features[field] = numeric
    return features
