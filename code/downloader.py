from database import (
    get_missing_german_episodes, 
    set_completion_status,
    get_series_title_from_db,
    get_series_url_from_db, 
    get_last_downloaded_episode,
    get_last_downloaded_season,
    get_last_downloaded_film,
    get_completion_status, 
    get_deutsch_completion_status,   
    set_missing_german_episodes,
    set_deutsch_completion, 
    set_last_downloaded_episode, 
    set_last_downloaded_film, 
    set_last_downloaded_season, 
    check_index_exist
             )

from html_request import (
    get_seasons_with_episode_count, 
    get_languages_for_episode, 
    get_episode_title
            )

from file_management import (
    move_and_rename_downloaded_file, 
    delete_old_non_german_version, 
    get_existing_file_path, 
    find_downloaded_file
            )

from url_builder import get_episode_url
from config import load_config
from logger import start_run_logging, stop_run_logging
import subprocess
import time
import re
from pathlib import Path
from typing import Optional, List, Dict

# ============================================
# Security & Validation
# ============================================

def validate_language(language: str) -> bool:
    """Validate language string against whitelist."""
    allowed_languages = {"German Dub", "English Dub", "German Sub", "English Sub"}
    return language in allowed_languages

def validate_path(path: str) -> bool:
    """Validate that path is safe and exists."""
    try:
        p = Path(path)
        return p.exists() and p.is_dir()
    except Exception:
        return False

def validate_url(url: str) -> bool:
    """Basic URL validation to prevent command injection."""
    # Allow only alphanumeric, hyphens, dots, slashes, colons for URLs
    return bool(re.match(r'^https?://[a-zA-Z0-9\-\./_:]+$', url))

