
import pandas as pd
from .config import FEATURE_COLUMNS, RAW_DATA_PATH
from .validation import validate_features, validate_record


def load_raw_data(path: str | None = None) -> pd.DataFrame:
    """
    Load dataset mentah dari Excel.
    Jika path None, pakai default RAW_DATA_PATH dari config.
    """
    file_path = path or RAW_DATA_PATH
    df = pd.read_excel(file_path)
    return df


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ambil hanya kolom fitur yang dipakai model.
    Pastikan urutan kolom sesuai dengan saat training.
    """
    return validate_features(df)


def prepare_single_record(record: dict) -> pd.DataFrame:
    """
    Menerima input satu produk dalam bentuk dict,
    lalu mengubah menjadi DataFrame 1 baris dengan kolom yang benar.
    Contoh record:
    {
        "Initial_Stock": 100,
        "Sold_Quantity": 60,
        ...
    }
    """
    return pd.DataFrame([validate_record(record)], columns=FEATURE_COLUMNS)
