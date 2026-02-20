"""Custom exception hierarchy for AniLoader."""

from __future__ import annotations


class AniLoaderError(Exception):
    """Base exception for all AniLoader errors."""


# ── Configuration ──────────────────────────────────────────────────────
class ConfigError(AniLoaderError):
    """Raised when the config file is missing, invalid, or unreadable."""


class ConfigValidationError(ConfigError):
    """Raised when a config value fails validation."""


# ── Network / Scraping ─────────────────────────────────────────────────
class NetworkError(AniLoaderError):
    """Raised on HTTP/DNS failures."""


class ScrapingError(AniLoaderError):
    """Raised when HTML parsing produces unexpected results."""


class ProviderError(AniLoaderError):
    """Raised when a streaming provider cannot be resolved."""


# ── Download ───────────────────────────────────────────────────────────
class DownloadError(AniLoaderError):
    """Raised when a download fails."""


class DownloadAlreadyRunningError(DownloadError):
    """Raised when a download is requested while another is running."""


class InsufficientDiskSpaceError(DownloadError):
    """Raised when not enough disk space is available."""


# ── Database ───────────────────────────────────────────────────────────
class DatabaseError(AniLoaderError):
    """Raised on SQLite failures."""


class SeriesNotFoundError(DatabaseError):
    """Raised when a series does not exist in the database."""


# ── File Management ───────────────────────────────────────────────────
class FileManagementError(AniLoaderError):
    """Raised on file move / rename failures."""
