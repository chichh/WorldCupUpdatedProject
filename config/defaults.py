"""Default configuration for World Cup 2026 betting tracker."""

DEFAULT_BET_AMOUNT = 20.0
DEFAULT_STARTING_BANKROLL = 1000.0

BET_CATEGORIES = ["Main Challenge", "For Fun"]
DEFAULT_BET_CATEGORY = "Main Challenge"

BET_STATUSES = ["Pending", "Bet Lost", "Bet Cashed Out", "Bet Won"]

# The three settled outcomes users pick from
SETTLED_OUTCOMES = ["Bet Lost", "Bet Cashed Out", "Bet Won"]

BET_TYPES = ["Match Outcome", "Goalscorer", "To Score or Assist", "Same Game Parlay", "Multiple Game Parlay"]

SAME_GAME_PARLAY = "Same Game Parlay"
MULTI_GAME_PARLAY = "Multiple Game Parlay"
LEGACY_PARLAY = "Parlay"
SCORE_OR_ASSIST = "To Score or Assist"
PLAYER_PROP_BET_TYPES = ("Goalscorer", SCORE_OR_ASSIST)

MATCH_OUTCOMES = [
    "Team 1 Win",
    "Team 2 Win",
    "Draw",
    "Team 1 or Draw",
    "Team 2 or Draw",
    "Over 2.5 Goals",
    "Under 2.5 Goals",
    "Both Teams to Score",
    "No Goalscorer",
]

PARLAY_LEG_TYPES = [
    "Match Winner",
    "Goalscorer",
    "To Score or Assist",
    "Correct Score",
    "Over/Under Goals",
    "Both Teams to Score",
    "First Goalscorer",
    "Other",
]

CORRECT_SCORES = [
    "1-0", "2-0", "2-1", "3-0", "3-1", "3-2",
    "0-0", "1-1", "2-2", "3-3",
    "0-1", "0-2", "1-2", "0-3", "1-3", "2-3",
    "Other",
]

OVER_UNDER_OPTIONS = [
    "Over 1.5 Goals",
    "Under 1.5 Goals",
    "Over 2.5 Goals",
    "Under 2.5 Goals",
    "Over 3.5 Goals",
    "Under 3.5 Goals",
]

BTTS_OPTIONS = ["Yes", "No"]

STAGES = [
    "Group A",
    "Group B",
    "Group C",
    "Group D",
    "Group E",
    "Group F",
    "Group G",
    "Group H",
    "Group I",
    "Group J",
    "Group K",
    "Group L",
    "Round of 32",
    "Round of 16",
    "Quarter-Final",
    "Semi-Final",
    "Third Place",
    "Final",
]

# FIFA World Cup 2026 participants (48 teams)
DEFAULT_TEAMS = [
    "Argentina",
    "Australia",
    "Austria",
    "Belgium",
    "Brazil",
    "Bosnia and Herzegovina",
    "Canada",
    "Colombia",
    "Croatia",
    "Curaçao",
    "Czech Republic",
    "Denmark",
    "Ecuador",
    "Egypt",
    "England",
    "France",
    "Germany",
    "Ghana",
    "Haiti",
    "Iran",
    "Italy",
    "Ivory Coast",
    "Japan",
    "Jordan",
    "Mexico",
    "Morocco",
    "Netherlands",
    "New Zealand",
    "Norway",
    "Panama",
    "Paraguay",
    "Poland",
    "Portugal",
    "Qatar",
    "Saudi Arabia",
    "Scotland",
    "Senegal",
    "South Africa",
    "South Korea",
    "Spain",
    "Switzerland",
    "Tunisia",
    "USA",
    "Uruguay",
    "Uzbekistan",
    "Wales",
    "Zambia",
    "Other",
]

DEFAULT_GOALSCORERS = [
    "No Goalscorer",
    "Any Team 1 Player",
    "Any Team 2 Player",
    "Lionel Messi",
    "Kylian Mbappé",
    "Erling Haaland",
    "Harry Kane",
    "Vinícius Júnior",
    "Rodrygo",
    "Lamine Yamal",
    "Pedri",
    "Jude Bellingham",
    "Mohamed Salah",
    "Son Heung-min",
    "Christian Pulisic",
    "Other",
]
