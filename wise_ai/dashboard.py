
import pandas as pd


def get_overview_kpis(df: pd.DataFrame) -> dict:
    """
    Mengembalikan ringkasan KPI untuk ditampilkan di dashboard:
    - total_products
    - high_risk_products
    - total_waste_amount (jika ada kolom Waste_Amount)
    """
    total_products = len(df)
    high_risk_products = (df["risk_level"] == "High").sum()

    total_waste_amount = df.get("Waste_Amount", pd.Series([0] * len(df))).sum()

    return {
        "total_products": int(total_products),
        "high_risk_products": int(high_risk_products),
        "total_waste_amount": float(total_waste_amount),
    }


def get_critical_products(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """
    Mengambil daftar produk paling kritis berdasarkan:
    - risk_level 'High'
    - kemudian sort by waste_proba desc
    """
    critical = df[df["risk_level"] == "High"].copy()
    critical = critical.sort_values(by="waste_proba", ascending=False)
    return critical.head(top_n)


def get_branch_performance(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mengelompokkan berdasarkan Branch dan menghitung:
    - avg_waste_proba
    - total_waste_amount (jika ada)
    - count_products
    """
    if "Waste_Amount" not in df.columns:
        df["Waste_Amount"] = 0

    grouped = (
        df.groupby("Branch")
        .agg(
            avg_waste_proba=("waste_proba", "mean"),
            total_waste_amount=("Waste_Amount", "sum"),
            total_products=("Product_ID", "count"),
        )
        .reset_index()
    )
    return grouped
