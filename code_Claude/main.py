"""
main.py – Entry-Point für AniLoader (code_Claude).

Startet den Flask-Server und führt alle Initialisierungsschritte aus.
"""

import os
import sys
import threading
from pathlib import Path

from flask import Flask, render_template
from flask_cors import CORS

# ── Modul-Imports ────────────────────────────────────────────────────────────
from config import cfg, load_config, download_dir
from database import init_db, insert_anime, load_anime
from downloader import current_download, download_lock
from logger import log, cleanup_old_logs
from network import fetch_series_title

from api import api  # Flask Blueprint


# ── Flask App ────────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "..", "static"),
)
CORS(app)
app.register_blueprint(api)


@app.after_request
def after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


@app.route("/")
def index():
    return render_template("index.html")


# ── anime.txt Import ────────────────────────────────────────────────────────

def _import_anime_txt():
    """Importiert URLs aus der alten anime.txt (falls vorhanden)."""
    data_dir = Path(cfg.get("data_folder_path", "."))
    txt = data_dir / "anime.txt"
    if not txt.exists():
        return

    log("[IMPORT] anime.txt gefunden – importiere...")
    try:
        with open(txt, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
        count = sum(1 for url in urls if insert_anime(url=url))
        log(f"[IMPORT] {count} URLs aus anime.txt importiert")
        txt.rename(txt.with_suffix(".txt.imported"))
    except Exception as e:
        log(f"[IMPORT-ERROR] {e}")


# ── Titel-Aktualisierung ────────────────────────────────────────────────────

def _refresh_titles():
    """Aktualisiert Titel aller Anime in der DB, die noch keinen Titel haben."""
    from database import update_anime
    try:
        for anime in load_anime():
            if not anime.get("title") or anime["title"] == anime.get("url", ""):
                try:
                    title = fetch_series_title(anime["url"])
                    if title and title != anime.get("title"):
                        update_anime(anime["id"], title=title)
                        log(f"[TITLE] {anime['url']} → {title}")
                except Exception as e:
                    log(f"[TITLE-ERROR] {anime['url']}: {e}")
    except Exception as e:
        log(f"[TITLE-ERROR] global: {e}")


# ── Startup ──────────────────────────────────────────────────────────────────

def aniloader_startup():
    """Alle Initialisierungsschritte in der richtigen Reihenfolge."""
    load_config()
    init_db()
    _import_anime_txt()

    # Sicherstellen, dass Download-Verzeichnis existiert
    download_dir().mkdir(parents=True, exist_ok=True)

    # Gelöschte Anime erkennen
    from downloader import deleted_check
    deleted_check()

    # Alte Logs aufräumen (> 7 Tage)
    cleanup_old_logs(days=7)

    # Titel auffrischen, wenn gewünscht
    if cfg.get("refresh_titles", False):
        _refresh_titles()

    log("[SYSTEM] AniLoader API starting...")

    # Autostart
    autostart = cfg.get("autostart_mode")
    if autostart in ("default", "german", "new", "check-missing"):
        with download_lock:
            already = current_download.get("status") == "running"
        if not already:
            from runner import run_mode
            threading.Thread(target=run_mode, args=(autostart,), daemon=True).start()
            log(f"[SYSTEM] Autostart gestartet: {autostart}")


# ── Main ─────────────────────────────────────────────────────────────────────

aniloader_startup()

if __name__ == "__main__":
    try:
        load_config()
    except Exception:
        pass
    port = cfg.get("port", 5050)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
