"""World Cup 2026 data: schedule, teams, standings, bracket from openfootball/worldcup.json."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BASE_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026"

REMOTE_FILES = {
    "worldcup_2026.json": f"{BASE_URL}/worldcup.json",
    "worldcup_teams.json": f"{BASE_URL}/worldcup.teams.json",
    "worldcup_groups.json": f"{BASE_URL}/worldcup.groups.json",
}

STAGE_ALIASES = {
    "Quarter-final": "Quarter-Final",
    "Semi-final": "Semi-Final",
    "Match for third place": "Third Place",
    "Final": "Final",
    "Round of 32": "Round of 32",
    "Round of 16": "Round of 16",
}

TEAM_ALIASES = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
}

REVERSE_TEAM_ALIASES = {v: k for k, v in TEAM_ALIASES.items()}

KNOCKOUT_ROUNDS = [
    "Round of 32",
    "Round of 16",
    "Quarter-final",
    "Semi-final",
    "Match for third place",
    "Final",
]


def _read_json(filename: str) -> Any:
    path = DATA_DIR / filename
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def refresh_all_from_remote() -> dict[str, bool]:
    """Download latest JSON files from GitHub. Returns success per file."""
    import urllib.request

    results: dict[str, bool] = {}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in REMOTE_FILES.items():
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                (DATA_DIR / filename).write_bytes(resp.read())
            results[filename] = True
        except Exception:
            results[filename] = False
    _clear_caches()
    return results


def _clear_caches() -> None:
    load_schedule.cache_clear()
    load_teams.cache_clear()
    load_groups.cache_clear()


def normalize_stage(match: dict[str, Any]) -> str:
    group = match.get("group")
    if group:
        return str(group)
    round_name = str(match.get("round", ""))
    return STAGE_ALIASES.get(round_name, round_name)


def resolve_team_name(name: str, known_teams: list[str] | None = None) -> str:
    mapped = TEAM_ALIASES.get(name, name)
    if not known_teams:
        return mapped
    if mapped in known_teams:
        return mapped
    for team in known_teams:
        if team.lower() == mapped.lower():
            return team
    return mapped


def team_variants(name: str) -> set[str]:
    names = {name, TEAM_ALIASES.get(name, name), REVERSE_TEAM_ALIASES.get(name, name)}
    return {n for n in names if n}


def teams_same(a: str, b: str) -> bool:
    return bool(team_variants(a) & team_variants(b))


@lru_cache(maxsize=1)
def load_schedule() -> list[dict[str, Any]]:
    data = _read_json("worldcup_2026.json")
    if not data:
        return []
    matches = data.get("matches", [])
    return sorted(matches, key=lambda m: (m.get("date", ""), m.get("num") or 0, m.get("team1", "")))


@lru_cache(maxsize=1)
def load_teams() -> list[dict[str, Any]]:
    data = _read_json("worldcup_teams.json")
    return data if isinstance(data, list) else []


@lru_cache(maxsize=1)
def load_groups() -> list[dict[str, Any]]:
    data = _read_json("worldcup_groups.json")
    if not data:
        return []
    return data.get("groups", [])


def get_flag_map() -> dict[str, str]:
    flags: dict[str, str] = {}
    for team in load_teams():
        icon = team.get("flag_icon", "")
        flags[team["name"]] = icon
        if team.get("name_normalised"):
            flags[team["name_normalised"]] = icon
        mapped = TEAM_ALIASES.get(team["name"])
        if mapped:
            flags[mapped] = icon
    return flags


def format_team(name: str, flags: dict[str, str] | None = None) -> str:
    flags = flags or get_flag_map()
    flag = flags.get(name) or flags.get(TEAM_ALIASES.get(name, "")) or flags.get(REVERSE_TEAM_ALIASES.get(name, "")) or ""
    return f"{flag} {name}".strip()


def match_has_score(match: dict[str, Any]) -> bool:
    score = match.get("score") or {}
    ft = score.get("ft")
    return isinstance(ft, list) and len(ft) == 2


def format_score(match: dict[str, Any]) -> str:
    if not match_has_score(match):
        return ""
    s1, s2 = match["score"]["ft"]
    return f"{s1}-{s2}"


def infer_match_result(match: dict[str, Any]) -> str:
    if not match_has_score(match):
        return ""
    s1, s2 = match["score"]["ft"]
    if s1 > s2:
        return "Team 1 Win"
    if s2 > s1:
        return "Team 2 Win"
    return "Draw"


def get_goalscorers_text(match: dict[str, Any]) -> str:
    scorers: list[str] = []
    for goal in match.get("goals1", []):
        if goal.get("owngoal"):
            scorers.append(f"{match['team2']} (OG: {goal['name']})")
        else:
            scorers.append(f"{match['team1']}: {goal['name']}")
    for goal in match.get("goals2", []):
        if goal.get("owngoal"):
            scorers.append(f"{match['team1']} (OG: {goal['name']})")
        else:
            scorers.append(f"{match['team2']}: {goal['name']}")
    return ", ".join(scorers)


def match_label(match: dict[str, Any]) -> str:
    stage = normalize_stage(match)
    num = match.get("num")
    prefix = f"#{num} · " if num else ""
    score = format_score(match)
    score_txt = f" ({score})" if score else ""
    return f"{prefix}{match['date']} · {stage} · {match['team1']} vs {match['team2']}{score_txt}"


def match_to_fields(match: dict[str, Any], known_teams: list[str] | None = None) -> dict[str, str]:
    return {
        "match_date": match["date"],
        "group_stage": normalize_stage(match),
        "team1": resolve_team_name(match["team1"], known_teams),
        "team2": resolve_team_name(match["team2"], known_teams),
    }


def get_schedule_filters(matches: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    stages = sorted({normalize_stage(m) for m in matches})
    rounds = sorted({str(m.get("round", "")) for m in matches if m.get("round")})
    return ["All stages"] + stages, ["All rounds"] + rounds


def filter_matches(
    matches: list[dict[str, Any]],
    stage_filter: str = "All stages",
    round_filter: str = "All rounds",
    search: str = "",
) -> list[dict[str, Any]]:
    result = matches
    if stage_filter != "All stages":
        result = [m for m in result if normalize_stage(m) == stage_filter]
    if round_filter != "All rounds":
        result = [m for m in result if m.get("round") == round_filter]
    if search.strip():
        q = search.strip().lower()
        result = [
            m
            for m in result
            if q in match_label(m).lower()
            or q in m["team1"].lower()
            or q in m["team2"].lower()
        ]
    return result


def find_match_index(matches: list[dict[str, Any]], fields: dict[str, str]) -> int | None:
    for i, m in enumerate(matches):
        normalized = match_to_fields(m)
        if (
            normalized["match_date"][:10] == str(fields.get("match_date", ""))[:10]
            and teams_same(normalized["team1"], fields.get("team1", ""))
            and teams_same(normalized["team2"], fields.get("team2", ""))
        ):
            return i
    return None


def _empty_standing(team: str) -> dict[str, Any]:
    return {
        "team": team,
        "played": 0,
        "won": 0,
        "drawn": 0,
        "lost": 0,
        "gf": 0,
        "ga": 0,
        "gd": 0,
        "points": 0,
    }


def compute_group_standings() -> dict[str, list[dict[str, Any]]]:
    """Compute standings per group from completed group-stage matches."""
    groups = load_groups()
    matches = [m for m in load_schedule() if m.get("group") and match_has_score(m)]
    standings: dict[str, dict[str, dict[str, Any]]] = {}

    for group in groups:
        group_name = group["name"]
        standings[group_name] = {team: _empty_standing(team) for team in group["teams"]}

    for match in matches:
        group_name = match.get("group")
        if not group_name or group_name not in standings:
            continue
        t1, t2 = match["team1"], match["team2"]
        if t1 not in standings[group_name] or t2 not in standings[group_name]:
            continue
        s1, s2 = match["score"]["ft"]
        for team, gf, ga, result in (
            (t1, s1, s2, "w" if s1 > s2 else ("d" if s1 == s2 else "l")),
            (t2, s2, s1, "w" if s2 > s1 else ("d" if s1 == s2 else "l")),
        ):
            row = standings[group_name][team]
            row["played"] += 1
            row["gf"] += gf
            row["ga"] += ga
            row["gd"] = row["gf"] - row["ga"]
            if result == "w":
                row["won"] += 1
                row["points"] += 3
            elif result == "d":
                row["drawn"] += 1
                row["points"] += 1
            else:
                row["lost"] += 1

    sorted_standings: dict[str, list[dict[str, Any]]] = {}
    for group_name, rows in standings.items():
        sorted_standings[group_name] = sorted(
            rows.values(),
            key=lambda r: (r["points"], r["gd"], r["gf"], r["team"]),
            reverse=True,
        )
    return sorted_standings


def get_group_position_codes() -> dict[str, str]:
    """Map codes like 1A, 2B to team names from current standings."""
    codes: dict[str, str] = {}
    for group_name, rows in compute_group_standings().items():
        letter = group_name.replace("Group ", "").strip()
        for i, row in enumerate(rows, start=1):
            codes[f"{i}{letter}"] = row["team"]
    return codes


def _winner_loser(match: dict[str, Any]) -> tuple[str | None, str | None]:
    if not match_has_score(match):
        return None, None
    s1, s2 = match["score"]["ft"]
    if s1 > s2:
        return match["team1"], match["team2"]
    if s2 > s1:
        return match["team2"], match["team1"]
    return None, None


def resolve_knockout_team(code: str, group_codes: dict[str, str], match_results: dict[int, dict[str, str | None]]) -> str:
    if re.fullmatch(r"\d+[A-L]", code):
        return group_codes.get(code, code)
    if re.fullmatch(r"W\d+", code):
        num = int(code[1:])
        return match_results.get(num, {}).get("winner") or code
    if re.fullmatch(r"L\d+", code):
        num = int(code[1:])
        return match_results.get(num, {}).get("loser") or code
    return code


def build_knockout_bracket() -> dict[str, list[dict[str, Any]]]:
    """Build knockout rounds with resolved team names and scores."""
    matches = load_schedule()
    group_codes = get_group_position_codes()
    knockout_matches = [m for m in matches if m.get("round") in KNOCKOUT_ROUNDS]

    match_results: dict[int, dict[str, str | None]] = {}
    for match in sorted(knockout_matches, key=lambda m: m.get("num") or 0):
        num = match.get("num")
        if num is None:
            continue
        winner, loser = _winner_loser(match)
        if winner:
            match_results[num] = {"winner": winner, "loser": loser}

    bracket: dict[str, list[dict[str, Any]]] = {r: [] for r in KNOCKOUT_ROUNDS}
    flags = get_flag_map()

    for match in knockout_matches:
        round_name = match["round"]
        num = match.get("num")
        t1 = resolve_knockout_team(match["team1"], group_codes, match_results)
        t2 = resolve_knockout_team(match["team2"], group_codes, match_results)
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
            "score": format_score(match),
            "score_ft": match.get("score", {}).get("ft"),
            "winner": winner,
            "winner_display": format_team(winner, flags) if winner else None,
            "ground": match.get("ground", ""),
            "played": match_has_score(match),
        })

    for round_name in bracket:
        bracket[round_name].sort(key=lambda m: m.get("num") or 0)
    return bracket


def get_group_matches(group_name: str | None = None) -> list[dict[str, Any]]:
    matches = [m for m in load_schedule() if m.get("group")]
    if group_name:
        matches = [m for m in matches if m.get("group") == group_name]
    return matches


def get_all_matches_with_display() -> list[dict[str, Any]]:
    flags = get_flag_map()
    rows = []
    for match in load_schedule():
        rows.append({
            "date": match.get("date", ""),
            "round": match.get("round", match.get("group", "")),
            "stage": normalize_stage(match),
            "team1": match["team1"],
            "team2": match["team2"],
            "team1_display": format_team(match["team1"], flags),
            "team2_display": format_team(match["team2"], flags),
            "score": format_score(match),
            "played": match_has_score(match),
            "ground": match.get("ground", ""),
            "num": match.get("num"),
            "goalscorers": get_goalscorers_text(match),
        })
    return rows


# Backward-compatible alias
def refresh_schedule_from_remote() -> bool:
    return refresh_all_from_remote().get("worldcup_2026.json", False)
