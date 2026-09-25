import pandas as pd
from .config import ALERT_EXPIRY_DAYS


def get_expiry_alerts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mengambil produk yang mendekati kadaluarsa (<= ALERT_EXPIRY_DAYS)
    dan/atau berisiko 'High'.
    """
    if "risk_level" not in df.columns:
        df = df.copy()
        df["risk_level"] = "Unknown"

    mask = (df["Expiry_Days_Left"] <= ALERT_EXPIRY_DAYS) | (df["risk_level"] == "High")
    alerts = df[mask].copy()
    alerts = alerts.sort_values(by=["Expiry_Days_Left", "waste_proba"], ascending=[True, False])
    return alerts
