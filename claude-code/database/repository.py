"""CRUD repository for all database entities.

Every public function opens and closes its own connection so callers
never have to worry about connection life‑cycle.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.exceptions import DatabaseError, SeriesNotFoundError
from core.logging_setup import get_logger
from database.connection import get_connection
from database.models import (
    Download,
    DownloadQueueItem,
    Episode,
    EpisodeLanguage,
    Season,
    Series,
)

log = get_logger("repository")


# ═══════════════════════════════════════════════════════════════════════
# Series
# ═══════════════════════════════════════════════════════════════════════

def upsert_series(series: Series) -> int:
    """Insert or update a series.  Returns the row id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO series (title, url, site, content_type, folder_name)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title       = excluded.title,
                site        = excluded.site,
                content_type= excluded.content_type,
                updated_at  = datetime('now')
            """,
            (series.title, series.url, series.site, series.content_type, series.folder_name),
        )
        conn.commit()
        return cur.lastrowid or _get_series_id_by_url(conn, series.url)
    finally:
        conn.close()


def get_series_by_id(series_id: int) -> Series:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM series WHERE id = ?", (series_id,)).fetchone()
        if not row:
            raise SeriesNotFoundError(f"No series with id={series_id}")
        return _row_to_series(row)
    finally:
        conn.close()


def get_series_by_url(url: str) -> Optional[Series]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM series WHERE url = ?", (url,)).fetchone()
        return _row_to_series(row) if row else None
    finally:
        conn.close()


def get_all_series(*, include_deleted: bool = False) -> List[Series]:
    conn = get_connection()
    try:
        if include_deleted:
            rows = conn.execute("SELECT * FROM series ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM series WHERE deleted = 0 ORDER BY id"
            ).fetchall()
        return [_row_to_series(r) for r in rows]
    finally:
        conn.close()


def update_series_field(series_id: int, **fields: Any) -> None:
    """Update arbitrary columns on a series row."""
    if not fields:
        return
    allowed = {
        "title", "complete", "german_complete", "deleted",
        "folder_name", "last_check", "content_type",
    }
    bad = set(fields) - allowed
    if bad:
        raise DatabaseError(f"Cannot update fields: {bad}")
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [series_id]
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE series SET {sets}, updated_at = datetime('now') WHERE id = ?",
            vals,
        )
        conn.commit()
    finally:
        conn.close()


def soft_delete_series(series_id: int) -> None:
    update_series_field(series_id, deleted=1)


def restore_series(series_id: int) -> None:
    update_series_field(series_id, deleted=0)


def get_series_stats() -> Dict[str, int]:
    """Return aggregate counts."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT
                COUNT(*)                                    AS total,
                SUM(CASE WHEN deleted = 0 THEN 1 ELSE 0 END)   AS active,
                SUM(CASE WHEN complete = 1 AND deleted = 0 THEN 1 ELSE 0 END)  AS complete,
                SUM(CASE WHEN german_complete = 1 AND deleted = 0 THEN 1 ELSE 0 END) AS german_complete,
                SUM(CASE WHEN deleted = 1 THEN 1 ELSE 0 END)   AS deleted_count
            FROM series
        """).fetchone()
        return {
            "total": row["total"],
            "active": row["active"],
            "complete": row["complete"],
            "german_complete": row["german_complete"],
            "deleted": row["deleted_count"],
        }
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# Seasons
# ═══════════════════════════════════════════════════════════════════════

def upsert_season(season: Season) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO seasons (series_id, season_number, is_movie_season, episode_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(series_id, season_number) DO UPDATE SET
                is_movie_season = excluded.is_movie_season,
                episode_count   = excluded.episode_count
            """,
            (season.series_id, season.season_number, int(season.is_movie_season), season.episode_count),
        )
        conn.commit()
        return cur.lastrowid or _get_season_id(conn, season.series_id, season.season_number)
    finally:
        conn.close()


