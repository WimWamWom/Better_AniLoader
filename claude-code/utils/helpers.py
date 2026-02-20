"""General helper/utility functions.

URL building, title sanitisation, site detection, etc.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Optional

from core.constants import (
    RE_ANIWORLD_SERIES,
    RE_STO_SERIES,
    ContentType,
    FolderMode,
    Site,
)
from core.logging_setup import get_logger

log = get_logger("helpers")

# ── Title sanitisation ────────────────────────────────────────────────

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]')
_MOVIE_LABEL = re.compile(r"\s*(\[Movie\]|The Movie|Movie)\s*", re.IGNORECASE)


def sanitize_title(title: str) -> str:
    """Remove filesystem‑unsafe characters from *title*."""
    return _UNSAFE_CHARS.sub("_", title).strip()


def sanitize_episode_title(title: str) -> str:
    """Like :func:`sanitize_title` but also strips "Movie" labels."""
    cleaned = _MOVIE_LABEL.sub("", title)
    return sanitize_title(cleaned).strip()


# ── URL helpers ───────────────────────────────────────────────────────

_STRIP_SUFFIX = re.compile(r"/(staffel-\d+|filme)(/.*)?$")


def sanitize_url(url: str) -> str:
    """Normalise a series URL to its base form (strip season/episode)."""
    url = url.strip().rstrip("/")
    return _STRIP_SUFFIX.sub("", url)


def detect_site(url: str) -> Site:
    """Return the :class:`Site` enum for *url*."""
    if "aniworld.to" in url:
        return Site.ANIWORLD
    if "s.to" in url or "serienstream.to" in url:
        return Site.SERIENSTREAM
    raise ValueError(f"Unknown site for URL: {url}")


def detect_content_type(url: str) -> ContentType:
    """Best‑effort content type from URL domain."""
    site = detect_site(url)
    if site == Site.ANIWORLD:
        return ContentType.ANIME
    return ContentType.SERIE


# ── URL builders ──────────────────────────────────────────────────────

def build_season_url(base_url: str, season: str | int) -> str:
    """Build a season URL.

    ``season`` can be a number, ``"0"`` (movies on aniworld.to → ``/filme``),
    or the string ``"filme"``.
    """
    base_url = base_url.rstrip("/")
    s = str(season).strip().lower()
    if s in ("0", "filme"):
        if "aniworld.to" in base_url:
            return f"{base_url}/filme"
        # s.to uses staffel-0 for specials
        return f"{base_url}/staffel-0"
    return f"{base_url}/staffel-{s}"


def build_episode_url(base_url: str, season: str | int, episode: str | int) -> str:
    """Build a full episode URL."""
    season_url = build_season_url(base_url, season)
    s = str(season).strip().lower()
    if s in ("0", "filme") and "aniworld.to" in base_url:
        return f"{season_url}/film-{episode}"
    return f"{season_url}/episode-{episode}"


# ── File‑system helpers ──────────────────────────────────────────────

def free_disk_gb(path: str) -> float:
    """Return free disk space in GB for the volume containing *path*."""
    try:
        usage = shutil.disk_usage(path)
        return usage.free / (1024 ** 3)
    except Exception:
        return 0.0


def get_target_folder(
    base_url: str,
    season: str | int,
    *,
    folder_mode: str,
    download_path: str,
    anime_path: str = "",
    series_path: str = "",
    movies_path: str = "",
) -> Path:
    """Determine the target root folder for a download.

    In **standard** mode everything goes to *download_path*.
    In **separate** mode content is routed by site and season type.
    """
    if folder_mode == FolderMode.STANDARD.value:
        return Path(download_path)

    # Separate mode
    site = detect_site(base_url)
    s = str(season).strip().lower()
    is_movie = s in ("0", "filme")

    if site == Site.ANIWORLD:
        if is_movie and movies_path:
            return Path(movies_path)
        return Path(anime_path) if anime_path else Path(download_path) / "Anime"
    else:
        if is_movie and movies_path:
            return Path(movies_path)
        return Path(series_path) if series_path else Path(download_path) / "Serien"


def build_episode_file_name(
    season: str | int,
    episode: str | int,
    title: str,
    language_suffix: str = "",
    extension: str = ".mkv",
) -> str:
    """Build a consistent file name like ``S01E005 - Title.mkv``."""
    s = str(season).strip().lower()
    if s in ("0", "filme"):
        prefix = f"Film{int(episode):03d}"
    else:
        prefix = f"S{int(season):02d}E{int(episode):03d}"

    name = f"{prefix} - {sanitize_episode_title(title)}"
    if language_suffix:
        name += language_suffix
    return name + extension
