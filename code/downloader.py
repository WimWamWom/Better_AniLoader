from database import check_index_exist, get_missing_german_episodes, set_completion_status, get_series_title_from_db, get_series_url_from_db, get_last_downloaded_episode, get_last_downloaded_season, get_last_downloaded_film, get_completion_status, get_deutsch_completion_status, set_deutsch_completion, set_last_downloaded_episode, set_last_downloaded_film, set_last_downloaded_season, set_missing_german_episodes
from html_request import get_seasons_with_episode_count, get_languages_for_episode, get_episode_title
from file_management import move_and_rename_downloaded_file, delete_old_non_german_version, get_existing_file_path, find_downloaded_file
from url_builder import get_episode_url
from config import load_config
from logger import start_run_logging, stop_run_logging
import subprocess
import time

def start_download_process(cmd_command: str) -> bool:
    try:
        # Set Windows console to UTF-8 (65001) before running aniworld
        # Let output go directly to console instead of capturing
        utf8_cmd = f"chcp 65001 >nul & {cmd_command}"
        result = subprocess.run(utf8_cmd, shell=True)
        # Wait for file system to catch up after download and for .part files to be finalized
        # Check for up to 30 seconds if .part files are being written
        if result.returncode == 0:
            time.sleep(5)  # Give some initial time for file operations
        return result.returncode == 0
    except Exception as error:
        print(f"Fehler beim Download: {error}")
        return False
    except Exception as error:
        print(f"Fehler beim Download: {error}")
        return False




