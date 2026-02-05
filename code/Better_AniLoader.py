import time
from flask import Flask
from flask_cors import CORS
from html_request import get_seasons_with_episode_count, get_languages_for_episode
from url_build import get_episode_url
from API_Endpoints import api

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
languages = [
    "German Dub",
    "German Sub",
    "English Dub",
    "English Sub",
]
SERVER_PORT = 5050



def CLI_download(url: str, german_only: bool = False) -> int:
    if languages[0] != "German Dub" and german_only:
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
                if languages[0] in sprachen:
                    sprache = languages[0]
                elif languages[1] in sprachen:
                    sprache = languages[1]
                elif languages[2] in sprachen:
                    sprache = languages[2]
                elif languages[3] in sprachen:
                    sprache = languages[3]
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
    # CLI-Modus für Entwicklung/Testing
    test_cli = True
    
    if test_cli:
        start = time.perf_counter()
        test_urls = [
                        "https://s.to/serie/the-rookie",
                        "https://s.to/serie/die-drachenreiter-von-berk",
                     ]
        for url in test_urls:
            CLI_download(url=url)
        elapsed = time.perf_counter() - start
        print(f"Elapsed: {elapsed:.2f}s")
    else:
        # Flask Server starten
        print(f"Starting Better_AniLoader Server on port {SERVER_PORT}...")
        print(f"API available at http://localhost:{SERVER_PORT}")
        app.run(host="0.0.0.0", port=SERVER_PORT, debug=True, threaded=True)