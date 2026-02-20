"""YAML-based configuration management with validation."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.constants import (
    DEFAULT_LANGUAGE_PRIORITY,
    DownloadMode,
    FolderMode,
    Language,
)
from core.exceptions import ConfigError, ConfigValidationError

# ── Paths ─────────────────────────────────────────────────────────────

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CONFIG_FILENAME = "config.yaml"


def _data_dir() -> Path:
    """Return (and create) the data directory."""
    d = Path(os.environ.get("ANILOADER_DATA_DIR", str(_DEFAULT_DATA_DIR)))
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return _data_dir() / _CONFIG_FILENAME


# ── Defaults ──────────────────────────────────────────────────────────

DEFAULT_CONFIG: Dict[str, Any] = {
    "download_path": str(Path(__file__).resolve().parent.parent / "Downloads"),
    "default_language": Language.GERMAN_DUB.value,
    "languages_priority": list(DEFAULT_LANGUAGE_PRIORITY),
    "folder_mode": FolderMode.STANDARD.value,
    "anime_path": "",
    "series_path": "",
    "movies_path": "",
    "logging": {
        "level": "INFO",
        "max_file_size_mb": 10,
        "backup_count": 5,
    },
    "server": {
        "host": "0.0.0.0",
        "port": 5050,
    },
    "rate_limit": {
        "requests_per_second": 2,
        "delay_between_downloads": 5,
    },
    "autostart_mode": None,
    "refresh_titles_on_start": False,
    "min_free_gb": 100.0,
}

# ── Loader / Saver ────────────────────────────────────────────────────


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge *override* into *base* (non‑destructive)."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> Dict[str, Any]:
    """Load config from YAML, creating a default file if missing.

    Missing keys are filled in from ``DEFAULT_CONFIG`` so the
    application always has a complete configuration.
    """
    path = config_path()

    if not path.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except Exception as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc

    merged = _deep_merge(DEFAULT_CONFIG, raw)
    _validate(merged)
    return merged


def save_config(cfg: Dict[str, Any]) -> None:
    """Atomically write *cfg* to the YAML config file."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            yaml.dump(cfg, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)
        tmp.replace(path)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise ConfigError(f"Cannot write config: {exc}") from exc


# ── Validation ────────────────────────────────────────────────────────

_VALID_LANGUAGES = {lang.value for lang in Language}
_VALID_FOLDER_MODES = {fm.value for fm in FolderMode}
_VALID_DOWNLOAD_MODES = {dm.value for dm in DownloadMode}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _validate(cfg: Dict[str, Any]) -> None:
    """Raise :class:`ConfigValidationError` on invalid values."""

    # download_path must be a non‑empty string
    dp = cfg.get("download_path", "")
    if not isinstance(dp, str) or not dp.strip():
        raise ConfigValidationError("download_path must be a non‑empty string")

    # default_language
    dl = cfg.get("default_language", "")
    if dl not in _VALID_LANGUAGES:
        raise ConfigValidationError(
            f"default_language '{dl}' not in {_VALID_LANGUAGES}"
        )

    # languages_priority – list of valid language strings
    lp = cfg.get("languages_priority", [])
    if not isinstance(lp, list) or not lp:
        raise ConfigValidationError("languages_priority must be a non‑empty list")
    for lang in lp:
        if lang not in _VALID_LANGUAGES:
            raise ConfigValidationError(
                f"Invalid language '{lang}' in languages_priority"
            )

    # folder_mode
    fm = cfg.get("folder_mode", "")
    if fm not in _VALID_FOLDER_MODES:
        raise ConfigValidationError(
            f"folder_mode '{fm}' not in {_VALID_FOLDER_MODES}"
        )

    # logging.level
    log_cfg = cfg.get("logging", {})
    ll = log_cfg.get("level", "INFO")
    if ll.upper() not in _VALID_LOG_LEVELS:
        raise ConfigValidationError(f"logging.level '{ll}' is not valid")

    # server.port
    srv = cfg.get("server", {})
    port = srv.get("port", 5050)
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise ConfigValidationError(f"server.port must be an integer 1‑65535, got {port}")

    # autostart_mode (optional)
    am = cfg.get("autostart_mode")
    if am is not None and am not in _VALID_DOWNLOAD_MODES:
        raise ConfigValidationError(
            f"autostart_mode '{am}' not in {_VALID_DOWNLOAD_MODES}"
        )

    # min_free_gb
    mfg = cfg.get("min_free_gb", 100.0)
    if not isinstance(mfg, (int, float)) or mfg < 0:
        raise ConfigValidationError("min_free_gb must be a non‑negative number")
