"""Streamlit page components for the betting tracker."""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config.defaults import DEFAULT_BET_AMOUNT, DEFAULT_BET_CATEGORY, PLAYER_PROP_BET_TYPES, SETTLED_OUTCOMES
from src.calculations import (
    category_pl_over_time,
    daily_summary,
    enrich_bets,
    get_bankroll_over_time,
    get_streak_stats,
    get_summary_stats,
    goalscorer_performance,
    performance_by_bet_type,
    performance_by_bet_type_settled,
    performance_by_category,
    performance_by_group,
    performance_by_stage_type,
    team_performance,
)
from src.odds import potential_payout_from_odds
from src.parlay import (
    TEXT_PREDICTION_PLACEHOLDERS,
    get_leg_prediction_options,
    is_multi_game_parlay,
    is_parlay_bet,
    is_same_game_parlay,
    legs_to_prediction,
    parse_parlay_legs,
    serialize_parlay_legs,
    uses_text_prediction,
)
from src.database import (
    add_bet,
    add_team,
    delete_bet,
    get_all_bets,
    get_setting,
    get_unique_matches,
    parse_date,
    quick_settle_bet,
    set_setting,
    update_bet,
    update_match_results,
)
from src.match_day import (
    format_match_card,
    get_bets_on_date,
    get_pending_bets_on_date,
    get_wc_matches_on_date,
    upcoming_match_dates,
)
from src.worldcup_data import (
    build_knockout_bracket,
    compute_group_standings,
    filter_matches,
    find_match_index,
    format_team,
    get_flag_map,
    get_goalscorers_text,
    get_schedule_filters,
    load_groups,
    load_schedule,
    match_has_score,
    match_label,
    match_to_fields,
)
from src.worldcup_sim import (
    auto_qualifying_third_groups,
    group_match_key,
    run_manual_simulation,
    run_score_simulation,
    split_played_upcoming,
    validate_manual_orders,
)
from src.worldcup_sync import sync_match_results_from_github


def _format_currency(value: float) -> str:
    return f"${value:,.2f}"


def _status_color(status: str) -> str:
    return {
        "Bet Won": "🟢",
        "Bet Lost": "🔴",
        "Bet Cashed Out": "🟡",
        "Pending": "⚪",
    }.get(status, "⚪")


def _maybe_sync_worldcup(force: bool = False) -> dict:
    """Refresh GitHub data and sync scores into bets (throttled to every 5 minutes)."""
    import time

    now = time.time()
    last = st.session_state.get("wc_last_sync", 0)
    if not force and now - last < 300:
        return st.session_state.get("wc_last_sync_result", {})

    teams = get_setting("teams", [])
    result = sync_match_results_from_github(refresh_remote=True, known_teams=teams)
    st.session_state.wc_last_sync = now
    st.session_state.wc_last_sync_result = result
    return result


def _render_sync_status(result: dict) -> None:
    updated = result.get("matches_updated", 0)
    refreshed = result.get("refreshed_files", 0)
    if refreshed:
        st.caption(f"Synced from [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json/tree/master/2026) — {updated} match results applied to your bets.")
    else:
        st.caption("Using cached schedule data (could not reach GitHub).")


