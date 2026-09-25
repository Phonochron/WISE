# wise_ai/prediction_engine.py

import joblib
import pandas as pd
from threading import Lock

from .config import MODEL_PATH, RISK_THRESHOLD_HIGH, RISK_THRESHOLD_MEDIUM
from .data_preprocessing import prepare_features, prepare_single_record


_model_cache = None  # simple cache supaya tidak load model berkali-kali
_model_cache_key = None
_model_lock = Lock()


def load_model():
    """Reload the model if its artifact changes while the server is running."""
    global _model_cache, _model_cache_key
    stat = MODEL_PATH.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    if _model_cache_key != key:
        with _model_lock:
            if _model_cache_key != key:
                loaded = joblib.load(MODEL_PATH)
                _model_cache = loaded
                _model_cache_key = key
    return _model_cache


def predict_waste_risk(df_products: pd.DataFrame) -> pd.DataFrame:
    """
    Menerima DataFrame produk (raw),
    mengembalikan DataFrame dengan kolom tambahan:
    - waste_proba  : probabilitas waste (0–1)
    - risk_level   : 'Low' / 'Medium' / 'High'
    """
    X = prepare_features(df_products)
    model = load_model()
    proba = model.predict_proba(X)[:, 1]  # probabilitas kelas 1 (waste)

    df_result = df_products.copy()
    df_result["waste_proba"] = proba
    df_result["risk_level"] = df_result["waste_proba"].apply(_label_risk_level)

    return df_result


def predict_single_product(record: dict) -> dict:
    """
    Prediksi satu produk (misalnya dari form web).
    Mengembalikan dict dengan probabilitas dan level risiko.
    """
    X = prepare_single_record(record)
    model = load_model()
    proba = float(model.predict_proba(X)[0, 1])
    risk_level = _label_risk_level(proba)

    return {
        "waste_proba": proba,
        "risk_level": risk_level,
    }


def _label_risk_level(p: float) -> str:
    """Mengubah probabilitas menjadi label risiko."""
    if p >= RISK_THRESHOLD_HIGH:
        return "High"
    if p >= RISK_THRESHOLD_MEDIUM:
        return "Medium"
    return "Low"

def run_full_pipeline(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Pipeline lengkap untuk:
    1) menyiapkan fitur
    2) menjalankan model prediksi waste
    3) menambahkan rekomendasi tindakan

    Digunakan untuk fitur upload data:
    - input: dataframe mentah dari file upload
    - output: dataframe yang sudah ada kolom probabilitas, risk_level, dan rekomendasi
    """
    df_pred = predict_waste_risk(df_raw)
    from .recommendation_system import generate_recommendations

    df_final = generate_recommendations(df_pred)

    return df_final
