import re
from pathlib import Path
from typing import Optional
from html_request import get_episode_title, get_series_title
from config import load_config
from url_build import get_episode_url

# ============================================================================
# Dateinamen und Pfade generieren
# ============================================================================


def get_folder_path(staffel: str, url: str) -> str:
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

def get_file_path(serien_url: str, season: str, episode: str, new_german: bool = False):
    folder_path = get_folder_path(season, serien_url)
    series_title = get_series_title(serien_url)

    if not series_title:
        print(f"Fehler: Konnte Serien-Titel nicht abrufen für URL: {serien_url}")
        raise Exception("Serien-Titel konnte nicht abgerufen werden.")
    
    file_name = get_file_name(serien_url, season, episode)



    if season.strip().lower() == "0" or season.strip().lower() == "filme":
        config = load_config()
        if not config:
            print("Fehler beim Laden der Konfiguration.")
            exit(1)

        if config.get('dedicated_movies_folder') or config.get('serien_separate_movies') or config.get('anime_separate_movies'):
            file_path = folder_path + "/" + file_name + "/" + f"{file_name}.mp4"
        else:
            file_path = folder_path + "/" + series_title + "/" + "Filme" + "/" + file_name + ".mp4"
    else:
        file_path = folder_path+ "/" + series_title+ "/" + f"Staffel {season}"+ "/" + file_name +".mp4"

    return Path(file_path)

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
# DATEI-ÜBERPRÜFUNG
# ============================================================================

def check_if_file_allready_exists(serien_url: str, season: str, episode: str) -> bool:
    file_path = get_file_path(serien_url, season, episode)
    if file_path.is_file():
        return True
    file_path = get_file_path(serien_url, season, episode, new_german=True)
    if file_path.is_file():
        return True
    return False

def check_if_download_complete(serien_url: str, season: str, episode: str) -> bool:
    config = load_config()
    if not config:
        print("Fehler beim Laden der Konfiguration.")
        return False
    download_path = config.get('download_path')
    base_path = Path(download_path)
    # Erzeuge das Namensmuster (SXXEXX oder FilmXXX)
    if season.strip().lower() == "0" or season.strip().lower() == "filme":
        prefix = f"Film{int(episode):03d}"
    else:
        prefix = f"S{int(season):02d}E{int(episode):03d}"
    # Suche nach einer Datei, die mit dem Prefix beginnt und auf .mp4 endet
    for file in base_path.glob(f"{prefix}*.mp4"):
        if file.is_file():
            return True
    return False

# ============================================================================
# DATEI-VERWALTUNG (Umbenennen, Verschieben, Löschen)
# ============================================================================

def rename_downloaded_file(
    series_folder: Path,
    season: int,
    episode: int,
    title: str,
    language: str,
    in_dedicated_movies_folder: bool = False
) -> Optional[Path]:
    """
    Benennt eine heruntergeladene Datei um, basierend auf Staffel, Episode, Titel und Sprache.
    
    Args:
        series_folder: Hauptordner der Serie/des Animes
        season: Staffelnummer (0 für Filme)
        episode: Episodennummer
        title: Episoden- oder Filmtitel
        language: Sprache der Episode (z.B. "German Dub", "English Sub")
        in_dedicated_movies_folder: True, wenn Filme separat gespeichert werden
    
    Returns:
        Neuer Pfad der umbenannten Datei oder None bei Fehler
    """
    # Implementierung hier

def delete_old_non_german_version(serien_url: str, season: str, episode: str) :
    file_path = get_file_path(serien_url, season, episode)
    if file_path.is_file():
        try:
            file_path.unlink()
            print(f"✓ Alte Datei gelöscht: {file_path.name}")
        except Exception as e:
            print(f"✗ Fehler beim Löschen der alten Datei: {e}")
    file_path = get_file_path(serien_url, season, episode, new_german=True)
    if file_path.is_file():
        try:
            file_path.unlink()
            print(f"✓ Alte Datei gelöscht: {file_path.name}")
        except Exception as e:
            print(f"✗ Fehler beim Löschen der alten Datei: {e}")


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

