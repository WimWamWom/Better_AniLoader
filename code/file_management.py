from pathlib import Path
from typing import Optional
import re
from html_request import get_episode_title, get_series_title
from config import load_config
from url_builder import get_episode_url
from database import get_folder_name_from_db, set_folder_name_in_db, get_db_id_by_url

# ============================================================================
# Dateinamen und Pfade generieren
# ============================================================================


def get_folder_path(staffel: str, url: str) -> str:
    """
        Erhalten des Basisordners für eine Staffel oder einen Film basierend auf der URL und Staffelnummer.
    
    :param staffel: Description
    :type staffel: str
    :param url: Description
    :type url: str
    :return: Description
    :rtype: str
    """
    config = load_config()
    if not config:  
        print("Fehler beim Laden der Konfiguration.")
        exit(1)
    STORAGE_MODE = config.get('storage_mode')
    DOWNLOAD_PATH = config.get('download_path')
    SERIES_PATH = config.get('series_path')
    ANIME_PATH = config.get('anime_path')
    MOVIES_PATH = config.get('movies_path')
    SERIEN_MOVIES_PATH = config.get('serien_movies_path')
    ANIME_MOVIES_PATH = config.get('anime_movies_path')
    ANIME_SEPARATE_MOVIES = config.get('anime_separate_movies')
    SERIEN_SEPARATE_MOVIES = config.get('serien_separate_movies')
    DEDICATED_MOVIES_FOLDER = config.get('dedicated_movies_folder')

    
    if STORAGE_MODE == "standard":
        return DOWNLOAD_PATH
    
    if STORAGE_MODE == "standard":
        return DOWNLOAD_PATH

    elif STORAGE_MODE == "separate":
        if "https://s.to/" in url:
            if staffel.strip().lower() == "0" or staffel.strip().lower() == "filme":
                if DEDICATED_MOVIES_FOLDER:
                    return MOVIES_PATH
                elif SERIEN_SEPARATE_MOVIES:
                    return SERIEN_MOVIES_PATH
                else:
                    return SERIES_PATH
            else:
                return SERIES_PATH

        elif "https://aniworld.to/" in url:
            if staffel.strip().lower() == "filme" or staffel.strip().lower() == "0":
                if DEDICATED_MOVIES_FOLDER:  
                    return MOVIES_PATH
                elif ANIME_SEPARATE_MOVIES:
                    return ANIME_MOVIES_PATH
                else:
                    return ANIME_PATH
            else:
                return ANIME_PATH

    print(f"Ungültige URL oder Staffel: {url} Staffel: {staffel}. Rückfall auf Standard-Downloadpfad.")       
    return DOWNLOAD_PATH

