"""Performance calculations for the betting tracker."""

from __future__ import annotations

from typing import Any

import pandas as pd

from config.defaults import PLAYER_PROP_BET_TYPES, SCORE_OR_ASSIST
from src.odds import missed_winnings, resolve_effective_odds, resolve_potential_payout
from src.parlay import is_multi_game_parlay, is_parlay_bet, is_same_game_parlay, parse_parlay_legs


def calculate_actual_return(row: dict[str, Any]) -> float | None:
    """Money returned from the bet based on the three outcomes."""
    status = row.get("status", "Pending")
    if status == "Bet Lost":
        return 0.0
    if status == "Bet Cashed Out":
        return float(row.get("cashout_amount") or 0)
    if status == "Bet Won":
        return float(resolve_potential_payout(row) or row.get("payout_amount") or 0)
    return None


def calculate_profit_loss(row: dict[str, Any]) -> float:
    status = row.get("status", "Pending")
    bet_amount = float(row.get("bet_amount") or 0)

    if status == "Bet Lost":
        return -bet_amount
    if status == "Bet Cashed Out":
        return float(row.get("cashout_amount") or 0) - bet_amount
    if status == "Bet Won":
        won = float(resolve_potential_payout(row) or row.get("payout_amount") or 0)
        return won - bet_amount
    return 0.0


def enrich_bets(bets: list[dict[str, Any]]) -> pd.DataFrame:
    if not bets:
        return pd.DataFrame()

    df = pd.DataFrame(bets)
    df["cashed_out"] = df["cashed_out"].fillna(False).astype(bool)
    df["profit_loss"] = df.apply(lambda row: calculate_profit_loss(row.to_dict()), axis=1)
    df["actual_return"] = df.apply(lambda row: calculate_actual_return(row.to_dict()), axis=1)
    df["effective_odds"] = df.apply(lambda row: resolve_effective_odds(row.to_dict()), axis=1)
    df["potential_payout_calc"] = df.apply(lambda row: resolve_potential_payout(row.to_dict()), axis=1)
    df["missed_winnings"] = df.apply(lambda row: missed_winnings(row.to_dict()), axis=1)
    df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
    df["settled"] = df["status"].isin(["Bet Won", "Bet Lost", "Bet Cashed Out"])
    if "bet_category" in df.columns:
        df["bet_category"] = df["bet_category"].fillna("Main Challenge")
    else:
        df["bet_category"] = "Main Challenge"
    return df


def get_summary_stats(df: pd.DataFrame, starting_bankroll: float = 1000.0) -> dict[str, Any]:
    if df.empty:
        return {
            "total_bets": 0,
            "settled_bets": 0,
            "pending_bets": 0,
            "total_wagered": 0.0,
            "settled_wagered": 0.0,
            "pending_wagered": 0.0,
            "pending_potential_win": 0.0,
            "total_payout": 0.0,
            "total_profit_loss": 0.0,
            "bets_won": 0,
            "bets_lost": 0,
            "bets_cashed_out": 0,
            "win_pct": 0.0,
            "loss_pct": 0.0,
            "cashout_pct": 0.0,
            "pending_pct": 0.0,
            "roi_pct": 0.0,
            "starting_bankroll": starting_bankroll,
            "current_bankroll": starting_bankroll,
            "total_winnings": 0.0,
            "potential_bankroll": starting_bankroll,
            "avg_bet_size": 0.0,
            "best_bet_profit": 0.0,
            "worst_bet_loss": 0.0,
            "total_missed_winnings": 0.0,
            "parlay_bets": 0,
        }

    settled = df[df["settled"]]
    pending_df = df[df["status"] == "Pending"]

    total_wagered = float(df["bet_amount"].sum())
    settled_wagered = float(settled["bet_amount"].sum()) if not settled.empty else 0.0
    pending_wagered = float(pending_df["bet_amount"].sum()) if not pending_df.empty else 0.0
    pending_potential = (
        float(pending_df["potential_payout_calc"].fillna(0).sum()) if not pending_df.empty else 0.0
    )

    total_payout = float(settled["actual_return"].fillna(0).sum()) if not settled.empty else 0.0
    settled_pl = float(settled["profit_loss"].sum()) if not settled.empty else 0.0

    won = int((df["status"] == "Bet Won").sum())
    lost = int((df["status"] == "Bet Lost").sum())
    cashed = int((df["status"] == "Bet Cashed Out").sum())
    pending_count = int((df["status"] == "Pending").sum())
    settled_count = won + lost + cashed
    total_count = len(df)

    missed = df.loc[df["status"] == "Bet Cashed Out", "missed_winnings"].fillna(0).sum()
    parlay_count = int(df["bet_type"].apply(is_parlay_bet).sum())

    current_bankroll = starting_bankroll + settled_pl - pending_wagered
    total_winnings = current_bankroll - starting_bankroll
    potential_bankroll = current_bankroll + pending_potential

    return {
        "total_bets": total_count,
        "settled_bets": settled_count,
        "pending_bets": pending_count,
        "total_wagered": total_wagered,
        "settled_wagered": settled_wagered,
        "pending_wagered": pending_wagered,
        "pending_potential_win": pending_potential,
        "total_payout": total_payout,
        "total_profit_loss": settled_pl,
        "bets_won": won,
        "bets_lost": lost,
        "bets_cashed_out": cashed,
        "win_pct": (won / settled_count * 100) if settled_count else 0.0,
        "loss_pct": (lost / settled_count * 100) if settled_count else 0.0,
        "cashout_pct": (cashed / settled_count * 100) if settled_count else 0.0,
        "pending_pct": (pending_count / total_count * 100) if total_count else 0.0,
        "roi_pct": (settled_pl / settled_wagered * 100) if settled_wagered else 0.0,
        "starting_bankroll": starting_bankroll,
        "current_bankroll": current_bankroll,
        "total_winnings": total_winnings,
        "potential_bankroll": potential_bankroll,
        "avg_bet_size": float(df["bet_amount"].mean()),
        "best_bet_profit": float(settled["profit_loss"].max()) if not settled.empty else 0.0,
        "worst_bet_loss": float(settled["profit_loss"].min()) if not settled.empty else 0.0,
        "total_missed_winnings": float(missed),
        "parlay_bets": parlay_count,
    }