def get_seasons_for_series(series_id: int) -> List[Season]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM seasons WHERE series_id = ? ORDER BY season_number",
            (series_id,),
        ).fetchall()
        return [_row_to_season(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# Episodes
# ═══════════════════════════════════════════════════════════════════════

def upsert_episode(episode: Episode) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO episodes
                (series_id, season_id, episode_number, title_de, title_en, url, is_movie)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title_de       = excluded.title_de,
                title_en       = excluded.title_en,
                episode_number = excluded.episode_number,
                is_movie       = excluded.is_movie
            """,
            (
                episode.series_id,
                episode.season_id,
                episode.episode_number,
                episode.title_de,
                episode.title_en,
                episode.url,
                int(episode.is_movie),
            ),
        )
        conn.commit()
        return cur.lastrowid or _get_episode_id_by_url(conn, episode.url)
    finally:
        conn.close()


def get_episodes_for_season(season_id: int) -> List[Episode]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM episodes WHERE season_id = ? ORDER BY episode_number",
            (season_id,),
        ).fetchall()
        return [_row_to_episode(r) for r in rows]
    finally:
        conn.close()


def get_episodes_for_series(series_id: int) -> List[Episode]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM episodes WHERE series_id = ? ORDER BY season_id, episode_number",
            (series_id,),
        ).fetchall()
        return [_row_to_episode(r) for r in rows]
    finally:
        conn.close()


def get_episode_by_url(url: str) -> Optional[Episode]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM episodes WHERE url = ?", (url,)).fetchone()
        return _row_to_episode(row) if row else None
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# Episode Languages
# ═══════════════════════════════════════════════════════════════════════

def set_episode_languages(episode_id: int, languages: List[str]) -> None:
    conn = get_connection()
    try:
        now = datetime.utcnow().isoformat()
        for lang in languages:
            conn.execute(
                """
                INSERT INTO episode_languages (episode_id, language, last_check)
                VALUES (?, ?, ?)
                ON CONFLICT(episode_id, language) DO UPDATE SET last_check = ?
                """,
                (episode_id, lang, now, now),
            )
        conn.commit()
    finally:
        conn.close()


def get_episode_languages(episode_id: int) -> List[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT language FROM episode_languages WHERE episode_id = ?",
            (episode_id,),
        ).fetchall()
        return [r["language"] for r in rows]
    finally:
        conn.close()


def get_episodes_missing_language(series_id: int, language: str) -> List[Episode]:
    """Return episodes of a series that do NOT have a completed download in *language*."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT e.* FROM episodes e
            WHERE e.series_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM downloads d
                  WHERE d.episode_id = e.id
                    AND d.language = ?
                    AND d.status = 'completed'
              )
            ORDER BY e.season_id, e.episode_number
            """,
            (series_id, language),
        ).fetchall()
        return [_row_to_episode(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# Downloads
# ═══════════════════════════════════════════════════════════════════════

def upsert_download(dl: Download) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO downloads
                (episode_id, language, file_path, file_size, status,
                 error_message, downloaded_at, checked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(episode_id, language) DO UPDATE SET
                file_path     = excluded.file_path,
                file_size     = excluded.file_size,
                status        = excluded.status,
                error_message = excluded.error_message,
                downloaded_at = excluded.downloaded_at,
                checked_at    = excluded.checked_at
            """,
            (
                dl.episode_id,
                dl.language,
                dl.file_path,
                dl.file_size,
                dl.status,
                dl.error_message,
                dl.downloaded_at,
                dl.checked_at,
            ),
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def get_downloads_for_episode(episode_id: int) -> List[Download]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM downloads WHERE episode_id = ? ORDER BY language",
            (episode_id,),
        ).fetchall()
        return [_row_to_download(r) for r in rows]
    finally:
        conn.close()


def get_downloads_by_status(status: str) -> List[Download]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM downloads WHERE status = ?", (status,)
        ).fetchall()
        return [_row_to_download(r) for r in rows]
    finally:
        conn.close()


