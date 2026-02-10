from pathlib import Path
import os
import json

BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = BASE_DIR / "Downloads"
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = DATA_DIR / 'config.json'
os.makedirs(DATA_DIR, exist_ok=True)

standart_werte = {
        "languages": ["German Dub", "German Sub", "English Dub", "English Sub"],
        "min_free_gb": 100.0,
        "port": 5050,
        "storage_mode": "standard",
        "autostart_mode": None,
        "refresh_titles": False,
        "anime_separate_movies": False,
        "serien_separate_movies": False,
        "dedicated_movies_folder": False,
        "download_path": str(DOWNLOAD_DIR),
        "data_folder_path": str(DATA_DIR),
        "anime_path": str(Path(DOWNLOAD_DIR) / "Anime"),
        "series_path": str(Path(DOWNLOAD_DIR) / "Serien"),
        "movies_path": str(Path(DOWNLOAD_DIR) / "Filme"),
        "anime_movies_path": str(Path(DOWNLOAD_DIR) / "Filme-Anime"),
        "serien_movies_path": str(Path(DOWNLOAD_DIR) / "Filme-Serien"),



    }


def ceck_and_init_config() -> bool:
    """
    Prüft, ob alle benötigten Schlüssel in config_json vorhanden sind und ergänzt fehlende mit Standardwerten.
    Legt eine neue config.json mit Standardwerten an, falls die Datei leer oder ungültig ist.
    Gibt True zurück, wenn Änderungen vorgenommen wurden, sonst False.
    """
    complete = True
    try:
        if not CONFIG_PATH.exists() or CONFIG_PATH.stat().st_size == 0:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as config_file:
                json.dump(standart_werte, config_file, indent=2, ensure_ascii=False)
            print("[CONFIG] Neue Standard-config.json angelegt.")
            complete = True
            return complete
    except Exception as exception:
        print(f"[CONFIG-ERROR] check_if_config_complete (create): {exception}")
        complete = False
    
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as config_file:
            config_json = json.load(config_file)
        for variable, wert in standart_werte.items():
            if variable not in config_json:
                config_json[variable] = wert
                complete = False
        if not complete:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as config_file:
                json.dump(config_json, config_file, indent=2, ensure_ascii=False)
            print("[CONFIG] Fehlende Schlüssel ergänzt und gespeichert.")
            complete = True
            return complete
    except Exception as exception:
        print(f"[CONFIG-ERROR] check_if_config_complete (update): {exception}")
        complete = False
        return complete
    return complete

def load_config():
    if ceck_and_init_config() == False:
        print("[CONFIG-ERROR] config.json ist ungültig oder unvollständig und konnte nicht automatisch korrigiert werden.")
        return False
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r', encoding='utf-8') as config_file:
                config_json = json.load(config_file)

                if not isinstance(config_json.get('data_folder_path'), str):
                    raise Exception("Ungültiger Wert für 'data_folder_path'. Erwartet wird ein String.")
                
                if not isinstance(config_json.get('languages'), list) :
                    raise Exception("Ungültiger Wert für 'languages'. Erwartet wird eine Liste von Strings.")

                if not isinstance(config_json.get('min_free_gb'), (int, float)):
                    raise Exception("Ungültiger Wert für 'min_free_gb'. Erwartet wird eine Zahl.")


                autostart_mode = str(config_json.get('autostart_mode')).strip().lower()
                allowed_modes = {None, 'default', 'german', 'new', 'check-missing'}
                if isinstance(autostart_mode, str):
                    if autostart_mode not in {'', 'none', 'off', 'disabled', 'false', 'null'} or autostart_mode in allowed_modes or autostart_mode is None:
                       raise Exception(f"Ungültiger Wert für 'autostart_mode'. Erwartet wird einer der folgenden Werte: {allowed_modes} oder eine falsy Angabe wie '', 'none', 'off', 'disabled', 'false', 'null'.")
                else:
                    raise Exception("Ungültiger Wert für 'autostart_mode'. Erwartet wird ein String.")

                if not isinstance(str(config_json.get('download_path')).strip(), str):
                    raise Exception("Ungültiger Wert für 'download_path'. Erwartet wird ein String.")                

                if str(config_json.get('storage_mode')).strip().lower() not in ['standard', 'separate']:
                    raise Exception("Ungültiger Wert für 'storage_mode'. Erwartet wird 'standard' oder 'separate'.")
                
                if not isinstance(config_json.get('movies_path'), str):
                    raise Exception("Ungültiger Wert für 'movies_path'. Erwartet wird ein String.")
                if not isinstance(config_json.get('series_path'), str):
                    raise Exception("Ungültiger Wert für 'series_path'. Erwartet wird ein String.")   
                if not isinstance(config_json.get('anime_path'), str):
                    raise Exception("Ungültiger Wert für 'anime_path'. Erwartet wird ein String.")
                if not isinstance(config_json.get('anime_separate_movies'), bool):
                    raise Exception("Ungültiger Wert für 'anime_separate_movies'. Erwartet wird ein Boolean.")
                if not isinstance(config_json.get('serien_separate_movies'), bool):
                    raise Exception("Ungültiger Wert für 'serien_separate_movies'. Erwartet wird ein Boolean.")
                if not isinstance(config_json.get('anime_movies_path'), str):
                    raise Exception("Ungültiger Wert für 'anime_movies_path'. Erwartet wird ein String.")
                if not isinstance(config_json.get('serien_movies_path'), str):
                    raise Exception("Ungültiger Wert für 'serien_movies_path'. Erwartet wird ein String.")

                if not isinstance(config_json.get('port'), int) or not (1 <= config_json.get('port') <= 65535):
                    raise Exception("Ungültiger Wert für 'port'. Erwartet wird eine Ganzzahl zwischen 1 und 65535.")

                if not isinstance(config_json.get('refresh_titles'), bool):
                    raise Exception("Ungültiger Wert für 'refresh_titles'. Erwartet wird ein Boolean.")

    except Exception as exception:
        print(f"[CONFIG-ERROR] load_config (validation): {exception}")
        return False

    try:        
        with open(CONFIG_PATH, 'r', encoding='utf-8') as config_file:
            config_json = json.load(config_file)
            return config_json
    except Exception as exception:
        print(f"[CONFIG-ERROR] load_config (print): {exception}")
        return False
    
def save_config(config_json: dict) -> bool:
    try:
        tmp_path = str(CONFIG_PATH) + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(config_json, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, CONFIG_PATH)
        print(f"[CONFIG] gespeichert")
        return True
    except Exception as exception:
        print(f"[CONFIG-ERROR] save_config: {exception}")
        return False
