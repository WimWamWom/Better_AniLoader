"""Constants, enums and URL patterns used across the project."""

from __future__ import annotations

import re
from enum import Enum
from typing import Dict, List, Tuple


# ── Supported Sites ───────────────────────────────────────────────────

class Site(str, Enum):
    """Supported streaming sites."""
    ANIWORLD = "aniworld"
    SERIENSTREAM = "serienstream"


# ── Content Types ─────────────────────────────────────────────────────

class ContentType(str, Enum):
    """Content classification for folder‑structure routing."""
    ANIME = "anime"
    SERIE = "serie"
    FILM = "film"


# ── Languages ─────────────────────────────────────────────────────────

class Language(str, Enum):
    """Language labels understood by the ``aniworld`` CLI."""
    GERMAN_DUB = "German Dub"
    GERMAN_SUB = "German Sub"
    ENGLISH_DUB = "English Dub"
    ENGLISH_SUB = "English Sub"


# Default priority order (configurable)
DEFAULT_LANGUAGE_PRIORITY: List[str] = [
    Language.GERMAN_DUB.value,
    Language.GERMAN_SUB.value,
    Language.ENGLISH_SUB.value,
    Language.ENGLISH_DUB.value,
]


# ── Language flag/key → Language mapping ──────────────────────────────

# aniworld.to uses <img src="/public/img/{key}.svg"> on episode pages
ANIWORLD_LANGUAGE_MAP: Dict[str, Language] = {
    "german": Language.GERMAN_DUB,
    "english": Language.ENGLISH_DUB,
    "japanese-german": Language.GERMAN_SUB,
    "japanese-english": Language.ENGLISH_SUB,
}

# s.to uses <svg><use href="#icon-flag-{key}"></svg>
STO_LANGUAGE_MAP: Dict[str, Language] = {
    "german": Language.GERMAN_DUB,
    "english": Language.ENGLISH_DUB,
    "english-german": Language.GERMAN_SUB,
}


# ── Language suffix for file naming ───────────────────────────────────

LANGUAGE_FILE_SUFFIX: Dict[str, str] = {
    Language.GERMAN_DUB.value: "",
    Language.GERMAN_SUB.value: " [Sub]",
    Language.ENGLISH_DUB.value: " [English Dub]",
    Language.ENGLISH_SUB.value: " [English Sub]",
}


# ── URL patterns ──────────────────────────────────────────────────────

ANIWORLD_BASE = "https://aniworld.to"
STO_BASE = "https://s.to"

# Regex patterns for URL classification
RE_ANIWORLD_SERIES = re.compile(
    r"^https?://(?:www\.)?aniworld\.to/anime/stream/([a-zA-Z0-9\-]+)/?$"
)
RE_ANIWORLD_SEASON = re.compile(
    r"^https?://(?:www\.)?aniworld\.to/anime/stream/([a-zA-Z0-9\-]+)/(staffel-\d+|filme)/?$"
)
RE_ANIWORLD_EPISODE = re.compile(
    r"^https?://(?:www\.)?aniworld\.to/anime/stream/([a-zA-Z0-9\-]+)/"
    r"(staffel-\d+/episode-\d+|filme/film-\d+)/?$"
)

RE_STO_SERIES = re.compile(
    r"^https?://(?:www\.)?(?:serienstream|s)\.to/serie/([a-zA-Z0-9\-]+)/?$"
)
RE_STO_SEASON = re.compile(
    r"^https?://(?:www\.)?(?:serienstream|s)\.to/serie/([a-zA-Z0-9\-]+)/staffel-\d+/?$"
)
RE_STO_EPISODE = re.compile(
    r"^https?://(?:www\.)?(?:serienstream|s)\.to/serie/([a-zA-Z0-9\-]+)/"
    r"staffel-\d+/episode-\d+/?$"
)


# ── Download status enum ─────────────────────────────────────────────

class DownloadStatus(str, Enum):
    """Status values for the ``downloads`` table."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    MISSING = "missing"
    CORRUPT = "corrupt"


# ── Folder structure modes ───────────────────────────────────────────

class FolderMode(str, Enum):
    """Download folder organisation mode."""
    STANDARD = "standard"
    SEPARATE = "separate"


# ── Download modes ───────────────────────────────────────────────────

class DownloadMode(str, Enum):
    """Operational modes for the download engine."""
    DEFAULT = "default"
    GERMAN = "german"
    NEW = "new"
    CHECK = "check"


# ── Misc ─────────────────────────────────────────────────────────────

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Minimum file size (bytes) to consider a download valid
MIN_VALID_FILE_SIZE = 1_000_000  # 1 MB

# Seconds to wait after aniworld cli returns for .part files to finalise
POST_DOWNLOAD_WAIT = 5

# File extensions we look for
VIDEO_EXTENSIONS = (".mkv", ".mp4")
