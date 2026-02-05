from pathlib import Path
import os
import json
import threading
from time import time

BASE_DIR = Path(__file__).resolve().parent
ANIME_TXT = BASE_DIR / "AniLoader.txt"
DEFAULT_DOWNLOAD_DIR = BASE_DIR / "Downloads"
DOWNLOAD_DIR = DEFAULT_DOWNLOAD_DIR
STORAGE_MODE = "standard"  # 'standard' oder 'separate'
MOVIES_PATH = ""  # Nur für separate Mode (wird nicht mehr verwendet)
SERIES_PATH = ""  # Nur für separate Mode (wird nicht mehr verwendet)
ANIME_PATH = ""  # Pfad für Animes (aniworld.to)
SERIEN_PATH = ""  # Pfad für Serien (s.to)
ANIME_SEPARATE_MOVIES = False  # Filme getrennt von Staffeln bei Animes
SERIEN_SEPARATE_MOVIES = False  # Filme getrennt von Staffeln bei Serien
ANIME_MOVIES_PATH = ""  # Separater Pfad für Anime-Filme (optional)
SERIEN_MOVIES_PATH = ""  # Separater Pfad für Serien-Filme (optional)
SERVER_PORT = 5050




DEFAULT_DATA_FOLDER = os.path.join(os.path.dirname(__file__),'..' ,'data')
data_folder = DEFAULT_DATA_FOLDER
config_path = os.path.join(data_folder, 'config.json')
db_path = os.path.join(data_folder, 'AniLoader.db')
log_path = os.path.join(data_folder, 'last_run.txt')
all_logs_path = os.path.join(data_folder, 'all_logs.txt')
CONFIG_WRITE_LOCK = threading.Lock()
os.makedirs(data_folder, exist_ok=True)

def save_last_log(log_content):
    with open(log_path, 'w', encoding='utf-8') as log_file:
        log_file.write(log_content)

def read_last_log():
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as log_file:
            return log_file.read()
    return "No previous log available."

CONFIG_PATH = Path(config_path)
DB_PATH = Path(db_path)

LANGUAGES = ["German Dub", "German Sub", "English Dub", "English Sub"]
MIN_FREE_GB = 2.0
MAX_PATH = 260
AUTOSTART_MODE = None  # 'default'|'german'|'new'|'check-missing' or None
REFRESH_TITLES = True  # Titelaktualisierung beim Start zulassen


def update_data_paths(new_data_folder):
    """Updates the global data folder paths when the data_folder_path config changes."""
    global data_folder, config_path, db_path, log_path, all_logs_path, CONFIG_PATH, DB_PATH
    data_folder = new_data_folder
    config_path = os.path.join(data_folder, 'config.json')
    db_path = os.path.join(data_folder, 'AniLoader.db')
    log_path = os.path.join(data_folder, 'last_run.txt')
    all_logs_path = os.path.join(data_folder, 'all_logs.txt')
    CONFIG_PATH = Path(config_path)
    DB_PATH = Path(db_path)
    # Ensure the new data folder exists
    os.makedirs(data_folder, exist_ok=True)

