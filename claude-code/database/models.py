"""Dataclass models mirroring the SQLite schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Series:
    """A tracked series / anime."""
    id: int = 0
    title: str = ""
    url: str = ""
    site: str = "aniworld"          # 'aniworld' | 'serienstream'
    content_type: str = "anime"     # 'anime' | 'serie' | 'film'
    complete: bool = False
    german_complete: bool = False
    deleted: bool = False
    folder_name: Optional[str] = None
    last_check: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Transient (not stored)
    seasons: List[Season] = field(default_factory=list, repr=False)


@dataclass
class Season:
    """A season (Staffel) of a series or a movie collection."""
    id: int = 0
    series_id: int = 0
    season_number: int = 0
    is_movie_season: bool = False
    episode_count: int = 0

    # Transient
    episodes: List[Episode] = field(default_factory=list, repr=False)


@dataclass
class Episode:
    """A single episode or movie entry."""
    id: int = 0
    series_id: int = 0
    season_id: int = 0
    episode_number: int = 0
    title_de: Optional[str] = None
    title_en: Optional[str] = None
    url: str = ""
    is_movie: bool = False

    # Transient
    languages: List[str] = field(default_factory=list, repr=False)


@dataclass
class EpisodeLanguage:
    """An available language for an episode."""
    id: int = 0
    episode_id: int = 0
    language: str = ""
    last_check: Optional[str] = None


@dataclass
class Download:
    """Download record for a specific episode+language combination."""
    id: int = 0
    episode_id: int = 0
    language: str = ""
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    status: str = "pending"
    error_message: Optional[str] = None
    downloaded_at: Optional[str] = None
    checked_at: Optional[str] = None


@dataclass
class DownloadQueueItem:
    """A queued download request (typically from the web UI)."""
    id: int = 0
    series_id: int = 0
    mode: str = "default"
    status: str = "queued"
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_msg: Optional[str] = None
