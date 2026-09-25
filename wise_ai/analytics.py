import pandas as pd


def get_waste_trend(df: pd.DataFrame, date_col: str | None = None) -> pd.DataFrame:
    """
    Contoh sederhana: kalau ada kolom tanggal, kita bisa group per hari.
    Kalau belum ada, fungsi ini bisa di-skip atau diganti dengan analisis lain.
    """
    if date_col is None or date_col not in df.columns:
        # Belum ada date, kita kembalikan summary global saja
        return pd.DataFrame()

    grouped = (
        df.groupby(date_col)
        .agg(
            total_waste=("Waste_Amount", "sum"),
            avg_waste_proba=("waste_proba", "mean"),
        )
        .reset_index()
    )
    return grouped


def get_stock_efficiency(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mengukur efisiensi stok per kategori:
    - avg_remaining_stock
    - avg_waste_proba
    """
    grouped = (
        df.groupby("Category")
        .agg(
            avg_remaining_stock=("Remaining_Stock", "mean"),
            avg_waste_proba=("waste_proba", "mean"),
        )
        .reset_index()
    )
    return grouped
