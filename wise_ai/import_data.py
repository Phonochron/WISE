"""Parsing and validation for uploaded stock datasets."""

import math
from io import BytesIO
from zipfile import BadZipFile, ZipFile

import pandas as pd

from .config import FEATURE_COLUMNS
from .validation import InputValidationError, validate_features


REQUIRED_DETAILS = ("Product_ID", "Product_Name", "Branch", "Category")
MAX_IMPORT_ROWS = 10_000


def read_uploaded_data(filename: str, content: bytes) -> pd.DataFrame:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in {"csv", "xlsx"}:
        raise InputValidationError("File must be CSV or XLSX")
    if not content:
        raise InputValidationError("File is empty")

    try:
        if extension == "csv":
            df = pd.read_csv(BytesIO(content), encoding="utf-8-sig", dtype={key: str for key in REQUIRED_DETAILS})
        else:
            with ZipFile(BytesIO(content)) as archive:
                if len(archive.infolist()) > 200 or sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                    raise InputValidationError("XLSX expands beyond the allowed size")
            df = pd.read_excel(BytesIO(content), engine="openpyxl", dtype={key: str for key in REQUIRED_DETAILS})
    except (ValueError, UnicodeError, OSError, ImportError, BadZipFile, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise InputValidationError("File could not be read as CSV or XLSX") from exc

    if df.empty:
        raise InputValidationError("Dataset must contain at least one row")
    if len(df) > MAX_IMPORT_ROWS:
        raise InputValidationError(f"Dataset exceeds {MAX_IMPORT_ROWS:,} rows")

    required = [*REQUIRED_DETAILS, *FEATURE_COLUMNS]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise InputValidationError(f"Missing columns: {', '.join(missing)}")

    for column in REQUIRED_DETAILS:
        if df[column].isna().any() or df[column].str.strip().eq("").any():
            raise InputValidationError(f"{column} must not be empty")
        df[column] = df[column].str.strip()

    features = validate_features(df)
    df[FEATURE_COLUMNS] = features

    if "Waste_Amount" in df.columns:
        waste = pd.to_numeric(df["Waste_Amount"], errors="coerce")
        if waste.isna().any() or not waste.map(math.isfinite).all():
            raise InputValidationError("Waste_Amount must contain finite numbers")
        if (waste < 0).any():
            raise InputValidationError("Waste_Amount must be non-negative")
        df["Waste_Amount"] = waste

    return df