def get_download_for_episode_language(episode_id: int, language: str) -> Optional[Download]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM downloads WHERE episode_id = ? AND language = ?",
            (episode_id, language),
        ).fetchone()
        return _row_to_download(row) if row else None
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# Download Queue
# ═══════════════════════════════════════════════════════════════════════

def enqueue_download(series_id: int, mode: str = "default") -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO download_queue (series_id, mode) VALUES (?, ?)",
            (series_id, mode),
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def get_pending_queue_items() -> List[DownloadQueueItem]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM download_queue WHERE status = 'queued' ORDER BY created_at"
        ).fetchall()
        return [_row_to_queue_item(r) for r in rows]
    finally:
        conn.close()


def update_queue_item_status(
    item_id: int, status: str, error_msg: str | None = None
) -> None:
    conn = get_connection()
    try:
        completed_at = datetime.utcnow().isoformat() if status in ("completed", "failed", "cancelled") else None
        conn.execute(
            """
            UPDATE download_queue
            SET status = ?, completed_at = ?, error_msg = ?
            WHERE id = ?
            """,
            (status, completed_at, error_msg, item_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_queue_items() -> List[DownloadQueueItem]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM download_queue ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_queue_item(r) for r in rows]
    finally:
        conn.close()


def clear_completed_queue() -> int:
    """Delete completed/failed/cancelled queue items.  Returns count."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM download_queue WHERE status IN ('completed','failed','cancelled')"
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# Row → Model helpers
# ═══════════════════════════════════════════════════════════════════════

def _row_to_series(row: sqlite3.Row) -> Series:
    return Series(
        id=row["id"],
        title=row["title"],
        url=row["url"],
        site=row["site"],
        content_type=row["content_type"],
        complete=bool(row["complete"]),
        german_complete=bool(row["german_complete"]),
        deleted=bool(row["deleted"]),
        folder_name=row["folder_name"],
        last_check=row["last_check"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_season(row: sqlite3.Row) -> Season:
    return Season(
        id=row["id"],
        series_id=row["series_id"],
        season_number=row["season_number"],
        is_movie_season=bool(row["is_movie_season"]),
        episode_count=row["episode_count"],
    )


def _row_to_episode(row: sqlite3.Row) -> Episode:
    return Episode(
        id=row["id"],
        series_id=row["series_id"],
        season_id=row["season_id"],
        episode_number=row["episode_number"],
        title_de=row["title_de"],
        title_en=row["title_en"],
        url=row["url"],
        is_movie=bool(row["is_movie"]),
    )


def _row_to_download(row: sqlite3.Row) -> Download:
    return Download(
        id=row["id"],
        episode_id=row["episode_id"],
        language=row["language"],
        file_path=row["file_path"],
        file_size=row["file_size"],
        status=row["status"],
        error_message=row["error_message"],
        downloaded_at=row["downloaded_at"],
        checked_at=row["checked_at"],
    )


def _row_to_queue_item(row: sqlite3.Row) -> DownloadQueueItem:
    return DownloadQueueItem(
        id=row["id"],
        series_id=row["series_id"],
        mode=row["mode"],
        status=row["status"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        error_msg=row["error_msg"],
    )


# ── Internal look‑ups ─────────────────────────────────────────────────

def _get_series_id_by_url(conn: sqlite3.Connection, url: str) -> int:
    row = conn.execute("SELECT id FROM series WHERE url = ?", (url,)).fetchone()
    return row["id"] if row else 0


def _get_season_id(conn: sqlite3.Connection, series_id: int, season_number: int) -> int:
    row = conn.execute(
        "SELECT id FROM seasons WHERE series_id = ? AND season_number = ?",
        (series_id, season_number),
    ).fetchone()
    return row["id"] if row else 0


def _get_episode_id_by_url(conn: sqlite3.Connection, url: str) -> int:
    row = conn.execute("SELECT id FROM episodes WHERE url = ?", (url,)).fetchone()
    return row["id"] if row else 0