def get_existing_file_path(serien_url: str, season: str, episode: str, config) -> Optional[Path]:
    """
    Erhalen des vollständigen Pfads für eine Episode oder einen Film basierend auf der Serien-URL, Staffel, Episode.
    
    Diese Funktion sucht nach einer vorhandenen Datei und berücksichtigt dabei verschiedene Sprachsuffixe.
    Verwendet den in der Datenbank gespeicherten Ordnernamen (z.B. "Titel (2020) [tt1234567]").
    
    :param serien_url: Url zu der Serie/dem Anime
    :type serien_url: str
    :param season: Staffelnummer (0 für Filme)
    :type season: str
    :param episode: Episodennummer
    :type episode: str
    :return: Vollständiger Pfad zur vorhandenen Datei oder None, wenn keine Datei gefunden wurde.
    """
    
    folder_path = get_folder_path(season, serien_url)
    
    # Versuche zunächst den gespeicherten Ordnernamen aus der DB zu holen
    db_id = get_db_id_by_url(serien_url)
    stored_folder_name = None
    if db_id:
        stored_folder_name = get_folder_name_from_db(db_id)
    
    # Falls kein Ordnername gespeichert ist, verwende den Serien-Titel als Fallback
    if not stored_folder_name:
        stored_folder_name = get_series_title(serien_url)
        if not stored_folder_name:
            print(f"Fehler: Konnte Serien-Titel nicht abrufen für URL: {serien_url}")
            return None
    
    file_name = get_file_name(serien_url, season, episode)
    
    if config is None:
        config = load_config()
    if not config:
        print("Fehler beim Laden der Konfiguration.")
        return None
    #Für Filme könnte es je nach Einstellung direkt im Serienordner liegen oder in einem separaten Filme-Ordner. Daher müssen wir beide Möglichkeiten prüfen.
    if season.strip().lower() == "0" or season.strip().lower() == "filme":
        if config.get('dedicated_movies_folder') or config.get('serien_separate_movies') or config.get('anime_separate_movies'):
            target_folder = Path(folder_path) / file_name
        else:
            target_folder = Path(folder_path) / stored_folder_name / "Filme"
    else:
        target_folder = Path(folder_path) / stored_folder_name / f"Staffel {season}"
    
    if not target_folder.exists():
        return None
    
    suffixes = ["", "[Sub]", "[English Dub]", "[English Sub]"]
    extensions = [".mkv", ".mp4"]  # mkv zuerst, mp4 als Fallback
    
    for suffix in suffixes:
    # Suche nach Dateien mit diesem Suffix
        for ext in extensions:
            for test_file in target_folder.glob(f"*{file_name}*{suffix}*{ext}"):
                if test_file.is_file():
                    return test_file
    
    # Keine Datei gefunden
    return None

def get_file_name(serien_url: str, season: str, episode: str):

    if season.strip().lower() == "0" or season.strip().lower() == "filme":
        config = load_config()
        if not config:
            print("Fehler beim Laden der Konfiguration.")
            exit(1)
        
        episode_url = get_episode_url(serien_url, season, episode)
        title = get_episode_title(episode_url=episode_url)

        #Separater Filme Ordner
        if config.get('dedicated_movies_folder') or config.get('serien_separate_movies') or config.get('anime_separate_movies'):
            if title:
                file_name = f"{title}"
                return file_name
            else:
                series_title = get_series_title(serien_url)
                file_name = f"{series_title}"

        count= f"Film{int(episode):03d}"
        file_name = f"{count} - {title}"


    else:
        episode_url = get_episode_url(serien_url, season, episode)
        title = get_episode_title(episode_url=episode_url)
        count = f"S{int(season):02d}E{int(episode):03d}"
        file_name = f"{count} - {title}"

    return file_name


# ============================================================================
# DATEI-VERWALTUNG (Umbenennen, Verschieben, Löschen)
# ============================================================================

