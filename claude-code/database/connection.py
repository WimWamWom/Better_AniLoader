"""SQLite connection management with schema initialisation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from core.exceptions import DatabaseError
from core.logging_setup import get_logger

log = get_logger("database")

_DB_FILENAME = "aniloader.db"

# ── Schema DDL ────────────────────────────────────────────────────────

_SCHEMA_SQL = """
-- Series / Anime / Show
CREATE TABLE IF NOT EXISTS series (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    url             TEXT    UNIQUE NOT NULL,
    site            TEXT    NOT NULL CHECK(site IN ('aniworld', 'serienstream')),
    content_type    TEXT    NOT NULL DEFAULT 'anime'
                            CHECK(content_type IN ('anime', 'serie', 'film')),
    complete        INTEGER NOT NULL DEFAULT 0,
    german_complete INTEGER NOT NULL DEFAULT 0,
    deleted         INTEGER NOT NULL DEFAULT 0,
    folder_name     TEXT,
    last_check      TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Seasons
CREATE TABLE IF NOT EXISTS seasons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id       INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    season_number   INTEGER NOT NULL,
    is_movie_season INTEGER NOT NULL DEFAULT 0,
    episode_count   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(series_id, season_number)
);

-- Episodes
CREATE TABLE IF NOT EXISTS episodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id       INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    season_id       INTEGER NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    episode_number  INTEGER NOT NULL,
    title_de        TEXT,
    title_en        TEXT,
    url             TEXT    UNIQUE NOT NULL,
    is_movie        INTEGER NOT NULL DEFAULT 0,
    UNIQUE(season_id, episode_number)
);

-- Available languages per episode
CREATE TABLE IF NOT EXISTS episode_languages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id  INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    language    TEXT    NOT NULL,
    last_check  TEXT    DEFAULT (datetime('now')),
    UNIQUE(episode_id, language)
);

-- Downloads (one row per episode+language combination)
CREATE TABLE IF NOT EXISTS downloads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id      INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    language        TEXT    NOT NULL,
    file_path       TEXT,
    file_size       INTEGER,
    status          TEXT    NOT NULL DEFAULT 'pending'
                            CHECK(status IN (
                                'pending','downloading','completed',
                                'failed','missing','corrupt'
                            )),
    error_message   TEXT,
    downloaded_at   TEXT,
    checked_at      TEXT,
    UNIQUE(episode_id, language)
);

-- Download queue (for web‑triggered downloads)
CREATE TABLE IF NOT EXISTS download_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id   INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    mode        TEXT    NOT NULL DEFAULT 'default'
                        CHECK(mode IN ('default','german','new','check')),
    status      TEXT    NOT NULL DEFAULT 'queued'
                        CHECK(status IN ('queued','running','completed','failed','cancelled')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    error_msg   TEXT
);

-- Indices
CREATE INDEX IF NOT EXISTS idx_episodes_series   ON episodes(series_id);
CREATE INDEX IF NOT EXISTS idx_episodes_season    ON episodes(season_id);
CREATE INDEX IF NOT EXISTS idx_downloads_episode  ON downloads(episode_id);
CREATE INDEX IF NOT EXISTS idx_downloads_status   ON downloads(status);
CREATE INDEX IF NOT EXISTS idx_series_url         ON series(url);
"""


# ── Connection helpers ────────────────────────────────────────────────


def _db_path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _DB_FILENAME


def get_connection(data_dir: Path | None = None) -> sqlite3.Connection:
    """Return a new SQLite connection with FK enforcement."""
    path = _db_path(data_dir)
    try:
        conn = sqlite3.connect(str(path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot connect to {path}: {exc}") from exc


def init_db(data_dir: Path | None = None) -> None:
    """Create all tables if they do not exist yet."""
    conn = get_connection(data_dir)
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        log.info("Database initialised at %s", _db_path(data_dir))
    except sqlite3.Error as exc:
        raise DatabaseError(f"Schema init failed: {exc}") from exc
    finally:
        conn.close()