def load_config():
    global LANGUAGES, MIN_FREE_GB, AUTOSTART_MODE, DOWNLOAD_DIR, SERVER_PORT, REFRESH_TITLES, STORAGE_MODE, MOVIES_PATH, SERIES_PATH, ANIME_PATH, SERIEN_PATH, ANIME_SEPARATE_MOVIES, SERIEN_SEPARATE_MOVIES, ANIME_MOVIES_PATH, SERIEN_MOVIES_PATH, data_folder
    try:
        # First, check if there's a data_folder_path override in the config
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                # Check for data_folder_path first
                data_folder_path = cfg.get('data_folder_path')
                if data_folder_path and isinstance(data_folder_path, str) and data_folder_path.strip():
                    try:
                        new_folder = Path(data_folder_path).expanduser()
                        try:
                            new_folder = new_folder.resolve()
                        except Exception:
                            pass
                        if str(new_folder) != data_folder:
                            update_data_paths(str(new_folder))
                            # Reload config from new location
                            if CONFIG_PATH.exists():
                                with open(CONFIG_PATH, 'r', encoding='utf-8') as f2:
                                    cfg = json.load(f2)
                    except Exception as e:
                        print(f"[CONFIG-WARN] Ungültiger data_folder_path: {e}, verwende Standard")
                
                # languages
                langs = cfg.get('languages')
                if isinstance(langs, list) and langs:
                    LANGUAGES = langs
                # min_free_gb
                try:
                    MIN_FREE_GB = float(cfg.get('min_free_gb', MIN_FREE_GB))
                except Exception:
                    pass
                # autostart_mode (normalize, validate)
                raw_mode = cfg.get('autostart_mode')
                allowed = {None, 'default', 'german', 'new', 'check-missing'}
                if isinstance(raw_mode, str):
                    raw_mode_norm = raw_mode.strip().lower()
                    if raw_mode_norm in {'', 'none', 'off', 'disabled'}:
                        AUTOSTART_MODE = None
                    elif raw_mode_norm in allowed:
                        AUTOSTART_MODE = raw_mode_norm
                    else:
                        AUTOSTART_MODE = None
                elif raw_mode is None:
                    AUTOSTART_MODE = None
                else:
                    AUTOSTART_MODE = None
                # download_path (add default if missing)
                changed = False
                dl_path = cfg.get('download_path')
                if isinstance(dl_path, str) and dl_path.strip():
                    try:
                        DOWNLOAD_DIR = Path(dl_path).expanduser()
                        try:
                            DOWNLOAD_DIR = DOWNLOAD_DIR.resolve()
                        except Exception:
                            # keep as provided if resolve fails
                            pass
                    except Exception:
                        DOWNLOAD_DIR = DEFAULT_DOWNLOAD_DIR
                else:
                    DOWNLOAD_DIR = DEFAULT_DOWNLOAD_DIR
                    cfg['download_path'] = str(DOWNLOAD_DIR)
                    changed = True
                # storage_mode, movies_path, series_path
                storage_mode = cfg.get('storage_mode', 'standard')
                if storage_mode in ['standard', 'separate']:
                    STORAGE_MODE = storage_mode
                else:
                    STORAGE_MODE = 'standard'
                    cfg['storage_mode'] = 'standard'
                    changed = True
                
                MOVIES_PATH = cfg.get('movies_path', '')
                if 'movies_path' not in cfg:
                    # Standardmäßig Unterordner "Filme" im Download-Verzeichnis
                    cfg['movies_path'] = str(DOWNLOAD_DIR / 'Filme')
                    MOVIES_PATH = str(DOWNLOAD_DIR / 'Filme')
                    changed = True
                    
                SERIES_PATH = cfg.get('series_path', '')
                if 'series_path' not in cfg:
                    # Standardmäßig Unterordner "Serien" im Download-Verzeichnis
                    cfg['series_path'] = str(DOWNLOAD_DIR / 'Serien')
                    SERIES_PATH = str(DOWNLOAD_DIR / 'Serien')
                    changed = True
                
                # Neue Content-Type basierte Pfade
                ANIME_PATH = cfg.get('anime_path', '')
                if 'anime_path' not in cfg:
                    cfg['anime_path'] = str(DOWNLOAD_DIR / 'Animes')
                    ANIME_PATH = str(DOWNLOAD_DIR / 'Animes')
                    changed = True
                    
                SERIEN_PATH = cfg.get('serien_path', '')
                if 'serien_path' not in cfg:
                    cfg['serien_path'] = str(DOWNLOAD_DIR / 'Serien')
                    SERIEN_PATH = str(DOWNLOAD_DIR / 'Serien')
                    changed = True
                
                # Film/Staffel Organisation
                ANIME_SEPARATE_MOVIES = cfg.get('anime_separate_movies', False)
                if 'anime_separate_movies' not in cfg:
                    cfg['anime_separate_movies'] = False
                    changed = True
                    
                SERIEN_SEPARATE_MOVIES = cfg.get('serien_separate_movies', False)
                if 'serien_separate_movies' not in cfg:
                    cfg['serien_separate_movies'] = False
                    changed = True
                
                # Separate Film-Pfade (optional)
                ANIME_MOVIES_PATH = cfg.get('anime_movies_path', '')
                SERIEN_MOVIES_PATH = cfg.get('serien_movies_path', '')
                # port (only from config; keep default if invalid)
                try:
                    port_val = cfg.get('port', SERVER_PORT)
                    if isinstance(port_val, str) and port_val.isdigit():
                        port_val = int(port_val)
                    if isinstance(port_val, int) and 1 <= port_val <= 65535:
                        SERVER_PORT = port_val
                    else:
                        cfg['port'] = SERVER_PORT
                        changed = True
                except Exception:
                    cfg['port'] = SERVER_PORT
                    changed = True
                # refresh_titles flag (default True)
                try:
                    if 'refresh_titles' in cfg:
                        REFRESH_TITLES = bool(cfg.get('refresh_titles'))
                    else:
                        cfg['refresh_titles'] = True
                        REFRESH_TITLES = True
                        changed = True
                except Exception:
                    REFRESH_TITLES = True
                    cfg['refresh_titles'] = True
                    changed = True
                # data_folder_path - add if missing but don't change global var during load
                if 'data_folder_path' not in cfg:
                    cfg['data_folder_path'] = data_folder
                    changed = True
                # persist if we added defaults
                if changed:
                    if _write_config_atomic(cfg):
                        print("[CONFIG] fehlende Schlüssel ergänzt und gespeichert")
                    else:
                        print("[CONFIG-ERROR] Ergänzung konnte nicht gespeichert werden (Datei evtl. gesperrt)")
                print(f"[CONFIG] geladen: languages={LANGUAGES} min_free_gb={MIN_FREE_GB} autostart_mode={AUTOSTART_MODE} data_folder={data_folder}")
        else:
            save_config()  # create default config
    except Exception as e:
        print(f"[CONFIG-ERROR] load_config: {e}")

