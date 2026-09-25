"""Validate manually reported product outcomes and summarize a single import."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation


class OutcomeValidationError(ValueError):
    pass


UNIT_FIELDS = ("sold_units", "donated_units", "redistributed_units", "wasted_units")
VALUE_FIELDS = ("revenue_value", "waste_value")


def validate_outcome(form, remaining_stock: int) -> dict:
    try:
        outcome_date = date.fromisoformat(form.get("outcome_date", ""))
    except ValueError as exc:
        raise OutcomeValidationError("Tanggal hasil tidak valid.") from exc
    if outcome_date > date.today():
        raise OutcomeValidationError("Tanggal hasil tidak boleh di masa depan.")
    result = {"outcome_date": outcome_date.isoformat()}
    for field in UNIT_FIELDS:
        raw = str(form.get(field, "")).strip()
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 12:
            raise OutcomeValidationError("Jumlah unit harus berupa bilangan bulat nonnegatif.")
        result[field] = int(raw)
    total = sum(result[field] for field in UNIT_FIELDS)
    if total == 0 or total > int(remaining_stock):
        raise OutcomeValidationError("Total hasil harus 1 sampai jumlah sisa stok saat impor.")
    for field in VALUE_FIELDS:
        raw = str(form.get(field, "")).strip()
        if not raw:
            result[field] = None
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise OutcomeValidationError("Nilai rupiah harus berupa angka nonnegatif.") from exc
        if not value.is_finite() or value < 0 or value > Decimal("999999999999999"):
            raise OutcomeValidationError("Nilai rupiah harus berupa angka nonnegatif yang valid.")
        result[field] = float(value)
    if result["revenue_value"] and not result["sold_units"]:
        raise OutcomeValidationError("Nilai penjualan memerlukan unit terjual.")
    if result["waste_value"] and not result["wasted_units"]:
        raise OutcomeValidationError("Nilai waste memerlukan unit terbuang.")
    note = str(form.get("note", "")).strip()
    if len(note) > 500:
        raise OutcomeValidationError("Catatan maksimal 500 karakter.")
    result["note"] = note
    return result


def summarize_outcomes(rows: list[dict]) -> dict:
    totals = {field: sum(row[field] for row in rows) for field in UNIT_FIELDS}
    totals.update({field: sum(row[field] for row in rows if row[field] is not None) for field in VALUE_FIELDS})
    coverage = {field: sum(row[field] is not None for row in rows) for field in VALUE_FIELDS}
    days = defaultdict(lambda: {field: 0 for field in UNIT_FIELDS})
    branches = defaultdict(lambda: {field: 0 for field in UNIT_FIELDS})
    for row in rows:
        for field in UNIT_FIELDS:
            days[row["outcome_date"]][field] += row[field]
            branches[row["Branch"]][field] += row[field]
    return {
        "count": len(rows), "totals": totals, "coverage": coverage,
        "days": [{"date": key, **days[key]} for key in sorted(days)],
        "branches": [{"branch": key, **branches[key]} for key in sorted(branches)],
    }
