"""Odds and payout helpers."""

from __future__ import annotations

from typing import Any


def combined_parlay_odds(outcome_odds: float | None, goalscorer_odds: float | None) -> float | None:
    if outcome_odds and goalscorer_odds and outcome_odds > 0 and goalscorer_odds > 0:
        return round(outcome_odds * goalscorer_odds, 2)
    return None


def potential_payout_from_odds(stake: float, odds: float | None) -> float | None:
    if odds and odds > 0 and stake > 0:
        return round(stake * odds, 2)
    return None


def parlay_potential_payout(
    stake: float,
    outcome_odds: float | None,
    goalscorer_odds: float | None,
) -> float | None:
    combined = combined_parlay_odds(outcome_odds, goalscorer_odds)
    return potential_payout_from_odds(stake, combined)


def resolve_potential_payout(row: dict[str, Any]) -> float | None:
    """Return potential payout: stake × total odds."""
    stake = float(row.get("bet_amount") or 0)
    return potential_payout_from_odds(stake, row.get("odds"))


def resolve_effective_odds(row: dict[str, Any]) -> float | None:
    odds = row.get("odds")
    return float(odds) if odds else None


def format_prediction(row: dict[str, Any]) -> str:
    from src.parlay import is_multi_game_parlay, is_parlay_bet, legs_to_prediction, parse_parlay_legs

    if is_parlay_bet(row.get("bet_type", "")):
        return legs_to_prediction(
            parse_parlay_legs(row),
            multi_game=is_multi_game_parlay(row.get("bet_type", "")),
        )
    return row.get("prediction") or ""


def missed_winnings(row: dict[str, Any]) -> float | None:
    """Amount left on the table when cashing out early."""
    if row.get("status") != "Bet Cashed Out":
        return None
    potential = resolve_potential_payout(row)
    cashout = row.get("cashout_amount")
    if potential is None or cashout is None:
        return None
    return round(float(potential) - float(cashout), 2)