def _render_knockout_bracket(bracket: dict | None = None, *, title_suffix: str = "") -> None:
    bracket = bracket or build_knockout_bracket()

    st.markdown(
        """
        <style>
        .ko-round { margin-bottom: 1.5rem; }
        .ko-round h4 { color: #1F4E79; border-bottom: 2px solid #1F4E79; padding-bottom: 4px; }
        .ko-match {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 10px 14px;
            margin: 8px 0;
            font-size: 0.95rem;
        }
        .ko-match .meta { color: #666; font-size: 0.8rem; margin-bottom: 6px; }
        .ko-team { display: flex; justify-content: space-between; padding: 3px 0; }
        .ko-team.winner { font-weight: 700; color: #006100; }
        .ko-score { font-weight: 700; min-width: 24px; text-align: right; }
        .ko-vs { text-align: center; color: #999; font-size: 0.75rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    round_order = [
        "Round of 32", "Round of 16", "Quarter-final",
        "Semi-final", "Match for third place", "Final",
    ]
    for round_name in round_order:
        matches = bracket.get(round_name, [])
        if not matches:
            continue
        st.markdown(f'<div class="ko-round"><h4>{round_name}{title_suffix}</h4></div>', unsafe_allow_html=True)
        cols = st.columns(2 if len(matches) > 4 else 1)
        for i, m in enumerate(matches):
            col = cols[i % len(cols)]
            s1, s2 = ("—", "—")
            if m.get("score_ft"):
                s1, s2 = str(m["score_ft"][0]), str(m["score_ft"][1])
            t1_cls = "winner" if m.get("winner") and m["winner"] == m["team1"] else ""
            t2_cls = "winner" if m.get("winner") and m["winner"] == m["team2"] else ""
            num = f"#{m['num']} · " if m.get("num") else ""
            meta = f"{num}{m.get('date', '')} {m.get('time', '')}".strip()
            html = f"""
            <div class="ko-match">
              <div class="meta">{meta}</div>
              <div class="ko-team {t1_cls}"><span>{m['team1_display']}</span><span class="ko-score">{s1}</span></div>
              <div class="ko-vs">vs</div>
              <div class="ko-team {t2_cls}"><span>{m['team2_display']}</span><span class="ko-score">{s2}</span></div>
            </div>
            """
            col.markdown(html, unsafe_allow_html=True)


def _render_standings_tables(standings: dict, flags: dict, *, highlight_top: int = 2) -> None:
    group_cols = st.columns(3)
    for idx, (group_name, rows) in enumerate(sorted(standings.items())):
        with group_cols[idx % 3]:
            st.markdown(f"**{group_name}**")
            table_rows = []
            for pos, row in enumerate(rows, start=1):
                marker = ""
                if pos <= highlight_top:
                    marker = " 🏆"
                elif pos == 3:
                    marker = " ◯"
                table_rows.append({
                    "#": pos,
                    "Team": format_team(row["team"], flags) + marker,
                    "P": row["played"],
                    "W": row["won"],
                    "D": row["drawn"],
                    "L": row["lost"],
                    "GF": row["gf"],
                    "GA": row["ga"],
                    "GD": row["gd"],
                    "Pts": row["points"],
                })
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)


def render_whatif() -> None:
    st.subheader("What-If Simulator")
    st.caption(
        "Explore scenarios without changing your bets or live tournament data. "
        "Completed group-stage matches are **locked** from [GitHub results](https://github.com/openfootball/worldcup.json/tree/master/2026)."
    )

    if "sim_scores" not in st.session_state:
        st.session_state.sim_scores = {}
    if "sim_qualified_third" not in st.session_state:
        st.session_state.sim_qualified_third = []

    played, upcoming = split_played_upcoming()
    flags = get_flag_map()
    actual_standings = compute_group_standings()

    col_reset, _ = st.columns([1, 4])
    if col_reset.button("Reset simulation", key="sim_reset"):
        st.session_state.sim_scores = {}
        st.session_state.sim_qualified_third = []
        st.rerun()

    mode = st.radio(
        "Simulation mode",
        [
            "Predict scores for upcoming games",
            "Pick group finish order & third-place qualifiers",
        ],
        horizontal=True,
        key="sim_mode",
    )

    sim_result = None

    if mode == "Predict scores for upcoming games":
        if played:
            with st.expander(f"Completed matches — {len(played)} locked", expanded=False):
                for m in played:
                    ft = m["score"]["ft"]
                    st.markdown(
                        f"🔒 {m['date']} · **{m['group']}** · "
                        f"{format_team(m['team1'], flags)} **{ft[0]}-{ft[1]}** {format_team(m['team2'], flags)}"
                    )

        st.markdown("#### Predict upcoming group-stage scores")
        st.caption("Check **Include** to count a result in the simulation (allows 0-0 draws).")
        new_scores: dict[str, tuple[int, int]] = dict(st.session_state.sim_scores)

        by_group: dict[str, list] = {}
        for m in upcoming:
            by_group.setdefault(m["group"], []).append(m)

        for group_name in sorted(by_group.keys()):
            st.markdown(f"**{group_name}**")
            for m in by_group[group_name]:
                key = group_match_key(m)
                existing = new_scores.get(key, (0, 0))
                c1, c2, c3, c4, c5, c6 = st.columns([3, 1, 1, 0.4, 1, 1])
                c1.markdown(f"{format_team(m['team1'], flags)} vs {format_team(m['team2'], flags)}")
                c2.caption(m["date"])
                include = c6.checkbox("Include", value=key in new_scores, key=f"sim_inc_{key}")
                s1 = c3.number_input("G1", min_value=0, max_value=20, value=existing[0], key=f"sim_s1_{key}", label_visibility="collapsed")
                c4.markdown("–")
                s2 = c5.number_input("G2", min_value=0, max_value=20, value=existing[1], key=f"sim_s2_{key}", label_visibility="collapsed")
                if include:
                    new_scores[key] = (int(s1), int(s2))
                elif key in new_scores:
                    del new_scores[key]

        st.session_state.sim_scores = new_scores
        sim_result = run_score_simulation(new_scores)

    else:
        st.markdown("#### Set finishing order per group")
        st.caption("🏆 = top 2 (qualify) · ◯ = 3rd place (may qualify as best third)")
        groups = load_groups()
        orders: dict[str, list[str]] = {}

        group_cols = st.columns(3)
        for idx, group in enumerate(groups):
            gname = group["name"]
            teams = group["teams"]
            current_rows = actual_standings.get(gname, [])
            default_order = [r["team"] for r in current_rows]
            for t in teams:
                if t not in default_order:
                    default_order.append(t)

            with group_cols[idx % 3]:
                st.markdown(f"**{gname}**")
                order = []
                for pos, label in enumerate(["1st", "2nd", "3rd", "4th"]):
                    default_team = default_order[pos] if pos < len(default_order) else teams[pos]
                    t_idx = teams.index(default_team) if default_team in teams else pos
                    order.append(
                        st.selectbox(label, teams, index=t_idx, key=f"sim_pos_{gname}_{pos}")
                    )
                orders[gname] = order

        all_letters = [g["name"].replace("Group ", "") for g in groups]
        third_options = {
            letter: format_team(
                actual_standings[f"Group {letter}"][2]["team"]
                if len(actual_standings.get(f"Group {letter}", [])) >= 3
                else "—",
                flags,
            )
            for letter in all_letters
        }
        default_qualified = (
            st.session_state.sim_qualified_third
            or sorted(auto_qualifying_third_groups(actual_standings))
        )

        st.markdown("#### Third-place qualifiers (pick exactly 8)")
        qualified = st.multiselect(
            "Groups whose 3rd-place team advances",
            options=all_letters,
            default=default_qualified[:8],
            format_func=lambda g: f"Group {g} — {third_options.get(g, g)}",
            key="sim_third_pick",
        )
        st.session_state.sim_qualified_third = qualified

        err = validate_manual_orders(orders)
        if err:
            st.error(err)
        elif len(qualified) != 8:
            st.warning(f"Select exactly **8** third-place groups ({len(qualified)} selected).")
        else:
            sim_result = run_manual_simulation(orders, set(qualified))

    if not sim_result:
        st.info("Configure the simulation above to see projected standings and knockout seeding.")
        return

    st.divider()
    st.markdown("### Simulated group standings")
    _render_standings_tables(sim_result["standings"], flags)

    qual_rows = []
    for letter in sorted(sim_result["qualified_third_groups"]):
        team = sim_result["third_by_group"].get(letter, "—")
        qual_rows.append({
            "Group": letter,
            "3rd-place team": format_team(team, flags),
            "Status": "Qualifies",
        })
    st.markdown("### Third-place teams advancing")
    st.dataframe(pd.DataFrame(qual_rows), use_container_width=True, hide_index=True)

    st.markdown("### Simulated Round of 32 matchups")
    st.caption("Knockout pairings based on your scenario. Later rounds show bracket placeholders (W74, etc.) until those games are played.")
    r32_bracket = {"Round of 32": sim_result["bracket"].get("Round of 32", [])}
    _render_knockout_bracket(r32_bracket, title_suffix=" (projected)")

    with st.expander("Full projected bracket structure"):
        _render_knockout_bracket(sim_result["bracket"], title_suffix=" (projected)")


def _add_form_prefix() -> str:
    if "add_form_id" not in st.session_state:
        st.session_state.add_form_id = 0
    return f"add_{st.session_state.add_form_id}_"


def _reset_add_form() -> None:
    st.session_state.add_form_id = st.session_state.get("add_form_id", 0) + 1


def _ensure_teams_in_list(*team_names: str) -> None:
    for name in team_names:
        if name and name not in ("Multiple Games", "TBD", "Other"):
            add_team(name)


def _render_match_details(
    teams: list[str],
    stages: list[str],
    key_prefix: str,
    existing: dict | None = None,
    show_add_team: bool = True,
) -> dict | None:
    """Pick a match from the WC schedule or enter details manually."""
    existing = existing or {}
    schedule_matches = load_schedule()
    has_schedule = bool(schedule_matches)

    if has_schedule:
        mode = st.radio(
            "Match selection",
            ["From World Cup schedule", "Enter manually"],
            horizontal=True,
            key=f"{key_prefix}match_mode",
        )
    else:
        mode = "Enter manually"
        st.caption("World Cup schedule unavailable — enter match details manually.")

    if mode == "From World Cup schedule":
        stage_filters, round_filters = get_schedule_filters(schedule_matches)
        f1, f2, f3 = st.columns([1, 1, 2])
        stage_filter = f1.selectbox("Filter by stage", stage_filters, key=f"{key_prefix}wc_stage")
        round_filter = f2.selectbox("Filter by round", round_filters, key=f"{key_prefix}wc_round")
        search = f3.text_input("Search teams", placeholder="e.g. Brazil", key=f"{key_prefix}wc_search")

        filtered = filter_matches(schedule_matches, stage_filter, round_filter, search)
        labels = ["— Select a match —"] + [match_label(m) for m in filtered]

        default_idx = 0
        if existing.get("team1") and existing.get("team2"):
            match_idx = find_match_index(filtered, existing)
            if match_idx is not None:
                default_idx = match_idx + 1

        pick = st.selectbox("World Cup match", labels, index=default_idx, key=f"{key_prefix}wc_pick")
        if pick == "— Select a match —":
            return None

        match = filtered[labels.index(pick) - 1]
        fields = match_to_fields(match, teams)
        st.caption(
            f"**{fields['match_date']}** · {fields['group_stage']} · "
            f"**{fields['team1']}** vs **{fields['team2']}**"
        )
        return fields

    col1, col2 = st.columns(2)
    default_date = existing.get("match_date")
    if default_date:
        try:
            date_val = date.fromisoformat(str(default_date)[:10])
        except ValueError:
            date_val = date.today()
    else:
        date_val = date.today()
    match_date = col1.date_input("Match Date", value=date_val, key=f"{key_prefix}date")
    stage_idx = stages.index(existing["group_stage"]) if existing.get("group_stage") in stages else 0
    group_stage = col2.selectbox("Group / Stage", stages, index=stage_idx, key=f"{key_prefix}stage")

    col_t1, col_t2 = st.columns(2)
    t1_idx = teams.index(existing["team1"]) if existing.get("team1") in teams else 0
    t2_idx = teams.index(existing["team2"]) if existing.get("team2") in teams else 0
    team1 = col_t1.selectbox("Team 1", teams, index=t1_idx, key=f"{key_prefix}t1")
    team2 = col_t2.selectbox("Team 2", teams, index=t2_idx, key=f"{key_prefix}t2")
    if show_add_team:
        _render_add_team_section(key_prefix.rstrip("_"))

    return {
        "match_date": parse_date(match_date),
        "group_stage": group_stage,
        "team1": team1,
        "team2": team2,
    }


def _render_add_team_section(key_prefix: str) -> None:
    """Inline UI to add a missing team to the global list."""
    with st.expander("Team not in the list? Add one"):
        new_team = st.text_input("New team name", key=f"{key_prefix}_new_team")
        if st.button("Add team", key=f"{key_prefix}_add_team"):
            if add_team(new_team):
                st.success(f"Added {new_team.strip()}")
                st.rerun()
            else:
                st.error("Enter a valid team name.")


def _validate_parlay_legs(parlay_legs: list[dict[str, str]] | None, multi_game: bool) -> str | None:
    if not parlay_legs:
        return "Please add at least two parlay legs."
    for i, leg in enumerate(parlay_legs, 1):
        if multi_game and not leg.get("match_date"):
            return f"Please select a World Cup match (or enter details) for leg {i}."
        if not leg.get("prediction"):
            return f"Please fill in a prediction for leg {i}."
        if multi_game:
            if not leg.get("team1") or not leg.get("team2"):
                return f"Please select both teams for leg {i}."
            if leg["team1"] == leg["team2"]:
                return f"Leg {i}: Team 1 and Team 2 must be different."
    return None


def _render_odds_fields(bet_type: str, prefix: str = "", existing: dict | None = None) -> dict:
    """Render odds input — for singles and parlays, one total odds field."""
    key = lambda name: f"{prefix}{name}" if prefix else name
    existing = existing or {}
    label = "Total Parlay Odds (decimal)" if is_parlay_bet(bet_type) else "Odds (decimal)"
    default = float(existing.get("odds") or 2.0)
    return {
        "odds": st.number_input(
            label, min_value=1.0, value=default, step=0.05, format="%.2f", key=key("odds")
        )
    }


def _render_parlay_legs(
    leg_types: list[str],
    match_outcomes: list[str],
    goalscorers: list[str],
    prefix: str = "",
    existing_bet: dict | None = None,
    multi_game: bool = False,
    stages: list[str] | None = None,
    teams: list[str] | None = None,
) -> tuple[list[dict[str, str]], str]:
    existing_legs = parse_parlay_legs(existing_bet or {})
    default_count = max(2, len(existing_legs)) if existing_legs else 2

    if multi_game:
        st.caption("Each leg is from a different match — pick from the World Cup schedule or enter manually.")

    num_legs = st.number_input(
        "Number of legs in parlay",
        min_value=2,
        max_value=10,
        value=default_count,
        step=1,
        key=f"{prefix}num_legs",
    )

    legs: list[dict[str, str]] = []
    for i in range(int(num_legs)):
        ex = existing_legs[i] if i < len(existing_legs) else {}
        st.markdown(f"**Leg {i + 1}**")

        leg_data: dict[str, str] = {}

        if multi_game and stages and teams:
            match_fields = _render_match_details(
                teams, stages, f"{prefix}leg{i}_", existing=ex, show_add_team=(i == 0),
            )
            if match_fields:
                leg_data.update(match_fields)
            else:
                leg_data.update({
                    "match_date": "",
                    "group_stage": "",
                    "team1": "",
                    "team2": "",
                })

        col1, col2 = st.columns(2)

        type_idx = leg_types.index(ex["leg_type"]) if ex.get("leg_type") in leg_types else 0
        leg_type = col1.selectbox("Bet type", leg_types, index=type_idx, key=f"{prefix}leg_type_{i}")

        if uses_text_prediction(leg_type):
            prediction = col2.text_input(
                "Prediction",
                value=ex.get("prediction", ""),
                placeholder=TEXT_PREDICTION_PLACEHOLDERS.get(leg_type, "Your prediction"),
                key=f"{prefix}leg_pred_{i}_{leg_type}",
            )
        else:
            options = get_leg_prediction_options(leg_type, match_outcomes, goalscorers) or []
            pred_idx = options.index(ex["prediction"]) if ex.get("prediction") in options else 0
            prediction = col2.selectbox(
                "Pick", options, index=pred_idx, key=f"{prefix}leg_pick_{i}_{leg_type}"
            )

        leg_data["leg_type"] = leg_type
        leg_data["prediction"] = prediction
        legs.append(leg_data)

    return legs, legs_to_prediction(legs, multi_game=multi_game)


def _render_settlement_fields(
    bet_amount: float,
    odds_info: dict,
    bet_type: str,
    prefix: str = "",
    existing: dict | None = None,
    allow_pending: bool = True,
) -> dict:
    """Three outcomes: Lost ($0), Cashed Out (partial), Won (full). Shows could've vs actually won."""
    key = lambda name: f"{prefix}{name}" if prefix else name
    existing = existing or {}

    options = (["Pending"] + SETTLED_OUTCOMES) if allow_pending else SETTLED_OUTCOMES
    current = existing.get("status", "Pending")
    if current not in options:
        current = "Pending" if allow_pending else SETTLED_OUTCOMES[0]

    st.markdown("**Bet result** — choose one")
    status = st.radio(
        "Outcome",
        options,
        index=options.index(current),
        horizontal=True,
        key=key("outcome"),
        label_visibility="collapsed",
    )

    couldve_won = potential_payout_from_odds(bet_amount, odds_info.get("odds"))

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Could've won**")
        st.caption("Stake × odds")
        if couldve_won is not None:
            st.metric("Full payout", _format_currency(couldve_won))
        else:
            st.warning("Enter odds above to calculate")

    cashout_amount = None
    payout_amount = None

    with col2:
        st.markdown("**Actually won**")
        if status == "Pending":
            st.info("Not settled — set result after the match")
        elif status == "Bet Lost":
            st.metric("Return", "$0.00")
        elif status == "Bet Cashed Out":
            st.caption("Enter what you received from the cash-out")
            cashout_amount = st.number_input(
                "Actually won ($)",
                min_value=0.0,
                value=float(existing.get("cashout_amount") or 0),
                step=1.0,
                key=key("cashout"),
            )
            if couldve_won and cashout_amount is not None:
                missed = couldve_won - cashout_amount
                if missed > 0:
                    st.caption(f"Left on table: {_format_currency(missed)}")
        elif status == "Bet Won":
            st.caption("Same as could've won")
            if couldve_won is not None:
                st.metric("Return", _format_currency(couldve_won))
                payout_amount = couldve_won
            else:
                st.warning("Enter odds to calculate payout")

    return {
        "status": status,
        "cashed_out": status == "Bet Cashed Out",
        "potential_payout": couldve_won,
        "cashout_amount": cashout_amount,
        "payout_amount": payout_amount,
    }


def _build_bet_payload(
    match_date,
    group_stage,
    team1,
    team2,
    bet_type,
    bet_amount,
    odds_info,
    settlement,
    prediction: str = "",
    parlay_legs: list[dict[str, str]] | None = None,
    final_score: str | None = None,
    actual_result: str | None = None,
    actual_goalscorer: str | None = None,
    notes: str = "",
    bet_category: str = DEFAULT_BET_CATEGORY,
) -> dict:
    payload = {
        "match_date": parse_date(match_date),
        "group_stage": group_stage,
        "team1": team1,
        "team2": team2,
        "bet_type": bet_type,
        "bet_category": bet_category,
        "prediction": prediction,
        "bet_amount": bet_amount,
        "final_score": final_score or None,
        "actual_result": actual_result or None,
        "actual_goalscorer": actual_goalscorer or None,
        "notes": notes,
        **settlement,
        **{k: v for k, v in odds_info.items() if v is not None},
    }
    if is_parlay_bet(bet_type) and parlay_legs:
        payload["parlay_legs"] = serialize_parlay_legs(parlay_legs)
    return payload


def _render_single_prediction(
    bet_type: str,
    match_outcomes: list[str],
    goalscorers: list[str],
    prefix: str = "",
    existing: dict | None = None,
) -> str:
    existing = existing or {}
    if bet_type in PLAYER_PROP_BET_TYPES:
        return st.text_input(
            bet_type,
            value=existing.get("prediction", ""),
            placeholder="Player name (e.g. Lionel Messi)",
            key=f"{prefix}prediction",
        )
    pred_idx = match_outcomes.index(existing["prediction"]) if existing.get("prediction") in match_outcomes else 0
    return st.selectbox("Match Outcome", match_outcomes, index=pred_idx, key=f"{prefix}prediction")


def _render_pending_summary(pending_count: int, staked: float, potential: float) -> None:
    """Aggregate pending-bet strip — visually distinct from per-bet settle cards."""
    bet_word = "bet" if pending_count == 1 else "bets"
    st.markdown(
        f"""
        <style>
        .pending-summary {{
            background: linear-gradient(135deg, #e8f4fd 0%, #f0f7fc 100%);
            border: 1px solid #b8d4e8;
            border-radius: 10px;
            padding: 14px 18px;
            margin-bottom: 12px;
        }}
        .pending-summary .summary-title {{
            color: #1F4E79;
            font-size: 0.8rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            text-transform: uppercase;
            margin-bottom: 10px;
        }}
        .pending-summary .summary-row {{
            display: flex;
            gap: 28px;
            flex-wrap: wrap;
        }}
        .pending-summary .summary-item {{
            min-width: 140px;
        }}
        .pending-summary .summary-item .label {{
            color: #5a6c7d;
            font-size: 0.78rem;
            margin-bottom: 2px;
        }}
        .pending-summary .summary-item .value {{
            color: #1F4E79;
            font-size: 1.2rem;
            font-weight: 600;
        }}
        </style>
        <div class="pending-summary">
            <div class="summary-title">Pending overview · {pending_count} {bet_word}</div>
            <div class="summary-row">
                <div class="summary-item">
                    <div class="label">Total staked</div>
                    <div class="value">{_format_currency(staked)}</div>
                </div>
                <div class="summary-item">
                    <div class="label">Potential return if all win</div>
                    <div class="value">{_format_currency(potential)}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_quick_settle_bet(bet: dict, key_prefix: str) -> None:
    """One-click Won / Lost / Cash Out for a pending bet."""
    bet_id = int(bet["id"])
    stake = float(bet.get("bet_amount") or 0)
    could_win = potential_payout_from_odds(stake, bet.get("odds"))
    could_txt = _format_currency(could_win) if could_win else "—"

    with st.container(border=True):
        header_l, header_r = st.columns([3, 1])
        header_l.markdown(f"**#{bet_id}** · {bet['team1']} vs {bet['team2']}")
        header_r.caption(bet.get("bet_category", ""))
        st.caption(bet["bet_type"])

        m1, m2 = st.columns(2)
        m1.metric("Stake", _format_currency(stake))
        m2.metric("Could win", could_txt)

        pred = str(bet.get("prediction", ""))[:120]
        if pred:
            st.caption(f"**Pick:** {pred}")

        c1, c2, c3, c4 = st.columns([1, 1, 1.5, 1])
        if c1.button("Won", key=f"{key_prefix}_won_{bet_id}", type="primary", use_container_width=True):
            if quick_settle_bet(bet_id, "Bet Won"):
                st.rerun()
        if c2.button("Lost", key=f"{key_prefix}_lost_{bet_id}", use_container_width=True):
            if quick_settle_bet(bet_id, "Bet Lost"):
                st.rerun()
        cashout_amt = c3.number_input(
            "Cash-out amount ($)",
            min_value=0.0,
            value=0.0,
            step=1.0,
            key=f"{key_prefix}_co_{bet_id}",
        )
        if c4.button("Cash Out", key=f"{key_prefix}_cash_{bet_id}", use_container_width=True):
            if quick_settle_bet(bet_id, "Bet Cashed Out", cashout_amt):
                st.rerun()


def _render_quick_settle_list(bets: list[dict], key_prefix: str, *, empty_msg: str = "No pending bets.") -> None:
    if not bets:
        st.info(empty_msg)
        return
    for bet in bets:
        _render_quick_settle_bet(bet, key_prefix)


def _render_performance_insights(df: pd.DataFrame, df_all: pd.DataFrame) -> None:
    st.markdown("#### Performance Insights")
    settled = df[df["settled"]] if not df.empty else df
    if settled.empty:
        st.info("Settle some bets to see performance insights.")
        return

    streaks = get_streak_stats(df)
    s1, s2, s3, s4 = st.columns(4)
    streak_label = (
        f"{streaks['current_streak']} {streaks['current_type']}"
        if streaks["current_streak"] else "—"
    )
    s1.metric("Current streak", streak_label)
    s2.metric("Best win streak", streaks["best_win_streak"])
    s3.metric("Worst loss streak", streaks["worst_loss_streak"])
    s4.metric("Last 10 results", " ".join(streaks["last_results"]) or "—")

    col_a, col_b = st.columns(2)
    with col_a:
        by_stage = performance_by_stage_type(df)
        if not by_stage.empty:
            st.markdown("**ROI by tournament phase** (settled)")
            fig = px.bar(
                by_stage,
                x="stage_type",
                y="profit_loss",
                color="profit_loss",
                text=by_stage["roi_pct"].apply(lambda x: f"{x:.0f}% ROI"),
                color_continuous_scale=["#FF6B6B", "#FFE66D", "#4ECDC4"],
                labels={"stage_type": "Phase", "profit_loss": "P/L ($)"},
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(height=300, showlegend=False, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        by_type = performance_by_bet_type_settled(df)
        if not by_type.empty:
            st.markdown("**ROI by bet type** (settled)")
            fig = px.bar(
                by_type,
                x="bet_type",
                y="profit_loss",
                color="profit_loss",
                text=by_type["roi_pct"].apply(lambda x: f"{x:.0f}% ROI"),
                color_continuous_scale=["#FF6B6B", "#FFE66D", "#4ECDC4"],
                labels={"bet_type": "Type", "profit_loss": "P/L ($)"},
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(height=300, showlegend=False, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig, use_container_width=True)

    if not df_all.empty and df_all["bet_category"].nunique() > 1:
        cat_time = category_pl_over_time(df_all)
        if not cat_time.empty:
            st.markdown("**Challenge vs Fun — cumulative P/L over time**")
            fig = px.line(
                cat_time,
                x="match_date",
                y="cumulative_pl",
                color="bet_category",
                markers=True,
                labels={"match_date": "Date", "cumulative_pl": "Cumulative P/L ($)", "bet_category": "Category"},
            )
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            fig.update_layout(height=320, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig, use_container_width=True)


def render_match_day() -> None:
    st.subheader("Match Day")
    st.caption("Today's World Cup schedule, live scores, and quick bet settlement.")
    _maybe_sync_worldcup()

    df_all = enrich_bets(get_all_bets())
    flags = get_flag_map()

    upcoming = upcoming_match_dates()
    default_date = date.today()
    if upcoming:
        try:
            default_date = date.fromisoformat(upcoming[0])
        except ValueError:
            pass

    col_date, col_jump = st.columns([2, 2])
    if "match_day_date" not in st.session_state:
        st.session_state.match_day_date = default_date
    selected = col_date.date_input("Select match day", key="match_day_date")
    date_str = selected.isoformat()

    if upcoming and col_jump.button("Next match day with games"):
        for d in upcoming:
            if d > date_str:
                st.session_state.match_day_date = date.fromisoformat(d)
                st.rerun()
                break

    wc_matches = get_wc_matches_on_date(date_str)
    day_bets = get_bets_on_date(df_all, date_str)
    pending_day = get_pending_bets_on_date(df_all, date_str)

    m1, m2, m3 = st.columns(3)
    m1.metric("WC matches", len(wc_matches))
    m2.metric("Your bets today", len(day_bets))
    m3.metric("Pending to settle", len(pending_day))

    if pending_day.empty:
        st.success("No pending bets for this day — you're all caught up!")
    else:
        st.markdown("#### Quick settle — today's pending bets")
        _render_quick_settle_list(
            pending_day.sort_values("match_date").to_dict("records"),
            "md_settle",
            empty_msg="",
        )

    st.markdown("#### Schedule & results")
    if not wc_matches:
        st.info("No World Cup matches on this date.")
    else:
        for match in wc_matches:
            card = format_match_card(match, flags)
            with st.container(border=True):
                st.markdown(
                    f"**{card['team1']}** {card['score']} **{card['team2']}**  \n"
                    f"{card['time']} · {card['stage']} · {card['status']} · {card['venue']}"
                )
                match_pending = pending_day[
                    (pending_day["team1"].isin([card["team1_raw"], card["team2_raw"]]))
                    | (pending_day["team2"].isin([card["team1_raw"], card["team2_raw"]]))
                ] if not pending_day.empty else pd.DataFrame()
                if not match_pending.empty:
                    for _, brow in match_pending.iterrows():
                        st.caption(
                            f"Pending bet #{int(brow['id'])} · {brow['bet_type']} · "
                            f"{_format_currency(float(brow['bet_amount']))} · {str(brow['prediction'])[:60]}"
                        )

    if not day_bets.empty:
        st.markdown("#### All your bets on this day")
        settled_day = day_bets[day_bets["status"] != "Pending"]
        if not settled_day.empty:
            st.dataframe(
                _dashboard_bets_table(settled_day).style.format({
                    "Stake": "${:,.2f}",
                    "Could've Won": "${:,.2f}",
                    "Actually Won": "${:,.2f}",
                    "P/L": "${:,.2f}",
                }, na_rep="—"),
                use_container_width=True,
                hide_index=True,
            )


def render_bet_log() -> None:
    st.subheader("Bet Log")
    st.caption(
        "Log singles, **Same Game Parlays** (multiple picks on one match), or **Multiple Game Parlays** "
        "(legs from different matches). Enter total parlay odds once. "
        "Outcomes: Lost ($0), Cashed Out (partial), or Won (full)."
    )

    teams = get_setting("teams", [])
    stages = get_setting("stages", [])
    bet_types = get_setting("bet_types", [])
    match_outcomes = get_setting("match_outcomes", [])
    goalscorers = get_setting("goalscorers", [])
    parlay_leg_types = get_setting("parlay_leg_types", ["Match Winner", "Goalscorer", "Correct Score"])
    bet_categories = get_setting("bet_categories", ["Main Challenge", "For Fun"])
    default_amount = float(get_setting("default_bet_amount", DEFAULT_BET_AMOUNT))

    tab_settle, tab_add, tab_edit = st.tabs(["Quick Settle", "Add Bet", "Edit / Delete"])

    with tab_settle:
        pending_all = [b for b in get_all_bets() if b.get("status") == "Pending"]
        st.caption("Settle pending bets with one click — no need to open the full edit form.")
        if not pending_all:
            st.info("No pending bets to settle.")
        else:
            staked = sum(float(b.get("bet_amount") or 0) for b in pending_all)
            potential = sum(
                potential_payout_from_odds(float(b.get("bet_amount") or 0), b.get("odds")) or 0
                for b in pending_all
            )
            _render_pending_summary(len(pending_all), staked, potential)
            _render_quick_settle_list(pending_all, "log_settle")

    with tab_add:
        form_prefix = _add_form_prefix()
        col_type, col_cat = st.columns(2)
        bet_type = col_type.selectbox("Bet Type", bet_types, key=f"{form_prefix}type")
        bet_category = col_cat.selectbox("Category", bet_categories, key=f"{form_prefix}category")

        is_mgp = is_multi_game_parlay(bet_type)
        is_sgp = is_same_game_parlay(bet_type)

        match_fields = None
        if is_mgp:
            st.info(
                "**Multiple Game Parlay** — each leg is from a different match. "
                "Pick matches per leg below, then enter **total parlay odds** under stake."
            )
            match_date = date.today()
            group_stage = "Multiple"
            team1 = "Multiple Games"
            team2 = ""
        else:
            st.markdown("#### Match details")
            match_fields = _render_match_details(teams, stages, form_prefix)
            if match_fields:
                match_date = date.fromisoformat(match_fields["match_date"][:10])
                group_stage = match_fields["group_stage"]
                team1 = match_fields["team1"]
                team2 = match_fields["team2"]
            else:
                match_date = date.today()
                group_stage = stages[0] if stages else ""
                team1 = teams[0] if teams else ""
                team2 = teams[1] if len(teams) > 1 else ""

        st.markdown("#### Your picks")
        parlay_legs = None
        if is_sgp:
            st.info(
                "**Same Game Parlay** — multiple picks on the match above. "
                "Enter **total parlay odds** under stake."
            )
            parlay_legs, prediction = _render_parlay_legs(
                parlay_leg_types, match_outcomes, goalscorers, prefix=form_prefix
            )
        elif is_mgp:
            parlay_legs, prediction = _render_parlay_legs(
                parlay_leg_types, match_outcomes, goalscorers,
                prefix=form_prefix, multi_game=True, stages=stages, teams=teams,
            )
        else:
            prediction = _render_single_prediction(
                bet_type, match_outcomes, goalscorers, prefix=form_prefix
            )

        st.markdown("#### Stake & result")
        bet_amount = st.number_input(
            "Bet Amount ($)", min_value=0.0, value=default_amount, step=1.0, key=f"{form_prefix}amount"
        )
        odds_info = _render_odds_fields(bet_type, prefix=form_prefix)
        settlement = _render_settlement_fields(
            bet_amount, odds_info, bet_type, prefix=form_prefix, allow_pending=True
        )

        col9, col10, col11 = st.columns(3)
        final_score = col9.text_input("Final Score (optional)", key=f"{form_prefix}final_score")
        actual_result = col10.text_input("Actual Result (optional)", key=f"{form_prefix}actual_result")
        actual_goalscorer = col11.text_input(
            "Actual Goalscorer (optional)",
            placeholder="Player name",
            key=f"{form_prefix}actual_gs",
        )
        notes = st.text_input("Notes", key=f"{form_prefix}notes")

        if st.button("Add Bet", type="primary", use_container_width=True, key=f"{form_prefix}submit"):
            parlay_error = _validate_parlay_legs(parlay_legs, is_mgp) if is_parlay_bet(bet_type) else None
            if not is_mgp and match_fields is None:
                st.error("Please select a World Cup match or enter match details manually.")
            elif not is_mgp and team1 == team2:
                st.error("Team 1 and Team 2 must be different.")
            elif parlay_error:
                st.error(parlay_error)
            elif bet_type in PLAYER_PROP_BET_TYPES and not prediction:
                st.error("Please enter a player name.")
            else:
                if not is_mgp:
                    _ensure_teams_in_list(team1, team2)
                elif parlay_legs:
                    for leg in parlay_legs:
                        _ensure_teams_in_list(leg.get("team1", ""), leg.get("team2", ""))
                add_bet(
                    _build_bet_payload(
                        match_date, group_stage, team1, team2, bet_type, bet_amount,
                        odds_info, settlement, prediction=prediction,
                        parlay_legs=parlay_legs,
                        final_score=final_score, actual_result=actual_result,
                        actual_goalscorer=actual_goalscorer, notes=notes,
                        bet_category=bet_category,
                    )
                )
                _reset_add_form()
                st.success("Bet added successfully!")
                st.rerun()

    with tab_edit:
        bets = get_all_bets()
        if not bets:
            st.info("No bets to edit yet.")
        else:
            bet_options = {}
            for b in bets:
                if is_multi_game_parlay(b["bet_type"]):
                    leg_count = len(parse_parlay_legs(b))
                    label = f"#{b['id']} — Multiple Game Parlay ({leg_count} legs)"
                else:
                    label = f"#{b['id']} — {b['team1']} vs {b['team2']} ({b['bet_type']})"
                bet_options[label] = b["id"]
            selected = st.selectbox("Select bet to edit", list(bet_options.keys()), key="edit_select")
            bet_id = bet_options[selected]
            bet = next(b for b in bets if b["id"] == bet_id)

            st.markdown("#### Bet details")
            col1, col2, col3, col4 = st.columns(4)
            bet_type = col3.selectbox(
                "Bet Type", bet_types,
                index=bet_types.index(bet["bet_type"]) if bet["bet_type"] in bet_types else 0,
                key=f"edit_type_{bet_id}",
            )
            bet_category = col4.selectbox(
                "Category", bet_categories,
                index=bet_categories.index(bet.get("bet_category", DEFAULT_BET_CATEGORY))
                if bet.get("bet_category") in bet_categories else 0,
                key=f"edit_cat_{bet_id}",
            )

            is_mgp = is_multi_game_parlay(bet_type)
            is_sgp = is_same_game_parlay(bet_type)

            if is_mgp:
                col1.caption(f"Earliest leg date: {bet['match_date'][:10]}")
                st.info("**Multiple Game Parlay** — each leg has its own match. Enter **total parlay odds** below.")
                match_date = date.fromisoformat(bet["match_date"][:10]) if bet.get("match_date") else date.today()
                group_stage = "Multiple"
                team1 = "Multiple Games"
                team2 = ""
            else:
                match_date = col1.date_input(
                    "Match Date", value=date.fromisoformat(bet["match_date"][:10]), key=f"edit_date_{bet_id}"
                )
                group_stage = col2.selectbox(
                    "Group / Stage", stages,
                    index=stages.index(bet["group_stage"]) if bet["group_stage"] in stages else 0,
                    key=f"edit_stage_{bet_id}",
                )
                col_t1, col_t2 = st.columns(2)
                team1 = col_t1.selectbox(
                    "Team 1", teams,
                    index=teams.index(bet["team1"]) if bet["team1"] in teams else 0,
                    key=f"edit_t1_{bet_id}",
                )
                team2 = col_t2.selectbox(
                    "Team 2", teams,
                    index=teams.index(bet["team2"]) if bet["team2"] in teams else 0,
                    key=f"edit_t2_{bet_id}",
                )
                _render_add_team_section(f"edit_{bet_id}")

            st.markdown("#### Your picks")
            parlay_legs = None
            if is_sgp:
                st.info("**Same Game Parlay** — each leg is on the match above. Enter **total parlay odds** below.")
                parlay_legs, prediction = _render_parlay_legs(
                    parlay_leg_types, match_outcomes, goalscorers,
                    prefix=f"edit_{bet_id}_", existing_bet=bet,
                )
            elif is_mgp:
                parlay_legs, prediction = _render_parlay_legs(
                    parlay_leg_types, match_outcomes, goalscorers,
                    prefix=f"edit_{bet_id}_", existing_bet=bet,
                    multi_game=True, stages=stages, teams=teams,
                )
            else:
                prediction = _render_single_prediction(
                    bet_type, match_outcomes, goalscorers, prefix=f"edit_{bet_id}_", existing=bet
                )

            st.markdown("#### Stake & result")
            bet_amount = st.number_input(
                "Bet Amount ($)", min_value=0.0, value=float(bet["bet_amount"]),
                step=1.0, key=f"edit_amount_{bet_id}",
            )
            odds_info = _render_odds_fields(bet_type, prefix=f"edit_{bet_id}_", existing=bet)
            settlement = _render_settlement_fields(
                bet_amount, odds_info, bet_type, prefix=f"edit_{bet_id}_",
                existing=bet, allow_pending=True,
            )

            col8, col9, col10 = st.columns(3)
            final_score = col8.text_input(
                "Final Score", value=bet.get("final_score") or "", key=f"edit_fs_{bet_id}"
            )
            actual_result = col9.text_input(
                "Actual Result", value=bet.get("actual_result") or "", key=f"edit_ar_{bet_id}"
            )
            actual_goalscorer = col10.text_input(
                "Actual Goalscorer", value=bet.get("actual_goalscorer") or "",
                placeholder="Player name", key=f"edit_ag_{bet_id}",
            )
            notes = st.text_input("Notes", value=bet.get("notes") or "", key=f"edit_notes_{bet_id}")

            col_save, col_del = st.columns(2)
            if col_save.button("Save Changes", type="primary", use_container_width=True, key=f"edit_save_{bet_id}"):
                parlay_error = _validate_parlay_legs(parlay_legs, is_mgp) if is_parlay_bet(bet_type) else None
                if not is_mgp and team1 == team2:
                    st.error("Team 1 and Team 2 must be different.")
                elif parlay_error:
                    st.error(parlay_error)
                elif bet_type in PLAYER_PROP_BET_TYPES and not prediction:
                    st.error("Please enter a player name.")
                else:
                    payload = _build_bet_payload(
                        match_date, group_stage, team1, team2, bet_type, bet_amount,
                        odds_info, settlement, prediction=prediction,
                        parlay_legs=parlay_legs,
                        final_score=final_score, actual_result=actual_result,
                        actual_goalscorer=actual_goalscorer, notes=notes,
                        bet_category=bet_category,
                    )
                    update_bet(bet_id, payload)
                    st.success("Bet updated!")
                    st.rerun()
            if col_del.button("Delete Bet", use_container_width=True, key=f"edit_del_{bet_id}"):
                delete_bet(bet_id)
                st.warning("Bet deleted.")
                st.rerun()

    st.divider()
    st.markdown("### All Bets")

    df = enrich_bets(get_all_bets())
    if df.empty:
        st.info("No bets logged yet. Add your first bet above.")
    else:
        filter_col1, filter_col2 = st.columns([1, 3])
        categories_in_data = ["All"] + sorted(df["bet_category"].unique().tolist())
        category_filter = filter_col1.selectbox("Filter by category", categories_in_data, key="log_category_filter")
        if category_filter != "All":
            df = df[df["bet_category"] == category_filter]

        display_cols = [
            "id", "match_date", "bet_category", "team1", "team2", "bet_type", "prediction",
            "bet_amount", "status", "potential_payout_calc", "actual_return", "profit_loss", "notes",
        ]
        styled = df[display_cols].copy()
        for col in ("potential_payout_calc", "actual_return", "profit_loss"):
            styled[col] = pd.to_numeric(styled[col], errors="coerce")
        styled["match_date"] = styled["match_date"].dt.strftime("%Y-%m-%d")
        styled.columns = [
            "ID", "Date", "Category", "Team 1", "Team 2", "Type", "Prediction",
            "Stake", "Result", "Could've Won", "Actually Won", "P/L", "Notes",
        ]

        def color_pl(val):
            if isinstance(val, (int, float)) and pd.notna(val) and val > 0:
                return "background-color: #C6EFCE; color: #006100"
            if isinstance(val, (int, float)) and pd.notna(val) and val < 0:
                return "background-color: #FFC7CE; color: #9C0006"
            return ""

        st.dataframe(
            styled.style.format({
                "Stake": "${:,.2f}",
                "Could've Won": "${:,.2f}",
                "Actually Won": "${:,.2f}",
                "P/L": "${:,.2f}",
            }, na_rep="—").map(color_pl, subset=["P/L"]),
            use_container_width=True,
            hide_index=True,
        )


def render_tournament() -> None:
    st.subheader("World Cup 2026")
    st.caption("Live standings, scores, and knockout bracket from [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json/tree/master/2026).")

    col_refresh, col_info = st.columns([1, 3])
    if col_refresh.button("Refresh from GitHub", type="primary"):
        result = _maybe_sync_worldcup(force=True)
        st.rerun()
    else:
        result = _maybe_sync_worldcup()
    _render_sync_status(result)

    tab_standings, tab_scores, tab_bracket = st.tabs(["Group Standings", "Scores & Fixtures", "Knockout Bracket"])

    flags = get_flag_map()

    with tab_standings:
        standings = compute_group_standings()
        if not standings:
            st.info("No group data available.")
        else:
            group_cols = st.columns(3)
            for idx, (group_name, rows) in enumerate(sorted(standings.items())):
                with group_cols[idx % 3]:
                    st.markdown(f"**{group_name}**")
                    table_rows = []
                    for pos, row in enumerate(rows, start=1):
                        table_rows.append({
                            "#": pos,
                            "Team": format_team(row["team"], flags),
                            "P": row["played"],
                            "W": row["won"],
                            "D": row["drawn"],
                            "L": row["lost"],
                            "GF": row["gf"],
                            "GA": row["ga"],
                            "GD": row["gd"],
                            "Pts": row["points"],
                        })
                    st.dataframe(
                        pd.DataFrame(table_rows),
                        use_container_width=True,
                        hide_index=True,
                    )

    with tab_scores:
        f1, f2, f3 = st.columns(3)
        stage_filters, round_filters = get_schedule_filters(load_schedule())
        stage_f = f1.selectbox("Stage", stage_filters, key="tourn_stage")
        round_f = f2.selectbox("Round", round_filters, key="tourn_round")
        status_f = f3.selectbox("Status", ["All", "Played", "Upcoming"], key="tourn_status")

        filtered = filter_matches(load_schedule(), stage_f, round_f)
        if status_f == "Played":
            filtered = [m for m in filtered if m.get("score")]
        elif status_f == "Upcoming":
            filtered = [m for m in filtered if not m.get("score")]

        score_rows = []
        for m in filtered:
            s1, s2 = m["team1"], m["team2"]
            score_txt = "vs"
            if m.get("score", {}).get("ft"):
                ft = m["score"]["ft"]
                score_txt = f"{ft[0]} - {ft[1]}"
            score_rows.append({
                "Date": m.get("date", ""),
                "Stage": m.get("group") or m.get("round", ""),
                "Team 1": format_team(s1, flags),
                "Score": score_txt,
                "Team 2": format_team(s2, flags),
                "Venue": m.get("ground", ""),
            })

        if not score_rows:
            st.info("No matches match your filters.")
        else:
            st.dataframe(pd.DataFrame(score_rows), use_container_width=True, hide_index=True)

    with tab_bracket:
        st.caption("Teams advance automatically as knockout results are published on GitHub. Group placeholders (e.g. 1A, W74) resolve from standings and completed matches.")
        _render_knockout_bracket()


def render_match_results() -> None:
    st.subheader("Match Results")
    st.caption("Scores auto-sync from [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json/tree/master/2026). Manual edits below override your bet records.")

    result = _maybe_sync_worldcup()
    col1, col2 = st.columns([1, 3])
    if col1.button("Refresh from GitHub", key="mr_refresh"):
        _maybe_sync_worldcup(force=True)
        st.rerun()
    col2.caption(f"Last sync applied **{result.get('matches_updated', 0)}** match results to your bets.")

    matches = get_unique_matches()
    teams = get_setting("teams", [])
    stages = get_setting("stages", [])
    match_outcomes = get_setting("match_outcomes", [])
    flags = get_flag_map()
    github_matches = [m for m in load_schedule() if m.get("score")]

    if github_matches:
        st.markdown("#### Latest results from GitHub")
        gh_rows = []
        for m in reversed(github_matches[-15:]):
            ft = m["score"]["ft"]
            gh_rows.append({
                "Date": m["date"],
                "Stage": m.get("group") or m.get("round", ""),
                "Match": f"{format_team(m['team1'], flags)} {ft[0]}-{ft[1]} {format_team(m['team2'], flags)}",
                "Scorers": get_goalscorers_text(m) or "—",
            })
        st.dataframe(pd.DataFrame(gh_rows), use_container_width=True, hide_index=True)

    with st.expander("Add results for a new match", expanded=not matches):
        _render_add_team_section("mr")
        with st.form("new_match_results"):
            col1, col2 = st.columns(2)
            match_date = col1.date_input("Match Date", value=date.today(), key="mr_date")
            group_stage = col2.selectbox("Group / Stage", stages, key="mr_stage")
            col3, col4 = st.columns(2)
            team1 = col3.selectbox("Team 1", teams, key="mr_t1")
            team2 = col4.selectbox("Team 2", teams, key="mr_t2")
            final_score = st.text_input("Final Score", placeholder="e.g. 2-1")
            col5, col6 = st.columns(2)
            actual_result = col5.selectbox("Actual Match Result", [""] + match_outcomes)
            actual_goalscorer = col6.text_input(
                "Actual Goalscorer",
                placeholder="Player name (e.g. Lionel Messi)",
            )

            if st.form_submit_button("Save Match Results", type="primary"):
                if team1 == team2:
                    st.error("Teams must be different.")
                elif not final_score:
                    st.error("Please enter the final score.")
                else:
                    # Create placeholder bets if match doesn't exist yet
                    existing = [m for m in matches if m["team1"] == team1 and m["team2"] == team2 and m["match_date"][:10] == parse_date(match_date)]
                    if not existing:
                        base = {
                            "match_date": parse_date(match_date),
                            "group_stage": group_stage,
                            "team1": team1,
                            "team2": team2,
                            "bet_amount": float(get_setting("default_bet_amount", DEFAULT_BET_AMOUNT)),
                            "bet_category": DEFAULT_BET_CATEGORY,
                            "status": "Pending",
                        }
                        add_bet({**base, "bet_type": "Match Outcome", "prediction": "TBD"})
                        add_bet({**base, "bet_type": "Goalscorer", "prediction": "TBD"})

                    update_match_results(
                        parse_date(match_date),
                        team1,
                        team2,
                        final_score,
                        actual_result,
                        actual_goalscorer,
                    )
                    st.success("Match results saved!")
                    st.rerun()

    if not matches:
        st.info("No matches yet. Add match results above or log bets in the Bet Log tab.")
        return

    for match in matches:
        label = f"{match['team1']} vs {match['team2']} — {match['match_date'][:10]} ({match['group_stage']})"
        with st.expander(label, expanded=not match.get("final_score")):
            with st.form(f"match_{match['team1']}_{match['team2']}_{match['match_date']}"):
                final_score = st.text_input("Final Score", value=match.get("final_score") or "", key=f"fs_{label}")
                col1, col2 = st.columns(2)
                actual_result = col1.selectbox(
                    "Actual Result",
                    [""] + match_outcomes,
                    index=([""] + match_outcomes).index(match["actual_result"])
                    if match.get("actual_result") in match_outcomes else 0,
                    key=f"ar_{label}",
                )
                actual_goalscorer = col2.text_input(
                    "Actual Goalscorer",
                    value=match.get("actual_goalscorer") or "",
                    placeholder="Player name",
                    key=f"ag_{label}",
                )
                if st.form_submit_button("Update", use_container_width=True):
                    update_match_results(
                        match["match_date"][:10],
                        match["team1"],
                        match["team2"],
                        final_score,
                        actual_result,
                        actual_goalscorer,
                    )
                    st.success("Updated!")
                    st.rerun()


def _dashboard_bets_table(df: pd.DataFrame) -> pd.DataFrame:
    """Format bets for dashboard status panels."""
    if df.empty:
        return pd.DataFrame()
    out = df.sort_values("match_date", ascending=False).copy()
    out["Date"] = out["match_date"].dt.strftime("%Y-%m-%d")
    out["Match"] = out.apply(lambda r: f"{r['team1']} vs {r['team2']}", axis=1)
    out["Stake"] = pd.to_numeric(out["bet_amount"], errors="coerce")
    out["Could've Won"] = pd.to_numeric(out["potential_payout_calc"], errors="coerce")
    out["Actually Won"] = pd.to_numeric(out["actual_return"], errors="coerce")
    out["P/L"] = pd.to_numeric(out["profit_loss"], errors="coerce")
    return out[
        ["Date", "Match", "bet_type", "prediction", "Stake", "Could've Won", "Actually Won", "P/L", "bet_category"]
    ].rename(columns={"bet_type": "Type", "prediction": "Prediction", "bet_category": "Category"})


def render_dashboard() -> None:
    st.subheader("Dashboard")
    _maybe_sync_worldcup()

    bets = get_all_bets()
    df_all = enrich_bets(bets)
    bet_categories = get_setting("bet_categories", ["Main Challenge", "For Fun"])
    starting_bankroll = float(get_setting("starting_bankroll", 1000))

    filter_options = ["All Bets"] + bet_categories
    selected_filter = st.selectbox("Show stats for", filter_options, key="dash_category_filter")
    df = df_all if selected_filter == "All Bets" else df_all[df_all["bet_category"] == selected_filter]
    stats = get_summary_stats(df, starting_bankroll)

    if selected_filter != "All Bets":
        st.caption(f"Showing **{selected_filter}** bets only. Switch to *All Bets* to see everything combined.")

    potential_delta = (
        f"+{_format_currency(stats['potential_bankroll'] - stats['current_bankroll'])} if all pending win"
        if stats["pending_bets"] > 0
        else "No pending bets"
    )

    st.markdown(
        f"""
        <style>
        .bankroll-hero {{
            background: linear-gradient(135deg, #1F4E79 0%, #2d6da8 100%);
            color: white;
            border-radius: 12px;
            padding: 28px 32px;
            margin-bottom: 8px;
        }}
        .bankroll-hero .label {{
            font-size: 0.95rem;
            opacity: 0.9;
            margin-bottom: 4px;
        }}
        .bankroll-hero .value {{
            font-size: 2.75rem;
            font-weight: 700;
            line-height: 1.1;
        }}
        .bankroll-hero .sub {{
            font-size: 0.85rem;
            opacity: 0.85;
            margin-top: 8px;
        }}
        .bankroll-card {{
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 10px;
            padding: 20px 24px;
            height: 100%;
        }}
        .bankroll-card .label {{
            color: #666;
            font-size: 0.85rem;
            margin-bottom: 4px;
        }}
        .bankroll-card .value {{
            font-size: 1.75rem;
            font-weight: 700;
            color: #1F4E79;
        }}
        .bankroll-card .sub {{
            color: #888;
            font-size: 0.8rem;
            margin-top: 6px;
        }}
        .bankroll-card.positive .value {{ color: #006100; }}
        .bankroll-card.negative .value {{ color: #9C0006; }}
        </style>
        <div class="bankroll-hero">
            <div class="label">Current Bankroll — available to bet</div>
            <div class="value">{_format_currency(stats["current_bankroll"])}</div>
            <div class="sub">Started with {_format_currency(stats["starting_bankroll"])}
            {" · " + _format_currency(stats["pending_wagered"]) + " in pending stakes" if stats["pending_wagered"] else ""}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    win_class = "positive" if stats["total_winnings"] >= 0 else "negative"
    col_win, col_pot = st.columns(2)
    with col_win:
        st.markdown(
            f"""
            <div class="bankroll-card {win_class}">
                <div class="label">Total Winnings</div>
                <div class="value">{_format_currency(stats["total_winnings"])}</div>
                <div class="sub">Current bankroll minus your {_format_currency(stats["starting_bankroll"])} starting balance</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_pot:
        st.markdown(
            f"""
            <div class="bankroll-card">
                <div class="label">Potential Bankroll</div>
                <div class="value">{_format_currency(stats["potential_bankroll"])}</div>
                <div class="sub">{potential_delta}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("#### Other stats")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Wagered", _format_currency(stats["total_wagered"]))
    c2.metric("Realized P/L (settled)", _format_currency(stats["total_profit_loss"]), delta=f"{stats['roi_pct']:.1f}% ROI")
    c3.metric("Total Returns (settled)", _format_currency(stats["total_payout"]))
    c4.metric("Pending at risk", _format_currency(stats["pending_wagered"]), delta=f"{stats['pending_bets']} bets")

    # KPI row 2 — outcome counts
    c5, c6, c7, c8, c9, c10 = st.columns(6)
    c5.metric("Total Bets", stats["total_bets"])
    c6.metric(
        "Pending",
        stats["pending_bets"],
        delta=f"{stats['pending_pct']:.1f}% · {_format_currency(stats['pending_wagered'])} staked",
    )
    c7.metric("Won", stats["bets_won"], delta=f"{stats['win_pct']:.1f}% of settled")
    c8.metric("Lost", stats["bets_lost"], delta=f"{stats['loss_pct']:.1f}% of settled")
    c9.metric("Cashed Out", stats["bets_cashed_out"], delta=f"{stats['cashout_pct']:.1f}% of settled")
    c10.metric("Parlays", stats["parlay_bets"])

    if stats["total_missed_winnings"] > 0:
        st.metric("Left on Table (cash-outs)", _format_currency(stats["total_missed_winnings"]))

    if df.empty:
        st.info("Add bets to see charts and analytics.")
        return

    # Bet lists by status
    st.markdown("#### Bets by status")
    tab_pending, tab_won, tab_lost, tab_cashed = st.tabs([
        f"Pending ({stats['pending_bets']})",
        f"Won ({stats['bets_won']})",
        f"Lost ({stats['bets_lost']})",
        f"Cashed Out ({stats['bets_cashed_out']})",
    ])

    with tab_pending:
        pending_df = df[df["status"] == "Pending"]
        if pending_df.empty:
            st.info("No pending bets.")
        else:
            _render_pending_summary(
                stats["pending_bets"],
                stats["pending_wagered"],
                stats["pending_potential_win"],
            )
            st.markdown("**Quick settle**")
            _render_quick_settle_list(
                pending_df.sort_values("match_date", ascending=False).to_dict("records"),
                "dash_settle",
            )
            with st.expander("View as table"):
                pending_table = _dashboard_bets_table(pending_df)
                st.dataframe(
                    pending_table.style.format({
                        "Stake": "${:,.2f}",
                        "Could've Won": "${:,.2f}",
                        "Actually Won": "${:,.2f}",
                        "P/L": "${:,.2f}",
                    }, na_rep="—"),
                    use_container_width=True,
                    hide_index=True,
                )

    with tab_won:
        won_df = df[df["status"] == "Bet Won"]
        if won_df.empty:
            st.info("No winning bets yet.")
        else:
            won_table = _dashboard_bets_table(won_df)
            st.dataframe(
                won_table.style.format({
                    "Stake": "${:,.2f}",
                    "Could've Won": "${:,.2f}",
                    "Actually Won": "${:,.2f}",
                    "P/L": "${:,.2f}",
                }, na_rep="—").map(
                    lambda v: "background-color: #C6EFCE; color: #006100"
                    if isinstance(v, (int, float)) and pd.notna(v) and v > 0 else "",
                    subset=["P/L"],
                ),
                use_container_width=True,
                hide_index=True,
            )

    with tab_lost:
        lost_df = df[df["status"] == "Bet Lost"]
        if lost_df.empty:
            st.info("No losing bets yet.")
        else:
            lost_table = _dashboard_bets_table(lost_df)
            st.dataframe(
                lost_table.style.format({
                    "Stake": "${:,.2f}",
                    "Could've Won": "${:,.2f}",
                    "Actually Won": "${:,.2f}",
                    "P/L": "${:,.2f}",
                }, na_rep="—").map(
                    lambda v: "background-color: #FFC7CE; color: #9C0006"
                    if isinstance(v, (int, float)) and pd.notna(v) and v < 0 else "",
                    subset=["P/L"],
                ),
                use_container_width=True,
                hide_index=True,
            )

    with tab_cashed:
        cashed_df = df[df["status"] == "Bet Cashed Out"]
        if cashed_df.empty:
            st.info("No cashed-out bets.")
        else:
            cashed_table = _dashboard_bets_table(cashed_df)
            st.dataframe(
                cashed_table.style.format({
                    "Stake": "${:,.2f}",
                    "Could've Won": "${:,.2f}",
                    "Actually Won": "${:,.2f}",
                    "P/L": "${:,.2f}",
                }, na_rep="—"),
                use_container_width=True,
                hide_index=True,
            )

    st.divider()
    _render_performance_insights(df, df_all)

    st.divider()
    # Side-by-side category comparison when viewing all bets
    if selected_filter == "All Bets" and not df_all.empty:
        by_cat = performance_by_category(df_all[df_all["settled"]]) if not df_all.empty else pd.DataFrame()
        if len(by_cat) > 1:
            st.markdown("#### Challenge vs Fun Bets")
            cols = st.columns(len(by_cat))
            for col, (_, row) in zip(cols, by_cat.iterrows()):
                col.metric(
                    row["bet_category"],
                    _format_currency(row["profit_loss"]),
                    delta=f"{row['roi_pct']:.1f}% ROI · {int(row['bets'])} bets",
                )

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### Running Bankroll")
        bankroll_df = get_bankroll_over_time(df, starting_bankroll)
        fig = px.line(
            bankroll_df,
            x="match_date",
            y="bankroll",
            markers=True,
            labels={"match_date": "Date", "bankroll": "Bankroll ($)"},
        )
        fig.add_hline(y=starting_bankroll, line_dash="dash", line_color="gray", annotation_text="Starting bankroll")
        fig.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.markdown("#### Cumulative Profit/Loss")
        fig2 = px.area(
            bankroll_df,
            x="match_date",
            y="cumulative_pl",
            labels={"match_date": "Date", "cumulative_pl": "Cumulative P/L ($)"},
        )
        fig2.add_hline(y=0, line_dash="dash", line_color="gray")
        fig2.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig2, use_container_width=True)

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### Performance by Bet Type (settled)")
        by_type = performance_by_bet_type_settled(df)
        if not by_type.empty:
            fig3 = px.bar(
                by_type,
                x="bet_type",
                y="profit_loss",
                color="profit_loss",
                color_continuous_scale=["#FF6B6B", "#FFE66D", "#4ECDC4"],
                labels={"bet_type": "Bet Type", "profit_loss": "Profit/Loss ($)"},
            )
            fig3.update_layout(height=300, showlegend=False, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig3, use_container_width=True)

    with col_b:
        by_cat_chart = performance_by_category(df[df["settled"]]) if not df.empty else pd.DataFrame()
        if not by_cat_chart.empty and len(by_cat_chart) > 1:
            st.markdown("#### Performance by Category")
            fig_cat = px.bar(
                by_cat_chart,
                x="bet_category",
                y="profit_loss",
                color="profit_loss",
                color_continuous_scale=["#FF6B6B", "#FFE66D", "#4ECDC4"],
                labels={"bet_category": "Category", "profit_loss": "Profit/Loss ($)"},
            )
            fig_cat.update_layout(height=300, showlegend=False, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.markdown("#### Bet Outcome Breakdown")
            status_counts = df["status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            if not status_counts.empty:
                fig4 = px.pie(status_counts, names="Status", values="Count", hole=0.4)
                fig4.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20))
                st.plotly_chart(fig4, use_container_width=True)

    st.markdown("#### Performance by Group / Stage")
    by_group = performance_by_group(df[df["settled"]]) if not df.empty else pd.DataFrame()
    if not by_group.empty:
        fig5 = px.bar(
            by_group,
            x="group_stage",
            y="profit_loss",
            color="profit_loss",
            color_continuous_scale=["#FF6B6B", "#FFE66D", "#4ECDC4"],
            labels={"group_stage": "Stage", "profit_loss": "Profit/Loss ($)"},
        )
        fig5.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig5, use_container_width=True)

    st.markdown("#### Daily Activity")
    daily = daily_summary(df)
    if not daily.empty:
        fig6 = go.Figure()
        fig6.add_trace(go.Bar(x=daily["date"], y=daily["wagered"], name="Wagered", marker_color="#4A90D9"))
        fig6.add_trace(go.Scatter(x=daily["date"], y=daily["profit_loss"], name="P/L", yaxis="y2", line=dict(color="#E74C3C")))
        fig6.update_layout(
            height=350,
            yaxis=dict(title="Wagered ($)"),
            yaxis2=dict(title="P/L ($)", overlaying="y", side="right"),
            margin=dict(l=20, r=20, t=30, b=20),
        )
        st.plotly_chart(fig6, use_container_width=True)


def render_team_stats() -> None:
    st.subheader("Team & Player Stats")

    df = enrich_bets(get_all_bets())
    if df.empty:
        st.info("No data yet.")
        return

    tab_teams, tab_scorers, tab_stages = st.tabs(["Teams", "Goalscorers", "By Stage"])

    with tab_teams:
        teams_df = team_performance(df)
        if teams_df.empty:
            st.info("No match outcome bets yet.")
        else:
            st.markdown("#### Best Performing Teams (Match Outcome Bets)")
            st.dataframe(
                teams_df.style.format({
                    "wagered": "${:,.2f}",
                    "profit_loss": "${:,.2f}",
                    "win_pct": "{:.1f}%",
                }),
                use_container_width=True,
                hide_index=True,
            )
            fig = px.bar(
                teams_df.head(15),
                x="team",
                y="profit_loss",
                color="profit_loss",
                color_continuous_scale=["#FF6B6B", "#FFE66D", "#4ECDC4"],
                labels={"team": "Team", "profit_loss": "Profit/Loss ($)"},
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

    with tab_scorers:
        scorers_df = goalscorer_performance(df)
        if scorers_df.empty:
            st.info("No goalscorer bets yet.")
        else:
            st.markdown("#### Most Profitable Goalscorer Bets")
            st.dataframe(
                scorers_df.style.format({
                    "wagered": "${:,.2f}",
                    "profit_loss": "${:,.2f}",
                    "win_pct": "{:.1f}%",
                }),
                use_container_width=True,
                hide_index=True,
            )
            fig = px.bar(
                scorers_df.head(15),
                x="prediction",
                y="profit_loss",
                color="profit_loss",
                color_continuous_scale=["#FF6B6B", "#FFE66D", "#4ECDC4"],
                labels={"prediction": "Goalscorer", "profit_loss": "Profit/Loss ($)"},
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

    with tab_stages:
        stages_df = performance_by_group(df)
        if not stages_df.empty:
            st.dataframe(
                stages_df.style.format({
                    "wagered": "${:,.2f}",
                    "profit_loss": "${:,.2f}",
                    "roi_pct": "{:.1f}%",
                }),
                use_container_width=True,
                hide_index=True,
            )


def render_settings() -> None:
    st.subheader("Settings")
    st.caption("Customize dropdown lists, defaults, and data management.")

    tab_config, tab_lists, tab_data = st.tabs(["Configuration", "Manage Lists", "Data Management"])

    with tab_config:
        with st.form("config_form"):
            default_bet = st.number_input(
                "Default Bet Amount ($)",
                min_value=0.0,
                value=float(get_setting("default_bet_amount", DEFAULT_BET_AMOUNT)),
                step=1.0,
            )
            starting_bankroll = st.number_input(
                "Starting Bankroll ($)",
                min_value=0.0,
                value=float(get_setting("starting_bankroll", 1000)),
                step=10.0,
            )
            if st.form_submit_button("Save Configuration", type="primary"):
                set_setting("default_bet_amount", default_bet)
                set_setting("starting_bankroll", starting_bankroll)
                st.success("Configuration saved!")
                st.rerun()

    with tab_lists:
        list_type = st.selectbox(
            "Edit list",
            ["teams", "goalscorers", "stages", "bet_statuses", "bet_types", "bet_categories", "parlay_leg_types", "match_outcomes"],
        )
        current = get_setting(list_type, [])
        new_items = st.text_area(
            f"{list_type.replace('_', ' ').title()} (one per line)",
            value="\n".join(current),
            height=300,
        )
        col1, col2 = st.columns(2)
        if col1.button("Save List", type="primary", use_container_width=True):
            items = [line.strip() for line in new_items.splitlines() if line.strip()]
            set_setting(list_type, items)
            st.success(f"Updated {len(items)} items.")
            st.rerun()
        if col2.button("Reset to Defaults", use_container_width=True):
            from config.defaults import (
                BET_CATEGORIES,
                BET_STATUSES,
                BET_TYPES,
                DEFAULT_GOALSCORERS,
                DEFAULT_TEAMS,
                MATCH_OUTCOMES,
                PARLAY_LEG_TYPES,
                STAGES,
            )
            defaults_map = {
                "teams": DEFAULT_TEAMS,
                "goalscorers": DEFAULT_GOALSCORERS,
                "stages": STAGES,
                "bet_statuses": BET_STATUSES,
                "bet_types": BET_TYPES,
                "bet_categories": BET_CATEGORIES,
                "parlay_leg_types": PARLAY_LEG_TYPES,
                "match_outcomes": MATCH_OUTCOMES,
            }
            set_setting(list_type, defaults_map[list_type])
            st.warning("List reset to defaults.")
            st.rerun()

    with tab_data:
        st.markdown("#### Export / Import")
        from src.excel_export import generate_excel_workbook

        excel_bytes = generate_excel_workbook()
        st.download_button(
            label="Download Excel Workbook",
            data=excel_bytes,
            file_name=f"world_cup_bets_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
        st.caption("Excel file includes Bet Log, Match Results, Dashboard (with formulas), Team Stats, and Settings sheets.")

        csv_df = enrich_bets(get_all_bets())
        if not csv_df.empty:
            csv_data = csv_df.to_csv(index=False)
            st.download_button(
                label="Download CSV Backup",
                data=csv_data,
                file_name=f"world_cup_bets_{date.today().isoformat()}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.divider()
        st.markdown("#### Danger Zone")
        if st.button("Clear All Bets", type="secondary"):
            st.session_state["confirm_clear"] = True

        if st.session_state.get("confirm_clear"):
            st.warning("This will permanently delete all bets. Are you sure?")
            if st.button("Yes, delete all bets"):
                from src.database import clear_all_bets
                clear_all_bets()
                st.session_state.pop("confirm_clear", None)
                st.success("All bets cleared.")
                st.rerun()
