"""
runner.py – Download-Orchestrator für AniLoader.

Implementiert die verschiedenen Download-Modi:
  - default:       Alle nicht-complete Animes durchlaufen
  - german:        Fehlende deutsche Folgen ersetzen
  - new:           Nur neue Episoden/Filme ab letztem Stand
  - check-missing: Lücken in bereits teilweise geladenen Animes füllen
  - full-check:    Vollständige Prüfung aller Animes von Anfang an

Queue-Einträge werden stets priorisiert verarbeitet.
"""

import os
import re
import time

from config import cfg, download_dir
from database import (
    init_db, load_anime, update_anime, check_deutsch_komplett,
    queue_prune_completed, queue_list, queue_delete_by_anime_id,
    queue_cleanup_ids,
)
from downloader import (
    current_download, download_lock, check_stop_requested, set_anime_status,
    download_episode, download_films, download_seasons,
    full_check_anime, deleted_check,
)
from file_ops import episode_already_downloaded, delete_old_non_german
from logger import log, clear_last_run
from network import fetch_series_title


# ═══════════════════════════════════════════════════════════════════════════════
#  Hilfsfunktionen
# ═══════════════════════════════════════════════════════════════════════════════

def _build_work_lists(anime_list: list[dict], queued_ids: list[int], priority_map: dict):
    """Teilt anime_list in priorisierte Queue-Items und Rest auf."""
    queue_work = sorted(
        [a for a in anime_list if a["id"] in queued_ids],
        key=lambda a: priority_map.get(a["id"], 1_000_000),
    )
    rest = [a for a in anime_list if a["id"] not in queued_ids]
    return queue_work, rest


def _parse_episode_url(url: str) -> tuple[int, int]:
    """Extrahiert Staffel und Episode aus einer Episode-URL."""
    m = re.search(r"/staffel-(\d+)/episode-(\d+)", url)
    if m:
        return int(m.group(1)), int(m.group(2))
    m2 = re.search(r"/film-(\d+)", url)
    return 0, int(m2.group(1)) if m2 else 1


def _process_german_check(anime: dict, idx: int) -> None:
    """Verarbeitet einen einzelnen Anime im German-Modus."""
    series_title = set_anime_status(anime, idx)
    anime_id = anime["id"]
    fehlende = anime.get("fehlende_deutsch_folgen", [])
    if not fehlende:
        log(f"[GERMAN] '{series_title}': Keine fehlenden deutschen Folgen")
        return

    log(f"[GERMAN] '{series_title}': {len(fehlende)} Folgen zu testen.")
    verbleibend = fehlende.copy()

    for url in fehlende:
        if check_stop_requested():
            log("[STOP] Download gestoppt")
            return
        season, episode = _parse_episode_url(url)
        result = download_episode(series_title, url, season, episode, anime_id, german_only=True)
        if result == "OK" and url in verbleibend:
            verbleibend.remove(url)
            update_anime(anime_id, fehlende_deutsch_folgen=verbleibend)
            log(f"[GERMAN] '{url}' erfolgreich auf deutsch.")
            if series_title:
                delete_old_non_german(
                    os.path.join(str(download_dir()), series_title),
                    season, episode,
                )
    check_deutsch_komplett(anime_id)


def _process_new(anime: dict, idx: int) -> str | None:
    """Verarbeitet einen einzelnen Anime im New-Modus."""
    series_title = set_anime_status(anime, idx)
    anime_id = anime["id"]
    base_url = anime["url"]

    start_film = (anime.get("last_film") or 0) + 1
    start_season = anime.get("last_season") or 1
    start_episode = (anime.get("last_episode") or 1) if start_season > 0 else 1

    log(f"[NEW] '{series_title}' ab Film {start_film} / Staffel {start_season}, Episode {start_episode}")

    r = download_films(series_title, base_url, anime_id, start_film=start_film)
    if r == "NO_SPACE":
        return "NO_SPACE"
    r2 = download_seasons(series_title, base_url, anime_id,
                          start_season=start_season, start_episode=start_episode)
    if r2 == "NO_SPACE":
        return "NO_SPACE"
    check_deutsch_komplett(anime_id)
    return None


