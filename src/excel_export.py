"""Generate Excel workbook with formulas, dropdowns, and conditional formatting."""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import xlsxwriter

from config.defaults import (
    BET_CATEGORIES,
    BET_STATUSES,
    BET_TYPES,
    DEFAULT_BET_AMOUNT,
    DEFAULT_GOALSCORERS,
    DEFAULT_STARTING_BANKROLL,
    DEFAULT_TEAMS,
    MATCH_OUTCOMES,
    STAGES,
)
from src.calculations import enrich_bets
from src.database import get_all_bets, get_setting


def _text(value) -> str:
    """Coerce a cell value to a safe Excel string (NaN/None → empty)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value)


def _write_lists_sheet(workbook, formats):
    ws = workbook.add_worksheet("Lists")
    ws.hide()

    lists = {
        "A": STAGES,
        "C": DEFAULT_TEAMS,
        "E": BET_TYPES,
        "G": MATCH_OUTCOMES,
        "I": DEFAULT_GOALSCORERS,
        "K": BET_STATUSES,
        "M": BET_CATEGORIES,
    }
    for col, items in lists.items():
        ws.write(f"{col}1", col.strip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") or "List")
        for i, item in enumerate(items, start=1):
            ws.write(f"{col}{i}", item)

    return ws


def _add_bet_log_sheet(workbook, formats, bets_df: pd.DataFrame):
    ws = workbook.add_worksheet("Bet Log")
    ws.set_tab_color("#1F4E79")

    headers = [
        "ID",
        "Match Date",
        "Group/Stage",
        "Team 1",
        "Team 2",
        "Bet Type",
        "Category",
        "Prediction",
        "Bet Amount ($)",
        "Odds",
        "Outcome Odds",
        "Goalscorer Odds",
        "Potential Payout ($)",
        "Cashed Out?",
        "Status",
        "Cash-out ($)",
        "Payout ($)",
        "Profit/Loss ($)",
        "Left on Table ($)",
        "Final Score",
        "Actual Result",
        "Actual Goalscorer",
        "Notes",
    ]

    for col, header in enumerate(headers):
        ws.write(0, col, header, formats["header"])

    ws.set_column(0, 0, 6)
    ws.set_column(1, 2, 12)
    ws.set_column(3, 4, 14)
    ws.set_column(5, 7, 18)
    ws.set_column(8, 18, 12)
    ws.set_column(19, 22, 14)

    start_row = 1
    max_rows = max(len(bets_df) + 50, 200)

    for row in range(start_row, max_rows):
        excel_row = row + 1
        ws.write_formula(
            row, 17,
            f'=IF(O{excel_row}="Bet Won",Q{excel_row}-I{excel_row},'
            f'IF(O{excel_row}="Bet Lost",-I{excel_row},'
            f'IF(O{excel_row}="Bet Cashed Out",P{excel_row}-I{excel_row},0)))',
            formats["currency"],
        )
        ws.write_formula(
            row, 18,
            f'=IF(N{excel_row}="Yes",M{excel_row}-P{excel_row},"")',
            formats["currency"],
        )

    stage_range = f"=Lists!$A$1:$A${len(STAGES)}"
    team_range = f"=Lists!$C$1:$C${len(DEFAULT_TEAMS)}"
    bet_type_range = f"=Lists!$E$1:$E${len(BET_TYPES)}"
    category_range = f"=Lists!$M$1:$M${len(BET_CATEGORIES)}"
    status_range = f"=Lists!$K$1:$K${len(BET_STATUSES)}"
    yes_no = '"Yes,No"'

    for row in range(start_row, max_rows):
        ws.data_validation(row, 2, row, 2, {"validate": "list", "source": stage_range})
        ws.data_validation(row, 3, row, 3, {"validate": "list", "source": team_range})
        ws.data_validation(row, 4, row, 4, {"validate": "list", "source": team_range})
        ws.data_validation(row, 5, row, 5, {"validate": "list", "source": bet_type_range})
        ws.data_validation(row, 6, row, 6, {"validate": "list", "source": category_range})
        ws.data_validation(row, 13, row, 13, {"validate": "list", "source": yes_no})
        ws.data_validation(row, 14, row, 14, {"validate": "list", "source": status_range})

    ws.conditional_format(
        f"R{start_row + 1}:R{max_rows}",
        {"type": "cell", "criteria": ">", "value": 0, "format": formats["profit"]},
    )
    ws.conditional_format(
        f"R{start_row + 1}:R{max_rows}",
        {"type": "cell", "criteria": "<", "value": 0, "format": formats["loss"]},
    )
    ws.conditional_format(
        f"O{start_row + 1}:O{max_rows}",
        {"type": "text", "criteria": "containing", "value": "Won", "format": formats["won_status"]},
    )
    ws.conditional_format(
        f"O{start_row + 1}:O{max_rows}",
        {"type": "text", "criteria": "containing", "value": "Lost", "format": formats["lost_status"]},
    )

    if not bets_df.empty:
        for i, (_, bet) in enumerate(bets_df.iterrows()):
            row = start_row + i
            ws.write(row, 0, bet.get("id", i + 1))
            ws.write(row, 1, str(bet.get("match_date", ""))[:10], formats["date"])
            ws.write(row, 2, _text(bet.get("group_stage")))
            ws.write(row, 3, _text(bet.get("team1")))
            ws.write(row, 4, _text(bet.get("team2")))
            ws.write(row, 5, _text(bet.get("bet_type")))
            ws.write(row, 6, _text(bet.get("bet_category")) or "Main Challenge")
            ws.write(row, 7, _text(bet.get("prediction")))
            ws.write(row, 8, float(bet.get("bet_amount", DEFAULT_BET_AMOUNT)), formats["currency"])
            if bet.get("effective_odds") and pd.notna(bet.get("effective_odds")):
                ws.write(row, 9, float(bet["effective_odds"]))
            pot = bet.get("potential_payout_calc")
            if pot is not None and pd.notna(pot):
                ws.write(row, 12, float(pot), formats["currency"])
            ws.write(row, 13, "Yes" if bet.get("cashed_out") else "No")
            ws.write(row, 14, _text(bet.get("status")) or "Pending")
            cashout = bet.get("cashout_amount")
            payout = bet.get("payout_amount")
            if cashout is not None and pd.notna(cashout):
                ws.write(row, 15, float(cashout), formats["currency"])
            if payout is not None and pd.notna(payout):
                ws.write(row, 16, float(payout), formats["currency"])
            ws.write(row, 19, _text(bet.get("final_score")))
            ws.write(row, 20, _text(bet.get("actual_result")))
            ws.write(row, 21, _text(bet.get("actual_goalscorer")))
            ws.write(row, 22, _text(bet.get("notes")))

    ws.freeze_panes(1, 0)
    return ws


def _add_match_results_sheet(workbook, formats, bets_df: pd.DataFrame):
    ws = workbook.add_worksheet("Match Results")
    ws.set_tab_color("#2E75B6")

    headers = ["Match Date", "Group/Stage", "Team 1", "Team 2", "Final Score", "Actual Result", "Actual Goalscorer"]
    for col, h in enumerate(headers):
        ws.write(0, col, h, formats["header"])

    if not bets_df.empty:
        matches = (
            bets_df.groupby(["match_date", "team1", "team2"], as_index=False)
            .first()[["match_date", "group_stage", "team1", "team2", "final_score", "actual_result", "actual_goalscorer"]]
        )
        for i, (_, m) in enumerate(matches.iterrows(), start=1):
            ws.write(i, 0, str(m["match_date"])[:10], formats["date"])
            ws.write(i, 1, _text(m["group_stage"]))
            ws.write(i, 2, _text(m["team1"]))
            ws.write(i, 3, _text(m["team2"]))
            ws.write(i, 4, _text(m.get("final_score")))
            ws.write(i, 5, _text(m.get("actual_result")))
            ws.write(i, 6, _text(m.get("actual_goalscorer")))

    ws.set_column(0, 6, 16)
    ws.freeze_panes(1, 0)


def _add_dashboard_sheet(workbook, formats, starting_bankroll: float):
    ws = workbook.add_worksheet("Dashboard")
    ws.set_tab_color("#548235")

    ws.merge_range("A1:F1", "World Cup Betting Challenge — Dashboard", formats["title"])
    ws.write("A3", "Key Performance Indicators", formats["section"])

    kpis = [
        ("Total Bets", '=COUNTA(\'Bet Log\'!A2:A500)'),
        ("Total Wagered", '=SUM(\'Bet Log\'!I2:I500)'),
        ("Total Payout", '=SUMIF(\'Bet Log\'!O2:O500,"Bet Won",\'Bet Log\'!Q2:Q500)+SUMIF(\'Bet Log\'!O2:O500,"Bet Cashed Out",\'Bet Log\'!P2:P500)'),
        ("Total Profit/Loss", '=SUM(\'Bet Log\'!R2:R500)'),
        ("Left on Table (cash-outs)", '=SUM(\'Bet Log\'!S2:S500)'),
        ("Main Challenge P/L", '=SUMIF(\'Bet Log\'!G2:G500,"Main Challenge",\'Bet Log\'!R2:R500)'),
        ("For Fun P/L", '=SUMIF(\'Bet Log\'!G2:G500,"For Fun",\'Bet Log\'!R2:R500)'),
        ("Bets Won", '=COUNTIF(\'Bet Log\'!O2:O500,"Bet Won")'),
        ("Bets Lost", '=COUNTIF(\'Bet Log\'!O2:O500,"Bet Lost")'),
        ("Bets Cashed Out", '=COUNTIF(\'Bet Log\'!N2:N500,"Yes")'),
        ("Parlays", '=COUNTIF(\'Bet Log\'!F2:F500,"Same Game Parlay")+COUNTIF(\'Bet Log\'!F2:F500,"Multiple Game Parlay")'),
        ("Win %", '=IFERROR(B11/(B11+B12+B13)*100,0)'),
        ("Loss %", '=IFERROR(B12/(B11+B12+B13)*100,0)'),
        ("Cash-out %", '=IFERROR(B13/(B11+B12+B13)*100,0)'),
        ("ROI %", '=IFERROR(B7/B5*100,0)'),
        ("Current Bankroll", f"={starting_bankroll}+B7"),
    ]

    for i, (label, formula) in enumerate(kpis, start=4):
        ws.write(f"A{i}", label, formats["kpi_label"])
        if "%" in label:
            ws.write_formula(f"B{i}", formula, formats["pct"])
        elif "Bankroll" in label or "Wagered" in label or "Payout" in label or "Profit" in label:
            ws.write_formula(f"B{i}", formula, formats["currency"])
        else:
            ws.write_formula(f"B{i}", formula, formats["number"])

    ws.write("A20", "Performance by Bet Type", formats["section"])
    ws.write_row("A21", ["Bet Type", "Bets", "Wagered", "Profit/Loss", "ROI %"], formats["header"])
    for i, bt in enumerate(BET_TYPES, start=22):
        ws.write(f"A{i}", bt)
        ws.write_formula(f"B{i}", f'=COUNTIF(\'Bet Log\'!F2:F500,"{bt}")')
        ws.write_formula(f"C{i}", f'=SUMIF(\'Bet Log\'!F2:F500,"{bt}",\'Bet Log\'!I2:I500)', formats["currency"])
        ws.write_formula(f"D{i}", f'=SUMIF(\'Bet Log\'!F2:F500,"{bt}",\'Bet Log\'!R2:R500)', formats["currency"])
        ws.write_formula(f"E{i}", f'=IFERROR(D{i}/C{i}*100,0)', formats["pct"])

    chart = workbook.add_chart({"type": "line"})
    chart.add_series(
        {
            "name": "Cumulative P/L",
            "categories": "='Bet Log'!$B$2:$B$200",
            "values": "='Bet Log'!$R$2:$R$200",
        }
    )
    chart.set_title({"name": "Profit/Loss by Match Date"})
    chart.set_x_axis({"name": "Match Date"})
    chart.set_y_axis({"name": "Profit/Loss ($)"})
    ws.insert_chart("D3", chart, {"x_scale": 1.5, "y_scale": 1.2})

    ws.set_column("A:A", 22)
    ws.set_column("B:E", 16)


def _add_team_stats_sheet(workbook, formats):
    ws = workbook.add_worksheet("Team & Player Stats")
    ws.set_tab_color("#BF8F00")

    ws.write("A1", "Goalscorer Bet Performance", formats["section"])
    ws.write_row("A2", ["Goalscorer", "Bets", "Wagered", "Profit/Loss", "Wins"], formats["header"])

    ws.write("G1", "Performance by Group/Stage", formats["section"])
    ws.write_row("G2", ["Stage", "Bets", "Wagered", "Profit/Loss"], formats["header"])

    for i, stage in enumerate(STAGES[:12], start=3):
        ws.write(f"G{i}", stage)
        ws.write_formula(f"H{i}", f'=COUNTIF(\'Bet Log\'!C2:C500,"{stage}")')
        ws.write_formula(f"I{i}", f'=SUMIF(\'Bet Log\'!C2:C500,"{stage}",\'Bet Log\'!I2:I500)', formats["currency"])
        ws.write_formula(f"J{i}", f'=SUMIF(\'Bet Log\'!C2:C500,"{stage}",\'Bet Log\'!R2:R500)', formats["currency"])

    ws.set_column("A:J", 16)


def _add_settings_sheet(workbook, formats):
    ws = workbook.add_worksheet("Settings")
    ws.set_tab_color("#7F7F7F")

    ws.write("A1", "Configuration", formats["title"])
    ws.write("A3", "Default Bet Amount ($)", formats["kpi_label"])
    ws.write("B3", DEFAULT_BET_AMOUNT, formats["currency"])
    ws.write("A4", "Starting Bankroll ($)", formats["kpi_label"])
    ws.write("B4", get_setting("starting_bankroll", DEFAULT_STARTING_BANKROLL), formats["currency"])

    ws.write("A6", "Available Lists (edit on Lists sheet)", formats["section"])
    ws.write("A7", "Teams, Stages, Bet Types, Statuses, Outcomes, Goalscorers")
    ws.set_column("A:B", 28)


def generate_excel_workbook() -> bytes:
    bets = get_all_bets()
    bets_df = enrich_bets(bets)
    starting_bankroll = float(get_setting("starting_bankroll", DEFAULT_STARTING_BANKROLL))

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})

    formats = {
        "header": workbook.add_format({"bold": True, "bg_color": "#1F4E79", "font_color": "white", "border": 1}),
        "title": workbook.add_format({"bold": True, "font_size": 16, "bg_color": "#1F4E79", "font_color": "white"}),
        "section": workbook.add_format({"bold": True, "font_size": 12, "bg_color": "#D9E2F3"}),
        "kpi_label": workbook.add_format({"bold": True}),
        "currency": workbook.add_format({"num_format": "$#,##0.00"}),
        "pct": workbook.add_format({"num_format": "0.0%"}),
        "number": workbook.add_format({"num_format": "#,##0"}),
        "date": workbook.add_format({"num_format": "yyyy-mm-dd"}),
        "profit": workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100", "num_format": "$#,##0.00"}),
        "loss": workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006", "num_format": "$#,##0.00"}),
        "won_status": workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"}),
        "lost_status": workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"}),
    }

    _write_lists_sheet(workbook, formats)
    _add_bet_log_sheet(workbook, formats, bets_df)
    _add_match_results_sheet(workbook, formats, bets_df)
    _add_dashboard_sheet(workbook, formats, starting_bankroll)
    _add_team_stats_sheet(workbook, formats)
    _add_settings_sheet(workbook, formats)

    workbook.close()
    output.seek(0)
    return output.read()


def generate_blank_template() -> bytes:
    """Generate empty Excel template for manual use."""
    return generate_excel_workbook()
