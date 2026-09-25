"""Product browsing and human review presentation rules."""

import pandas as pd


RISK_LABELS = {"High": "Tinggi", "Medium": "Sedang", "Low": "Rendah"}
REVIEW_LABELS = {
    "pending": "Belum ditinjau",
    "approved": "Disetujui",
    "rejected": "Ditolak",
    "completed": "Ditandai selesai",
}
ACTION_LABELS = {
    "discount": "Diskon",
    "redistribute": "Redistribusi stok",
    "donate": "Donasi",
    "recipe": "Promosi resep",
    "monitor": "Pantau produk",
}


def filter_products(df: pd.DataFrame, query: str = "", branch: str = "", category: str = "", risk: str = "", attention: bool = False) -> pd.DataFrame:
    result = df.copy()
    if query:
        text = query.casefold()
        mask = result["Product_ID"].astype(str).str.casefold().str.contains(text, regex=False, na=False)
        mask |= result["Product_Name"].astype(str).str.casefold().str.contains(text, regex=False, na=False)
        result = result[mask]
    if branch:
        result = result[result["Branch"] == branch]
    if category:
        result = result[result["Category"] == category]
    if risk:
        result = result[result["risk_level"] == risk]
    if attention:
        result = result[(result["Expiry_Days_Left"] <= 3) | (result["risk_level"] == "High")]
    return result.sort_values("waste_proba", ascending=False)


def recommended_actions(product: dict) -> list[dict[str, str]]:
    actions = []
    if product.get("action_discount", 0) > 0:
        actions.append({"key": "discount", "label": f"Diskon {product['action_discount']}%", "description": "Pertimbangkan diskon untuk mempercepat penjualan."})
    if product.get("action_redistribute"):
        actions.append({"key": "redistribute", "label": ACTION_LABELS["redistribute"], "description": "Tinjau ketersediaan dan kebutuhan cabang tujuan."})
    if product.get("action_donate"):
        actions.append({"key": "donate", "label": ACTION_LABELS["donate"], "description": "Pastikan produk dan penerima memenuhi persyaratan donasi."})
    if product.get("action_recipe"):
        actions.append({"key": "recipe", "label": ACTION_LABELS["recipe"], "description": "Gunakan sebagai ide promosi produk."})
    if not actions:
        actions.append({"key": "monitor", "label": ACTION_LABELS["monitor"], "description": "Belum ada tindakan khusus; lanjutkan pemantauan."})
    return actions
