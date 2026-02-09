import os
import time
from flask import Flask
from flask_cors import CORS
from html_request import get_seasons_with_episode_count, get_languages_for_episode
from url_build import get_episode_url
from API_Endpoints import api
from config import load_config
from database import add_to_db, init_db, update_index, get_series_title, last_downloaded_episode, last_downloaded_season, last_downloaded_film, anime_completion, update_title
from file_management import get_file_path


# -------------------- Flask App Setup --------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
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

   

def CLI_download(url: str, german_only: bool = False) -> int:
    config = load_config()
    if not config:  
        print("Fehler beim Laden der Konfiguration. Bitte überprüfen Sie die config.json.")
        exit(1)
    LANGUAGES = config.get('languages')
    if LANGUAGES[0] != "German Dub" and german_only:
        return -1
    seasons = get_seasons_with_episode_count(url)
    if seasons == -1:
        print("Error retrieving seasons or episodes.")
        return 1
    for season in seasons:
        output_path = config.get('download_path')
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
                print("aniworld", "--language", sprache, "-o", output_path, "--episode", episode_url)
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
    config = load_config()
    if not config: 
        print("Fehler beim Laden der Konfiguration. Bitte überprüfen Sie die config.json.")
        exit(1)

    PORT = config.get('port')
    init_db()
    update_index()
    if config.get('refresh_titles') == True:
        update_title()

    test_mode = False
    if test_mode:
        print(get_file_path("https://s.to/serie/seishun-buta-yarou-wa-bunny-girl-senpai-no-yume-o-minai", "0", "1"))
        print(get_file_path("https://s.to/serie/seishun-buta-yarou-wa-bunny-girl-senpai-no-yume-o-minai", "0", "2"))
        print(get_file_path("https://s.to/serie/seishun-buta-yarou-wa-bunny-girl-senpai-no-yume-o-minai", "0", "3"))
        print(get_file_path("https://s.to/serie/the-rookie", "1", "1"))
        print(get_file_path("https://s.to/serie/the-rookie", "4", "10"))
        print(get_file_path("https://s.to/serie/the-rookie", "6", "7"))


        test_urls = [
            "https://s.to/serie/seishun-buta-yarou-wa-bunny-girl-senpai-no-yume-o-minai",
            "https://s.to/serie/the-rookie",
            "https://s.to/serie/die-drachenreiter-von-berk",
                    ]
        for url in test_urls:
            add_to_db(url)
            CLI_download(url=url, german_only=False)
        
    else:
        # Flask Server starten und laufen lassen
        print(f"Starting Better_AniLoader Server on port {PORT}...")
        print(f"API available at http://localhost:{PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
   
    elapsed = time.perf_counter() - start
    print(f"Elapsed: {elapsed:.2f}s")