def download(mode: str = "default"):
    """
    Startet den Download-Prozess basierend auf dem angegebenen Modus.
    - mode: "default" | "german" | "new" | "check-missing"
    """    
    start_run_logging()
    
    try:
        if mode not in ["default", "german", "new", "check-missing"]:
            raise ValueError("Ungültiger Modus. Erlaubte Werte: 'default', 'german', 'new', 'check-missing'.")
        
        config = load_config()
        if not config: 
            raise Exception("Fehler beim Laden der Konfiguration. Bitte überprüfen Sie die config.json.")
        LANGUAGES = config.get('languages')
        DOWNLOAD_PATH = config.get('download_path')
        start_download_msg = (f"|| Starting download {mode}  ||")
        print("=" * len(start_download_msg))
        print(start_download_msg)
        print("=" * len(start_download_msg))
        
        
        next_index_exist = False
        index = 1
        if check_index_exist(index):
            next_index_exist = True
        else:
            print("[INFO] Keine Serien in der Datenbank gefunden. Bitte füge zuerst Serien hinzu.")
            return
        while next_index_exist:
            id = index
            try:
                title = get_series_title_from_db(id)
                serien_url = get_series_url_from_db(id)
                start_serie_msg = (f"|| Starting download for series: {title} ||")
                print("=" * len(start_serie_msg))
                print(start_serie_msg)
                print("=" * len(start_serie_msg))
                
                seasons_with_episode_count = get_seasons_with_episode_count(serien_url)
                if not seasons_with_episode_count or seasons_with_episode_count == -1:
                    print(f"[ERROR] Could not retrieve seasons or episodes for series: {title}. Got: {seasons_with_episode_count}")
                    continue
        

    #================================================
    #Default Mode
    #================================================

                if mode == "default":
                    missing_german_episodes = []
                    downloaded_episodes = 0  # Counter für heruntergeladene Episoden
                    
                    # Überprüfe, ob die Serie bereits komplett heruntergeladen wurde
                    if get_completion_status(id) == True:
                        print(f"[SKIP] Serie '{title}' bereits komplett heruntergeladen.")
                        continue

                    
                    if seasons_with_episode_count == -1:
                        raise Exception("Error retrieving seasons or episodes.")
                    
                    last_downloaded_film = get_last_downloaded_film(id)
                    last_downloaded_season = get_last_downloaded_season(id)
                    last_downloaded_episode = get_last_downloaded_episode(id)

                    for season in seasons_with_episode_count:
                        # Überspringe bereits heruntergeladene Staffeln
                        if (int(season) < last_downloaded_season): 
                            continue
                        for episode in seasons_with_episode_count[season]:
                            # Überspringe bereits heruntergeladene Episoden (inklusive Filme in Staffel 0)
                            if int(episode) < last_downloaded_episode or (int(episode) < last_downloaded_film and int(season) == 0):
                                continue
                            
                            if get_existing_file_path(serien_url, season, episode, config) != None:
                                print(f"[SKIP] Datei für S{int(season):02d}E{int(episode):03d} bereits vorhanden. ")
                                continue
                            
                            episode_url = get_episode_url(serien_url, season, episode)
                            sprachen = get_languages_for_episode(episode_url)
                            if sprachen != -1:
                                if LANGUAGES[0] in sprachen:
                                    sprache = LANGUAGES[0]
                                elif LANGUAGES[1] in sprachen:
                                    sprache = LANGUAGES[1]
                                elif LANGUAGES[2] in sprachen:
                                    sprache = LANGUAGES[2]
                                elif LANGUAGES[3] in sprachen:
                                    sprache = LANGUAGES[3]
                                else:
                                    return -1
                                if sprache != "German Dub":
                                        missing_german_episodes.append(episode_url)
                                cmd = str(f'aniworld --language "{sprache}" -o "{DOWNLOAD_PATH}" --episode {episode_url}')
                                try:
                                    print(f"[INFO] Starting download command: {cmd}")
                                    succes = start_download_process(cmd)
                                    if succes:
                                        print(f"[OK] Download successful for S{int(season):02d}E{int(episode):03d}")
                                        downloaded_episodes += 1
                                except Exception as e:
                                    print(f"[ERROR] Error during download process: {e}")
                                    continue  
                            else:
                                print(f"[ERROR] Could not retrieve languages for episode: {episode_url}")

                            #get_output_from_download_process(cmd)
                            downloaded_file = find_downloaded_file(season=season, episode=episode, config=config, url=serien_url)
                            if downloaded_file == None:
                                print(f"[ERROR] Download failed for S{int(season):02d}E{int(episode):03d}. No file found after download process.")
                                continue

                            elif downloaded_file is not None:
                                print(f"[VERIFY] File found: {get_episode_title(episode_url)}")
                                move_and_rename_downloaded_file(serien_url=serien_url, season=season, episode=episode, language=sprache)

                            
                            # Nach Abschluss des Downloads die letzte heruntergeladene Episode aktualisieren (inklusive Filme in Staffel 0)
                            if int(season) == 0 or season.strip().lower() == "filme":
                                set_last_downloaded_film(id, int(episode))
                            set_last_downloaded_episode(id, int(season), int(episode))

                        # Nach Abschluss einer Staffel die letzte heruntergeladene Staffel aktualisieren      
                        set_last_downloaded_season(id, int(season))


                    # Nach Abschluss aller Downloads den Status der deutschen Vollständigkeit aktualisieren
                    allready_missing_german_episodes = get_missing_german_episodes(id)
                    if len(missing_german_episodes) == 0 and (allready_missing_german_episodes == None or len(allready_missing_german_episodes) == 0):
                        set_deutsch_completion(id, True)
                    else:
                        set_deutsch_completion(id, False)
                        if allready_missing_german_episodes != None or len(allready_missing_german_episodes) != 0:
                            missing_german_episodes = (allready_missing_german_episodes or []) + missing_german_episodes
                            if missing_german_episodes:
                                set_missing_german_episodes(id, missing_german_episodes)
            
                    # Nur als komplett markieren, wenn mindestens eine Episode heruntergeladen wurde
                    if downloaded_episodes > 0:
                        set_completion_status(id, True)
                    else:
                        print(f"[INFO] Keine neuen Episoden heruntergeladen für Series {id}. Status wird NICHT auf komplett gesetzt.")

    #================================================
    #German Mode
    #================================================
                            
                elif mode == "german":
                    if get_deutsch_completion_status(id) == True:
                        print(f"[SKIP] Serie '{title}' bereits komplett auf Deutsch verfügbar.")
                        continue           
                    deutsch = "German Dub"
                    missing_german_episodes = get_missing_german_episodes(id)
                    for season in seasons_with_episode_count:
                        for episode in seasons_with_episode_count[season]:
                            episode_url = get_episode_url(serien_url, season, episode)
                            if episode_url in missing_german_episodes:
                                sprachen = get_languages_for_episode(episode_url)
                                if sprachen == -1:
                                    print(f"[ERROR] Could not retrieve languages for episode: {episode_url}")
                                    continue
                                if deutsch not in sprachen:
                                    print(f"[SKIP] Episode {episode_url} noch nicht auf Deutsch verfügbar.")
                                    continue

                                cmd = str(f'aniworld --language "{deutsch}" -o "{DOWNLOAD_PATH}" --episode {episode_url}')
                                try:
                                    print(f"[INFO] Starting download command: {cmd}")
                                    succes = start_download_process(cmd)
                                    if succes:
                                        exsiting_file = get_existing_file_path(serien_url=serien_url, season=season, episode=episode, config=config)
                                        if exsiting_file is not None:
                                            exsiting_file = str(exsiting_file)
                                            if '[Sub]' in exsiting_file or '[English Dub]' in exsiting_file or '[English Sub]' in exsiting_file:
                                                delete_old_non_german_version(serien_url=serien_url, season=season, episode=episode, config=config)
                                        
                                        move_and_rename_downloaded_file(serien_url=serien_url, season=season, episode=episode, language=deutsch)
                                        print(f"[SUCCESS] Download successfull for episode {episode_url}")
                                        missing_german_episodes.remove(episode_url)


                                except Exception as e:
                                    print(f"[ERROR] Error during download process: {e}")
                                    continue
                                # Aktualisiere die fehlenden deutschen Episoden in der Datenbank
                                set_missing_german_episodes(id, missing_german_episodes)
                                # Wenn keine fehlenden deutschen Episoden mehr übrig sind, aktualisiere den Status der deutschen Vollständigkeit
                                if len(missing_german_episodes) == 0 or missing_german_episodes == None:
                                    set_deutsch_completion(id, True)

    #================================================
    #Check Missing Mode
    #================================================

                elif mode == "check-missing":
                    missing_german_episodes = []
                    seasons_with_episode_count = get_seasons_with_episode_count(serien_url)
                    if seasons_with_episode_count == -1:
                        raise Exception("Error retrieving seasons or episodes.")
        
                    for season in seasons_with_episode_count:
                        for episode in seasons_with_episode_count[season]:   

                            existing_file = get_existing_file_path(serien_url=serien_url, season=season, episode=episode, config=config)
                            if existing_file is not None:
                                print(f"[SKIP] Datei für S{int(season):02d}E{int(episode):03d} bereits vorhanden.")
                                existing_file = str(existing_file)
                                if '[Sub]' in existing_file or '[English Dub]' in existing_file or '[English Sub]' in existing_file:
                                    missing_german_episodes.append(get_episode_url(serien_url, season, episode))
                                continue
                                
                            episode_url = get_episode_url(serien_url, season, episode)
                            sprachen = get_languages_for_episode(episode_url)
                            if sprachen != -1:
                                if LANGUAGES[0] in sprachen:
                                    sprache = LANGUAGES[0]
                                elif LANGUAGES[1] in sprachen:
                                    sprache = LANGUAGES[1]
                                elif LANGUAGES[2] in sprachen:
                                    sprache = LANGUAGES[2]
                                elif LANGUAGES[3] in sprachen:
                                    sprache = LANGUAGES[3]
                                else:
                                    return -1
                                if sprache != "German Dub":
                                        missing_german_episodes.append(episode_url)
                                cmd = str(f'aniworld --language "{sprache}" -o "{DOWNLOAD_PATH}" --episode {episode_url}')
                                try:
                                    print(f"[INFO] Starting download command: {cmd}")
                                    succes = start_download_process(cmd)
                                    if succes:
                                        print(f"[OK] Download successfull for S{int(season):02d}E{int(episode):03d}")
                                except Exception as e:
                                    print(f"[ERROR] Error during download process: {e}")
                                    continue 
                            
                            else:
                                print(f"[ERROR] Could not retrieve languages for episode: {episode_url}")


                            if get_existing_file_path(serien_url, season, episode, config) == None:
                                print(f"[ERROR] Download failed for S{int(season):02d}E{int(episode):03d}. No file found after download process.")
                                continue
                            elif get_existing_file_path(serien_url, season, episode, config) is not None:
                                print(f"[VERIFY] File found: {get_episode_title(episode_url)}")

                            # Nach Abschluss des Downloads die letzte heruntergeladene Episode aktualisieren (inklusive Filme in Staffel 0)
                            if int(season) == 0 or season.strip().lower() == "filme":
                                set_last_downloaded_film(id, int(episode))
                            set_last_downloaded_episode(id, int(season), int(episode))

                        # Nach Abschluss einer Staffel die letzte heruntergeladene Staffel aktualisieren
                        set_last_downloaded_season(id, int(season))

    #================================================
    #New Mode
    #================================================

                elif mode == "new":
                    missing_german_episodes = []
                    seasons_with_episode_count = get_seasons_with_episode_count(serien_url)
                    if seasons_with_episode_count == -1:
                        raise Exception("Error retrieving seasons or episodes.")
                    # Nur bei kompletten Serien auf neue Episoden prüfen
                    if get_completion_status(id) == False:
                        print(f"[SKIP] Serie '{title}' noch nicht komplett heruntergeladen. Bitte zuerst im 'default' Modus ausführen.")
                        continue

                    # Letzte heruntergeladene Werte aus DB holen
                    last_downloaded_season = get_last_downloaded_season(id)
                    last_downloaded_episode = get_last_downloaded_episode(id)
                    last_downloaded_film = get_last_downloaded_film(id)

                    # Letzte verfügbare Werte ermitteln
                    last_available_season = max(seasons_with_episode_count.keys(), key=int)
                    last_available_episode = max(seasons_with_episode_count[str(last_downloaded_season)]) if str(last_downloaded_season) in seasons_with_episode_count else 0
            
                    last_available_film = 0
                    if "0" in seasons_with_episode_count:
                        last_available_film = max(seasons_with_episode_count["0"])
                    elif "filme" in seasons_with_episode_count:
                        last_available_film = max(seasons_with_episode_count["filme"])

                    # Bestimmen was heruntergeladen werden soll
                    download_seasons = []
                    
                    # Neue Staffel(n) gefunden
                    if int(last_available_season) > last_downloaded_season:
                        print(f"[INFO] Neue Staffel(n) ab Staffel {last_available_season} gefunden.")
                        # Alle neuen Staffeln hinzufügen
                        for staffel in range(last_downloaded_season + 1, int(last_available_season) + 1):
                            if str(staffel) in seasons_with_episode_count:
                                download_seasons.append(str(staffel))
                    
                    # Neue Episoden in letzter Staffel
                    elif last_downloaded_season == int(last_available_season) and int(last_available_episode) > last_downloaded_episode:
                        print(f"[INFO] Neue Episode(n) in Staffel {last_downloaded_season} gefunden (E{last_downloaded_episode + 1} bis E{last_available_episode}).")
                        download_seasons.append(str(last_downloaded_season))
                    
                    # Neue Filme
                    if int(last_available_film) > last_downloaded_film:
                        print(f"[INFO] Neuer Film/Filme gefunden (Film {last_downloaded_film + 1} bis {last_available_film}).")
                        if "0" in seasons_with_episode_count:
                            download_seasons.append("0")
                        elif "filme" in seasons_with_episode_count:
                            download_seasons.append("filme")
                    
                    # Warnungen ausgeben
                    if int(last_available_season) < last_downloaded_season:
                        print(f"[WARN] Die letzte heruntergeladene Staffel {last_downloaded_season} ist höher als die aktuell verfügbare Staffel {last_available_season}. Bitte überprüfe die Serie manuell.")
                        continue
                    if last_downloaded_season == int(last_available_season) and int(last_available_episode) < last_downloaded_episode:
                        print(f"[WARN] Die letzte heruntergeladene Episode S{int(last_downloaded_season):02d}E{int(last_downloaded_episode):03d} ist höher als die aktuell verfügbare Episode. Bitte überprüfe die Serie manuell.")
                        continue
                    
                    if int(last_available_film) > 0 and int(last_available_film) < last_downloaded_film:
                        print(f"[WARN] Der letzte heruntergeladene Film S00E{int(last_downloaded_film):03d} ist höher als der aktuell verfügbare Film S00E{int(last_available_film):03d}. Bitte überprüfe die Serie manuell.")
                        continue
                    
                    # Wenn nichts Neues gefunden wurde
                    if len(download_seasons) == 0:
                        print(f"[INFO] Keine neuen Episoden oder Filme für '{title}' gefunden.")
                        continue
                    
                    # Nur die relevanten Staffeln herunterladen
                    for season in download_seasons:
                        for episode in seasons_with_episode_count[season]:
                            
                            if season == str(last_downloaded_season) and int(episode) <= last_downloaded_episode:
                                continue  # Bereits heruntergeladen
                            
                            if (season == "0" or season.lower() == "filme") and int(episode) <= last_downloaded_film:
                                continue  # Film bereits heruntergeladen
                            
                            # Prüfen ob Datei bereits existiert
                            existing_file = get_existing_file_path(serien_url=serien_url, season=season, episode=episode, config=config)
                            if existing_file is not None:
                                print(f"[SKIP] Datei für S{int(season):02d}E{int(episode):03d} bereits vorhanden.")
                                continue
                            

                            episode_url = get_episode_url(serien_url, season, episode)
                            sprachen = get_languages_for_episode(episode_url)
                            if sprachen != -1:
                                if LANGUAGES[0] in sprachen:
                                    sprache = LANGUAGES[0]
                                elif LANGUAGES[1] in sprachen:
                                    sprache = LANGUAGES[1]
                                elif LANGUAGES[2] in sprachen:
                                    sprache = LANGUAGES[2]
                                elif LANGUAGES[3] in sprachen:
                                    sprache = LANGUAGES[3]
                                else:
                                    return -1
                                if sprache != "German Dub":
                                    missing_german_episodes.append(episode_url)
                                cmd = str(f'aniworld --language "{sprache}" -o "{DOWNLOAD_PATH}" --episode {episode_url}')
                                try:
                                    print(f"[INFO] Starting download command: {cmd}")
                                    succes = start_download_process(cmd)
                                    if succes:
                                        print(f"[OK] Download successfull for S{int(season):02d}E{int(episode):03d}")
                                except Exception as e:
                                    print(f"[ERROR] Error during download process: {e}")
                                    continue                         
                            else:
                                print(f"[ERROR] Could not retrieve languages for episode: {episode_url}")
                                continue
                            
                            
                            if get_existing_file_path(serien_url, season, episode, config) == None:
                                print(f"[ERROR] Download failed for S{int(season):02d}E{int(episode):03d}. No file found after download process.")
                                continue
                            elif get_existing_file_path(serien_url, season, episode, config) is not None:
                                print(f"[VERIFY] File found: {get_episode_title(episode_url)}")


                            # Nach Abschluss des Downloads die letzte heruntergeladene Episode aktualisieren
                            if int(season) == 0 or season.strip().lower() == "filme":
                                set_last_downloaded_film(id, int(episode))
                            set_last_downloaded_episode(id, int(season), int(episode))

                        # Nach Abschluss einer Staffel die letzte heruntergeladene Staffel aktualisieren
                        set_last_downloaded_season(id, int(season))

            except Exception as e:
                print(f"[ERROR] Error processing series with ID {id}: {e}")
            
            # Nach jeder Serie zum nächsten Index wechseln (WICHTIG: Das muss NACH allen Modi sein!)
            index += 1
            if check_index_exist(index):
                next_index_exist = True
            else:
                next_index_exist = False
        
#================================================
#Übergang zur nächsten Serie
#================================================        
    except Exception as e:
        print(f"[ERROR] Error during download process: {e}")


    
    finally:
        stop_run_logging()
