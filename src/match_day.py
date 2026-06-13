"""Match-day schedule and bet linking."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from src.parlay import is_multi_game_parlay, parse_parlay_legs
from src.worldcup_data import format_score, format_team, get_flag_map, load_schedule, match_has_score


def get_wc_matches_on_date(match_date: str) -> list[dict[str, Any]]:
    target = match_date[:10]
    return [m for m in load_schedule() if str(m.get("date", ""))[:10] == target]


def bet_applies_to_date(bet: dict[str, Any], match_date: str) -> bool:
    target = match_date[:10]
    if str(bet.get("match_date", ""))[:10] == target:
        return True
    if is_multi_game_parlay(bet.get("bet_type", "")):
        for leg in parse_parlay_legs(bet):
            if str(leg.get("match_date", ""))[:10] == target:
                return True
    return False


def get_bets_on_date(df: pd.DataFrame, match_date: str) -> pd.DataFrame:
    if df.empty:
        return df
    target = match_date[:10]
    ids: set[int] = set()
    for _, row in df.iterrows():
        bet = row.to_dict()
        if bet_applies_to_date(bet, target):
            ids.add(int(bet["id"]))
    return df[df["id"].isin(ids)].copy()


def get_pending_bets_on_date(df: pd.DataFrame, match_date: str) -> pd.DataFrame:
    day_bets = get_bets_on_date(df, match_date)
    if day_bets.empty:
        return day_bets
    return day_bets[day_bets["status"] == "Pending"].copy()


def format_match_card(match: dict[str, Any], flags: dict[str, str] | None = None) -> dict[str, str]:
    flags = flags or get_flag_map()
    score = format_score(match) if match_has_score(match) else "vs"
    status = "Final" if match_has_score(match) else "Upcoming"
    return {
        "time": match.get("time", ""),
        "stage": match.get("group") or match.get("round", ""),
        "team1": format_team(match["team1"], flags),
        "team2": format_team(match["team2"], flags),
        "score": score,
        "status": status,
        "venue": match.get("ground", ""),
        "team1_raw": match["team1"],
        "team2_raw": match["team2"],
    }


def upcoming_match_dates() -> list[str]:
    """Dates with WC matches, from today onward."""
    today = date.today().isoformat()
    dates = sorted({str(m["date"])[:10] for m in load_schedule() if str(m.get("date", ""))[:10] >= today})
    return dates
