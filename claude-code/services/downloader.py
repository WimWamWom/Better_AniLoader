"""Download orchestrator – the four operational modes.

Delegates actual video downloading to the ``aniworld`` CLI tool and
coordinates scraping, file management, and database bookkeeping.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.config import load_config
from core.constants import (
    LANGUAGE_FILE_SUFFIX,
    MIN_VALID_FILE_SIZE,
    POST_DOWNLOAD_WAIT,
    DownloadMode,
    DownloadStatus,
    Language,
)
from core.exceptions import (
    DownloadAlreadyRunningError,
    DownloadError,
    InsufficientDiskSpaceError,
)
from core.logging_setup import get_logger
from database import repository as repo
from database.models import Download, Episode, Season, Series
from services.file_manager import (
    delete_non_german_version,
    find_downloaded_file,
    find_existing_managed_file,
    move_and_rename,
)
from services.scraper import (
    fetch_all_seasons_with_episodes,
    fetch_episode_title,
    fetch_languages_for_episode,
    fetch_series_title,
)
from utils.helpers import (
    build_episode_url,
    detect_content_type,
    detect_site,
    free_disk_gb,
)

log = get_logger("downloader")

# ── Global state ──────────────────────────────────────────────────────

_running = False
_stop_requested = False


def is_running() -> bool:
    return _running


def request_stop() -> None:
    global _stop_requested
    _stop_requested = True


def _check_stop() -> bool:
    """Return True if the user requested an abort."""
    return _stop_requested


# ═══════════════════════════════════════════════════════════════════════
# CLI wrapper
# ═══════════════════════════════════════════════════════════════════════

def _run_aniworld_cli(
    episode_url: str,
    language: str,
    download_path: str,
) -> bool:
    """Shell out to ``aniworld`` to download a single episode.

    Returns ``True`` on success (return code 0).
    """
    cmd = f'aniworld --language "{language}" -a Download -o "{download_path}" {episode_url}'

    # Windows: force UTF‑8 console
    if sys.platform == "win32":
        cmd = f"chcp 65001 >nul & {cmd}"

    log.info("Running: %s", cmd)
    try:
        result = subprocess.run(cmd, shell=True, timeout=1800)  # 30 min timeout
        if result.returncode == 0:
            time.sleep(POST_DOWNLOAD_WAIT)
            return True
        log.warning("aniworld exited with code %d", result.returncode)
        return False
    except subprocess.TimeoutExpired:
        log.error("Download timed out for %s", episode_url)
        return False
    except Exception as exc:
        log.error("Download process error: %s", exc)
        return False


# ═══════════════════════════════════════════════════════════════════════
# Language selection
# ═══════════════════════════════════════════════════════════════════════

def _select_language(
    available: List[str],
    priority: List[str],
) -> Optional[str]:
    """Pick the best language from *available* according to *priority*."""
    for lang in priority:
        if lang in available:
            return lang
    return available[0] if available else None


# ═══════════════════════════════════════════════════════════════════════
# Core download for a single episode
# ═══════════════════════════════════════════════════════════════════════

def _download_episode(
    *,
    series: Series,
    season_number: str | int,
    episode_number: str | int,
    episode_url: str,
    config: dict,
    force_language: Optional[str] = None,
) -> tuple[bool, str]:
    """Download one episode.  Returns ``(success, language_used)``."""

    # Check disk space
    min_free = config.get("min_free_gb", 100.0)
    if free_disk_gb(config["download_path"]) < min_free:
        raise InsufficientDiskSpaceError(
            f"Less than {min_free} GB free on {config['download_path']}"
        )

    # Determine language
    if force_language:
        language = force_language
    else:
        available = fetch_languages_for_episode(episode_url)
        if not available:
            log.warning("No languages found for %s", episode_url)
            return False, ""
        priority = config.get("languages_priority", [Language.GERMAN_DUB.value])
        language = _select_language(available, priority)
        if not language:
            log.warning("No suitable language for %s", episode_url)
            return False, ""

    # Upsert episode in DB (languages)
    ep_row = repo.get_episode_by_url(episode_url)
    if ep_row:
        available = fetch_languages_for_episode(episode_url) if not force_language else [force_language]
        if available:
            repo.set_episode_languages(ep_row.id, available)

    # Run the download
    success = _run_aniworld_cli(
        episode_url, language, config["download_path"]
    )

    if not success:
        if ep_row:
            repo.upsert_download(Download(
                episode_id=ep_row.id,
                language=language,
                status=DownloadStatus.FAILED.value,
                error_message="aniworld CLI returned non-zero",
            ))
        return False, language

    # Move and rename the file
    final_path = move_and_rename(
        series_url=series.url,
        series_title=series.title,
        season=season_number,
        episode=episode_number,
        episode_url=episode_url,
        language=language,
        config=config,
    )

    if final_path and ep_row:
        repo.upsert_download(Download(
            episode_id=ep_row.id,
            language=language,
            file_path=str(final_path),
            file_size=final_path.stat().st_size if final_path.exists() else None,
            status=DownloadStatus.COMPLETED.value,
            downloaded_at=datetime.utcnow().isoformat(),
        ))

    return bool(final_path), language


# ═══════════════════════════════════════════════════════════════════════
# Sync series data from web → DB
# ═══════════════════════════════════════════════════════════════════════

def _sync_series_data(series: Series) -> Dict[str, List[Dict[str, str]]]:
    """Fetch season/episode data from the site and upsert into DB.

    Returns the ``{season: [episode_dicts]}`` mapping.
    """
    all_data = fetch_all_seasons_with_episodes(series.url)

    for season_str, episodes in all_data.items():
        s_num = int(season_str) if season_str.isdigit() else 0
        is_movie = season_str.strip().lower() in ("0", "filme")
        season_obj = Season(
            series_id=series.id,
            season_number=s_num,
            is_movie_season=is_movie,
            episode_count=len(episodes),
        )
        season_id = repo.upsert_season(season_obj)

        for ep in episodes:
            ep_title = fetch_episode_title(ep["url"]) or ""
            ep_title_en = fetch_episode_title(ep["url"], english=True)
            episode_obj = Episode(
                series_id=series.id,
                season_id=season_id,
                episode_number=int(ep["number"]),
                title_de=ep_title,
                title_en=ep_title_en,
                url=ep["url"],
                is_movie=is_movie,
            )
            repo.upsert_episode(episode_obj)

    # Update last check timestamp
    repo.update_series_field(series.id, last_check=datetime.utcnow().isoformat())
    return all_data


# ═══════════════════════════════════════════════════════════════════════
# MODES
# ═══════════════════════════════════════════════════════════════════════


def run_download(mode: str = "default") -> None:
    """Main entry point for all download modes."""
    global _running, _stop_requested
    if _running:
        raise DownloadAlreadyRunningError("A download is already in progress")

    _running = True
    _stop_requested = False

    try:
        config = load_config()
        all_series = repo.get_all_series()

        if not all_series:
            log.info("No series in database. Add series first.")
            return

        log.info("=" * 60)
        log.info("Starting download – mode=%s – %d series", mode, len(all_series))
        log.info("=" * 60)

        for series in all_series:
            if _check_stop():
                log.info("Download stopped by user request")
                break

            try:
                if mode == DownloadMode.DEFAULT.value:
                    _mode_default(series, config)
                elif mode == DownloadMode.GERMAN.value:
                    _mode_german(series, config)
                elif mode == DownloadMode.NEW.value:
                    _mode_new(series, config)
                elif mode == DownloadMode.CHECK.value:
                    _mode_check(series, config)
                else:
                    log.error("Unknown mode: %s", mode)
                    return
            except InsufficientDiskSpaceError as exc:
                log.error("Disk space: %s – aborting", exc)
                break
            except Exception as exc:
                log.error("Error processing '%s': %s", series.title, exc, exc_info=True)
                continue

        log.info("=" * 60)
        log.info("Download run complete (mode=%s)", mode)
        log.info("=" * 60)

    finally:
        _running = False
        _stop_requested = False


# ── Default mode ──────────────────────────────────────────────────────

def _mode_default(series: Series, config: dict) -> None:
    """Download all missing episodes using language priority."""
    if series.complete:
        log.info("[SKIP] '%s' already marked complete", series.title)
        return

    log.info("── Default: %s ──", series.title)
    all_data = _sync_series_data(series)
    if not all_data:
        log.warning("No season data for %s", series.title)
        return

    missing_german: List[str] = []
    downloaded_count = 0
    folder_name = series.folder_name or series.title

    for season_str, episodes in all_data.items():
        for ep in episodes:
            if _check_stop():
                return

            ep_num = ep["number"]
            ep_url = ep["url"]

            # Skip if already downloaded
            existing = find_existing_managed_file(
                series_url=series.url,
                folder_name=folder_name,
                season=season_str,
                episode=ep_num,
                config=config,
            )
            if existing:
                log.debug("[SKIP] Already exists: S%sE%s", season_str, ep_num)
                # Track non-German
                name = existing.name
                if "[Sub]" in name or "[English" in name:
                    missing_german.append(ep_url)
                continue

            try:
                success, lang_used = _download_episode(
                    series=series,
                    season_number=season_str,
                    episode_number=ep_num,
                    episode_url=ep_url,
                    config=config,
                )
                if success:
                    downloaded_count += 1
                    if lang_used != Language.GERMAN_DUB.value:
                        missing_german.append(ep_url)
                else:
                    log.warning("Download failed for S%sE%s", season_str, ep_num)
            except Exception as exc:
                log.error("Episode error S%sE%s: %s", season_str, ep_num, exc)

    # Update series status
    repo.update_series_field(
        series.id,
        german_complete=1 if not missing_german else 0,
    )
    if downloaded_count > 0:
        repo.update_series_field(series.id, complete=1)
        log.info("'%s': %d episodes downloaded, marked complete", series.title, downloaded_count)


# ── German mode ───────────────────────────────────────────────────────

def _mode_german(series: Series, config: dict) -> None:
    """Check for newly available German dubs and re‑download."""
    if series.german_complete:
        log.info("[SKIP] '%s' already fully German", series.title)
        return

    log.info("── German: %s ──", series.title)
    folder_name = series.folder_name or series.title

    # Find episodes with non-German downloads
    episodes = repo.get_episodes_for_series(series.id)
    remaining_non_german: List[str] = []

    for ep in episodes:
        if _check_stop():
            return

        # Check if we have a non-German version
        existing = find_existing_managed_file(
            series_url=series.url,
            folder_name=folder_name,
            season=_get_season_number(ep.season_id),
            episode=ep.episode_number,
            config=config,
        )
        if not existing:
            continue

        name = existing.name
        if "[Sub]" not in name and "[English" not in name:
            continue  # Already German

        # Check if German is now available
        languages = fetch_languages_for_episode(ep.url)
        if Language.GERMAN_DUB.value not in languages:
            remaining_non_german.append(ep.url)
            log.debug("German still not available for %s", ep.url)
            continue

        # Delete old version and re‑download in German
        season_number = _get_season_number(ep.season_id)
        delete_non_german_version(
            series_url=series.url,
            folder_name=folder_name,
            season=season_number,
            episode=ep.episode_number,
            config=config,
        )

        try:
            success, _ = _download_episode(
                series=series,
                season_number=season_number,
                episode_number=ep.episode_number,
                episode_url=ep.url,
                config=config,
                force_language=Language.GERMAN_DUB.value,
            )
            if success:
                log.info("German download OK: S%sE%s", season_number, ep.episode_number)
            else:
                remaining_non_german.append(ep.url)
        except Exception as exc:
            log.error("German DL error: %s", exc)
            remaining_non_german.append(ep.url)

    if not remaining_non_german:
        repo.update_series_field(series.id, german_complete=1)
        log.info("'%s' now fully available in German", series.title)


# ── New mode ──────────────────────────────────────────────────────────

def _mode_new(series: Series, config: dict) -> None:
    """Check completed series for newly released episodes."""
    if not series.complete:
        log.info("[SKIP] '%s' not yet complete – use default mode first", series.title)
        return

    log.info("── New: %s ──", series.title)
    folder_name = series.folder_name or series.title

    # Get current state from website
    current_data = fetch_all_seasons_with_episodes(series.url)
    if not current_data:
        log.warning("Cannot fetch current data for %s", series.url)
        return

    # Get stored state from DB
    db_seasons = repo.get_seasons_for_series(series.id)
    db_season_map: Dict[int, int] = {}  # season_number → episode_count
    for s in db_seasons:
        db_episodes = repo.get_episodes_for_season(s.id)
        db_season_map[s.season_number] = len(db_episodes)

    new_found = False

    for season_str, episodes in current_data.items():
        s_num = int(season_str) if season_str.isdigit() else 0
        db_count = db_season_map.get(s_num, 0)
        web_count = len(episodes)

        if web_count <= db_count:
            continue

        new_found = True
        log.info("New episodes in Season %s: %d (was %d)", season_str, web_count, db_count)

        # Sync this season to DB
        is_movie = season_str.strip().lower() in ("0", "filme")
        season_id = repo.upsert_season(Season(
            series_id=series.id,
            season_number=s_num,
            is_movie_season=is_movie,
            episode_count=web_count,
        ))

        for ep in episodes:
            if _check_stop():
                return

            ep_num = int(ep["number"])
            # Skip already known episodes
            if ep_num <= db_count:
                continue

            # Upsert episode in DB
            ep_title = fetch_episode_title(ep["url"]) or ""
            episode_obj = Episode(
                series_id=series.id,
                season_id=season_id,
                episode_number=ep_num,
                title_de=ep_title,
                url=ep["url"],
                is_movie=is_movie,
            )
            repo.upsert_episode(episode_obj)

            try:
                success, lang_used = _download_episode(
                    series=series,
                    season_number=season_str,
                    episode_number=ep_num,
                    episode_url=ep["url"],
                    config=config,
                )
                if success:
                    log.info("New episode downloaded: S%sE%03d", season_str, ep_num)
            except Exception as exc:
                log.error("New episode error: %s", exc)

    if not new_found:
        log.info("No new episodes for '%s'", series.title)


# ── Check mode ────────────────────────────────────────────────────────

def _mode_check(series: Series, config: dict) -> None:
    """Verify all downloads – check file existence and size."""
    log.info("── Check: %s ──", series.title)
    folder_name = series.folder_name or series.title

    # Sync latest data
    _sync_series_data(series)

    episodes = repo.get_episodes_for_series(series.id)
    missing_count = 0
    corrupt_count = 0

    for ep in episodes:
        if _check_stop():
            return

        season_number = _get_season_number(ep.season_id)

        existing = find_existing_managed_file(
            series_url=series.url,
            folder_name=folder_name,
            season=season_number,
            episode=ep.episode_number,
            config=config,
        )

        if not existing:
            # File missing
            missing_count += 1
            log.warning(
                "[MISSING] S%sE%03d – %s",
                season_number, ep.episode_number, ep.title_de or ep.url,
            )
            repo.upsert_download(Download(
                episode_id=ep.id,
                language="",
                status=DownloadStatus.MISSING.value,
                checked_at=datetime.utcnow().isoformat(),
            ))
            continue

        # File exists – check size
        try:
            size = existing.stat().st_size
        except OSError:
            size = 0

        if size < MIN_VALID_FILE_SIZE:
            corrupt_count += 1
            log.warning(
                "[CORRUPT] S%sE%03d – size %d bytes (< %d)",
                season_number, ep.episode_number, size, MIN_VALID_FILE_SIZE,
            )
            # Determine language from file name
            lang = _detect_language_from_filename(existing.name)
            repo.upsert_download(Download(
                episode_id=ep.id,
                language=lang,
                file_path=str(existing),
                file_size=size,
                status=DownloadStatus.CORRUPT.value,
                checked_at=datetime.utcnow().isoformat(),
            ))
        else:
            lang = _detect_language_from_filename(existing.name)
            repo.upsert_download(Download(
                episode_id=ep.id,
                language=lang,
                file_path=str(existing),
                file_size=size,
                status=DownloadStatus.COMPLETED.value,
                checked_at=datetime.utcnow().isoformat(),
            ))

    log.info(
        "Check complete for '%s': %d missing, %d corrupt, %d OK",
        series.title, missing_count, corrupt_count,
        len(episodes) - missing_count - corrupt_count,
    )


# ── Helpers ───────────────────────────────────────────────────────────

def _get_season_number(season_id: int) -> str:
    """Look up season number from DB."""
    seasons = repo.get_seasons_for_series(0)  # hack – we need by season_id
    # Direct query is simpler
    from database.connection import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT season_number FROM seasons WHERE id = ?", (season_id,)
        ).fetchone()
        return str(row["season_number"]) if row else "1"
    finally:
        conn.close()


def _detect_language_from_filename(filename: str) -> str:
    """Infer the download language from the file name suffix."""
    if "[English Sub]" in filename:
        return Language.ENGLISH_SUB.value
    if "[English Dub]" in filename:
        return Language.ENGLISH_DUB.value
    if "[Sub]" in filename:
        return Language.GERMAN_SUB.value
    return Language.GERMAN_DUB.value
