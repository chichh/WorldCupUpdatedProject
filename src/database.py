"""SQLite persistence for bets and settings."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

from config.defaults import (
    BET_CATEGORIES,
    BET_STATUSES,
    BET_TYPES,
    DEFAULT_BET_AMOUNT,
    DEFAULT_BET_CATEGORY,
    DEFAULT_GOALSCORERS,
    DEFAULT_STARTING_BANKROLL,
    DEFAULT_TEAMS,
    LEGACY_PARLAY,
    MATCH_OUTCOMES,
    MULTI_GAME_PARLAY,
    PARLAY_LEG_TYPES,
    SAME_GAME_PARLAY,
    SCORE_OR_ASSIST,
    STAGES,
)

from src.parlay import is_parlay_bet

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bets.db"


def _ensure_db_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection():
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_date TEXT NOT NULL,
                group_stage TEXT NOT NULL,
                team1 TEXT NOT NULL,
                team2 TEXT NOT NULL,
                bet_type TEXT NOT NULL,
                bet_category TEXT NOT NULL DEFAULT 'Main Challenge',
                prediction TEXT NOT NULL,
                bet_amount REAL NOT NULL DEFAULT 20,
                odds REAL,
                outcome_odds REAL,
                goalscorer_odds REAL,
                outcome_prediction TEXT,
                goalscorer_prediction TEXT,
                parlay_legs TEXT,
                potential_payout REAL,
                cashed_out INTEGER NOT NULL DEFAULT 0,
                final_score TEXT,
                actual_result TEXT,
                actual_goalscorer TEXT,
                status TEXT NOT NULL DEFAULT 'Pending',
                cashout_amount REAL,
                payout_amount REAL,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        _migrate_db(conn)
        _seed_defaults(conn)


def _migrate_db(conn: sqlite3.Connection) -> None:
    """Add new columns to existing databases."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(bets)").fetchall()}
    migrations = {
        "odds": "REAL",
        "outcome_odds": "REAL",
        "goalscorer_odds": "REAL",
        "outcome_prediction": "TEXT",
        "goalscorer_prediction": "TEXT",
        "potential_payout": "REAL",
        "cashed_out": "INTEGER NOT NULL DEFAULT 0",
        "bet_category": "TEXT DEFAULT 'Main Challenge'",
        "parlay_legs": "TEXT",
    }
    for column, col_type in migrations.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE bets ADD COLUMN {column} {col_type}")


def _seed_defaults(conn: sqlite3.Connection) -> None:
    defaults = {
        "teams": DEFAULT_TEAMS,
        "goalscorers": DEFAULT_GOALSCORERS,
        "stages": STAGES,
        "bet_statuses": BET_STATUSES,
        "bet_types": BET_TYPES,
        "match_outcomes": MATCH_OUTCOMES,
        "bet_categories": BET_CATEGORIES,
        "parlay_leg_types": PARLAY_LEG_TYPES,
        "default_bet_amount": DEFAULT_BET_AMOUNT,
        "starting_bankroll": DEFAULT_STARTING_BANKROLL,
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
    # Migrate bet types: Parlay -> Same Game Parlay + Multiple Game Parlay
    row = conn.execute("SELECT value FROM settings WHERE key = 'bet_types'").fetchone()
    if row:
        types = json.loads(row["value"])
        changed = False
        if LEGACY_PARLAY in types:
            idx = types.index(LEGACY_PARLAY)
            types[idx : idx + 1] = [SAME_GAME_PARLAY, MULTI_GAME_PARLAY]
            changed = True
        for new_type in (SAME_GAME_PARLAY, MULTI_GAME_PARLAY):
            if new_type not in types:
                types.append(new_type)
                changed = True
        if SCORE_OR_ASSIST not in types:
            if "Goalscorer" in types:
                types.insert(types.index("Goalscorer") + 1, SCORE_OR_ASSIST)
            else:
                types.append(SCORE_OR_ASSIST)
            changed = True
        if changed:
            conn.execute(
                "UPDATE settings SET value = ? WHERE key = 'bet_types'",
                (json.dumps(types),),
            )
    conn.execute(
        "UPDATE bets SET bet_type = ? WHERE bet_type = ?",
        (SAME_GAME_PARLAY, LEGACY_PARLAY),
    )
    row = conn.execute("SELECT value FROM settings WHERE key = 'parlay_leg_types'").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)",
            ("parlay_leg_types", json.dumps(PARLAY_LEG_TYPES)),
        )
    else:
        leg_types = json.loads(row["value"])
        leg_changed = False
        for leg_type in PARLAY_LEG_TYPES:
            if leg_type not in leg_types:
                if leg_type == SCORE_OR_ASSIST and "Goalscorer" in leg_types:
                    leg_types.insert(leg_types.index("Goalscorer") + 1, leg_type)
                else:
                    leg_types.append(leg_type)
                leg_changed = True
        if leg_changed:
            conn.execute(
                "UPDATE settings SET value = ? WHERE key = 'parlay_leg_types'",
                (json.dumps(leg_types),),
            )