def _process_default(anime: dict, idx: int) -> str | None:
    """Verarbeitet einen einzelnen Anime im Default-Modus."""
    if anime["complete"]:
        log(f"[SKIP] '{anime['title']}' bereits komplett.")
        return None

    series_title = set_anime_status(anime, idx)
    anime_id = anime["id"]
    base_url = anime["url"]

    start_film = (anime.get("last_film") or 0) + 1
    start_season = anime.get("last_season") or 1
    start_episode = (anime.get("last_episode") or 1) if start_season > 0 else 1

    log(f"[START] '{series_title}' ab Film {start_film} / Staffel {start_season}, Episode {start_episode}")

    r = download_films(series_title, base_url, anime_id, start_film=start_film)
    if r == "NO_SPACE":
        return "NO_SPACE"
    r2 = download_seasons(series_title, base_url, anime_id,
                          start_season=max(1, start_season), start_episode=start_episode)
    if r2 == "NO_SPACE":
        return "NO_SPACE"
    check_deutsch_komplett(anime_id)
    update_anime(anime_id, complete=1)
    log(f"[OK] Download abgeschlossen für: '{series_title}'")
    return None


def _process_check_missing(anime: dict, idx: int) -> str | None:
    """Prüft und lädt fehlende Episoden/Filme für einen Anime."""
    series_title = set_anime_status(anime, idx)
    anime_id = anime["id"]
    base_url = anime["url"]

    # Nur Anime berücksichtigen die bereits Downloads haben
    if (anime["last_film"] == 0 and anime["last_season"] == 0 and
            anime["last_episode"] == 0 and not anime["complete"]):
        return None

    log(f"[CHECK-MISSING] Prüfe '{series_title}' auf fehlende Downloads.")

    # Filme prüfen
    film_num = 1
    while True:
        film_url = f"{base_url}/filme/film-{film_num}"
        dl_dir = str(download_dir())
        if episode_already_downloaded(os.path.join(dl_dir, str(series_title or "")), 0, film_num):
            log(f"[OK] Film {film_num} vorhanden.")
        else:
            result = download_episode(series_title, film_url, 0, film_num, anime_id)
            if result == "NO_STREAMS":
                break
            if result == "NO_SPACE":
                return "NO_SPACE"
        film_num += 1

    # Staffeln prüfen
    season = 1
    consecutive_empty = 0
    while True:
        ep = 1
        found = False
        while True:
            ep_url = f"{base_url}/staffel-{season}/episode-{ep}"
            dl_dir = str(download_dir())
            if episode_already_downloaded(os.path.join(dl_dir, str(series_title or "")), season, ep):
                log(f"[OK] S{season}E{ep} vorhanden.")
                ep += 1
                continue
            result = download_episode(series_title, ep_url, season, ep, anime_id)
            if result == "NO_STREAMS":
                if ep == 1:
                    break
                log(f"[INFO] Staffel {season} beendet nach {ep - 1} Episoden.")
                break
            if result == "NO_SPACE":
                return "NO_SPACE"
            found = True
            ep += 1

        consecutive_empty = 0 if found else consecutive_empty + 1
        if consecutive_empty >= 2:
            log(f"[CHECK-MISSING] '{series_title}' keine weiteren Staffeln.")
            break
        season += 1

    check_deutsch_komplett(anime_id)
    log(f"[CHECK-MISSING] Kontrolle für '{series_title}' abgeschlossen.")
    return None


def _process_full_check(anime: dict, idx: int) -> str | None:
    """Vollständiger Check eines Anime."""
    series_title = set_anime_status(anime, idx)
    r = full_check_anime(series_title, anime["url"], anime["id"])
    if r == "NO_SPACE":
        return "NO_SPACE"
    return None


# ── Queue-Recheck nach jedem DB-Eintrag (alle Modi) ──────────────────────────

def _recheck_queue(mode: str, processor) -> str | None:
    """Prüft Queue auf neue Einträge und verarbeitet sie sofort."""
    try:
        queue_prune_completed()
        queued_now = queue_list()
        if not queued_now:
            return None

        amap = {a["id"]: a for a in load_anime()}
        work = [amap[q["anime_id"]] for q in queued_now if q.get("anime_id") in amap]
        work.sort(key=lambda a: next(
            (i for i, q in enumerate(queued_now) if q["anime_id"] == a["id"]), 999999
        ))

        log(f"[QUEUE] {len(work)} neue Einträge – abarbeiten ({mode})")
        for q_anime in work:
            if q_anime.get("deleted"):
                queue_delete_by_anime_id(q_anime["id"])
                continue
            result = processor(q_anime, 0)
            queue_delete_by_anime_id(q_anime["id"])
            if result == "NO_SPACE":
                return "NO_SPACE"
    except Exception as e:
        log(f"[QUEUE] Re-Check Fehler ({mode}): {e}")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Haupt-Runner
