"""REST API routes for AniLoader.

Endpoints
---------
- ``GET  /``                   – Web UI (index page)
- ``GET  /start?mode=…``      – Start a download run
- ``POST /add``               – Add a series URL
- ``GET  /status``            – Current download status
- ``POST /stop``              – Stop running download
- ``GET  /health``            – Health check
- ``GET  /config``            – Read config
- ``POST /config``            – Update config
- ``GET  /disk``              – Free disk space
- ``GET  /database``          – List all series
- ``GET  /counts``            – Aggregate statistics
- ``GET  /logs``              – Last log content
- ``POST /search``            – Search aniworld.to / s.to
- ``DELETE /series/{id}``     – Soft‑delete a series
- ``POST   /series/{id}/restore`` – Restore a series
- ``GET  /queue``             – Download queue
- ``DELETE /queue/completed`` – Clear finished queue items
- ``POST /upload``            – Upload a TXT file with URLs
- ``POST /export``            – Export DB as JSON
"""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from core.config import load_config, save_config
from core.constants import DownloadMode
from core.logging_setup import get_logger
from database import repository as repo
from database.models import Series
from services.downloader import is_running, request_stop, run_download
from services.scraper import fetch_series_title, search_aniworld, search_sto
from utils.helpers import detect_content_type, detect_site, free_disk_gb, sanitize_url

log = get_logger("api.routes")

router = APIRouter()

# ── Global download state ─────────────────────────────────────────────

_dl_status: Dict[str, Any] = {
    "status": "idle",
    "mode": None,
    "started_at": None,
}
_dl_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════
# Web UI
# ═══════════════════════════════════════════════════════════════════════

