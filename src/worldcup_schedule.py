"""World Cup 2026 schedule — re-exports from worldcup_data for backward compatibility."""

from src.worldcup_data import (  # noqa: F401
    filter_matches,
    find_match_index,
    get_schedule_filters,
    load_schedule,
    match_label,
    match_to_fields,
    refresh_all_from_remote,
    refresh_schedule_from_remote,
    resolve_team_name,
)
