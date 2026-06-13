"""Sync World Cup match results from GitHub into the bets database."""

from __future__ import annotations

from typing import Any

from src.database import get_all_bets, update_match_results
from src.worldcup_data import (
    format_score,
    get_goalscorers_text,
    infer_match_result,
    load_schedule,
    match_has_score,
    refresh_all_from_remote,
    resolve_team_name,
    teams_same,
)


def _find_db_teams(
    bets: list[dict[str, Any]],
    match_date: str,
    json_team1: str,
    json_team2: str,
) -> tuple[str, str] | None:
    """Find team names as stored in the DB for a JSON match."""
    date_prefix = match_date[:10]
    for bet in bets:
        if str(bet.get("match_date", ""))[:10] != date_prefix:
            continue
        db_t1, db_t2 = bet.get("team1", ""), bet.get("team2", "")
        if teams_same(db_t1, json_team1) and teams_same(db_t2, json_team2):
            return db_t1, db_t2
        if teams_same(db_t1, json_team2) and teams_same(db_t2, json_team1):
            return db_t1, db_t2
    return None


def sync_match_results_from_github(
    *,
    refresh_remote: bool = True,
    known_teams: list[str] | None = None,
) -> dict[str, int]:
    """
    Pull latest scores from openfootball/worldcup.json and update matching bets.
    Returns counts: refreshed_files, matches_updated, matches_skipped.
    """
    refreshed = 0
    if refresh_remote:
        results = refresh_all_from_remote()
        refreshed = sum(1 for ok in results.values() if ok)

    bets = get_all_bets()
    updated = 0
    skipped = 0

    for match in load_schedule():
        if not match_has_score(match):
            continue

        match_date = match["date"]
        json_t1, json_t2 = match["team1"], match["team2"]
        db_teams = _find_db_teams(bets, match_date, json_t1, json_t2)

        if db_teams:
            team1, team2 = db_teams
        else:
            team1 = resolve_team_name(json_t1, known_teams)
            team2 = resolve_team_name(json_t2, known_teams)

        final_score = format_score(match)
        actual_result = infer_match_result(match)
        actual_goalscorer = get_goalscorers_text(match)

        update_match_results(
            match_date,
            team1,
            team2,
            final_score,
            actual_result,
            actual_goalscorer,
        )
        updated += 1

    return {
        "refreshed_files": refreshed,
        "matches_updated": updated,
        "matches_skipped": skipped,
    }
