"""Integrity checker – verifies downloaded files on disk.

Used by the ``check`` mode and the ``/start?mode=check`` API endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List

from core.constants import (
    MIN_VALID_FILE_SIZE,
    DownloadStatus,
    Language,
)
from core.logging_setup import get_logger
from database import repository as repo
from database.models import Download, Episode
from services.file_manager import find_existing_managed_file

log = get_logger("checker")


@dataclass
class CheckResult:
    """Summary of a check run for one series."""
    series_id: int
    series_title: str
    total_episodes: int = 0
    ok_count: int = 0
    missing_count: int = 0
    corrupt_count: int = 0
    episodes_missing: list = field(default_factory=list)
    episodes_corrupt: list = field(default_factory=list)


def check_series(series_id: int, config: dict) -> CheckResult:
    """Verify all episodes of a series.

    For each episode, checks:
    1. Does the file exist on disk?
    2. Is the file size above the minimum threshold?

    Updates the ``downloads`` table with current status.
    """
    series = repo.get_series_by_id(series_id)
    folder_name = series.folder_name or series.title
    episodes = repo.get_episodes_for_series(series_id)

    result = CheckResult(
        series_id=series_id,
        series_title=series.title,
        total_episodes=len(episodes),
    )

    for ep in episodes:
        season_number = _get_season_number(ep.season_id)

        existing = find_existing_managed_file(
            series_url=series.url,
            folder_name=folder_name,
            season=season_number,
            episode=ep.episode_number,
            config=config,
        )

        now = datetime.utcnow().isoformat()

        if not existing:
            result.missing_count += 1
            result.episodes_missing.append({
                "season": season_number,
                "episode": ep.episode_number,
                "title": ep.title_de or ep.url,
            })
            repo.upsert_download(Download(
                episode_id=ep.id,
                language="",
                status=DownloadStatus.MISSING.value,
                checked_at=now,
            ))
            continue

        try:
            size = existing.stat().st_size
        except OSError:
            size = 0

        lang = _detect_lang(existing.name)

        if size < MIN_VALID_FILE_SIZE:
            result.corrupt_count += 1
            result.episodes_corrupt.append({
                "season": season_number,
                "episode": ep.episode_number,
                "title": ep.title_de or ep.url,
                "size": size,
            })
            repo.upsert_download(Download(
                episode_id=ep.id,
                language=lang,
                file_path=str(existing),
                file_size=size,
                status=DownloadStatus.CORRUPT.value,
                checked_at=now,
            ))
        else:
            result.ok_count += 1
            repo.upsert_download(Download(
                episode_id=ep.id,
                language=lang,
                file_path=str(existing),
                file_size=size,
                status=DownloadStatus.COMPLETED.value,
                checked_at=now,
            ))

    log.info(
        "Check '%s': %d OK, %d missing, %d corrupt (of %d)",
        series.title,
        result.ok_count,
        result.missing_count,
        result.corrupt_count,
        result.total_episodes,
    )
    return result


def check_all_series(config: dict) -> List[CheckResult]:
    """Run integrity check across all active series."""
    results: List[CheckResult] = []
    for series in repo.get_all_series():
        try:
            r = check_series(series.id, config)
            results.append(r)
        except Exception as exc:
            log.error("Check error for '%s': %s", series.title, exc)
    return results


# ── Helpers ───────────────────────────────────────────────────────────

def _get_season_number(season_id: int) -> str:
    from database.connection import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT season_number FROM seasons WHERE id = ?", (season_id,)
        ).fetchone()
        return str(row["season_number"]) if row else "1"
    finally:
        conn.close()


def _detect_lang(filename: str) -> str:
    if "[English Sub]" in filename:
        return Language.ENGLISH_SUB.value
    if "[English Dub]" in filename:
        return Language.ENGLISH_DUB.value
    if "[Sub]" in filename:
        return Language.GERMAN_SUB.value
    return Language.GERMAN_DUB.value
