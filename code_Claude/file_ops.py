"""
file_ops.py – Dateisystem-Operationen für AniLoader.

Zuständig für:
  - Titel-Sanierung (Windows-kompatibel)
  - Pfadlängen-Check (MAX_PATH)
  - Prüfung ob Episode bereits heruntergeladen
  - Löschen alter nicht-deutscher Versionen
  - Umbenennen heruntergeladener Dateien
  - Freier-Speicher-Prüfung
"""

import os
import re
import shutil
from pathlib import Path

from config import MAX_PATH, download_dir
from logger import log


# ═══════════════════════════════════════════════════════════════════════════════
#  Titel-Sanierung
# ═══════════════════════════════════════════════════════════════════════════════

def sanitize_title(name: str) -> str:
    """Entfernt Windows-verbotene Zeichen aus Ordner-/Dateinamen."""
    return re.sub(r'[<>:"/\\|?*]', "", name)


def sanitize_episode_title(name: str) -> str:
    """Saniert Episodentitel und entfernt 'Movie'-Varianten."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s*\[?The\s+Movie\]?\s*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*\[?Movie\]?\s*", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  Pfadlänge
# ═══════════════════════════════════════════════════════════════════════════════

def check_length(dest_folder: Path, base_name: str, title: str, lang_suffix: str,
                 ext: str = ".mp4") -> str:
    """Kürzt den Titel falls der Gesamtpfad MAX_PATH überschreitet."""
    simulated = base_name
    if title:
        simulated += f" - {title}"
    if lang_suffix:
        simulated += f" {lang_suffix}"
    simulated += ext

    if len(str(dest_folder / simulated)) <= MAX_PATH:
        return title

    reserved = len(str(dest_folder)) + len(base_name) + len(ext) + len(lang_suffix) + 10
    max_len = max(0, MAX_PATH - reserved)
    shortened = title[:max_len]
    if shortened != title:
        log(f"[INFO] Titel gekürzt: '{title}' -> '{shortened}'")
    return shortened


# ═══════════════════════════════════════════════════════════════════════════════
#  Speicherplatz
# ═══════════════════════════════════════════════════════════════════════════════

def free_space_gb(path: str | Path) -> float:
    """Gibt verfügbaren Speicherplatz in GB zurück."""
    total, used, free = shutil.disk_usage(str(path))
    return round(free / (1024 ** 3), 1)


# ═══════════════════════════════════════════════════════════════════════════════
#  Episode bereits vorhanden?
# ═══════════════════════════════════════════════════════════════════════════════

def _folder_variants(series_folder: str) -> list[str]:
    """Gibt Ordner-Varianten zurück (. ↔ # Tausch)."""
    variants = [series_folder]
    if "." in series_folder:
        variants.append(series_folder.replace(".", "#"))
    elif "#" in series_folder:
        variants.append(series_folder.replace("#", "."))
    return variants


def episode_already_downloaded(series_folder: str, season: int, episode: int,
                                in_dedicated_movies: bool = False) -> bool:
    """Prüft ob die Episode/der Film bereits als .mp4 existiert."""
    folders = _folder_variants(series_folder)

    if season > 0:
        pattern = f"S{season:02d}E{episode:03d}"
    else:
        series_name = Path(series_folder).name
        pattern_film = f"{series_name} - Film{episode:02d}" if in_dedicated_movies else f"Film{episode:02d}"
        pattern_movie = f"Movie{episode:02d}"

    if season == 0 and in_dedicated_movies:
        parent = Path(series_folder).parent
        if parent.exists():
            for f in parent.rglob("*.mp4"):
                low = f.name.lower()
                if pattern_film.lower() in low or pattern_movie.lower() in low:
                    return True
    else:
        for folder in folders:
            if not os.path.exists(folder):
                continue
            for f in Path(folder).rglob("*.mp4"):
                low = f.name.lower()
                if season > 0:
                    if pattern.lower() in low:
                        return True
                else:
                    if (pattern_film.lower() in low or
                            pattern_movie.lower() in low):
                        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
#  Alte nicht-deutsche Versionen löschen
# ═══════════════════════════════════════════════════════════════════════════════

def delete_old_non_german(series_folder: str, season: int, episode: int,
                          in_dedicated_movies: bool = False) -> None:
    """Löscht [Sub]/[English Dub]/[English Sub]-Dateien für die gegebene Episode."""
    base = Path(series_folder)

    if season > 0:
        pattern = f"S{season:02d}E{episode:03d}"
    else:
        series_name = base.name
        pattern = f"{series_name} - Film{episode:02d}"
        pattern_movie = f"Movie{episode:02d}"
        pattern_film_old = f"Film{episode:02d}"

    if season == 0 and in_dedicated_movies and base.exists():
        base = base.parent

    for f in base.rglob("*.mp4"):
        low = f.name.lower()
        if season > 0:
            matches = pattern.lower() in low
        else:
            matches = (pattern.lower() in low or
                       pattern_movie.lower() in low or
                       pattern_film_old.lower() in low)

        if matches and ("[sub]" in low or "[english dub]" in low or "[english sub]" in low):
            try:
                os.remove(f)
                log(f"[DEL] Alte Version gelöscht: {f.name}")
            except Exception as e:
                log(f"[FEHLER] Konnte Datei nicht löschen: {f.name} -> {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Heruntergeladene Datei umbenennen
# ═══════════════════════════════════════════════════════════════════════════════

LANG_SUFFIX = {
    "German Dub": "",
    "German Sub": "[Sub]",
    "English Dub": "[English Dub]",
    "English Sub": "[English Sub]",
}


def rename_downloaded(series_folder: str, season: int, episode: int,
                      title: str | None, language: str,
                      in_dedicated_movies: bool = False) -> bool:
    """Sucht die heruntergeladene Datei und benennt sie nach Schema um."""
    lang_suffix = LANG_SUFFIX.get(language, "")
    folders = _folder_variants(series_folder)

    # Datei finden
    if season > 0:
        search_pattern = f"S{season:02d}E{episode:03d}"
        matching = []
        for folder in folders:
            if os.path.exists(folder):
                matching.extend(
                    f for f in Path(folder).rglob("*.mp4")
                    if search_pattern.lower() in f.name.lower()
                )
        if not matching:
            log(f"[WARN] Keine Datei gefunden für {search_pattern} in {folders}")
            return False
        file_to_rename = matching[0]
        pat = search_pattern
    else:
        # Filme: suche Movie/Episode Pattern
        search_pats = [
            f"Movie {episode:03d}", f"Movie{episode:03d}",
            f"Episode {episode:03d}", f"Episode{episode:03d}",
        ]
        matching = []
        for folder in folders:
            if os.path.exists(folder):
                for f in Path(folder).rglob("*.mp4"):
                    low = f.name.lower()
                    if any(sp.lower() in low for sp in search_pats):
                        matching.append(f)
                        break
        if not matching:
            log(f"[WARN] Keine Datei gefunden für Film/Movie/Episode {episode} in {folders}")
            return False
        file_to_rename = matching[0]

        if in_dedicated_movies:
            series_name = Path(series_folder).name
            pat = f"{series_name} - Film{episode:02d}"
        else:
            pat = f"Film{episode:02d}"

    safe_title = sanitize_episode_title(title) if title else ""

    # Zielordner bestimmen
    if season == 0 and in_dedicated_movies:
        parent = Path(series_folder).parent
        dest_folder = (parent / safe_title) if safe_title else (Path(series_folder) / f"Film{episode:02d}")
    elif season == 0:
        dest_folder = Path(series_folder) / "Filme"
    else:
        dest_folder = Path(series_folder) / f"Staffel {season}"

    dest_folder.mkdir(parents=True, exist_ok=True)
    safe_title = check_length(dest_folder, pat, safe_title, lang_suffix)

    new_name = pat
    if safe_title:
        new_name += f" - {safe_title}"
    if lang_suffix:
        new_name += f" {lang_suffix}"
    new_name += ".mp4"

    new_path = dest_folder / new_name
    try:
        shutil.move(str(file_to_rename), str(new_path))
        log(f"[OK] Umbenannt: {file_to_rename.name} -> {new_name}")

        # Leere Serien-Ordner aufräumen bei dedizierten Film-Ordnern
        if season == 0 and in_dedicated_movies:
            for folder in folders:
                fp = Path(folder)
                if fp.exists() and fp.is_dir():
                    try:
                        if not any(fp.iterdir()):
                            fp.rmdir()
                            log(f"[CLEANUP] Leerer Ordner gelöscht: {folder}")
                    except Exception as e:
                        log(f"[CLEANUP-WARN] Konnte Ordner nicht löschen: {folder} -> {e}")
        return True
    except Exception as e:
        log(f"[FEHLER] Umbenennen fehlgeschlagen: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  Prüfung ob Datei deutsch/nicht-deutsch ist
# ═══════════════════════════════════════════════════════════════════════════════

def check_file_language(search_path: Path, pattern: str) -> tuple[bool, bool]:
    """
    Sucht in search_path nach Dateien die zum Pattern passen.
    Gibt (is_german, is_non_german) zurück.
    """
    is_german = False
    is_non_german = False
    if search_path.exists():
        for f in search_path.rglob("*.mp4"):
            low = f.name.lower()
            if pattern.lower() in low:
                if "[sub]" in low or "[english" in low:
                    is_non_german = True
                else:
                    is_german = True
                break
    return is_german, is_non_german