def start_download_process(language: str, download_path: str, episode_url: str) -> bool:
    """
    Safely execute aniworld download command.
    All inputs are validated before execution.
    """
    try:
        # Validate all inputs
        if not validate_language(language):
            print(f"[ERROR] Invalid language: {language}")
            return False
        if not validate_path(download_path):
            print(f"[ERROR] Invalid download path: {download_path}")
            return False
        if not validate_url(episode_url):
            print(f"[ERROR] Invalid episode URL: {episode_url}")
            return False
        
        # Build command as list (no shell injection possible)
        cmd = [
            "aniworld",
            "--language", language,
            "-o", download_path,
            "--episode", episode_url
        ]
        
        print(f"[INFO] Starting download command: {' '.join(cmd)}")
        
        # Execute without shell on Windows with UTF-8 encoding
        result = subprocess.run(
            cmd,
            shell=False,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode == 0:
            time.sleep(5)  # Wait for filesystem
            
        return result.returncode == 0
        
    except Exception as error:
        print(f"[ERROR] Fehler beim Download: {error}")
        return False

# ============================================
# Helper Functions
# ============================================

def select_language(available_languages: List[str], preferred_languages: List[str]) -> Optional[str]:
    """Select the best available language based on preferences."""
    if available_languages == -1:
        return None
    
    for preferred in preferred_languages:
        if preferred in available_languages:
            return preferred
    return None

def should_skip_episode(season: int, episode: int, 
                        last_season: int, last_episode: int, last_film: int) -> bool:
    """Check if episode should be skipped based on download history."""
    # Skip if in an older season
    if season < last_season:
        return True
    
    # Skip films that were already downloaded
    if season == 0 and episode < last_film:
        return True
    
    # Skip episodes in the SAME season that were already downloaded
    if season == last_season and episode < last_episode:
        return True
    
    return False

def update_missing_german_list(db_id: int, missing_episodes: List[str]) -> None:
    """Update database with missing german episodes and completion status."""
    existing_missing = get_missing_german_episodes(db_id) or []
    combined = list(set(existing_missing + missing_episodes))
    
    if combined:
        set_missing_german_episodes(db_id, combined)
        set_deutsch_completion(db_id, False)
    else:
        set_deutsch_completion(db_id, True)

# ============================================
# Episode Download Operations
# ============================================

def download_episode(episode_url: str, language: str, download_path: str,
                     season: str, episode: str, config: dict, serien_url: str) -> bool:
    """
    Download a single episode and verify the result.
    Returns True if successful, False otherwise.
    """
    success = start_download_process(language, download_path, episode_url)
    if not success:
        return False
    
    # Verify download
    downloaded_file = find_downloaded_file(
        season=season, 
        episode=episode, 
        config=config, 
        url=serien_url
    )
    
    if downloaded_file is None:
        print(f"[ERROR] Download failed for S{int(season):02d}E{int(episode):03d}. No file found.")
        return False
    
    # Move and rename
    print(f"[VERIFY] File found: {get_episode_title(episode_url)}")
    move_and_rename_downloaded_file(
        serien_url=serien_url,
        season=season,
        episode=episode,
        language=language
    )
    
    return True

def process_episode_download(serien_url: str, season: str, episode: str,
                             languages: List[str], download_path: str, 
                             config: dict) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Process download for a single episode.
    Returns: (success, selected_language, episode_url)
    """
    # Check if file already exists
    if get_existing_file_path(serien_url, season, episode, config) is not None:
        print(f"[SKIP] Datei für S{int(season):02d}E{int(episode):03d} bereits vorhanden.")
        return False, None, None
    
    # Get episode info
    episode_url = get_episode_url(serien_url, season, episode)
    available_languages = get_languages_for_episode(episode_url)
    
    if available_languages == -1:
        print(f"[ERROR] Could not retrieve languages for episode: {episode_url}")
        return False, None, episode_url
    
    # Select language
    language = select_language(available_languages, languages)
    if language is None:
        print(f"[ERROR] No suitable language found for episode: {episode_url}")
        return False, None, episode_url
    
    # Download episode
    success = download_episode(
        episode_url, language, download_path,
        season, episode, config, serien_url
    )
    
    return success, language, episode_url

def update_download_progress(db_id: int, season: str, episode: str) -> None:
    """Update database with download progress."""
    season_int = int(season)
    episode_int = int(episode)
    
    if season_int == 0 or season.strip().lower() == "filme":
        set_last_downloaded_film(db_id, episode_int)
    
    set_last_downloaded_episode(db_id, season_int, episode_int)

def finalize_season(db_id: int, season: str) -> None:
    """Mark season as completed in database."""
    set_last_downloaded_season(db_id, int(season))

def download_and_track_episode(serien_url: str, season: str, episode: str,
                               languages: List[str], download_path: str,
                               config: dict, db_id: int,
                               missing_german_episodes: List[str],
                               track_missing: bool = True) -> bool:
    """
    Download an episode and track progress. Returns True if successful.
    
    :param track_missing: If True, adds episode_url to missing_german_episodes on failure
    """
    success, language, episode_url = process_episode_download(
        serien_url, season, episode, languages, download_path, config
    )
    
    if success:
        print(f"[OK] Download successful for S{int(season):02d}E{int(episode):03d}")
        update_download_progress(db_id, season, episode)
        
        if language and language != "German Dub" and episode_url:
            missing_german_episodes.append(episode_url)
        return True
    elif track_missing and episode_url and language != "German Dub":
        missing_german_episodes.append(episode_url)
    
    return False

# ============================================
# Mode-Specific Download Functions
# ============================================

def download_mode_default(db_id: int, title: str, serien_url: str, 
                         seasons_with_episode_count: Dict, config: dict) -> None:
    """Handle default download mode - download all missing episodes."""
    # Skip if already complete
    if get_completion_status(db_id) is True:
        print(f"[SKIP] Serie '{title}' bereits komplett heruntergeladen.")
        return
    
    languages = config.get('languages')
    download_path = config.get('download_path')
    
    if not languages or not download_path:
        print("[ERROR] Invalid configuration: languages or download_path missing.")
        return
    missing_german_episodes = []
    downloaded_episodes = 0
    
    # Get download progress
    last_film = get_last_downloaded_film(db_id)
    last_season = get_last_downloaded_season(db_id)
    last_episode = get_last_downloaded_episode(db_id)
    
    # Process each season and episode
    for season in seasons_with_episode_count:
        if int(season) < last_season:
            continue
            
        for episode in seasons_with_episode_count[season]:
            # Skip already downloaded
            if should_skip_episode(int(season), int(episode), last_season, last_episode, last_film):
                continue
            
            # Download episode
            success, language, episode_url = process_episode_download(
                serien_url, season, episode, languages, download_path, config
            )
            
            if success:
                print(f"[OK] Download successful for S{int(season):02d}E{int(episode):03d}")
                downloaded_episodes += 1
                update_download_progress(db_id, season, episode)
                
                # Track non-German episodes
                if language and language != "German Dub":
                    missing_german_episodes.append(episode_url)
            elif episode_url:
                # Track as missing German if language unavailable
                if language != "German Dub":
                    missing_german_episodes.append(episode_url)
        
        finalize_season(db_id, season)
    
    # Update completion status
    update_missing_german_list(db_id, missing_german_episodes)
    
    if downloaded_episodes > 0:
        set_completion_status(db_id, True)
    else:
        print(f"[INFO] Keine neuen Episoden heruntergeladen für Series {db_id}.")

def download_mode_german(db_id: int, title: str, serien_url: str,
                        seasons_with_episode_count: Dict, config: dict) -> None:
    """Handle german mode - replace non-German episodes with German versions."""
    # Skip if already complete
    if get_deutsch_completion_status(db_id) is True:
        print(f"[SKIP] Serie '{title}' bereits komplett auf Deutsch verfügbar.")
        return
    
    download_path = config.get('download_path')
    if not download_path:
        print("[ERROR] Invalid configuration: download_path missing.")
        return
    
    deutsch = "German Dub"
    missing_german_episodes = get_missing_german_episodes(db_id) or []
    
    # Process each season and episode
    for season in seasons_with_episode_count:
        for episode in seasons_with_episode_count[season]:
            episode_url = get_episode_url(serien_url, season, episode)
            
            # Only process episodes in missing list
            if episode_url not in missing_german_episodes:
                continue
            
            # Check if German is available
            available_languages = get_languages_for_episode(episode_url)
            if available_languages == -1:
                print(f"[ERROR] Could not retrieve languages for episode: {episode_url}")
                continue
            
            if deutsch not in available_languages:
                print(f"[SKIP] Episode {episode_url} noch nicht auf Deutsch verfügbar.")
                continue
            
            # Download German version
            success = start_download_process(deutsch, download_path, episode_url)
            if not success:
                continue
            
            # Delete old non-German version
            existing_file = get_existing_file_path(serien_url, season, episode, config)
            if existing_file:
                existing_file_str = str(existing_file)
                if any(tag in existing_file_str for tag in ['[Sub]', '[English Dub]', '[English Sub]']):
                    delete_old_non_german_version(serien_url, season, episode, config)
            
            # Move new German version
            move_and_rename_downloaded_file(serien_url, season, episode, deutsch)
            print(f"[OK] Download successful for episode {episode_url}")
            missing_german_episodes.remove(episode_url)
    
    # Update status
    set_missing_german_episodes(db_id, missing_german_episodes)
    if not missing_german_episodes:
        set_deutsch_completion(db_id, True)

def download_mode_check_missing(db_id: int, title: str, serien_url: str,
                               seasons_with_episode_count: Dict, config: dict) -> None:
    """Handle check-missing mode - verify and download missing episodes."""
    languages = config.get('languages')
    download_path = config.get('download_path')
    
    if not languages or not download_path:
        print(f"[ERROR] Invalid configuration: languages or download_path missing.")
        return
    missing_german_episodes = []
    
    # Process each season and episode
    for season in seasons_with_episode_count:
        for episode in seasons_with_episode_count[season]:
            # Check existing file
            existing_file = get_existing_file_path(serien_url, season, episode, config)
            if existing_file:
                print(f"[SKIP] Datei für S{int(season):02d}E{int(episode):03d} bereits vorhanden.")
                existing_file_str = str(existing_file)
                # Track if non-German
                if any(tag in existing_file_str for tag in ['[Sub]', '[English Dub]', '[English Sub]']):
                    missing_german_episodes.append(get_episode_url(serien_url, season, episode))
                continue
            
            # Download missing episode and track progress
            download_and_track_episode(
                serien_url, season, episode, languages, download_path,
                config, db_id, missing_german_episodes, track_missing=True
            )
        
        finalize_season(db_id, season)
    
    # Update missing German episodes
    if missing_german_episodes:
        set_missing_german_episodes(db_id, missing_german_episodes)

def download_mode_new(db_id: int, title: str, serien_url: str,
                     seasons_with_episode_count: Dict, config: dict) -> None:
    """Handle new mode - download only new episodes for completed series."""
    # Only process complete series
    if get_completion_status(db_id) is False:
        print(f"[SKIP] Serie '{title}' noch nicht komplett. Bitte zuerst 'default' ausführen.")
        return
    
    languages = config.get('languages')
    download_path = config.get('download_path')
    
    if not languages or not download_path:
        print(f"[ERROR] Invalid configuration: languages or download_path missing.")
        return
    missing_german_episodes = []
    
    # Get current progress
    last_season = get_last_downloaded_season(db_id)
    last_episode = get_last_downloaded_episode(db_id)
    last_film = get_last_downloaded_film(db_id)
    
    # Get available content
    last_available_season = max(seasons_with_episode_count.keys(), key=int)
    last_available_episode = 0
    if str(last_season) in seasons_with_episode_count:
        last_available_episode = max(seasons_with_episode_count[str(last_season)])
    
    last_available_film = 0
    if "0" in seasons_with_episode_count:
        last_available_film = max(seasons_with_episode_count["0"])
    elif "filme" in seasons_with_episode_count:
        last_available_film = max(seasons_with_episode_count["filme"])
    
    # Determine what to download
    download_seasons = []
    
    # New seasons
    if int(last_available_season) > last_season:
        print(f"[INFO] Neue Staffel(n) ab Staffel {last_available_season} gefunden.")
        for s in range(last_season + 1, int(last_available_season) + 1):
            if str(s) in seasons_with_episode_count:
                download_seasons.append(str(s))
    
    # New episodes in last season
    elif last_season == int(last_available_season) and int(last_available_episode) > last_episode:
        print(f"[INFO] Neue Episode(n) in Staffel {last_season} ab E{last_episode + 1}.")
        download_seasons.append(str(last_season))
    
    # New films
    if int(last_available_film) > last_film:
        print(f"[INFO] Neue(r) Film(e) gefunden (Film {last_film + 1} bis {last_available_film}).")
        if "0" in seasons_with_episode_count:
            download_seasons.append("0")
        elif "filme" in seasons_with_episode_count:
            download_seasons.append("filme")
    
    # Validation warnings
    if int(last_available_season) < last_season:
        print(f"[WARN] Letzte Staffel {last_season} höher als verfügbar {last_available_season}.")
        return
    
    if not download_seasons:
        print(f"[INFO] Keine neuen Episoden für '{title}' gefunden.")
        return
    
    # Download new content
    for season in download_seasons:
        for episode in seasons_with_episode_count[season]:
            # Skip already downloaded
            if season == str(last_season) and int(episode) <= last_episode:
                continue
            if (season == "0" or season.lower() == "filme") and int(episode) <= last_film:
                continue
            
            # Check if exists
            if get_existing_file_path(serien_url, season, episode, config):
                print(f"[SKIP] Datei für S{int(season):02d}E{int(episode):03d} bereits vorhanden.")
                continue
            
            # Download episode and track progress
            download_and_track_episode(
                serien_url, season, episode, languages, download_path,
                config, db_id, missing_german_episodes, track_missing=False
            )
        
        finalize_season(db_id, season)
    
    # Update missing German episodes
    if missing_german_episodes:
        update_missing_german_list(db_id, missing_german_episodes)

# ============================================
# Main Download Function
# ============================================

def download(mode: str = "default"):
    """
    Main coordinator for download process.
    Supported modes: "default" | "german" | "new" | "check-missing"
    """
    # Validate mode
    valid_modes = ["default", "german", "new", "check-missing"]
    if mode not in valid_modes:
        raise ValueError(f"Ungültiger Modus '{mode}'. Erlaubt: {', '.join(valid_modes)}")
    
    start_run_logging()
    
    try:
        # Load configuration
        config = load_config()
        if not config:
            raise Exception("Fehler beim Laden der Konfiguration. Prüfen Sie config.json.")
        
        # Print header
        header = f"|| Starting download {mode} ||"
        print("=" * len(header))
        print(header)
        print("=" * len(header))
        
        # Check if database has entries
        if not check_index_exist(1):
            print("[INFO] Keine Serien in der Datenbank gefunden. Bitte fügen Sie zuerst Serien hinzu.")
            return
        
        # Mode dispatcher map
        mode_handlers = {
            "default": download_mode_default,
            "german": download_mode_german,
            "check-missing": download_mode_check_missing,
            "new": download_mode_new
        }
        
        mode_handler = mode_handlers[mode]
        
        # Process each series in database
        index = 1
        while check_index_exist(index):
            db_id = index
            
            try:
                # Get series info
                title = get_series_title_from_db(db_id)
                serien_url = get_series_url_from_db(db_id)
                
                # Print series header
                series_header = f"|| Starting download for series: {title} ||"
                print("=" * len(series_header))
                print(series_header)
                print("=" * len(series_header))
                
                # Get seasons and episodes
                seasons_with_episode_count = get_seasons_with_episode_count(serien_url)
                if not seasons_with_episode_count or seasons_with_episode_count == -1:
                    print(f"[ERROR] Could not retrieve seasons/episodes for: {title}")
                    index += 1
                    continue
                
                # Delegate to mode-specific handler
                mode_handler(db_id, title, serien_url, seasons_with_episode_count, config)
                
            except Exception as e:
                print(f"[ERROR] Error processing series ID {db_id}: {e}")
            
            index += 1
    
    except Exception as e:
        print(f"[ERROR] Error during download process: {e}")
    
    finally:
        stop_run_logging()