def find_downloaded_file(season: str, episode: str, config: dict, url: str) -> Optional[Path]:
    if config is None:
        config = load_config()
        if not config:
            print("Fehler beim Laden der Konfiguration.")
            return None
        
    titel = get_series_title(url)
    download_path = config.get('download_path')
    if not download_path:
        print("[ERROR] Download-Pfad nicht in der Konfiguration gefunden.")
        return None
    
    download_path_obj = Path(download_path)
    if not download_path_obj.exists():
        print(f"[ERROR] Download-Pfad existiert nicht: {download_path}")
        return None
    
    # Bestimme das Such-Muster (S01E05 oder Film001)
    if season.strip().lower() == "0" or season.strip().lower() == "filme":
        prefix = f"Movie{int(episode):03d}"
    else:
        prefix = f"S{int(season):02d}E{int(episode):03d}"
    
    # Suche zuerst direkt im Download-Pfad (mkv zuerst, dann mp4)
    for ext in [".mkv", ".mp4"]:
        for file in download_path_obj.glob(f"*{prefix}*{ext}"):
            if file.is_file():
                return file
    if titel is None:
        print(f"[ERROR] Konnte Serien-Titel nicht abrufen für URL: {url}")
        return None
    
    # Suche nach Ordner mit neuem aniworld-cli Format: "Titel (Jahr) [IMDB-Nummer]"
    # Regex-Pattern: Titel gefolgt von optionalem (Jahr) und [IMDB-ID]
    escaped_titel = re.escape(titel)
    pattern = re.compile(rf"^{escaped_titel}(\s*\(\d{{4}}\))?(\s*\[tt\d+\])?$", re.IGNORECASE)
    
    for folder in download_path_obj.iterdir():
        if folder.is_dir():
            # Prüfe ob Ordnername dem neuen Format entspricht
            if pattern.match(folder.name) or folder.name == titel:
                for ext in [".mkv", ".mp4"]:
                    for file in folder.glob(f"*{prefix}*{ext}"):
                        if file.is_file():
                            return file
    
    # Falls nicht gefunden, suche im einfachen Serien-Titel-Unterordner (Legacy)
    serie_folder = Path(Path(download_path_obj) / Path(titel))
    if serie_folder.exists():
        for ext in [".mkv", ".mp4"]:
            for file in serie_folder.glob(f"*{prefix}*{ext}"):
                if file.is_file():
                    return file
    
    return None

def move_downloaded_file(serien_url: str, season: str, episode: str, config: dict) -> Optional[Path]:
    # Konfiguration laden falls nicht übergeben
    if config is None:
        config = load_config()
        if not config:
            print("[ERROR] Fehler beim Laden der Konfiguration.")
            return None

    source_file = find_downloaded_file(season, episode, config, serien_url)
    
    if not source_file:
        print(f"[ERROR] Keine heruntergeladene Datei gefunden für Season {season}, Episode {episode}")
        return None
    
    print(f"[OK] Datei gefunden: {source_file.name}")
    
    # Ermittle den Quell-Ordnernamen (z.B. "Naruto (2002) [tt0409591]")
    download_path_str = config.get('download_path')
    if not download_path_str:
        print("[ERROR] Download-Pfad nicht in der Konfiguration gefunden.")
        return None
    download_path = Path(download_path_str)
    source_folder_name = source_file.parent.name
    
    # Prüfe ob der Ordnername dem aniworld-cli Format entspricht (Titel mit Jahr/IMDB)
    # und nicht der Download-Root-Ordner ist
    if source_file.parent != download_path:
        # Ermittle DB-ID und prüfe ob folder_name bereits gespeichert ist
        db_id = get_db_id_by_url(serien_url)
        if db_id:
            stored_folder_name = get_folder_name_from_db(db_id)
            if not stored_folder_name:
                # Speichere den gefundenen Ordnernamen in der Datenbank
                set_folder_name_in_db(db_id, source_folder_name)
                print(f"[DB] Ordnername gespeichert: {source_folder_name}")
                stored_folder_name = source_folder_name
        else:
            stored_folder_name = source_folder_name
    else:
        # Datei liegt direkt im Download-Ordner, verwende Serien-Titel
        stored_folder_name = get_series_title(serien_url)
    
    # Bestimme den Zielordner
    folder_path = get_folder_path(season, serien_url)
    
    if not stored_folder_name:
        print("[ERROR] Konnte Ordnernamen nicht ermitteln")
        return None
    
    if season.strip().lower() == "0" or season.strip().lower() == "filme":
        if config.get('dedicated_movies_folder') or config.get('serien_separate_movies') or config.get('anime_separate_movies'):
            target_folder = Path(folder_path)
        else:
            target_folder = Path(folder_path) / stored_folder_name / "Filme"
    else:
        target_folder = Path(folder_path) / stored_folder_name / f"Staffel {season}"
    
    target_folder.mkdir(parents=True, exist_ok=True)
    
    # Zieldatei-Pfad
    destination = target_folder / source_file.name
    
    # Verschiebe die Datei
    try:
        source_file.rename(destination)
        print(f"[OK] Verschoben: {source_file.name} → {target_folder}")
        return destination
    except Exception as e:
        print(f"[ERROR] Fehler beim Verschieben: {e}")
        return None

