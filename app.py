"""World Cup Betting Challenge Tracker — Streamlit App."""

import streamlit as st

from src.database import init_db
from src.pages import (
    render_bet_log,
    render_dashboard,
    render_match_day,
    render_match_results,
    render_settings,
    render_team_stats,
    render_tournament,
    render_whatif,
)

st.set_page_config(
    page_title="World Cup Betting Tracker",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        color: #1F4E79;
        margin-bottom: 0;
    }
    .sub-header {
        color: #666;
        margin-top: 0;
        margin-bottom: 1.5rem;
    }
    div[data-testid="stMetric"] {
        background: #f8f9fa;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #e9ecef;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

init_db()

with st.sidebar:
    st.markdown("## ⚽ WC Betting")
    st.markdown("Track $20 bets on every match")
    st.divider()

    page = st.radio(
        "Navigation",
        [
            "Dashboard",
            "Match Day",
            "Bet Log",
            "World Cup",
            "What-If Simulator",
            "Match Results",
            "Team & Player Stats",
            "Settings",
        ],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("World Cup 2026 Betting Challenge")
    st.caption("$20 per bet · Outcome + Goalscorer")

st.markdown('<p class="main-header">World Cup Betting Challenge Tracker</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Log your bets, enter match results, and let the dashboard calculate everything automatically.</p>',
    unsafe_allow_html=True,
)

if page == "Dashboard":
    render_dashboard()
elif page == "Match Day":
    render_match_day()
elif page == "Bet Log":
    render_bet_log()
elif page == "World Cup":
    render_tournament()
elif page == "What-If Simulator":
    render_whatif()
elif page == "Match Results":
    render_match_results()
elif page == "Team & Player Stats":
    render_team_stats()
elif page == "Settings":
    render_settings()
