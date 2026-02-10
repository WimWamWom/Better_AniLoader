"""
api.py – Flask-Blueprint mit allen API-Endpoints für AniLoader.

Alle Endpoints sind funktionsgleich zu old_AniLoader.py.
"""

import concurrent.futures
import json
import os
import re
import sqlite3
import threading
from pathlib import Path

from flask import Blueprint, request, jsonify

from config import (
    cfg, load_config, save_config, download_dir, db_path, all_logs_path, log_path,
)
from database import (
    init_db, insert_anime, load_anime, update_anime, check_deutsch_komplett,
    queue_add, queue_list, queue_clear, queue_delete, queue_delete_by_anime_id,
    queue_reorder, queue_prune_completed,
)
from downloader import current_download, download_lock
from file_ops import free_space_gb
from logger import log, read_all_logs
from network import search_provider

api = Blueprint("api", __name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  Download-Steuerung
# ═══════════════════════════════════════════════════════════════════════════════

@api.route("/start_download", methods=["POST", "GET"])
def start_download():
    from runner import run_mode
    body = request.get_json(silent=True) or {}
    mode = request.args.get("mode") or body.get("mode") or "default"
    if mode not in ("default", "german", "new", "check-missing", "full-check"):
        return jsonify({"status": "error", "msg": "Ungültiger Mode"}), 400
    with download_lock:
        if current_download["status"] == "running":
            return jsonify({"status": "already_running"}), 409
    threading.Thread(target=run_mode, args=(mode,), daemon=True).start()
    return jsonify({"status": "started", "mode": mode})


@api.route("/stop_download", methods=["POST"])
def stop_download():
    with download_lock:
        if current_download["status"] != "running":
            return jsonify({"status": "not_running"}), 400
        current_download["stop_requested"] = True
        log("[STOP] Stop-Anforderung erhalten")
    return jsonify({"status": "ok", "msg": "Download wird nach aktueller Episode gestoppt"})


@api.route("/status")
def status():
    with download_lock:
        data = dict(current_download)
    return jsonify(data)


@api.route("/health")
def health():
    return jsonify({"ok": True}), 200


# ═══════════════════════════════════════════════════════════════════════════════
#  Konfiguration
# ═══════════════════════════════════════════════════════════════════════════════

@api.route("/config", methods=["GET", "POST"])
def config_endpoint():
    if request.method == "GET":
        try:
            load_config()
            return jsonify(_config_dict())
        except Exception as e:
            log(f"[ERROR] api_config GET: {e}")
            return jsonify({"error": "failed"}), 500

    # POST
    data = request.get_json() or {}
    changed = False

    try:
        # Languages
        langs = data.get("languages")
        if isinstance(langs, list) and langs:
            cfg["languages"] = list(langs)
            changed = True

        # min_free_gb
        mfg = data.get("min_free_gb")
        if mfg is not None:
            cfg["min_free_gb"] = float(mfg)
            changed = True

        # download_path
        dp = data.get("download_path")
        if isinstance(dp, str) and dp.strip():
            try:
                resolved = Path(dp).expanduser().resolve()
                resolved.mkdir(parents=True, exist_ok=True)
                cfg["download_path"] = str(resolved)
                changed = True
            except Exception as e:
                return jsonify({"status": "failed", "error": f"Ungültiger Speicherort: {e}"}), 400

        # data_folder_path
        dfp = data.get("data_folder_path")
        if isinstance(dfp, str) and dfp.strip():
            try:
                new_folder = Path(dfp).expanduser().resolve()
                new_folder.mkdir(parents=True, exist_ok=True)
                cfg["data_folder_path"] = str(new_folder)
                changed = True
                log(f"[CONFIG] Data-Ordner geändert zu: {new_folder}")
            except Exception as e:
                return jsonify({"status": "failed", "error": f"Ungültiger Data-Ordner: {e}"}), 400

        # storage_mode
        sm = data.get("storage_mode")
        if sm in ("standard", "separate"):
            cfg["storage_mode"] = sm
            changed = True

        # Pfade (direkt)
        for key in ("movies_path", "series_path", "anime_path", "serien_path",
                     "anime_movies_path", "serien_movies_path"):
            if key in data:
                val = data[key]
                cfg[key] = val.strip() if isinstance(val, str) else val
                changed = True

        # Booleans
        for key in ("anime_separate_movies", "serien_separate_movies"):
            if key in data:
                cfg[key] = bool(data[key])
                changed = True

        # autostart_mode
        autostart_key_present = "autostart_mode" in data or "autostart" in data
        autostart = data.get("autostart_mode") if "autostart_mode" in data else data.get("autostart")
        if autostart_key_present:
            allowed = {"default", "german", "new", "check-missing"}
            if autostart is None:
                cfg["autostart_mode"] = None
                changed = True
            elif isinstance(autostart, str):
                norm = autostart.strip().lower()
                if norm in ("", "none", "off", "disabled"):
                    cfg["autostart_mode"] = None
                    changed = True
                elif norm in allowed:
                    cfg["autostart_mode"] = norm
                    changed = True
                else:
                    return jsonify({"status": "failed", "error": "invalid autostart_mode"}), 400
            else:
                return jsonify({"status": "failed", "error": "invalid autostart_mode"}), 400

        # refresh_titles
        rt = data.get("refresh_titles")
        if rt is not None:
            cfg["refresh_titles"] = bool(rt)
            changed = True

        if changed:
            ok = save_config()
            load_config()
            log(f"[CONFIG] POST gespeichert")
            return jsonify({"status": "ok" if ok else "failed", "config": _config_dict()})

        return jsonify({"status": "nochange", "config": _config_dict()})

    except Exception as e:
        log(f"[ERROR] api_config POST: {e}")
        return jsonify({"status": "failed", "error": str(e)}), 400


def _config_dict() -> dict:
    return {
        "languages": cfg.get("languages"),
        "min_free_gb": cfg.get("min_free_gb"),
        "download_path": cfg.get("download_path"),
        "storage_mode": cfg.get("storage_mode"),
        "movies_path": cfg.get("movies_path"),
        "series_path": cfg.get("series_path"),
        "anime_path": cfg.get("anime_path"),
        "serien_path": cfg.get("serien_path"),
        "anime_separate_movies": cfg.get("anime_separate_movies"),
        "serien_separate_movies": cfg.get("serien_separate_movies"),
        "anime_movies_path": cfg.get("anime_movies_path"),
        "serien_movies_path": cfg.get("serien_movies_path"),
        "port": cfg.get("port"),
        "autostart_mode": cfg.get("autostart_mode"),
        "refresh_titles": cfg.get("refresh_titles"),
        "data_folder_path": cfg.get("data_folder_path"),
    }


@api.route("/pick_folder", methods=["GET"])
def pick_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as e:
        return jsonify({"status": "failed", "selected": None, "error": f"tkinter nicht verfügbar: {e}"}), 500

    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        try:
            path = filedialog.askdirectory(title="Download-Verzeichnis wählen")
        finally:
            root.destroy()

        if not path:
            return jsonify({"status": "canceled", "selected": None}), 200
        return jsonify({"status": "ok", "selected": path}), 200
    except Exception as e:
        return jsonify({"status": "failed", "selected": None, "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
#  Queue
# ═══════════════════════════════════════════════════════════════════════════════

@api.route("/queue", methods=["GET", "POST", "DELETE"])
def queue_endpoint():
    try:
        if request.method == "GET":
            queue_prune_completed()
            return jsonify(queue_list())

        if request.method == "POST":
            data = request.get_json() or {}
            if "order" in data:
                try:
                    ids = [int(x) for x in data.get("order") or []]
                except Exception:
                    return jsonify({"status": "failed", "error": "invalid order list"}), 400
                return jsonify({"status": "ok" if queue_reorder(ids) else "failed"})
            aid = data.get("anime_id")
            try:
                aid = int(str(aid))
            except Exception:
                return jsonify({"status": "failed", "error": "invalid anime_id"}), 400
            return jsonify({"status": "ok" if queue_add(aid) else "failed"})

        if request.method == "DELETE":
            payload = request.get_json(silent=True) or {}
            qid = request.args.get("id") or payload.get("id")
            aid = request.args.get("anime_id") or payload.get("anime_id")
            if qid is not None:
                return jsonify({"status": "ok" if queue_delete(int(str(qid))) else "failed"})
            if aid is not None:
                return jsonify({"status": "ok" if queue_delete_by_anime_id(int(str(aid))) else "failed"})
            return jsonify({"status": "ok" if queue_clear() else "failed"})

        return jsonify({"status": "failed", "error": "Method not allowed"}), 405
    except Exception as e:
        log(f"[ERROR] api_queue: {e}")
        return jsonify({"status": "failed", "error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
#  System-Info
# ═══════════════════════════════════════════════════════════════════════════════

@api.route("/disk")
def disk():
    try:
        free = free_space_gb(str(download_dir()))
        return jsonify({"free_gb": free})
    except Exception as e:
        return jsonify({"free_gb": None, "error": str(e)}), 500


@api.route("/logs")
def logs():
    try:
        return jsonify(read_all_logs())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api.route("/last_run")
def last_run():
    try:
        lp = log_path()
        if os.path.exists(lp):
            with open(lp, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n") if content else []
            return jsonify(lines)
        return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
#  Datenbank
# ═══════════════════════════════════════════════════════════════════════════════

@api.route("/database")
def database():
    q = request.args.get("q", "").strip()
    complete = request.args.get("complete", "").strip()
    deutsch = request.args.get("deutsch", "").strip()
    sort_by = request.args.get("sort_by", "id")
    order = request.args.get("order", "asc").lower()
    limit = request.args.get("limit")
    offset = request.args.get("offset", 0)

    allowed_sort = {"id", "title", "last_film", "last_episode", "last_season"}
    if sort_by not in allowed_sort:
        sort_by = "id"
    order_sql = "DESC" if order == "desc" else "ASC"

    sql = "SELECT id, title, url, complete, deutsch_komplett, deleted, fehlende_deutsch_folgen, last_film, last_episode, last_season FROM anime"
    params: list = []
    clauses: list[str] = []

    if q:
        clauses.append("(title LIKE ? OR url LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    if complete == "deleted":
        clauses.append("deleted = 1")
    elif complete in ("0", "1"):
        clauses.append("complete = ?")
        params.append(int(complete))
        clauses.append("deleted = 0")
    else:
        clauses.append("deleted = 0")

    if deutsch in ("0", "1"):
        clauses.append("deutsch_komplett = ?")
        params.append(int(deutsch))

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += f" ORDER BY {sort_by} {order_sql}"

    if limit:
        try:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        except Exception:
            pass

    conn = sqlite3.connect(db_path())
    c = conn.cursor()
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()

    return jsonify([
        {
            "id": r[0], "title": r[1], "url": r[2],
            "complete": bool(r[3]), "deutsch_komplett": bool(r[4]),
            "deleted": bool(r[5]), "fehlende": json.loads(r[6] or "[]"),
            "last_film": r[7], "last_episode": r[8], "last_season": r[9],
        }
        for r in rows
    ])


@api.route("/counts")
def counts():
    try:
        anime_id = request.args.get("id")
        title_param = request.args.get("title")
        series_title = None

        if anime_id and anime_id.isdigit():
            try:
                conn = sqlite3.connect(db_path())
                c = conn.cursor()
                c.execute("SELECT title FROM anime WHERE id = ?", (int(anime_id),))
                row = c.fetchone()
                if row and row[0]:
                    series_title = row[0]
                conn.close()
            except Exception:
                pass

        if not series_title:
            series_title = title_param
        if not series_title:
            return jsonify({"per_season": {}, "total_seasons": 0, "total_episodes": 0, "films": 0})

        # In allen möglichen Pfaden suchen
        possible: list[Path] = []
        if cfg.get("storage_mode") == "separate":
            for key in ("anime_path", "serien_path", "movies_path", "series_path"):
                val = cfg.get(key, "")
                if val and val.strip():
                    possible.append(Path(val))
        if not possible or cfg.get("storage_mode") == "standard":
            possible = [download_dir()]

        base = None
        for p in possible:
            candidate = p / series_title
            if candidate.exists() and candidate.is_dir():
                base = candidate
                break
        if not base:
            base = download_dir() / series_title

        per_season: dict[str, int] = {}
        total_eps = 0
        films = 0

        if base.exists() and base.is_dir():
            filme_dir = base / "Filme"
            if filme_dir.exists():
                films = sum(1 for _ in filme_dir.glob("*.mp4"))
            for d in base.iterdir():
                if d.is_dir():
                    m = re.match(r"^Staffel\s+(\d+)$", d.name, re.IGNORECASE)
                    if m:
                        s = m.group(1)
                        cnt = sum(1 for _ in d.glob("*.mp4"))
                        per_season[s] = cnt
                        total_eps += cnt

        return jsonify({
            "per_season": per_season, "total_seasons": len(per_season),
            "total_episodes": total_eps, "films": films, "title": series_title,
        })
    except Exception as e:
        log(f"[ERROR] api_counts: {e}")
        return jsonify({"error": str(e), "per_season": {}, "total_seasons": 0,
                        "total_episodes": 0, "films": 0}), 500


# ═══════════════════════════════════════════════════════════════════════════════
#  Anime-Verwaltung
# ═══════════════════════════════════════════════════════════════════════════════

@api.route("/export", methods=["POST"])
def export():
    data = request.get_json() or {}
    url = data.get("url")
    if not url:
        return jsonify({"status": "error", "msg": "Keine URL angegeben"}), 400
    ok = insert_anime(url)
    return jsonify({"status": "ok" if ok else "failed"})


@api.route("/add_link", methods=["POST"])
def add_link():
    try:
        body = request.get_json(silent=True) or {}
        url = body.get("url", "").strip()
        if not url:
            return jsonify({"status": "error", "msg": "Keine URL angegeben"}), 400
        if not url.startswith(("http://", "https://")):
            return jsonify({"status": "error", "msg": "Ungültige URL"}), 400
        ok = insert_anime(url=url)
        if ok:
            log(f"[ADD_LINK] URL hinzugefügt: {url}")
            return jsonify({"status": "ok", "msg": "URL erfolgreich hinzugefügt"})
        return jsonify({"status": "error", "msg": "URL bereits vorhanden oder Fehler"}), 400
    except Exception as e:
        log(f"[ERROR] api_add_link: {e}")
        return jsonify({"status": "error", "msg": str(e)}), 500


@api.route("/search", methods=["POST"])
def search():
    try:
        body = request.get_json(silent=True) or {}
        query = body.get("query", "").strip()
        if not query:
            return jsonify({"status": "ok", "results": [], "count": 0})

        providers = [("aniworld", "https://aniworld.to"), ("sto", "https://s.to")]
        all_results: list[dict] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(search_provider, query, name, url): name
                for name, url in providers
            }
            for future in concurrent.futures.as_completed(futures):
                pname = futures[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    log(f"[SEARCH] {len(results)} Ergebnisse von {pname}")
                except Exception as e:
                    log(f"[SEARCH-ERROR] {pname}: {e}")

        log(f"[SEARCH] Gesamt: {len(all_results)} Ergebnisse für '{query}'")
        return jsonify({"status": "ok", "results": all_results,
                        "count": len(all_results), "total": len(all_results)})
    except Exception as e:
        log(f"[ERROR] api_search: {e}")
        return jsonify({"status": "error", "msg": str(e)}), 500


@api.route("/anime", methods=["DELETE"])
def anime_delete():
    try:
        anime_id = request.args.get("id") or (request.get_json(silent=True) or {}).get("id")
        if anime_id is None:
            return jsonify({"status": "failed", "error": "missing id"}), 400
        aid = int(str(anime_id))

        conn = sqlite3.connect(db_path())
        c = conn.cursor()
        c.execute("SELECT url, title FROM anime WHERE id = ?", (aid,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({"status": "failed", "error": "not found"}), 404

        aurl, atitle = row
        c.execute("DELETE FROM queue WHERE anime_id = ?", (aid,))
        c.execute("DELETE FROM queue WHERE anime_url = ?", (aurl,))
        c.execute("DELETE FROM anime WHERE id = ?", (aid,))
        conn.commit()
        conn.close()
        log(f"[DB] Anime gelöscht: ID {aid} • '{atitle}'")
        return jsonify({"status": "ok"})
    except Exception as e:
        log(f"[ERROR] api_anime_delete: {e}")
        return jsonify({"status": "failed", "error": str(e)}), 500


@api.route("/anime/restore", methods=["POST"])
def anime_restore():
    try:
        data = request.get_json(silent=True) or {}
        anime_id = data.get("id") or request.args.get("id")
        add_to_queue = bool(data.get("queue", True))
        if anime_id is None:
            return jsonify({"status": "failed", "error": "missing id"}), 400
        aid = int(str(anime_id))

        conn = sqlite3.connect(db_path())
        c = conn.cursor()
        c.execute("SELECT id FROM anime WHERE id = ?", (aid,))
        if not c.fetchone():
            conn.close()
            return jsonify({"status": "failed", "error": "not found"}), 404
        c.execute("""
            UPDATE anime SET complete=0, deutsch_komplett=0, deleted=0,
                   fehlende_deutsch_folgen='[]', last_film=0, last_episode=0, last_season=0
            WHERE id = ?
        """, (aid,))
        conn.commit()
        conn.close()
        log(f"[DB] Anime reaktiviert: ID {aid}")

        queued = False
        if add_to_queue:
            try:
                queued = queue_add(aid)
            except Exception as e:
                log(f"[QUEUE] queue_add on restore: {e}")
        return jsonify({"status": "ok", "queued": bool(queued)})
    except Exception as e:
        log(f"[ERROR] api_anime_restore: {e}")
        return jsonify({"status": "failed", "error": str(e)}), 500


@api.route("/check")
def check():
    url = request.args.get("url")
    if not url:
        return jsonify({"exists": False})
    try:
        conn = sqlite3.connect(db_path())
        c = conn.cursor()
        c.execute("SELECT 1 FROM anime WHERE url = ? AND deleted = 0", (url,))
        exists = c.fetchone() is not None
        conn.close()
    except Exception:
        exists = False
    return jsonify({"exists": exists})


# ═══════════════════════════════════════════════════════════════════════════════
#  Datei-Upload
# ═══════════════════════════════════════════════════════════════════════════════

@api.route("/upload_txt", methods=["POST"])
def upload_txt():
    try:
        if "file" not in request.files:
            return jsonify({"status": "error", "msg": "Keine Datei hochgeladen"}), 400
        file = request.files["file"]
        if not file.filename or file.filename == "":
            return jsonify({"status": "error", "msg": "Keine Datei ausgewählt"}), 400
        if not file.filename.endswith(".txt"):
            return jsonify({"status": "error", "msg": "Nur TXT-Dateien erlaubt"}), 400

        content = file.read().decode("utf-8")
        links = [line.strip() for line in content.split("\n") if line.strip()]
        if not links:
            return jsonify({"status": "error", "msg": "Keine URLs gefunden"}), 400

        imported = sum(1 for url in links if insert_anime(url=url))
        log(f"[UPLOAD] {imported} URLs aus '{file.filename}' importiert")
        return jsonify({"status": "ok", "msg": f"{imported} URLs importiert", "count": imported})
    except Exception as e:
        log(f"[ERROR] api_upload_txt: {e}")
        return jsonify({"status": "error", "msg": str(e)}), 500
