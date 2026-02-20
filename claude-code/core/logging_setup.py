"""Structured logging with rotating file handler and coloured console output."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "aniloader"
_initialised = False


def setup_logging(
    *,
    level: str = "INFO",
    log_dir: Optional[Path] = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """Configure the application‑wide logger (idempotent).

    Parameters
    ----------
    level:
        Logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    log_dir:
        Directory for the rotating log file.  Defaults to ``data/logs``.
    max_bytes:
        Max size (bytes) of a single log file before rotation.
    backup_count:
        Number of rotated log files to keep.

    Returns
    -------
    logging.Logger
        The configured root logger for the application.
    """
    global _initialised
    logger = logging.getLogger(_LOGGER_NAME)

    if _initialised:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Console handler ───────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_ColouredFormatter(fmt=fmt))
    logger.addHandler(console)

    # ── File handler (rotating) ───────────────────────────────────────
    if log_dir is None:
        log_dir = Path(__file__).resolve().parent.parent / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_dir / "aniloader.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    _initialised = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger of the application root logger.

    Call :func:`setup_logging` once before first use so that
    handlers are configured.
    """
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)


# ── Coloured formatter ────────────────────────────────────────────────

_COLOURS = {
    "DEBUG": "\033[36m",      # cyan
    "INFO": "\033[32m",       # green
    "WARNING": "\033[33m",    # yellow
    "ERROR": "\033[31m",      # red
    "CRITICAL": "\033[1;31m", # bold red
}
_RESET = "\033[0m"


class _ColouredFormatter(logging.Formatter):
    """Wraps each log message in ANSI colour codes (console only)."""

    def __init__(self, fmt: logging.Formatter) -> None:
        super().__init__()
        self._inner = fmt

    def format(self, record: logging.LogRecord) -> str:
        msg = self._inner.format(record)
        colour = _COLOURS.get(record.levelname, "")
        return f"{colour}{msg}{_RESET}" if colour else msg
