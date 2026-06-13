"""Parlay leg helpers."""

from __future__ import annotations

import json
from typing import Any

from config.defaults import (
    BTTS_OPTIONS,
    LEGACY_PARLAY,
    MULTI_GAME_PARLAY,
    OVER_UNDER_OPTIONS,
    SAME_GAME_PARLAY,
)

TEXT_PREDICTION_PLACEHOLDERS = {
    "Goalscorer": "Player name (e.g. Lionel Messi)",
    "First Goalscorer": "Player name (e.g. Lionel Messi)",
    "To Score or Assist": "Player name (e.g. Jude Bellingham)",
    "Correct Score": "Score (e.g. 2-1)",
    "Other": "Your prediction",
}


def is_parlay_bet(bet_type: str) -> bool:
    return bet_type in (SAME_GAME_PARLAY, MULTI_GAME_PARLAY, LEGACY_PARLAY)


def is_same_game_parlay(bet_type: str) -> bool:
    return bet_type in (SAME_GAME_PARLAY, LEGACY_PARLAY)


def is_multi_game_parlay(bet_type: str) -> bool:
    return bet_type == MULTI_GAME_PARLAY


def uses_text_prediction(leg_type: str) -> bool:
    return leg_type in TEXT_PREDICTION_PLACEHOLDERS


def get_leg_prediction_options(
    leg_type: str,
    match_outcomes: list[str],
    goalscorers: list[str],
) -> list[str] | None:
    """Return dropdown options for a leg type, or None if free-text."""
    if uses_text_prediction(leg_type):
        return None
    mapping = {
        "Match Winner": match_outcomes,
        "Over/Under Goals": OVER_UNDER_OPTIONS,
        "Both Teams to Score": BTTS_OPTIONS,
    }
    return mapping.get(leg_type)


def parse_parlay_legs(bet: dict[str, Any]) -> list[dict[str, str]]:
    raw = bet.get("parlay_legs")
    if raw:
        if isinstance(raw, str):
            return json.loads(raw)
        return list(raw)

    legs: list[dict[str, str]] = []
    if bet.get("outcome_prediction"):
        legs.append({"leg_type": "Match Winner", "prediction": bet["outcome_prediction"]})
    if bet.get("goalscorer_prediction"):
        legs.append({"leg_type": "Goalscorer", "prediction": bet["goalscorer_prediction"]})
    return legs


def legs_to_prediction(legs: list[dict[str, str]], multi_game: bool = False) -> str:
    if not legs:
        return ""
    parts = []
    for leg in legs:
        if multi_game or leg.get("team1"):
            match = f"{leg.get('team1', '?')} vs {leg.get('team2', '?')}"
            parts.append(f"{match} — {leg['leg_type']}: {leg['prediction']}")
        else:
            parts.append(f"{leg['leg_type']}: {leg['prediction']}")
    return " | ".join(parts)


def serialize_parlay_legs(legs: list[dict[str, str]]) -> str:
    return json.dumps(legs)


def normalize_parlay_bet(bet: dict[str, Any]) -> None:
    """Populate parlay_legs and prediction on the bet dict in place."""
    bet_type = bet.get("bet_type", "")
    if bet_type == LEGACY_PARLAY:
        bet["bet_type"] = SAME_GAME_PARLAY
        bet_type = SAME_GAME_PARLAY

    legs = bet.get("parlay_legs")
    if isinstance(legs, str):
        legs = json.loads(legs)
    if not legs:
        legs = parse_parlay_legs(bet)

    multi_game = is_multi_game_parlay(bet_type)
    bet["parlay_legs"] = serialize_parlay_legs(legs) if legs else None
    bet["prediction"] = legs_to_prediction(legs, multi_game=multi_game)
    bet["outcome_prediction"] = None
    bet["goalscorer_prediction"] = None
    bet["outcome_odds"] = None
    bet["goalscorer_odds"] = None

    if multi_game and legs:
        bet["team1"] = "Multiple Games"
        bet["team2"] = ""
        bet["group_stage"] = bet.get("group_stage") or "Multiple"
        dates = [leg.get("match_date") for leg in legs if leg.get("match_date")]
        if dates:
            bet["match_date"] = min(dates)