def get_bankroll_over_time(df: pd.DataFrame, starting_bankroll: float = 1000.0) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["match_date", "bankroll", "cumulative_pl"])

    settled = df[df["settled"]].sort_values("match_date")
    if settled.empty:
        return pd.DataFrame(
            {"match_date": [df["match_date"].min()], "bankroll": [starting_bankroll], "cumulative_pl": [0.0]}
        )

    cumulative = settled["profit_loss"].cumsum()
    result = pd.DataFrame(
        {
            "match_date": settled["match_date"],
            "bankroll": starting_bankroll + cumulative,
            "cumulative_pl": cumulative,
        }
    )
    return result


def performance_by_group(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    grouped = (
        df.groupby("group_stage", as_index=False)
        .agg(
            bets=("id", "count"),
            wagered=("bet_amount", "sum"),
            profit_loss=("profit_loss", "sum"),
            wins=("status", lambda s: (s == "Bet Won").sum()),
        )
        .sort_values("profit_loss", ascending=False)
    )
    grouped["roi_pct"] = grouped.apply(
        lambda r: (r["profit_loss"] / r["wagered"] * 100) if r["wagered"] else 0.0,
        axis=1,
    )
    return grouped


def performance_by_category(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    grouped = (
        df.groupby("bet_category", as_index=False)
        .agg(
            bets=("id", "count"),
            wagered=("bet_amount", "sum"),
            profit_loss=("profit_loss", "sum"),
            wins=("status", lambda s: (s == "Bet Won").sum()),
            losses=("status", lambda s: (s == "Bet Lost").sum()),
            cashed_out=("status", lambda s: (s == "Bet Cashed Out").sum()),
        )
        .sort_values("profit_loss", ascending=False)
    )
    grouped["roi_pct"] = grouped.apply(
        lambda r: (r["profit_loss"] / r["wagered"] * 100) if r["wagered"] else 0.0,
        axis=1,
    )
    return grouped


def performance_by_bet_type(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    grouped = (
        df.groupby("bet_type", as_index=False)
        .agg(
            bets=("id", "count"),
            wagered=("bet_amount", "sum"),
            profit_loss=("profit_loss", "sum"),
            wins=("status", lambda s: (s == "Bet Won").sum()),
            losses=("status", lambda s: (s == "Bet Lost").sum()),
        )
    )
    settled = grouped["wins"] + grouped["losses"]
    grouped["win_pct"] = grouped.apply(
        lambda r: (r["wins"] / settled.loc[r.name] * 100) if settled.loc[r.name] else 0.0,
        axis=1,
    )
    grouped["roi_pct"] = grouped.apply(
        lambda r: (r["profit_loss"] / r["wagered"] * 100) if r["wagered"] else 0.0,
        axis=1,
    )
    return grouped


def team_performance(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    rows = []
    for _, bet in df.iterrows():
        if is_multi_game_parlay(bet["bet_type"]):
            for leg in parse_parlay_legs(bet.to_dict()):
                for team in (leg.get("team1"), leg.get("team2")):
                    if team:
                        rows.append(
                            {
                                "team": team,
                                "bets": 1,
                                "wagered": bet["bet_amount"],
                                "profit_loss": bet["profit_loss"],
                                "won": 1 if bet["status"] == "Bet Won" else 0,
                            }
                        )
        elif is_same_game_parlay(bet["bet_type"]):
            for team_col in ("team1", "team2"):
                team = bet[team_col]
                if team and team != "Multiple Games":
                    rows.append(
                        {
                            "team": team,
                            "bets": 1,
                            "wagered": bet["bet_amount"],
                            "profit_loss": bet["profit_loss"],
                            "won": 1 if bet["status"] == "Bet Won" else 0,
                        }
                    )
        elif bet["bet_type"] == "Match Outcome":
            for team_col in ("team1", "team2"):
                team = bet[team_col]
                rows.append(
                    {
                        "team": team,
                        "bets": 1,
                        "wagered": bet["bet_amount"],
                        "profit_loss": bet["profit_loss"],
                        "won": 1 if bet["status"] == "Bet Won" else 0,
                    }
                )

    if not rows:
        return pd.DataFrame()

    result = (
        pd.DataFrame(rows)
        .groupby("team", as_index=False)
        .agg({"bets": "sum", "wagered": "sum", "profit_loss": "sum", "won": "sum"})
        .sort_values("profit_loss", ascending=False)
    )
    result["win_pct"] = result.apply(
        lambda r: (r["won"] / r["bets"] * 100) if r["bets"] else 0.0,
        axis=1,
    )
    return result


def goalscorer_performance(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    gs = df[df["bet_type"].apply(lambda t: t in PLAYER_PROP_BET_TYPES or is_parlay_bet(t))].copy()
    if gs.empty:
        return pd.DataFrame()

    from src.parlay import parse_parlay_legs

    rows = []
    for _, bet in gs.iterrows():
        if is_parlay_bet(bet["bet_type"]):
            for leg in parse_parlay_legs(bet.to_dict()):
                if leg["leg_type"] in ("Goalscorer", "First Goalscorer", SCORE_OR_ASSIST):
                    rows.append({
                        "prediction": leg["prediction"],
                        "id": bet["id"],
                        "bet_amount": bet["bet_amount"],
                        "profit_loss": bet["profit_loss"],
                        "status": bet["status"],
                    })
        else:
            rows.append({
                "prediction": bet["prediction"],
                "id": bet["id"],
                "bet_amount": bet["bet_amount"],
                "profit_loss": bet["profit_loss"],
                "status": bet["status"],
            })

    if not rows:
        return pd.DataFrame()

    gs_expanded = pd.DataFrame(rows)
    result = (
        gs_expanded.groupby("prediction", as_index=False)
        .agg(
            bets=("id", "count"),
            wagered=("bet_amount", "sum"),
            profit_loss=("profit_loss", "sum"),
            wins=("status", lambda s: (s == "Bet Won").sum()),
        )
        .sort_values("profit_loss", ascending=False)
    )
    result["win_pct"] = result.apply(
        lambda r: (r["wins"] / r["bets"] * 100) if r["bets"] else 0.0,
        axis=1,
    )
    return result


def daily_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    tmp = df.copy()
    tmp["date"] = tmp["match_date"].dt.date
    return (
        tmp.groupby("date", as_index=False)
        .agg(
            bets=("id", "count"),
            wagered=("bet_amount", "sum"),
            profit_loss=("profit_loss", "sum"),
        )
    )


def _stage_bucket(group_stage: str) -> str:
    if not group_stage:
        return "Other"
    if str(group_stage).startswith("Group "):
        return "Group Stage"
    lower = group_stage.lower()
    if any(k in lower for k in ("round of", "quarter", "semi", "final", "third")):
        return "Knockout"
    if group_stage == "Multiple":
        return "Multi-Match Parlay"
    return "Other"


def performance_by_stage_type(df: pd.DataFrame) -> pd.DataFrame:
    """ROI and P/L split between group stage and knockout bets (settled only)."""
    if df.empty:
        return pd.DataFrame()
    settled = df[df["settled"]].copy()
    if settled.empty:
        return pd.DataFrame()
    settled["stage_type"] = settled["group_stage"].apply(_stage_bucket)
    grouped = (
        settled.groupby("stage_type", as_index=False)
        .agg(
            bets=("id", "count"),
            wagered=("bet_amount", "sum"),
            profit_loss=("profit_loss", "sum"),
            wins=("status", lambda s: (s == "Bet Won").sum()),
            losses=("status", lambda s: (s == "Bet Lost").sum()),
        )
        .sort_values("profit_loss", ascending=False)
    )
    grouped["roi_pct"] = grouped.apply(
        lambda r: (r["profit_loss"] / r["wagered"] * 100) if r["wagered"] else 0.0,
        axis=1,
    )
    grouped["win_pct"] = grouped.apply(
        lambda r: (r["wins"] / r["bets"] * 100) if r["bets"] else 0.0,
        axis=1,
    )
    return grouped


def performance_by_bet_type_settled(df: pd.DataFrame) -> pd.DataFrame:
    """Bet-type breakdown using settled bets only for accurate ROI."""
    if df.empty:
        return pd.DataFrame()
    settled = df[df["settled"]]
    if settled.empty:
        return pd.DataFrame()
    grouped = (
        settled.groupby("bet_type", as_index=False)
        .agg(
            bets=("id", "count"),
            wagered=("bet_amount", "sum"),
            profit_loss=("profit_loss", "sum"),
            wins=("status", lambda s: (s == "Bet Won").sum()),
            losses=("status", lambda s: (s == "Bet Lost").sum()),
        )
    )
    grouped["win_pct"] = grouped.apply(
        lambda r: (r["wins"] / r["bets"] * 100) if r["bets"] else 0.0,
        axis=1,
    )
    grouped["roi_pct"] = grouped.apply(
        lambda r: (r["profit_loss"] / r["wagered"] * 100) if r["wagered"] else 0.0,
        axis=1,
    )
    return grouped.sort_values("profit_loss", ascending=False)


def get_streak_stats(df: pd.DataFrame) -> dict[str, Any]:
    """Win/loss streaks from settled bets in chronological order."""
    settled = df[df["settled"]].sort_values(["match_date", "id"])
    empty = {
        "current_streak": 0,
        "current_type": "none",
        "best_win_streak": 0,
        "worst_loss_streak": 0,
        "last_results": [],
    }
    if settled.empty:
        return empty

    codes: list[str] = []
    for _, row in settled.iterrows():
        status = row["status"]
        if status == "Bet Won":
            codes.append("W")
        elif status == "Bet Lost":
            codes.append("L")
        else:
            codes.append("C")

    best_win = worst_loss = cur_win = cur_loss = 0
    for c in codes:
        if c == "W":
            cur_win += 1
            cur_loss = 0
            best_win = max(best_win, cur_win)
        elif c == "L":
            cur_loss += 1
            cur_win = 0
            worst_loss = max(worst_loss, cur_loss)
        else:
            cur_win = cur_loss = 0

    current_streak = 0
    current_type = "none"
    if codes:
        last = codes[-1]
        for c in reversed(codes):
            if c != last:
                break
            current_streak += 1
        current_type = {"W": "wins", "L": "losses", "C": "cash-outs"}.get(last, "none")

    return {
        "current_streak": current_streak,
        "current_type": current_type,
        "best_win_streak": best_win,
        "worst_loss_streak": worst_loss,
        "last_results": codes[-10:],
    }


def category_pl_over_time(df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative realized P/L per category over time."""
    if df.empty:
        return pd.DataFrame()
    settled = df[df["settled"]].sort_values(["match_date", "id"])
    if settled.empty:
        return pd.DataFrame()
    cumulative: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    for _, row in settled.iterrows():
        cat = row["bet_category"]
        cumulative[cat] = cumulative.get(cat, 0.0) + float(row["profit_loss"])
        rows.append({
            "match_date": row["match_date"],
            "bet_category": cat,
            "cumulative_pl": cumulative[cat],
        })
    return pd.DataFrame(rows)
