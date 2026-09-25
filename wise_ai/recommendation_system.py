
import pandas as pd


def generate_recommendations(df_with_risk: pd.DataFrame) -> pd.DataFrame:
    """
    Menerima DataFrame yang SUDAH punya kolom:
    - risk_level
    - Remaining_Stock
    - Expiry_Days_Left

    Menghasilkan rekomendasi untuk setiap produk:
    - action_discount   : persentase diskon yang disarankan
    - action_redistribute: True/False
    - action_donate     : True/False
    - action_recipe     : True/False (opsional promosi resep)
    """
    df = df_with_risk.copy()

    df["action_discount"] = df.apply(_suggest_discount, axis=1)
    df["action_redistribute"] = df.apply(_suggest_redistribute, axis=1)
    df["action_donate"] = df.apply(_suggest_donate, axis=1)
    df["action_recipe"] = df.apply(_suggest_recipe, axis=1)

    return df


def _suggest_discount(row) -> int:
    """Logika sederhana pengaturan diskon dinamis."""
    risk = row["risk_level"]
    expiry = row["Expiry_Days_Left"]
    remaining = row["Remaining_Stock"]

    if risk == "High":
        if expiry <= 1:
            return 40
        return 30
    elif risk == "Medium":
        if remaining > 50:
            return 20
        return 10
    else:
        return 0


def _suggest_redistribute(row) -> bool:
    """
    Redistribusi stok ke cabang lain jika stok banyak dan risk Medium/High.
    (nanti bisa dihubungkan dengan data cabang di level lanjut)
    """
    return (row["risk_level"] in ["Medium", "High"]) and (row["Remaining_Stock"] > 50)


def _suggest_donate(row) -> bool:
    """
    Donasi jika risk High dan tinggal sedikit hari kadaluarsa.
    """
    return (row["risk_level"] == "High") and (row["Expiry_Days_Left"] <= 2)


def _suggest_recipe(row) -> bool:
    """
    Rekomendasi resep untuk promosi ke pelanggan.
    Di sini contoh: produk Bakery/Fruit sering dipromosikan.
    """
    name = str(row.get("Category", "")).lower()
    return any(k in name for k in ["bakery", "fruit"])