# ═══════════════════════════════════════════════════════════════════════════════

def run_mode(mode: str = "default") -> None:
    """Haupt-Orchestrator: behandelt alle Download-Modi."""
    global current_download

    clear_last_run()

    with download_lock:
        if current_download["status"] == "running":
            log("[INFO] Download bereits laufend – start abgebrochen.")
            return
        current_download.update({
            "status": "running", "mode": mode,
            "current_index": 0, "current_title": None,
            "started_at": time.time(), "anime_started_at": None,
            "episode_started_at": None, "current_season": None,
            "current_episode": None, "current_is_film": None,
            "current_id": None, "current_url": None,
            "stop_requested": False,
        })

    try:
        init_db()
        anime_list = load_anime()
        queue_prune_completed()
        queued = queue_list()
        queued_ids = [q["anime_id"] for q in queued]
        priority_map = {aid: idx for idx, aid in enumerate(queued_ids)}
        if queued_ids:
            log(f"[QUEUE] {len(queued_ids)} Einträge werden priorisiert.")

        log(f"[INFO] Modus: {mode}")
        queue_work, rest = _build_work_lists(anime_list, queued_ids, priority_map)

        # Wähle den passenden Prozessor
        processors = {
            "german": _process_german_check,
            "new": _process_new,
            "check-missing": _process_check_missing,
            "full-check": _process_full_check,
        }
        processor = processors.get(mode, _process_default)

        mode_labels = {
            "german": "Prüfe auf neue deutsche Synchro",
            "new": "Prüfe auf neue Episoden & Filme",
            "check-missing": "Prüfe auf fehlende Episoden & Filme",
            "full-check": "Kompletter Check (alle Animes von Anfang an)",
        }
        log(f"=== Modus: {mode_labels.get(mode, 'Standard')} ===")

        # ── 1. Queue abarbeiten ──
        if queue_work:
            log(f"[QUEUE] Starte mit {len(queue_work)} Einträgen")
        for idx, anime in enumerate(queue_work):
            if check_stop_requested():
                log("[STOP] Download gestoppt")
                return
            if anime.get("deleted"):
                log(f"[SKIP] '{anime['title']}' übersprungen (deleted).")
                continue
            result = processor(anime, idx)
            queue_delete_by_anime_id(anime["id"])
            if result == "NO_SPACE":
                log(f"[ERROR] Abbruch wegen fehlendem Speicher ({mode}).")
                return

        # ── 2. Restliche DB-Einträge ──
        for idx, anime in enumerate(rest):
            if check_stop_requested():
                log("[STOP] Download gestoppt")
                return
            if anime.get("deleted"):
                log(f"[SKIP] '{anime['title']}' übersprungen (deleted).")
                continue
            result = processor(anime, idx)
            if result == "NO_SPACE":
                log(f"[ERROR] Abbruch wegen fehlendem Speicher ({mode}).")
                return

            # Nach jedem Eintrag: Queue re-checken
            qr = _recheck_queue(mode, processor)
            if qr == "NO_SPACE":
                return

        # Queue-Cleanup
        if queued_ids:
            queue_cleanup_ids(queued_ids)

        log("[INFO] Alle Aufgaben abgeschlossen.")

    except Exception as e:
        log(f"[ERROR] Unhandled exception in run_mode: {e}")
    finally:
        with download_lock:
            if current_download.get("status") != "kein-speicher":
                current_download.update({
                    "status": "finished", "current_index": None,
                    "current_title": None, "current_season": None,
                    "current_episode": None, "current_is_film": None,
                    "anime_started_at": None, "episode_started_at": None,
                    "current_id": None, "current_url": None,
                })
            else:
                current_download.update({
                    "current_index": None, "current_title": None,
                    "current_season": None, "current_episode": None,
                    "current_is_film": None, "anime_started_at": None,
                    "episode_started_at": None, "current_id": None,
                    "current_url": None,
                })
