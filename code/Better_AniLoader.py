import time
from flask import Flask, json
from flask_cors import CORS
from html_request import get_seasons_with_episode_count, get_languages_for_episode
from url_build import get_episode_url
from API_Endpoints import api
from config import load_config



# -------------------- Flask App Setup --------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": "*", 
    "allow_headers": "*", 
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "supports_credentials": False,
    "expose_headers": "*"
}})

# API Blueprint registrieren
app.register_blueprint(api)

# CORS Preflight Handler
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', '*')
    response.headers.add('Access-Control-Allow-Methods', '*')
    return response

# -------------------- Konfiguration --------------------
def import_config_data(print_enabled: bool = True)-> bool:
    global LANGUAGES, MIN_FREE_GB, PORT, DOWNLOAD_PATH, STORAGE_MODE, ANIME_SEPARATE_MOVIES, SERIEN_SEPARATE_MOVIES, MOVIES_PATH, SERIES_PATH, ANIME_PATH, ANIME_MOVIES_PATH, SERIEN_MOVIES_PATH, AUTOSTART_MODENUL, REFRESH_TITLES, DATA_FOLDER_PATH
    config_data = load_config()
    if not config_data:
        print("Fehler beim Laden der Konfiguration. Bitte überprüfen Sie die config.json.")
        return False

    LANGUAGES = config_data.get('languages')   
    MIN_FREE_GB = config_data.get('min_free_gb')
    PORT = config_data.get('port')
    DOWNLOAD_PATH = config_data.get('download_path')
    STORAGE_MODE = config_data.get('storage_mode')
    ANIME_SEPARATE_MOVIES = config_data.get('anime_separate_movies')
    SERIEN_SEPARATE_MOVIES = config_data.get('serien_separate_movies')
    MOVIES_PATH = config_data.get('movies_path')
    SERIES_PATH = config_data.get('series_path')
    ANIME_PATH = config_data.get('anime_path')
    ANIME_MOVIES_PATH = config_data.get('anime_movies_path')
    SERIEN_MOVIES_PATH = config_data.get('serien_movies_path')
    AUTOSTART_MODENUL = config_data.get('autostart_modenul')
    REFRESH_TITLES = config_data.get('refresh_titles')
    DATA_FOLDER_PATH = config_data.get('data_folder_path')
    if print_enabled:
        print(f"Konfiguration erfolgreich geladen. Aktuelle Werte:")
        print(json.dumps(config_data, indent=2, ensure_ascii=False))
    return True



def CLI_download(url: str, german_only: bool = False) -> int:
    if LANGUAGES[0] != "German Dub" and german_only:
        return -1
    seasons = get_seasons_with_episode_count(url)
    if seasons == -1:
        print("Error retrieving seasons or episodes.")
        return 1
    for season in seasons:
        for episode in seasons[season]:
            episode_url = get_episode_url(url, season, episode)
            sprachen = get_languages_for_episode(episode_url)
            if sprachen != -1:
                if german_only and "German Dub" not in sprachen:
                    continue
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
                print("aniworld", "--language", sprache, "-o", "C:\\Users\\wroehner\\Desktop\\Git\\AniLoader Test\\Downloads", "--episode", episode_url)
            else:
                print(f"Could not retrieve languages for episode: {episode_url}")
    return 0 

def check_new_german(episode_url: str) -> bool:
    sprachen = get_languages_for_episode(episode_url)
    if sprachen != -1:
        if "German Dub" in sprachen:
            return True
    return False


if __name__ == "__main__":
    start = time.perf_counter()
    if import_config_data(print_enabled=True) is False:
        exit(1)

    test_mode = True
    
    if test_mode:
        test_urls = [
            "https://s.to/serie/the-rookie",
            "https://s.to/serie/die-drachenreiter-von-berk",
                    ]
        for url in test_urls:
            CLI_download(url=url, german_only=False)
        
    else:
        # Flask Server starten
        print(f"Starting Better_AniLoader Server on port {PORT}...")
        print(f"API available at http://localhost:{PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)


            
    elapsed = time.perf_counter() - start
    print(f"Elapsed: {elapsed:.2f}s")

