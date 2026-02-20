"""File management – locating, moving and renaming downloaded files.

Handles both "standard" and "separate" folder‑structure modes and
delegates to the ``aniworld`` CLI's naming convention for discovery.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from core.constants import (
    LANGUAGE_FILE_SUFFIX,
    VIDEO_EXTENSIONS,
    FolderMode,
)
from core.exceptions import FileManagementError
from core.logging_setup import get_logger
from database import repository as repo
from services.scraper import fetch_episode_title, fetch_series_title
from utils.helpers import (
    build_episode_file_name,
    detect_site,
    get_target_folder,
    sanitize_episode_title,
)

log = get_logger("file_manager")


# ═══════════════════════════════════════════════════════════════════════
# Locate downloaded files
# ═══════════════════════════════════════════════════════════════════════

def find_downloaded_file(
    *,
    series_url: str,
    series_title: str,
    season: str | int,
    episode: str | int,
    download_path: str,
) -> Optional[Path]:
    """Search the *download_path* for a file matching the episode.

    Searches flat files and subdirectories matching the aniworld‑CLI
    naming convention ``Title (Year) [tt‹id›]``.
    """
    dp = Path(download_path)
    if not dp.exists():
        log.warning("Download path does not exist: %s", download_path)
        return None

    s = str(season).strip().lower()
    if s in ("0", "filme"):
        prefix = f"Movie{int(episode):03d}"
    else:
        prefix = f"S{int(season):02d}E{int(episode):03d}"

    # 1) Flat in download_path
    found = _glob_video(dp, prefix)
    if found:
        return found

    # 2) Sub‑folders matching "Title*"
    if series_title:
        escaped = re.escape(series_title)
        pattern = re.compile(
            rf"^{escaped}(\s*\(\d{{4}}\))?(\s*\[tt\d+\])?$",
            re.IGNORECASE,
        )
        for folder in dp.iterdir():
            if folder.is_dir() and (pattern.match(folder.name) or folder.name == series_title):
                found = _glob_video(folder, prefix)
                if found:
                    return found
                # Also check Season sub-folders
                for sub in folder.iterdir():
                    if sub.is_dir():
                        found = _glob_video(sub, prefix)
                        if found:
                            return found

    return None


def _glob_video(directory: Path, prefix: str) -> Optional[Path]:
    """Find first video file containing *prefix* in *directory*."""
    for ext in VIDEO_EXTENSIONS:
        for f in directory.glob(f"*{prefix}*{ext}"):
            if f.is_file():
                return f
    return None


# ═══════════════════════════════════════════════════════════════════════
# Locate existing (already managed) files
# ═══════════════════════════════════════════════════════════════════════

def find_existing_managed_file(
    *,
    series_url: str,
    folder_name: str,
    season: str | int,
    episode: str | int,
    config: dict,
) -> Optional[Path]:
    """Check the organised target folder for an existing file.

    Returns the ``Path`` if found, else ``None``.
    """
    target_root = get_target_folder(
        series_url,
        season,
        folder_mode=config.get("folder_mode", "standard"),
        download_path=config.get("download_path", "."),
        anime_path=config.get("anime_path", ""),
        series_path=config.get("series_path", ""),
        movies_path=config.get("movies_path", ""),
    )

    s = str(season).strip().lower()
    if s in ("0", "filme"):
        target_dir = target_root / folder_name / "Filme"
    else:
        target_dir = target_root / folder_name / f"Staffel {season}"

    if not target_dir.exists():
        return None

    # Build lookup prefix
    if s in ("0", "filme"):
        prefix = f"Film{int(episode):03d}"
    else:
        prefix = f"S{int(season):02d}E{int(episode):03d}"

    suffixes = ["", "[Sub]", "[English Dub]", "[English Sub]"]
    for suffix in suffixes:
        for ext in VIDEO_EXTENSIONS:
            pattern = f"*{prefix}*{suffix}*{ext}" if suffix else f"*{prefix}*{ext}"
            for f in target_dir.glob(pattern):
                if f.is_file():
                    return f
    return None


# ═══════════════════════════════════════════════════════════════════════
# Move & rename
# ═══════════════════════════════════════════════════════════════════════

def move_and_rename(
    *,
    series_url: str,
    series_title: str,
    season: str | int,
    episode: str | int,
    episode_url: str,
    language: str,
    config: dict,
) -> Optional[Path]:
    """Find a downloaded file, move it into the organised structure,
    and rename it to the standard naming pattern.

    Returns the final ``Path`` on success, ``None`` on failure.
    """
    download_path = config.get("download_path", ".")

    # 1. Locate the raw downloaded file
    source = find_downloaded_file(
        series_url=series_url,
        series_title=series_title,
        season=season,
        episode=episode,
        download_path=download_path,
    )
    if source is None:
        log.error("No downloaded file found for S%sE%s", season, episode)
        return None

    log.info("Found downloaded file: %s", source.name)

    # 2. Determine folder name (from DB or from the file's parent)
    folder_name = _resolve_folder_name(
        series_url=series_url,
        series_title=series_title,
        source_file=source,
        download_path=download_path,
    )
    if not folder_name:
        log.error("Cannot determine folder name for %s", series_url)
        return None

    # 3. Build target directory
    target_root = get_target_folder(
        series_url,
        season,
        folder_mode=config.get("folder_mode", "standard"),
        download_path=download_path,
        anime_path=config.get("anime_path", ""),
        series_path=config.get("series_path", ""),
        movies_path=config.get("movies_path", ""),
    )

    s = str(season).strip().lower()
    if s in ("0", "filme"):
        target_dir = target_root / folder_name / "Filme"
    else:
        target_dir = target_root / folder_name / f"Staffel {season}"

    target_dir.mkdir(parents=True, exist_ok=True)

    # 4. Build target file name
    ep_title = fetch_episode_title(episode_url) or f"Episode {episode}"
    lang_suffix = LANGUAGE_FILE_SUFFIX.get(language, "")
    new_name = build_episode_file_name(
        season, episode, ep_title, lang_suffix, source.suffix
    )

    target_path = target_dir / new_name

    # 5. Move / rename
    try:
        if source == target_path:
            log.info("File already at correct path: %s", target_path)
            return target_path
        source.rename(target_path)
        log.info("Moved: %s → %s", source.name, target_path)
        return target_path
    except Exception as exc:
        log.error("Move failed: %s", exc)
        return None


def delete_non_german_version(
    *,
    series_url: str,
    folder_name: str,
    season: str | int,
    episode: str | int,
    config: dict,
) -> bool:
    """Delete a previously downloaded non‑German version of an episode."""
    existing = find_existing_managed_file(
        series_url=series_url,
        folder_name=folder_name,
        season=season,
        episode=episode,
        config=config,
    )
    if not existing:
        return False

    name = existing.name
    if "[Sub]" in name or "[English Dub]" in name or "[English Sub]" in name:
        try:
            existing.unlink()
            log.info("Deleted old non‑German file: %s", name)
            return True
        except Exception as exc:
            log.error("Cannot delete %s: %s", name, exc)
    return False


# ── Internal helpers ──────────────────────────────────────────────────

def _resolve_folder_name(
    *,
    series_url: str,
    series_title: str,
    source_file: Path,
    download_path: str,
) -> str:
    """Determine the canonical folder name for a series.

    Priority: DB stored name → source file parent dir name → series title.
    """
    # 1. Check DB
    series_row = repo.get_series_by_url(series_url)
    if series_row and series_row.folder_name:
        return series_row.folder_name

    # 2. If the file is in a sub‑folder of download_path, use that name
    dp = Path(download_path)
    if source_file.parent != dp:
        folder_name = source_file.parent.name
        # Persist for future lookups
        if series_row:
            repo.update_series_field(series_row.id, folder_name=folder_name)
        return folder_name

    # 3. Fallback to series title
    return series_title or "Unknown"
