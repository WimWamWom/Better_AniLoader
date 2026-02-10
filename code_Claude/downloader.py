"""
downloader.py – Download-Engine für AniLoader.

Verantwortlich für:
  - CLI-Aufruf (aniworld) – nur für den tatsächlichen Download
  - Einzelepisoden-Download inkl. Sprach-Auswahl via html_request
  - Film- und Staffel-Downloads
  - Vollständige Prüfung (full_check)
  - deleted_check
"""

import json
import os
import re
import subprocess
import time
import threading
from pathlib import Path

from config import cfg, get_content_type, get_base_path, is_dedicated_movies_folder, db_path
from database import (
    update_anime, load_anime, check_deutsch_komplett,
    queue_delete_by_anime_id, queue_prune_completed, queue_list,
)
from file_ops import (
    episode_already_downloaded, rename_downloaded, delete_old_non_german,
    free_space_gb, check_file_language,
)
from logger import log
from network import (
    get_languages, select_language, fetch_episode_title, fetch_series_title,
)

import sqlite3

# ═══════════════════════════════════════════════════════════════════════════════
#  Download-Status (global, thread-safe)
# ═══════════════════════════════════════════════════════════════════════════════

current_download: dict = {
    "status": "idle",
    "mode": None,
    "current_index": None,
    "current_title": None,
    "started_at": None,
    "anime_started_at": None,
    "episode_started_at": None,
    "current_season": None,
    "current_episode": None,
    "current_is_film": None,
    "current_id": None,
    "current_url": None,
    "stop_requested": False,
}
download_lock = threading.Lock()


def check_stop_requested() -> bool:
    with download_lock:
        return current_download.get("stop_requested", False)


def set_episode_status(season: int, episode: int) -> None:
    """Setzt Staffel/Episode/Film-Status für das UI."""
    try:
        with download_lock:
            current_download["current_season"] = season
            current_download["current_episode"] = episode
            current_download["current_is_film"] = (season == 0)
            current_download["episode_started_at"] = time.time()
    except Exception:
        pass


def set_anime_status(anime: dict, idx: int) -> str:
    """Setzt den aktuell bearbeiteten Anime für das UI und gibt den Titel zurück."""
    series_title = str(anime.get("title") or fetch_series_title(anime["url"]))
    with download_lock:
        current_download["current_index"] = idx
        current_download["current_title"] = series_title
        current_download["anime_started_at"] = time.time()
        current_download["current_id"] = anime["id"]
        current_download["current_url"] = anime["url"]
        current_download["episode_started_at"] = None
    return series_title


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI-Ausführung (aniworld)
# ═══════════════════════════════════════════════════════════════════════════════

def _run_cli(cmd: list[str]) -> str:
    """Startet aniworld CLI und gibt Status zurück: OK, FAILED, NO_STREAMS, LANGUAGE_ERROR."""
    try:
        cmd_display = " ".join(f'"{a}"' if " " in a else a for a in cmd)
        log(f"[CLI] Starte: {cmd_display}")

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=env,
        )
        outs, _ = process.communicate(timeout=600)
        out = outs or ""
        log(f"[CLI] Beendet mit Code: {process.returncode}")

        if "No streams available for episode" in out:
            return "NO_STREAMS"
        if "No provider found for language" in out:
            return "LANGUAGE_ERROR"

        error_indicators = [
            "Something went wrong", "No direct link found",
            "Failed to execute any anime actions", "Invalid action configuration",
            "charmap' codec can't encode", "Unexpected download error",
        ]
        if any(ind in out for ind in error_indicators):
            log("[CLI] Download-Fehler erkannt in Ausgabe")
            return "FAILED"

        if process.returncode == 0:
            log("[CLI] Download erfolgreich")
            time.sleep(3)
            return "OK"
        log(f"[CLI] Fehlgeschlagen (Code: {process.returncode})")
        return "FAILED"

    except subprocess.TimeoutExpired:
        log("[FEHLER] CLI-Timeout nach 600 Sekunden")
        try:
            process.kill()
        except Exception:
            pass
        return "FAILED"
    except Exception as e:
        log(f"[FEHLER] _run_cli: {e}")
        return "FAILED"