def save_config():
    try:
        cfg = {
            'languages': LANGUAGES,
            'min_free_gb': MIN_FREE_GB,
            'download_path': str(DOWNLOAD_DIR),
            'storage_mode': STORAGE_MODE,
            'movies_path': MOVIES_PATH,
            'series_path': SERIES_PATH,
            'anime_path': ANIME_PATH,
            'serien_path': SERIEN_PATH,
            'anime_separate_movies': ANIME_SEPARATE_MOVIES,
            'serien_separate_movies': SERIEN_SEPARATE_MOVIES,
            'anime_movies_path': ANIME_MOVIES_PATH,
            'serien_movies_path': SERIEN_MOVIES_PATH,
            'port': SERVER_PORT,
            'autostart_mode': AUTOSTART_MODE,
            'refresh_titles': REFRESH_TITLES,
            'data_folder_path': data_folder
        }
        # atomic write to avoid partial files
        tmp_path = str(CONFIG_PATH) + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, CONFIG_PATH)
        print(f"[CONFIG] gespeichert")
        return True
    except Exception as e:
        print(f"[CONFIG-ERROR] save_config: {e}")
        return False
def _write_config_atomic(cfg: dict) -> bool:
    """Write config.json with retries and atomic replace where possible.
    Handles transient PermissionError on Windows by retrying and finally
    falling back to a direct write if needed.
    """
    try:
        with CONFIG_WRITE_LOCK:
            dir_path = os.path.dirname(str(CONFIG_PATH))
            os.makedirs(dir_path, exist_ok=True)
            tmp_path = str(CONFIG_PATH) + ".tmp"
            # make sure target file is writable (remove read-only)
            try:
                if os.path.exists(CONFIG_PATH):
                    os.chmod(CONFIG_PATH, os.stat.S_IWRITE | os.stat.S_IREAD)
            except Exception:   
                pass
            for attempt in range(5):
                try:
                    with open(tmp_path, 'w', encoding='utf-8') as wf:
                        json.dump(cfg, wf, indent=2, ensure_ascii=False)
                    os.replace(tmp_path, CONFIG_PATH)
                    return True
                except PermissionError:
                    # Clean temp and backoff
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass
                    time.sleep(0.3 * (attempt + 1))
                    continue
                except Exception:
                    # Cleanup and break to fallback
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass
                    break
            # Fallback: non-atomic write
            try:
                with open(CONFIG_PATH, 'w', encoding='utf-8') as wf:
                    json.dump(cfg, wf, indent=2, ensure_ascii=False)
                return True
            except Exception as e:
                print(f"[CONFIG-ERROR] final write failed: {e}")
                return False
    except Exception as e:
        print(f"[CONFIG-ERROR] _write_config_atomic: {e}")
        return False

