"""CLI entry point and argument parsing.

Usage examples::

    # Start the web server (default)
    python -m claude-code serve

    # Run a download
    python -m claude-code download --mode default

    # Add a series
    python -m claude-code add "https://aniworld.to/anime/stream/one-piece"

    # Check downloads
    python -m claude-code download --mode check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.config import load_config
from core.constants import DownloadMode
from core.logging_setup import setup_logging, get_logger
from database.connection import init_db


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aniloader",
        description="AniLoader – Anime/Series download management system",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ── serve ──────────────────────────────────────────────────────────
    srv = sub.add_parser("serve", help="Start the web server + REST API")
    srv.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    srv.add_argument("--port", type=int, default=5050, help="Port (default: 5050)")

    # ── download ───────────────────────────────────────────────────────
    dl = sub.add_parser("download", help="Run a download cycle")
    dl.add_argument(
        "--mode", "-m",
        choices=[m.value for m in DownloadMode],
        default=DownloadMode.DEFAULT.value,
        help="Download mode (default: default)",
    )

    # ── add ────────────────────────────────────────────────────────────
    add = sub.add_parser("add", help="Add a series URL to the database")
    add.add_argument("url", help="Series URL (aniworld.to or s.to)")

    # ── check ──────────────────────────────────────────────────────────
    sub.add_parser("check", help="Verify integrity of all downloads")

    # ── import‑txt ─────────────────────────────────────────────────────
    imp = sub.add_parser("import-txt", help="Import URLs from a TXT file")
    imp.add_argument("file", help="Path to the TXT file with one URL per line")

    # ── export ─────────────────────────────────────────────────────────
    sub.add_parser("export", help="Export the database as JSON")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and dispatch to the appropriate handler."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Load config early for logging setup
    cfg = load_config()
    log_cfg = cfg.get("logging", {})
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        max_bytes=log_cfg.get("max_file_size_mb", 10) * 1024 * 1024,
        backup_count=log_cfg.get("backup_count", 5),
    )
    log = get_logger("cli")

    # Always ensure DB exists
    init_db()

    if args.command is None or args.command == "serve":
        return _cmd_serve(args, cfg, log)
    elif args.command == "download":
        return _cmd_download(args, log)
    elif args.command == "add":
        return _cmd_add(args, log)
    elif args.command == "check":
        return _cmd_check(cfg, log)
    elif args.command == "import-txt":
        return _cmd_import_txt(args, log)
    elif args.command == "export":
        return _cmd_export(log)
    else:
        parser.print_help()
        return 1


# ── Command handlers ──────────────────────────────────────────────────

def _cmd_serve(args, cfg: dict, log) -> int:
    from api.app import start_server
    host = getattr(args, "host", None) or cfg.get("server", {}).get("host", "0.0.0.0")
    port = getattr(args, "port", None) or cfg.get("server", {}).get("port", 5050)
    start_server(host=host, port=port)
    return 0


def _cmd_download(args, log) -> int:
    from services.downloader import run_download
    log.info("Starting download run (mode=%s)", args.mode)
    try:
        run_download(args.mode)
    except Exception as exc:
        log.error("Download failed: %s", exc, exc_info=True)
        return 1
    return 0


def _cmd_add(args, log) -> int:
    from database import repository as repo
    from database.models import Series
    from services.scraper import fetch_series_title
    from utils.helpers import detect_content_type, detect_site, sanitize_url

    url = sanitize_url(args.url)
    try:
        site = detect_site(url)
    except ValueError:
        log.error("Unknown site: %s", url)
        return 1

    title = fetch_series_title(url) or url
    ct = detect_content_type(url).value
    series_id = repo.upsert_series(
        Series(title=title, url=url, site=site.value, content_type=ct)
    )
    log.info("Added: %s (%s) → id=%d", title, url, series_id)
    return 0


def _cmd_check(cfg: dict, log) -> int:
    from services.checker import check_all_series
    results = check_all_series(cfg)
    total_missing = sum(r.missing_count for r in results)
    total_corrupt = sum(r.corrupt_count for r in results)
    total_ok = sum(r.ok_count for r in results)
    log.info(
        "Check complete: %d OK, %d missing, %d corrupt",
        total_ok, total_missing, total_corrupt,
    )
    return 0


def _cmd_import_txt(args, log) -> int:
    from database import repository as repo
    from database.models import Series
    from services.scraper import fetch_series_title
    from utils.helpers import detect_content_type, detect_site, sanitize_url

    path = Path(args.file)
    if not path.exists():
        log.error("File not found: %s", path)
        return 1

    lines = path.read_text(encoding="utf-8").splitlines()
    added = 0
    for line in lines:
        raw = line.strip()
        if not raw.startswith("http"):
            continue
        try:
            url = sanitize_url(raw)
            site = detect_site(url)
            title = fetch_series_title(url) or url
            ct = detect_content_type(url).value
            repo.upsert_series(
                Series(title=title, url=url, site=site.value, content_type=ct)
            )
            added += 1
            log.info("Imported: %s", title)
        except Exception as exc:
            log.warning("Skipping %s: %s", raw, exc)

    log.info("Import complete: %d series added", added)
    return 0


def _cmd_export(log) -> int:
    import json
    from database import repository as repo

    all_series = repo.get_all_series(include_deleted=True)
    data = []
    for s in all_series:
        data.append({
            "id": s.id,
            "title": s.title,
            "url": s.url,
            "site": s.site,
            "content_type": s.content_type,
            "complete": s.complete,
            "german_complete": s.german_complete,
            "deleted": s.deleted,
            "folder_name": s.folder_name,
        })

    out = Path(__file__).parent.parent / "data" / "export.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Exported %d series to %s", len(data), out)
    return 0