def _verify_download(base_path: Path, season: int, episode: int) -> bool:
    """Prüft ob die heruntergeladene Datei existiert (mit Retry)."""
    if season > 0:
        pattern = f"S{season:02d}E{episode:03d}"
    else:
        pattern = None

    for retry in range(5):
        if retry > 0:
            log(f"[VERIFY] Suche Datei, Versuch {retry + 1}/5...")
            time.sleep(2)
        for f in Path(base_path).rglob("*.mp4"):
            low = f.name.lower()
            if pattern:
                if pattern.lower() in low:
                    log(f"[VERIFY] Datei gefunden: {f.name}")
                    return True
            else:
                if (f"movie {episode:03d}" in low or f"movie{episode:03d}" in low or
                        f"episode {episode:03d}" in low or f"episode{episode:03d}" in low):
                    log(f"[VERIFY] Datei gefunden: {f.name}")
                    return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
#  Einzelepisoden-Download
# ═══════════════════════════════════════════════════════════════════════════════

def download_episode(series_title: str, episode_url: str, season: int, episode: int,
                     anime_id: int, german_only: bool = False) -> str:
    """
    Lädt eine einzelne Episode/einen Film herunter.

    Ablauf:
      1. Sprachen via html_request ermitteln (kein CLI-Aufruf nötig)
      2. Beste Sprache gemäß Priorität wählen
      3. Nur für den eigentlichen Download wird aniworld-CLI aufgerufen
      4. Datei verifizieren + umbenennen

    Returns: OK, SKIPPED, FAILED, NO_STREAMS, NO_SPACE
    """
    set_episode_status(season, episode)

    content_type = get_content_type(episode_url)
    is_film = (season == 0)
    base_path = get_base_path(content_type, is_film)
    in_dedicated = is_dedicated_movies_folder(content_type) if is_film else False

    # Speicherplatz prüfen
    try:
        free_gb = free_space_gb(str(base_path))
    except Exception as e:
        log(f"[ERROR] Speicher nicht ermittelbar: {e}")
        return "FAILED"

    min_free = cfg.get("min_free_gb", 2.0)
    if free_gb < min_free:
        log(f"[ERROR] Zu wenig Speicher ({free_gb} GB < {min_free} GB) in {base_path}")
        with download_lock:
            current_download["status"] = "kein-speicher"
        return "NO_SPACE"

    series_folder = os.path.join(str(base_path), series_title)

    # Bereits vorhanden? (nur wenn nicht german_only – dort wird Ersetzung gewünscht)
    if not german_only:
        if episode_already_downloaded(series_folder, season, episode, in_dedicated):
            label = f"S{season}E{episode}" if season > 0 else f"Film {episode}"
            log(f"[SKIP] Bereits vorhanden: {series_title} - {label}")
            with download_lock:
                current_download["episode_started_at"] = None
            return "SKIPPED"

    # Sprachen via HTML ermitteln (vermeidet unnötigen CLI-Aufruf)
    try:
        available_langs = get_languages(episode_url)
    except Exception:
        available_langs = []

    if not available_langs:
        log(f"[INFO] Keine Sprachen/Streams gefunden: {episode_url}")
        return "NO_STREAMS"

    # Sprache wählen
    languages = cfg.get("languages", ["German Dub", "German Sub", "English Dub", "English Sub"])
    langs_to_try = ["German Dub"] if german_only else languages

    episode_downloaded = False
    german_available = False

    for lang in langs_to_try:
        if lang not in available_langs:
            log(f"[INFO] Sprache {lang} nicht verfügbar für {episode_url}")
            continue

        log(f"[DOWNLOAD] Versuche {lang} -> {episode_url}")
        cmd = ["aniworld", "--language", lang, "-o", str(base_path), "--episode", episode_url]
        result = _run_cli(cmd)
        log(f"[DOWNLOAD-RESULT] {lang} -> {result}")

        if result == "NO_STREAMS":
            return "NO_STREAMS"

        if result == "OK":
            if not _verify_download(base_path, season, episode):
                log(f"[WARN] CLI OK aber keine Datei gefunden für {lang}. Nächste Sprache.")
                continue

            title = fetch_episode_title(episode_url)
            if not rename_downloaded(series_folder, season, episode, title, lang, in_dedicated):
                log(f"[WARN] Umbenennung fehlgeschlagen für {episode_url}")
                continue

            if lang == "German Dub":
                german_available = True
                if german_only:
                    delete_old_non_german(series_folder, season, episode, in_dedicated)

            episode_downloaded = True
            log(f"[OK] {lang} erfolgreich: {episode_url}")
            break

        if result == "LANGUAGE_ERROR":
            log(f"[INFO] Sprache {lang} nicht gefunden, nächste.")
            time.sleep(2)
            continue

        time.sleep(2)

    # Fehlende deutsche Folgen tracken
    if not german_available:
        _track_missing_german(anime_id, episode_url, base_path)

    return "OK" if episode_downloaded else "FAILED"