def get_setting(key: str, fallback: Any = None) -> Any:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return fallback
        return json.loads(row["value"])


def set_setting(key: str, value: Any) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )


def add_team(name: str) -> bool:
    """Add a team to the teams list. Returns True if added."""
    cleaned = name.strip()
    if not cleaned:
        return False
    teams = get_setting("teams", [])
    if cleaned in teams:
        return True
    teams.append(cleaned)
    teams.sort(key=str.lower)
    set_setting("teams", teams)
    return True


def _normalize_bet(bet: dict[str, Any]) -> dict[str, Any]:
    """Fill derived fields and normalize outcome state."""
    from src.odds import potential_payout_from_odds
    from src.parlay import normalize_parlay_bet

    bet_type = bet.get("bet_type", "")
    status = bet.get("status", "Pending")

    bet["cashed_out"] = status == "Bet Cashed Out"
    bet["bet_category"] = bet.get("bet_category") or DEFAULT_BET_CATEGORY

    if status == "Bet Lost":
        bet["payout_amount"] = None
        bet["cashout_amount"] = None
    elif status == "Bet Won":
        bet["cashout_amount"] = None
    elif status == "Bet Cashed Out":
        bet["payout_amount"] = None

    stake = float(bet.get("bet_amount") or 0)

    if is_parlay_bet(bet_type):
        normalize_parlay_bet(bet)

    bet["potential_payout"] = potential_payout_from_odds(stake, bet.get("odds"))

    if status == "Bet Won" and bet.get("potential_payout"):
        bet["payout_amount"] = bet["potential_payout"]

    return bet


def add_bet(bet: dict[str, Any]) -> int:
    bet = _normalize_bet(bet)
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bets (
                match_date, group_stage, team1, team2, bet_type, bet_category, prediction,
                bet_amount, odds, outcome_odds, goalscorer_odds,
                outcome_prediction, goalscorer_prediction, parlay_legs, potential_payout, cashed_out,
                final_score, actual_result, actual_goalscorer,
                status, cashout_amount, payout_amount, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bet["match_date"],
                bet["group_stage"],
                bet["team1"],
                bet["team2"],
                bet["bet_type"],
                bet.get("bet_category", DEFAULT_BET_CATEGORY),
                bet.get("prediction", ""),
                bet.get("bet_amount", DEFAULT_BET_AMOUNT),
                bet.get("odds"),
                bet.get("outcome_odds"),
                bet.get("goalscorer_odds"),
                bet.get("outcome_prediction"),
                bet.get("goalscorer_prediction"),
                bet.get("parlay_legs"),
                bet.get("potential_payout"),
                1 if bet.get("cashed_out") else 0,
                bet.get("final_score"),
                bet.get("actual_result"),
                bet.get("actual_goalscorer"),
                bet.get("status", "Pending"),
                bet.get("cashout_amount"),
                bet.get("payout_amount"),
                bet.get("notes", ""),
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)


