from pathlib import Path
import os

# Path utama project (otomatis dari file ini)
BASE_DIR = Path(__file__).resolve().parent.parent

# Path model machine learning
MODEL_PATH = BASE_DIR / "models" / "wise_model.pkl"

# Path dataset (kalau load dari raw)
RAW_DATA_PATH = BASE_DIR / "data" / "raw" / "dataset_1000.xlsx"

FEATURE_COLUMNS = [
    "Initial_Stock",
    "Sold_Quantity",
    "Remaining_Stock",
    "Expiry_Days_Left",
    "Price",
    "Discount_Applied",
    "Temperature_(°C)",
    "Historical_Avg_Sales",
]

# Threshold probabilitas risiko waste
RISK_THRESHOLD_HIGH = 0.7
RISK_THRESHOLD_MEDIUM = 0.4

# Batas hari kadaluarsa untuk alert
ALERT_EXPIRY_DAYS = 3


def get_server_config() -> dict:
    """Read local server settings when the development server starts."""
    host = os.getenv("WISE_HOST", "127.0.0.1")
    port_text = os.getenv("WISE_PORT", "5000")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError("WISE_PORT must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise ValueError("WISE_PORT must be an integer between 1 and 65535")

    debug_text = os.getenv("WISE_DEBUG", "false").lower()
    if debug_text not in {"true", "false", "1", "0"}:
        raise ValueError("WISE_DEBUG must be true, false, 1, or 0")

    return {"host": host, "port": port, "debug": debug_text in {"true", "1"}}