def _track_missing_german(anime_id: int, episode_url: str, base_path: Path) -> None:
    """Fügt Episode zu fehlende_deutsch_folgen hinzu."""
    try:
        conn = sqlite3.connect(db_path())
        c = conn.cursor()
        c.execute("SELECT fehlende_deutsch_folgen FROM anime WHERE id = ?", (anime_id,))
        row = c.fetchone()
        fehlende = json.loads(row[0]) if row and row[0] else []
        if episode_url not in fehlende:
            try:
                free_after = free_space_gb(str(base_path))
            except Exception:
                free_after = 0
            if free_after >= cfg.get("min_free_gb", 2.0):
                fehlende.append(episode_url)
                update_anime(anime_id, fehlende_deutsch_folgen=fehlende)
                log(f"[INFO] Zu fehlende_deutsch_folgen hinzugefügt: {episode_url}")
            else:
                log(f"[WARN] DB nicht aktualisiert (Speicher): {episode_url}")
        conn.close()
    except Exception as e:
        log(f"[DB-ERROR] _track_missing_german: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Film- und Staffel-Downloads
# ═══════════════════════════════════════════════════════════════════════════════

def download_films(series_title: str, base_url: str, anime_id: int,
                   german_only: bool = False, start_film: int = 1) -> str | None:
    """Lädt alle Filme ab start_film herunter."""
    film_num = start_film
    log(f"[INFO] Starte Filmprüfung ab Film {start_film}")

    while True:
        film_url = f"{base_url}/filme/film-{film_num}"
        result = download_episode(series_title, film_url, 0, film_num, anime_id, german_only)

        if result == "NO_SPACE":
            log("[ERROR] Film-Downloads abgebrochen (Speicher).")
            return "NO_SPACE"
        if result in ("NO_STREAMS", "FAILED"):
            log(f"[INFO] Keine weiteren Filme bei Film {film_num}.")
            break
        if result in ("OK", "SKIPPED"):
            update_anime(anime_id, last_film=film_num)
        film_num += 1
        time.sleep(1)
    return None


def download_seasons(series_title: str, base_url: str, anime_id: int,
                     german_only: bool = False,
                     start_season: int = 1, start_episode: int = 1) -> str | None:
    """Lädt alle Staffeln ab start_season/start_episode herunter."""
    season = max(1, start_season)
    consecutive_empty = 0

    while True:
        ep = start_episode
        found = False
        consecutive_failed = 0
        log(f"[DOWNLOAD] Prüfe Staffel {season} von '{series_title}'")

        while True:
            ep_url = f"{base_url}/staffel-{season}/episode-{ep}"
            result = download_episode(series_title, ep_url, season, ep, anime_id, german_only)

            if result == "NO_SPACE":
                return "NO_SPACE"
            if result in ("NO_STREAMS", "FAILED"):
                consecutive_failed += 1
                if ep == start_episode:
                    log(f"[INFO] Keine Episoden in Staffel {season}.")
                    break
                if consecutive_failed >= 3:
                    log(f"[INFO] Staffel {season} beendet nach 3 Fehlern bei Episode {ep}.")
                    break
                log(f"[WARN] Episode {ep} fehlgeschlagen ({consecutive_failed}/3)")
                ep += 1
                time.sleep(1)
                continue

            consecutive_failed = 0
            found = True
            update_anime(anime_id, last_episode=ep, last_season=season)
            ep += 1
            time.sleep(1)

        consecutive_empty = 0 if found else consecutive_empty + 1
        if consecutive_empty >= 2:
            log(f"[INFO] Keine weiteren Staffeln für '{series_title}'.")
            break
        season += 1
        start_episode = 1
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Full-Check (vollständige Prüfung von Anfang an)
# ═══════════════════════════════════════════════════════════════════════════════

def full_check_anime(series_title: str, base_url: str, anime_id: int) -> str:
    """Vollständige Prüfung eines Anime: Filme + Staffeln + Deutsch-Ersetzung."""
    log(f"[FULL-CHECK] Starte für '{series_title}'")

    content_type = get_content_type(base_url)
    base_path = get_base_path(content_type, is_film=False)
    series_folder = os.path.join(str(base_path), series_title)
    in_dedicated = is_dedicated_movies_folder(content_type)

    # ── 1. Filme prüfen ───────────────────────────────────────────────
    film_num = 1
    consecutive_missing = 0
    last_film = 0
    films_complete = False

    while consecutive_missing < 3:
        film_url = f"{base_url}/filme/film-{film_num}"

        if episode_already_downloaded(series_folder, 0, film_num, in_dedicated):
            log(f"[FULL-CHECK] Film{film_num:02d} existiert lokal")
            last_film = film_num

            search_path = Path(series_folder).parent if in_dedicated else Path(series_folder)
            is_german, is_non_german = check_file_language(search_path, f"film{film_num:02d}")

            if is_non_german and not is_german:
                log(f"[FULL-CHECK] Film{film_num:02d} nicht deutsch, versuche Ersetzung")
                r = download_episode(series_title, film_url, 0, film_num, anime_id, german_only=True)
                if r == "NO_SPACE":
                    return "NO_SPACE"
                if r == "OK":
                    delete_old_non_german(series_folder, 0, film_num, in_dedicated)

            consecutive_missing = 0
        else:
            r = download_episode(series_title, film_url, 0, film_num, anime_id)
            if r == "NO_SPACE":
                return "NO_SPACE"
            if r == "NO_STREAMS":
                consecutive_missing += 1
            elif r == "OK":
                last_film = film_num
                consecutive_missing = 0
            else:
                consecutive_missing += 1

        film_num += 1
        time.sleep(0.5)

    films_complete = consecutive_missing >= 3

    # ── 2. Staffeln prüfen ────────────────────────────────────────────
    season = 1
    consecutive_empty = 0
    last_season = 0
    last_episode = 0

    while consecutive_empty < 2:
        ep = 1
        found = False
        consecutive_missing_eps = 0

        while consecutive_missing_eps < 3:
            ep_url = f"{base_url}/staffel-{season}/episode-{ep}"

            if episode_already_downloaded(series_folder, season, ep, False):
                found = True
                last_season = season
                last_episode = ep

                is_german, is_non_german = check_file_language(Path(series_folder), f"s{season:02d}e{ep:03d}")
                if is_non_german and not is_german:
                    r = download_episode(series_title, ep_url, season, ep, anime_id, german_only=True)
                    if r == "NO_SPACE":
                        return "NO_SPACE"
                    if r == "OK":
                        delete_old_non_german(series_folder, season, ep, False)
                consecutive_missing_eps = 0
            else:
                r = download_episode(series_title, ep_url, season, ep, anime_id)
                if r == "NO_SPACE":
                    return "NO_SPACE"
                if r == "NO_STREAMS":
                    consecutive_missing_eps += 1
                elif r == "OK":
                    found = True
                    last_season = season
                    last_episode = ep
                    consecutive_missing_eps = 0
                else:
                    consecutive_missing_eps += 1

            ep += 1
            time.sleep(0.5)

        consecutive_empty = 0 if found else consecutive_empty + 1
        season += 1

    seasons_complete = consecutive_empty >= 2

    # ── 3. DB aktualisieren ───────────────────────────────────────────
    conn = sqlite3.connect(db_path())
    c = conn.cursor()
    c.execute("SELECT fehlende_deutsch_folgen FROM anime WHERE id = ?", (anime_id,))
    row = c.fetchone()
    conn.close()
    fehlende = json.loads(row[0]) if row and row[0] else []

    if last_film > 0:
        update_anime(anime_id, last_film=last_film)
    if last_season > 0 and last_episode > 0:
        update_anime(anime_id, last_season=last_season, last_episode=last_episode)

    if not fehlende:
        update_anime(anime_id, deutsch_komplett=1)
        log(f"[FULL-CHECK] '{series_title}' komplett auf Deutsch")
    else:
        update_anime(anime_id, deutsch_komplett=0)
        log(f"[FULL-CHECK] '{series_title}' hat {len(fehlende)} fehlende deutsche Folgen")

    # Complete-Status
    has_content = False
    if os.path.exists(series_folder):
        if list(Path(series_folder).rglob("*.mp4")):
            has_content = True

    if not has_content and in_dedicated and cfg.get("storage_mode") == "separate":
        movie_base = None
        if content_type == "anime":
            movie_base = Path(cfg.get("anime_movies_path", "")) if cfg.get("anime_movies_path", "").strip() else (
                Path(cfg.get("anime_path", "")) / "Filme" if cfg.get("anime_path", "").strip() else None
            )
        elif content_type == "serie":
            movie_base = Path(cfg.get("serien_movies_path", "")) if cfg.get("serien_movies_path", "").strip() else (
                Path(cfg.get("serien_path", "")) / "Filme" if cfg.get("serien_path", "").strip() else None
            )
        if movie_base and movie_base.exists() and list(movie_base.rglob("*.mp4")):
            has_content = True

    if has_content and films_complete and seasons_complete:
        update_anime(anime_id, complete=1)
        log(f"[FULL-CHECK] '{series_title}' als complete markiert")

    log(f"[FULL-CHECK] Prüfung für '{series_title}' abgeschlossen")
    return "OK"


# ═══════════════════════════════════════════════════════════════════════════════
#  deleted_check
# ═══════════════════════════════════════════════════════════════════════════════

def deleted_check() -> list[str]:
    """
    Prüft ob complete-Anime noch im Dateisystem existieren.
    Setzt fehlende auf deleted=1 und Initialwerte zurück.
    """
    try:
        conn = sqlite3.connect(db_path())
        c = conn.cursor()
        c.execute("SELECT id, title FROM anime WHERE complete = 1")
        complete_animes = c.fetchall()

        # Alle relevanten Pfade sammeln
        paths: set[Path] = set()
        if cfg.get("storage_mode") == "separate":
            for key in ("anime_path", "serien_path", "anime_movies_path",
                        "serien_movies_path", "movies_path", "series_path"):
                val = cfg.get(key, "")
                if val and val.strip():
                    paths.add(Path(val))

        if cfg.get("storage_mode") == "standard" or not paths:
            from config import download_dir
            paths.add(download_dir())

        # Alle Ordnernamen sammeln
        local_names: set[str] = set()
        for p in paths:
            if p.exists() and p.is_dir():
                try:
                    local_names.update(d.name for d in p.iterdir() if d.is_dir())
                except Exception as e:
                    log(f"[CHECK-WARN] Fehler beim Lesen von {p}: {e}")

        deleted = []
        for aid, title in complete_animes:
            if title not in local_names:
                deleted.append(title)
                c.execute("""
                    UPDATE anime SET complete=0, deutsch_komplett=0, deleted=1,
                           fehlende_deutsch_folgen='[]', last_film=0, last_episode=0, last_season=0
                    WHERE id = ?
                """, (aid,))

        conn.commit()
        conn.close()
        log(f"[INFO] Gelöschte Animes: {deleted}")
        return deleted
    except Exception as e:
        log(f"[ERROR] deleted_check: {e}")
        return []