def update_bet(bet_id: int, bet: dict[str, Any]) -> None:
    bet = _normalize_bet(bet)
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE bets SET
                match_date = ?, group_stage = ?, team1 = ?, team2 = ?,
                bet_type = ?, bet_category = ?, prediction = ?, bet_amount = ?,
                odds = ?, outcome_odds = ?, goalscorer_odds = ?,
                outcome_prediction = ?, goalscorer_prediction = ?, parlay_legs = ?,
                potential_payout = ?, cashed_out = ?,
                final_score = ?, actual_result = ?, actual_goalscorer = ?,
                status = ?, cashout_amount = ?, payout_amount = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                bet["match_date"],
                bet["group_stage"],
                bet["team1"],
                bet["team2"],
                bet["bet_type"],
                bet.get("bet_category", DEFAULT_BET_CATEGORY),
                bet.get("prediction", ""),
                bet.get("bet_amount", DEFAULT_BET_AMOUNT),
                bet.get("odds"),
                bet.get("outcome_odds"),
                bet.get("goalscorer_odds"),
                bet.get("outcome_prediction"),
                bet.get("goalscorer_prediction"),
                bet.get("parlay_legs"),
                bet.get("potential_payout"),
                1 if bet.get("cashed_out") else 0,
                bet.get("final_score"),
                bet.get("actual_result"),
                bet.get("actual_goalscorer"),
                bet.get("status", "Pending"),
                bet.get("cashout_amount"),
                bet.get("payout_amount"),
                bet.get("notes", ""),
                now,
                bet_id,
            ),
        )


def delete_bet(bet_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM bets WHERE id = ?", (bet_id,))


def get_all_bets() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM bets ORDER BY match_date, id").fetchall()
        result = []
        for row in rows:
            bet = dict(row)
            bet["cashed_out"] = bool(bet.get("cashed_out", 0))
            bet["bet_category"] = bet.get("bet_category") or DEFAULT_BET_CATEGORY
            result.append(bet)
        return result


def get_bet(bet_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone()
        return dict(row) if row else None


def quick_settle_bet(bet_id: int, status: str, cashout_amount: float | None = None) -> bool:
    """Update a bet's outcome without opening the full edit form."""
    bet = get_bet(bet_id)
    if not bet or bet.get("status") != "Pending":
        return False
    if status not in ("Bet Won", "Bet Lost", "Bet Cashed Out"):
        return False
    bet["status"] = status
    if status == "Bet Cashed Out":
        bet["cashout_amount"] = float(cashout_amount or 0)
    update_bet(bet_id, bet)
    return True


def get_unique_matches() -> list[dict[str, Any]]:
    """Return one row per unique match for the Match Results sheet."""
    from src.parlay import is_multi_game_parlay, parse_parlay_legs

    bets = get_all_bets()
    seen: dict[str, dict[str, Any]] = {}
    for bet in bets:
        if is_multi_game_parlay(bet.get("bet_type", "")):
            for leg in parse_parlay_legs(bet):
                t1, t2 = leg.get("team1"), leg.get("team2")
                if not t1 or not t2:
                    continue
                leg_date = leg.get("match_date") or bet["match_date"]
                key = f"{leg_date}|{t1}|{t2}"
                if key not in seen:
                    seen[key] = {
                        "match_date": leg_date,
                        "group_stage": leg.get("group_stage") or bet.get("group_stage") or "",
                        "team1": t1,
                        "team2": t2,
                        "final_score": bet.get("final_score") or "",
                        "actual_result": bet.get("actual_result") or "",
                        "actual_goalscorer": bet.get("actual_goalscorer") or "",
                    }
            continue
        if bet.get("team1") == "Multiple Games":
            continue
        key = f"{bet['match_date']}|{bet['team1']}|{bet['team2']}"
        if key not in seen:
            seen[key] = {
                "match_date": bet["match_date"],
                "group_stage": bet["group_stage"],
                "team1": bet["team1"],
                "team2": bet["team2"],
                "final_score": bet.get("final_score") or "",
                "actual_result": bet.get("actual_result") or "",
                "actual_goalscorer": bet.get("actual_goalscorer") or "",
            }
    return sorted(seen.values(), key=lambda m: m["match_date"])


def update_match_results(
    match_date: str,
    team1: str,
    team2: str,
    final_score: str,
    actual_result: str,
    actual_goalscorer: str,
) -> None:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE bets SET
                final_score = ?, actual_result = ?, actual_goalscorer = ?, updated_at = ?
            WHERE match_date = ? AND team1 = ? AND team2 = ?
            """,
            (
                final_score,
                actual_result,
                actual_goalscorer,
                now,
                match_date,
                team1,
                team2,
            ),
        )


def import_bets_from_records(records: list[dict[str, Any]]) -> int:
    count = 0
    for record in records:
        add_bet(record)
        count += 1
    return count


def clear_all_bets() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM bets")


def parse_date(value: str | date | datetime | None) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)
