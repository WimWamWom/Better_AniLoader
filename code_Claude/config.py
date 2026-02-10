"""
config.py – Konfigurationsverwaltung für AniLoader.

Verwaltet das Laden, Validieren und Speichern der config.json.
Alle Konfigurationswerte werden in einem globalen dict `cfg` gehalten,
auf das andere Module per `from config import cfg` zugreifen.
"""

import json
import os
import stat
import time
import threading
from pathlib import Path

# ── Pfad-Defaults ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent          # Better_AniLoader/
DEFAULT_DATA_FOLDER = str(BASE_DIR / "data")
DEFAULT_DOWNLOAD_DIR = str(BASE_DIR / "Downloads")

# ── Globaler Config-Speicher ───────────────────────────────────────────────────
cfg: dict = {}

# ── Lock für atomares Schreiben (Windows PermissionError) ──────────────────────
_write_lock = threading.Lock()

# ── Standardwerte ──────────────────────────────────────────────────────────────
DEFAULTS: dict = {
    "languages": ["German Dub", "German Sub", "English Dub", "English Sub"],
    "min_free_gb": 2.0,
    "port": 5050,
    "download_path": DEFAULT_DOWNLOAD_DIR,
    "storage_mode": "standard",
    "movies_path": "",
    "series_path": "",
    "anime_path": "",
    "serien_path": "",
    "anime_separate_movies": False,
    "serien_separate_movies": False,
    "anime_movies_path": "",
    "serien_movies_path": "",
    "autostart_mode": None,
    "refresh_titles": True,
    "data_folder_path": DEFAULT_DATA_FOLDER,
}

MAX_PATH = 260  # Windows-Limit


# ── Abgeleitete Pfade (werden nach jedem load_config aktualisiert) ─────────────
def _data_dir() -> str:
    return cfg.get("data_folder_path", DEFAULT_DATA_FOLDER)


def config_path() -> Path:
    return Path(_data_dir()) / "config.json"


def db_path() -> Path:
    return Path(_data_dir()) / "AniLoader.db"


def log_path() -> Path:
    return Path(_data_dir()) / "last_run.txt"


def all_logs_path() -> Path:
    return Path(_data_dir()) / "all_logs.txt"


def download_dir() -> Path:
    raw = cfg.get("download_path", DEFAULT_DOWNLOAD_DIR)
    return Path(raw)


