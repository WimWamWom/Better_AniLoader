"""Scanner service – periodic checking for new episodes and German availability."""

from __future__ import annotations

from typing import Dict, List

from core.logging_setup import get_logger
from database import repository as repo
from services.scraper import fetch_all_seasons_with_episodes, fetch_languages_for_episode

log = get_logger("scanner")


def scan_for_new_episodes(series_id: int) -> Dict[str, List[str]]:
    """Compare DB state with website for a single series.

    Returns a dict ``{season: [new_episode_numbers]}``.
    """
    series = repo.get_series_by_id(series_id)
    current_data = fetch_all_seasons_with_episodes(series.url)

    db_seasons = repo.get_seasons_for_series(series_id)
    db_season_map: Dict[int, int] = {}
    for s in db_seasons:
        db_episodes = repo.get_episodes_for_season(s.id)
        db_season_map[s.season_number] = len(db_episodes)

    new_eps: Dict[str, List[str]] = {}

    for season_str, episodes in current_data.items():
        s_num = int(season_str) if season_str.isdigit() else 0
        db_count = db_season_map.get(s_num, 0)
        new_in_season = [
            ep["number"] for ep in episodes if int(ep["number"]) > db_count
        ]
        if new_in_season:
            new_eps[season_str] = new_in_season
            log.info(
                "Series '%s' S%s: %d new episode(s)",
                series.title, season_str, len(new_in_season),
            )

    return new_eps


def scan_german_availability(series_id: int) -> List[str]:
    """Check which episodes have German Dub newly available.

    Returns a list of episode URLs that *now* have German Dub
    but didn't before (i.e. currently lack a completed German download).
    """
    from core.constants import Language

    series = repo.get_series_by_id(series_id)
    episodes = repo.get_episodes_missing_language(
        series_id, Language.GERMAN_DUB.value
    )

    newly_available: List[str] = []
    for ep in episodes:
        languages = fetch_languages_for_episode(ep.url)
        if Language.GERMAN_DUB.value in languages:
            newly_available.append(ep.url)
            log.info(
                "German Dub now available: %s S?E%03d",
                series.title, ep.episode_number,
            )

    return newly_available


def scan_all_series_for_new() -> Dict[int, Dict[str, List[str]]]:
    """Scan every non‑deleted series for new episodes.

    Returns ``{series_id: {season: [new_eps]}}``.
    """
    result: Dict[int, Dict[str, List[str]]] = {}
    for series in repo.get_all_series():
        if not series.complete:
            continue
        new = scan_for_new_episodes(series.id)
        if new:
            result[series.id] = new
    return result
