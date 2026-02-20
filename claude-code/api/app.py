"""FastAPI application factory and server start‑up."""

from __future__ import annotations

import threading
import uvicorn

from core.config import load_config
from core.logging_setup import get_logger, setup_logging
from database.connection import init_db

log = get_logger("api.app")


def create_app():
    """Build and return the configured FastAPI application."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    from pathlib import Path

    from api.routes import router

    app = FastAPI(
        title="AniLoader",
        version="1.0.0",
        description="Anime/Series download management system",
    )

    # CORS – allow all origins for local / Docker use
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    app.include_router(router)

    # Serve static files and templates
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


def start_server(host: str = "0.0.0.0", port: int = 5050) -> None:
    """Initialise the database, configure logging, and start uvicorn."""
    cfg = load_config()
    log_cfg = cfg.get("logging", {})

    setup_logging(
        level=log_cfg.get("level", "INFO"),
        max_bytes=log_cfg.get("max_file_size_mb", 10) * 1024 * 1024,
        backup_count=log_cfg.get("backup_count", 5),
    )

    init_db()

    srv_cfg = cfg.get("server", {})
    host = srv_cfg.get("host", host)
    port = srv_cfg.get("port", port)

    log.info("Starting AniLoader server on %s:%d", host, port)

    # Auto‑start download if configured
    autostart = cfg.get("autostart_mode")
    if autostart:
        from services.downloader import run_download
        t = threading.Thread(target=run_download, args=(autostart,), daemon=True)
        t.start()
        log.info("Autostart download (mode=%s) launched", autostart)

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")