def rename_file_with_title(file_path: Path, serien_url: str, season: str, episode: str, language: str, config: dict) -> Optional[Path]:
    if not file_path.exists():
        print(f"[ERROR] Datei existiert nicht: {file_path}")
        return None
    
    # Hole den Episodentitel
    episode_url = get_episode_url(serien_url, season, episode)
    title = get_episode_title(episode_url)
    
    if not title:
        print("[ERROR] Konnte Episodentitel nicht abrufen")
        return None
    
    # Bestimme den Sprachsuffix
    language_suffix = {
        "German Dub": "",
        "German Sub": " [Sub]",
        "English Dub": " [English Dub]",
        "English Sub": " [English Sub]"
    }.get(language, "")
    
    if season.strip().lower() == "0" or season.strip().lower() == "filme":
        # Film
        base_name = f"Film{int(episode):03d}"
    else:
        # Normale Episode
        base_name = f"S{int(season):02d}E{int(episode):03d}"
    
    # Kompletter neuer Dateiname (behält originale Dateierweiterung bei)
    original_extension = file_path.suffix  # z.B. ".mkv" oder ".mp4"
    new_filename = f"{base_name} - {title}"
    if language_suffix:
        new_filename += language_suffix
    new_filename += original_extension
    
    new_file_path = file_path.parent / new_filename

    if file_path == new_file_path:
        print(f"[INFO] Datei hat bereits den richtigen Namen: {new_filename}")
        return new_file_path
    
    # Umbenennen
    try:
        file_path.rename(new_file_path)
        print(f"[OK] Umbenannt: {file_path.name} → {new_filename}")
        return new_file_path
    except Exception as e:
        print(f"[ERROR] Fehler beim Umbenennen: {e}")
        return None

def move_and_rename_downloaded_file(serien_url: str, season: str, episode: str, language: str) -> Optional[Path]:
    config = load_config()
    if not config:
        print("[ERROR] Fehler beim Laden der Konfiguration.")
        return None
    
    moved_file = move_downloaded_file(serien_url, season, episode, config)
    if not moved_file:
        return None
    
    final_file = rename_file_with_title(moved_file, serien_url, season, episode, language, config)
    if not final_file:
        return None
    
    print(f"[OK] Erfolgreich verarbeitet: {final_file.name}")
    return final_file


def delete_old_non_german_version(serien_url: str, season: str, episode: str, config: dict) -> bool:
    """
    Löscht alte nicht-deutsche Versionen einer Episode.
    
    Args:
        serien_url: URL zur Serie/zum Anime
        season: Staffelnummer
        episode: Episodennummer
    """
    file_path = get_existing_file_path(serien_url, season, episode, config)
    if file_path is None:
        print(f"[WARN] Keine vorhandene Datei gefunden für Season {season}, Episode {episode}")
        return False
    if file_path.is_file():
        try:
            file_path.unlink()
            print(f"[OK] Alte Datei gelöscht: {file_path.name}")
            return True
        except Exception as e:
            print(f"[ERROR] Fehler beim Löschen der alten Datei: {e}")
            return False
    return False


def move_file(source: Path, destination: Path) -> bool:
    """
    Verschiebt eine Datei sicher von Quelle zu Ziel.
    
    Args:
        source: Quell-Dateipfad
        destination: Ziel-Dateipfad
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    try:
        # Stelle sicher, dass der Zielordner existiert
        destination.parent.mkdir(parents=True, exist_ok=True)
        
        # Verschiebe die Datei
        source.rename(destination)
        print(f"✓ Verschoben: {source.name} → {destination}")
        return True
    except Exception as e:
        print(f"✗ Fehler beim Verschieben: {e}")
        return False

