# World Cup Betting Challenge Tracker

A Streamlit dashboard for tracking your FIFA World Cup 2026 betting challenge — $20 on every match outcome and goalscorer bet.

## Features

- **Bet Log** — Add single bets, two singles per match, or **parlays** (outcome + goalscorer combined)
- **Odds tracking** — Enter decimal odds; potential payout auto-calculated
- **Cash-out tracking** — Mark if you cashed out, enter amount received, see what you left on the table
- **Match Results** — Enter final scores and actual outcomes (updates all related bets)
- **Dashboard** — Auto-calculated KPIs, ROI, win rates, and interactive charts
- **Team & Player Stats** — Performance breakdowns by team, goalscorer, and stage
- **Settings** — Customize dropdown lists, default bet amount, starting bankroll
- **Excel Export** — Download a full workbook with formulas, dropdowns, and conditional formatting

## Auto-Calculated Metrics

- Profit/loss per bet
- Total wagered, payout, and profit/loss
- Bets won, lost, cashed out (with percentages)
- Return on investment (ROI)
- Running bankroll over time
- Performance by group/stage and bet type (outcome vs goalscorer)
- Best performing teams and goalscorer bets

## Quick Start

```bash
cd BettingWorldCup
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Workflow

1. Go to **Bet Log** → choose **Quick Add Match** (2 singles) or **Add Parlay** (combined bet)
2. Enter **odds** for each leg — potential payout calculates automatically
3. After the match, go to **Match Results** → enter the final score and actual outcome
4. Return to **Bet Log → Edit** → set Won/Lost, check **Cashed Out?** if applicable, enter payout
5. Check **Dashboard** — includes "Left on Table" for early cash-outs

## Excel Workbook Sheets

| Sheet | Purpose |
|-------|---------|
| Bet Log | Enter all bets; profit/loss auto-calculated via formulas |
| Match Results | Enter final scores and actual goalscorers |
| Dashboard | KPIs and charts driven by Bet Log formulas |
| Team & Player Stats | Breakdown by team, goalscorer, and stage |
| Settings | Default bet amount and starting bankroll |
| Lists (hidden) | Dropdown source data for validation |

## Data Storage

Bets are stored locally in `data/bets.db` (SQLite). No cloud or account required.

## Customization

In **Settings → Manage Lists**, edit:
- Teams (48 World Cup 2026 teams pre-loaded)
- Goalscorers
- Groups/stages
- Bet statuses and types
- Match outcome options
