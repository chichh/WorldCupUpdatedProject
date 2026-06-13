"""Import bets from a CSV backup exported by the app."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd

from src.database import parse_date

BET_FIELDS = (
    "match_date",
    "group_stage",
    "team1",
    "team2",
    "bet_type",
    "bet_category",
    "prediction",
    "bet_amount",
    "odds",
    "outcome_odds",
    "goalscorer_odds",
    "outcome_prediction",
    "goalscorer_prediction",
    "parlay_legs",
    "potential_payout",
    "final_score",
    "actual_result",
    "actual_goalscorer",
    "status",
    "cashout_amount",
    "payout_amount",
    "notes",
)

NUMERIC_FIELDS = {
    "bet_amount",
    "odds",
    "outcome_odds",
    "goalscorer_odds",
    "potential_payout",
    "cashout_amount",
    "payout_amount",
}


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _clean_field(field: str, value: Any) -> Any:
    if _is_empty(value):
        return None
    if field == "match_date":
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        return parse_date(str(value))
    if field in NUMERIC_FIELDS:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if field == "parlay_legs" and not isinstance(value, str):
        return str(value)
    return str(value).strip() if isinstance(value, str) else value


def parse_csv_backup(data: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse an exported CSV backup into bet records ready for add_bet."""
    errors: list[str] = []
    try:
        df = pd.read_csv(io.BytesIO(data))
    except Exception as exc:
        return [], [f"Could not read CSV file: {exc}"]

    if df.empty:
        return [], ["The CSV file has no rows."]

    missing = [field for field in ("team1", "team2", "bet_type", "bet_amount") if field not in df.columns]
    if missing:
        return [], [f"CSV is missing required columns: {', '.join(missing)}"]

    records: list[dict[str, Any]] = []
    for row_num, row in df.iterrows():
        if all(_is_empty(row.get(field)) for field in ("team1", "team2", "bet_type")):
            continue

        record: dict[str, Any] = {}
        for field in BET_FIELDS:
            if field in df.columns:
                record[field] = _clean_field(field, row.get(field))

        if _is_empty(record.get("match_date")):
            errors.append(f"Row {row_num + 2}: missing match date — skipped.")
            continue
        if _is_empty(record.get("team1")):
            errors.append(f"Row {row_num + 2}: missing team — skipped.")
            continue
        if _is_empty(record.get("team2")) and record.get("bet_type") != "Multiple Game Parlay":
            errors.append(f"Row {row_num + 2}: missing team — skipped.")
            continue
        if _is_empty(record.get("bet_type")):
            errors.append(f"Row {row_num + 2}: missing bet type — skipped.")
            continue
        if record.get("bet_amount") is None:
            errors.append(f"Row {row_num + 2}: missing bet amount — skipped.")
            continue

        record.setdefault("status", "Pending")
        record.setdefault("prediction", "")
        record.setdefault("notes", "")
        records.append(record)

    if not records and not errors:
        errors.append("No valid bet rows found in the CSV.")

    return records, errors