@router.get("/", response_class=HTMLResponse)
async def index():
    tpl = Path(__file__).parent / "templates" / "index.html"
    if tpl.exists():
        return HTMLResponse(tpl.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>AniLoader</h1><p>Web UI template not found.</p>")


# ═══════════════════════════════════════════════════════════════════════
# Download control
# ═══════════════════════════════════════════════════════════════════════

@router.get("/start")
@router.post("/start")
async def start_download(mode: str = Query("default")):
    """``/start?mode=default|german|new|check``"""
    global _dl_status

    valid_modes = {m.value for m in DownloadMode}
    if mode not in valid_modes:
        return JSONResponse(
            {"status": "error", "msg": f"Invalid mode. Valid: {valid_modes}"},
            status_code=400,
        )

    with _dl_lock:
        if is_running():
            return JSONResponse(
                {"status": "error", "msg": "Download already running"},
                status_code=409,
            )

        def _run():
            global _dl_status
            _dl_status = {"status": "running", "mode": mode, "started_at": time.time()}
            try:
                run_download(mode)
            finally:
                _dl_status = {"status": "idle", "mode": None, "started_at": None}

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    return {"status": "ok", "msg": f"Download started (mode={mode})"}


@router.get("/status")
async def status():
    return _dl_status


@router.post("/stop")
async def stop_download():
    if is_running():
        request_stop()
        return {"status": "ok", "msg": "Stop requested"}
    return {"status": "ok", "msg": "No download running"}


@router.get("/health")
async def health():
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════
# Series management
# ═══════════════════════════════════════════════════════════════════════

@router.post("/add")
async def add_series(request: Request):
    """Add a series URL.  Body: ``{"url": "https://..."}``"""
    body = await request.json()
    raw_url = body.get("url", "").strip()
    if not raw_url:
        return JSONResponse({"status": "error", "msg": "URL required"}, status_code=400)

    clean_url = sanitize_url(raw_url)

    # Only accept known sites
    try:
        site = detect_site(clean_url)
    except ValueError:
        return JSONResponse(
            {"status": "error", "msg": "Only aniworld.to and s.to URLs accepted"},
            status_code=400,
        )

    # Fetch title from website
    title = fetch_series_title(clean_url) or clean_url
    content_type = detect_content_type(clean_url).value

    series = Series(
        title=title,
        url=clean_url,
        site=site.value,
        content_type=content_type,
    )
    series_id = repo.upsert_series(series)
    log.info("Added series: %s (%s) → id=%d", title, clean_url, series_id)

    return {"status": "ok", "id": series_id, "title": title}


@router.get("/database")
async def list_series(
    q: Optional[str] = None,
    complete: Optional[int] = None,
    deutsch: Optional[int] = None,
    include_deleted: bool = False,
):
    """List series with optional filtering."""
    all_series = repo.get_all_series(include_deleted=include_deleted)

    if q:
        q_lower = q.lower()
        all_series = [s for s in all_series if q_lower in s.title.lower()]
    if complete is not None:
        all_series = [s for s in all_series if s.complete == bool(complete)]
    if deutsch is not None:
        all_series = [s for s in all_series if s.german_complete == bool(deutsch)]

    return [_series_dict(s) for s in all_series]


@router.get("/counts")
async def counts():
    return repo.get_series_stats()


@router.delete("/series/{series_id}")
async def delete_series(series_id: int):
    repo.soft_delete_series(series_id)
    return {"status": "ok"}


@router.post("/series/{series_id}/restore")
async def restore_series(series_id: int):
    repo.restore_series(series_id)
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════
# Search
# ═══════════════════════════════════════════════════════════════════════

@router.post("/search")
async def search(request: Request):
    """Body: ``{"keyword": "...", "site": "aniworld"|"serienstream"}``"""
    body = await request.json()
    keyword = body.get("keyword", "").strip()
    site = body.get("site", "aniworld")

    if not keyword:
        return JSONResponse({"status": "error", "msg": "keyword required"}, status_code=400)

    if site == "serienstream":
        results = search_sto(keyword)
    else:
        results = search_aniworld(keyword)

    return {"status": "ok", "results": results}


# ═══════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════

@router.get("/config")
async def get_config():
    cfg = load_config()
    return {"status": "ok", "config": cfg}


@router.post("/config")
async def update_config(request: Request):
    body = await request.json()
    try:
        save_config(body)
        return {"status": "ok", "msg": "Config saved"}
    except Exception as exc:
        return JSONResponse({"status": "error", "msg": str(exc)}, status_code=500)


# ═══════════════════════════════════════════════════════════════════════
# System info
# ═══════════════════════════════════════════════════════════════════════

@router.get("/disk")
async def disk():
    cfg = load_config()
    path = cfg.get("download_path", ".")
    gb = free_disk_gb(path)
    return {"status": "ok", "free_gb": round(gb, 2), "path": path}


@router.get("/logs")
async def get_logs(lines: int = Query(200)):
    """Return the last *n* lines of the log file."""
    log_path = Path(__file__).parent.parent / "data" / "logs" / "aniloader.log"
    if not log_path.exists():
        return {"status": "ok", "lines": []}
    try:
        all_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return {"status": "ok", "lines": all_lines[-lines:]}
    except Exception as exc:
        return JSONResponse({"status": "error", "msg": str(exc)}, status_code=500)


# ═══════════════════════════════════════════════════════════════════════
# Queue
# ═══════════════════════════════════════════════════════════════════════

@router.get("/queue")
async def get_queue():
    items = repo.get_all_queue_items()
    return [
        {
            "id": it.id,
            "series_id": it.series_id,
            "mode": it.mode,
            "status": it.status,
            "created_at": it.created_at,
            "completed_at": it.completed_at,
            "error_msg": it.error_msg,
        }
        for it in items
    ]


@router.delete("/queue/completed")
async def clear_queue():
    count = repo.clear_completed_queue()
    return {"status": "ok", "cleared": count}


# ═══════════════════════════════════════════════════════════════════════
# Import / Export
# ═══════════════════════════════════════════════════════════════════════

@router.post("/upload")
async def upload_txt(file: UploadFile = File(...)):
    """Upload a ``.txt`` file with one URL per line."""
    if not file.filename or not file.filename.endswith(".txt"):
        return JSONResponse({"status": "error", "msg": "Only .txt files accepted"}, status_code=400)

    content = (await file.read()).decode("utf-8", errors="replace")
    urls = [line.strip() for line in content.splitlines() if line.strip().startswith("http")]

    added = 0
    for raw_url in urls:
        try:
            clean = sanitize_url(raw_url)
            site = detect_site(clean)
            title = fetch_series_title(clean) or clean
            ct = detect_content_type(clean).value
            repo.upsert_series(Series(title=title, url=clean, site=site.value, content_type=ct))
            added += 1
        except Exception as exc:
            log.warning("Skipping URL %s: %s", raw_url, exc)

    return {"status": "ok", "added": added, "total_lines": len(urls)}


@router.post("/export")
async def export_db():
    """Export all series as a JSON download."""
    all_series = repo.get_all_series(include_deleted=True)
    data = [_series_dict(s) for s in all_series]
    out_path = Path(__file__).parent.parent / "data" / "export.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return FileResponse(str(out_path), filename="aniloader_export.json", media_type="application/json")


# ── Helpers ───────────────────────────────────────────────────────────

def _series_dict(s: Series) -> Dict[str, Any]:
    return {
        "id": s.id,
        "title": s.title,
        "url": s.url,
        "site": s.site,
        "content_type": s.content_type,
        "complete": s.complete,
        "german_complete": s.german_complete,
        "deleted": s.deleted,
        "folder_name": s.folder_name,
        "last_check": s.last_check,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }
