"""What-if World Cup simulation (isolated from bets and live data)."""

from __future__ import annotations

import copy
from typing import Any

from src.worldcup_data import (
    KNOCKOUT_ROUNDS,
    _empty_standing,
    _winner_loser,
    format_team,
    get_flag_map,
    load_groups,
    load_schedule,
    match_has_score,
    resolve_knockout_team,
)

# Round of 32 third-place slot -> eligible group letters (from worldcup.json)
THIRD_PLACE_SLOT_GROUPS: dict[int, list[str]] = {
    74: ["A", "B", "C", "D", "F"],
    77: ["C", "D", "F", "G", "H"],
    79: ["C", "E", "F", "H", "I"],
    80: ["E", "H", "I", "J", "K"],
    81: ["B", "E", "F", "I", "J"],
    82: ["A", "E", "H", "I", "J"],
    85: ["E", "F", "G", "I", "J"],
    87: ["D", "E", "I", "J", "L"],
}


def group_match_key(match: dict[str, Any]) -> str:
    return f"{match['date']}|{match.get('group', '')}|{match['team1']}|{match['team2']}"


def get_group_stage_matches() -> list[dict[str, Any]]:
    return [m for m in load_schedule() if m.get("group")]


def split_played_upcoming() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    played, upcoming = [], []
    for m in get_group_stage_matches():
        (played if match_has_score(m) else upcoming).append(m)
    return played, upcoming


def _apply_result(row: dict[str, Any], gf: int, ga: int) -> None:
    row["played"] += 1
    row["gf"] += gf
    row["ga"] += ga
    row["gd"] = row["gf"] - row["ga"]
    if gf > ga:
        row["won"] += 1
        row["points"] += 3
    elif gf == ga:
        row["drawn"] += 1
        row["points"] += 1
    else:
        row["lost"] += 1


def compute_standings_from_matches(matches: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build group standings from a list of matches (played + simulated)."""
    groups = load_groups()
    standings: dict[str, dict[str, dict[str, Any]]] = {}
    for group in groups:
        standings[group["name"]] = {team: _empty_standing(team) for team in group["teams"]}

    for match in matches:
        if not match.get("group") or not match_has_score(match):
            continue
        group_name = match["group"]
        if group_name not in standings:
            continue
        t1, t2 = match["team1"], match["team2"]
        if t1 not in standings[group_name] or t2 not in standings[group_name]:
            continue
        s1, s2 = match["score"]["ft"]
        _apply_result(standings[group_name][t1], s1, s2)
        _apply_result(standings[group_name][t2], s2, s1)

    return {
        group_name: sorted(
            rows.values(),
            key=lambda r: (r["points"], r["gd"], r["gf"], r["team"]),
            reverse=True,
        )
        for group_name, rows in standings.items()
    }


def merge_with_simulated_scores(
    simulated: dict[str, tuple[int, int]],
) -> list[dict[str, Any]]:
    """Locked played results + user-entered scores for upcoming games."""
    merged: list[dict[str, Any]] = []
    for match in get_group_stage_matches():
        m = copy.deepcopy(match)
        key = group_match_key(m)
        if match_has_score(m):
            merged.append(m)
        elif key in simulated:
            s1, s2 = simulated[key]
            m["score"] = {"ft": [int(s1), int(s2)]}
            merged.append(m)
    return merged


def auto_qualifying_third_groups(standings: dict[str, list[dict[str, Any]]]) -> set[str]:
    """Pick the 8 best third-placed groups by stats."""
    thirds: list[dict[str, Any]] = []
    for group_name, rows in standings.items():
        if len(rows) < 3:
            continue
        letter = group_name.replace("Group ", "")
        thirds.append({"group": letter, **rows[2]})
    thirds.sort(key=lambda r: (r["points"], r["gd"], r["gf"], r["team"]), reverse=True)
    return {r["group"] for r in thirds[:8]}


def standings_to_position_codes(
    standings: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, str], dict[str, str]]:
    """Return (position codes like 1A, and third-place team per group letter)."""
    codes: dict[str, str] = {}
    third_by_group: dict[str, str] = {}
    for group_name, rows in standings.items():
        letter = group_name.replace("Group ", "")
        for i, row in enumerate(rows, start=1):
            codes[f"{i}{letter}"] = row["team"]
        if len(rows) >= 3:
            third_by_group[letter] = rows[2]["team"]
    return codes, third_by_group


def manual_standings_from_order(
    group_orders: dict[str, list[str]],
) -> dict[str, list[dict[str, Any]]]:
    """Build synthetic standings from user-picked 1st–4th finish order per group."""
    standings: dict[str, list[dict[str, Any]]] = {}
    synthetic_pts = [9, 6, 3, 0]
    for group_name, order in group_orders.items():
        rows = []
        for i, team in enumerate(order):
            rows.append({
                "team": team,
                "played": 3,
                "won": 0,
                "drawn": 0,
                "lost": 0,
                "gf": 0,
                "ga": 0,
                "gd": 0,
                "points": synthetic_pts[i] if i < 4 else 0,
            })
        standings[group_name] = rows
    return standings


def parse_third_place_code(code: str) -> list[str]:
    if not code.startswith("3"):
        return []
    body = code[1:]
    if "/" in body:
        return body.split("/")
    if len(body) == 1 and body.isalpha():
        return [body]
    return []


def resolve_third_place_slot(
    code: str,
    third_by_group: dict[str, str],
    qualified_groups: set[str],
    assigned_groups: set[str],
    match_num: int | None = None,
) -> str:
    """Resolve a third-place bracket code to a team name."""
    if match_num and match_num in THIRD_PLACE_SLOT_GROUPS:
        eligible = THIRD_PLACE_SLOT_GROUPS[match_num]
    else:
        eligible = parse_third_place_code(code)

    for letter in eligible:
        if letter in qualified_groups and letter not in assigned_groups and letter in third_by_group:
            assigned_groups.add(letter)
            return third_by_group[letter]
    return code


def build_simulated_knockout_bracket(
    group_codes: dict[str, str],
    third_by_group: dict[str, str],
    qualified_third_groups: set[str],
) -> dict[str, list[dict[str, Any]]]:
    """Build Round of 32 seeding from simulated group-stage outcomes."""
    matches = load_schedule()
    knockout_matches = [m for m in matches if m.get("round") in KNOCKOUT_ROUNDS]
    flags = get_flag_map()
    assigned_third: set[str] = set()
    match_results: dict[int, dict[str, str | None]] = {}

    def resolve(code: str, match_num: int | None = None) -> str:
        if code.startswith("3"):
            return resolve_third_place_slot(
                code, third_by_group, qualified_third_groups, assigned_third, match_num
            )
        return resolve_knockout_team(code, group_codes, match_results)

    bracket: dict[str, list[dict[str, Any]]] = {r: [] for r in KNOCKOUT_ROUNDS}

    for match in knockout_matches:
        round_name = match["round"]
        num = match.get("num")
        t1 = resolve(match["team1"], num)
        t2 = resolve(match["team2"], num)
        winner, _ = _winner_loser(match)

        bracket[round_name].append({
            "num": num,
            "date": match.get("date", ""),
            "time": match.get("time", ""),
            "team1": t1,
            "team2": t2,
            "team1_raw": match["team1"],
            "team2_raw": match["team2"],
            "team1_display": format_team(t1, flags),
            "team2_display": format_team(t2, flags),
            "score": "",
            "score_ft": None,
            "winner": winner,
            "winner_display": format_team(winner, flags) if winner else None,
            "ground": match.get("ground", ""),
            "played": match_has_score(match),
            "simulated": not match_has_score(match),
        })

    for round_name in bracket:
        bracket[round_name].sort(key=lambda m: m.get("num") or 0)
    return bracket


def run_score_simulation(simulated_scores: dict[str, tuple[int, int]]) -> dict[str, Any]:
    matches = merge_with_simulated_scores(simulated_scores)
    standings = compute_standings_from_matches(matches)
    qualified = auto_qualifying_third_groups(standings)
    codes, third_by_group = standings_to_position_codes(standings)
    bracket = build_simulated_knockout_bracket(codes, third_by_group, qualified)
    return {
        "standings": standings,
        "qualified_third_groups": qualified,
        "third_by_group": third_by_group,
        "position_codes": codes,
        "bracket": bracket,
        "matches_used": len(matches),
    }


def run_manual_simulation(
    group_orders: dict[str, list[str]],
    qualified_third_groups: set[str],
) -> dict[str, Any]:
    standings = manual_standings_from_order(group_orders)
    codes, third_by_group = standings_to_position_codes(standings)
    bracket = build_simulated_knockout_bracket(codes, third_by_group, qualified_third_groups)
    return {
        "standings": standings,
        "qualified_third_groups": qualified_third_groups,
        "third_by_group": third_by_group,
        "position_codes": codes,
        "bracket": bracket,
    }


def validate_manual_orders(group_orders: dict[str, list[str]]) -> str | None:
    groups = load_groups()
    for group in groups:
        name = group["name"]
        teams = group["teams"]
        order = group_orders.get(name, [])
        if len(order) != 4:
            return f"Pick all 4 positions for {name}."
        if set(order) != set(teams):
            return f"Invalid finishing order for {name} — use each team exactly once."
    return None