# ── Laden ──────────────────────────────────────────────────────────────────────
def load_config() -> dict:
    """Lädt config.json, ergänzt fehlende Schlüssel und gibt das dict zurück."""
    global cfg
    cp = config_path()
    os.makedirs(cp.parent, exist_ok=True)

    if not cp.exists() or cp.stat().st_size == 0:
        cfg = dict(DEFAULTS)
        _write_atomic(cfg)
        return cfg

    try:
        with open(cp, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        cfg = dict(DEFAULTS)
        _write_atomic(cfg)
        return cfg

    # Schlüssel ergänzen
    changed = False
    for key, default in DEFAULTS.items():
        if key not in raw:
            raw[key] = default
            changed = True

    # data_folder_path ggf. anwenden
    dfp = raw.get("data_folder_path")
    if dfp and isinstance(dfp, str) and dfp.strip():
        try:
            resolved = str(Path(dfp).expanduser().resolve())
            raw["data_folder_path"] = resolved
        except Exception:
            pass

    # download_path normalisieren
    dp = raw.get("download_path")
    if isinstance(dp, str) and dp.strip():
        try:
            raw["download_path"] = str(Path(dp).expanduser().resolve())
        except Exception:
            pass
    else:
        raw["download_path"] = DEFAULT_DOWNLOAD_DIR
        changed = True

    # storage_mode validieren
    if raw.get("storage_mode") not in ("standard", "separate"):
        raw["storage_mode"] = "standard"
        changed = True

    # autostart_mode normalisieren
    raw_mode = raw.get("autostart_mode")
    allowed_modes = {None, "default", "german", "new", "check-missing", "full-check"}
    if isinstance(raw_mode, str):
        norm = raw_mode.strip().lower()
        if norm in ("", "none", "off", "disabled", "false", "null"):
            raw["autostart_mode"] = None
        elif norm in allowed_modes:
            raw["autostart_mode"] = norm
        else:
            raw["autostart_mode"] = None
    elif raw_mode is not None:
        raw["autostart_mode"] = None

    # Port validieren
    try:
        port = int(raw.get("port", 5050))
        if not 1 <= port <= 65535:
            port = 5050
        raw["port"] = port
    except Exception:
        raw["port"] = 5050
        changed = True

    # min_free_gb validieren
    try:
        raw["min_free_gb"] = float(raw.get("min_free_gb", 2.0))
    except Exception:
        raw["min_free_gb"] = 2.0
        changed = True

    # Booleans sicherstellen
    for bool_key in ("anime_separate_movies", "serien_separate_movies", "refresh_titles"):
        if not isinstance(raw.get(bool_key), bool):
            raw[bool_key] = DEFAULTS[bool_key]
            changed = True

    # Languages validieren
    langs = raw.get("languages")
    if not isinstance(langs, list) or not langs:
        raw["languages"] = list(DEFAULTS["languages"])
        changed = True

    cfg = raw
    os.makedirs(_data_dir(), exist_ok=True)

    if changed:
        _write_atomic(cfg)

    return cfg


# ── Speichern ──────────────────────────────────────────────────────────────────
def save_config(updates: dict | None = None) -> bool:
    """Speichert die aktuelle Config (optional mit Updates) atomar."""
    global cfg
    if updates:
        cfg.update(updates)
    return _write_atomic(cfg)


def _write_atomic(data: dict) -> bool:
    """Schreibt config.json mit Retry-Logik und atomarem Replace."""
    try:
        with _write_lock:
            cp = config_path()
            os.makedirs(cp.parent, exist_ok=True)

            # Read-only entfernen falls nötig
            try:
                if cp.exists():
                    os.chmod(cp, stat.S_IWRITE | stat.S_IREAD)
            except Exception:
                pass

            tmp = str(cp) + ".tmp"
            for attempt in range(5):
                try:
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    os.replace(tmp, cp)
                    return True
                except PermissionError:
                    try:
                        if os.path.exists(tmp):
                            os.remove(tmp)
                    except Exception:
                        pass
                    time.sleep(0.3 * (attempt + 1))
                except Exception:
                    try:
                        if os.path.exists(tmp):
                            os.remove(tmp)
                    except Exception:
                        pass
                    break

            # Fallback: direktes Schreiben
            try:
                with open(cp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                return True
            except Exception:
                return False
    except Exception:
        return False


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────
def get_content_type(url: str) -> str:
    """Gibt 'anime' oder 'serie' zurück, basierend auf der URL."""
    if "s.to" in url.lower():
        return "serie"
    return "anime"


def get_base_path(content_type: str = "anime", is_film: bool = False) -> Path:
    """Bestimmt den Download-Pfad basierend auf storage_mode, content_type, is_film."""
    if cfg.get("storage_mode") == "separate":
        if content_type == "anime":
            if is_film and cfg.get("anime_separate_movies"):
                if cfg.get("anime_movies_path", "").strip():
                    p = Path(cfg["anime_movies_path"])
                    p.mkdir(parents=True, exist_ok=True)
                    return p
                if cfg.get("anime_path", "").strip():
                    p = Path(cfg["anime_path"]) / "Filme"
                    p.mkdir(parents=True, exist_ok=True)
                    return p
            if cfg.get("anime_path", "").strip():
                p = Path(cfg["anime_path"])
                p.mkdir(parents=True, exist_ok=True)
                return p

        elif content_type == "serie":
            if is_film and cfg.get("serien_separate_movies"):
                if cfg.get("serien_movies_path", "").strip():
                    p = Path(cfg["serien_movies_path"])
                    p.mkdir(parents=True, exist_ok=True)
                    return p
                if cfg.get("serien_path", "").strip():
                    p = Path(cfg["serien_path"]) / "Filme"
                    p.mkdir(parents=True, exist_ok=True)
                    return p
            if cfg.get("serien_path", "").strip():
                p = Path(cfg["serien_path"])
                p.mkdir(parents=True, exist_ok=True)
                return p

        # Legacy Fallback
        if is_film and cfg.get("movies_path", "").strip():
            p = Path(cfg["movies_path"])
            p.mkdir(parents=True, exist_ok=True)
            return p
        if not is_film and cfg.get("series_path", "").strip():
            p = Path(cfg["series_path"])
            p.mkdir(parents=True, exist_ok=True)
            return p

    return download_dir()


def is_dedicated_movies_folder(content_type: str) -> bool:
    """Prüft ob ein dedizierter Film-Ordner aktiv ist."""
    if cfg.get("storage_mode") != "separate":
        return False
    if content_type == "anime":
        return bool(cfg.get("anime_separate_movies"))
    if content_type == "serie":
        return bool(cfg.get("serien_separate_movies"))
    return False
