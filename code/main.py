import os
import time
from flask import Flask
from flask_cors import CORS
from API_Endpoints import api
from config import load_config
from database import init_db, update_index, update_title, add_url_to_db
from downloader import download
from txt_manager import read_aniloader_txt, write_to_aniloader_txt_bak
from helper import sanitize_url

# -------------------- Flask App Setup --------------------
from config import PATH_ANILOADER_TXT, PATH_ANILOADER_TXT_BAK, BASE_DIR
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

# -------------------- START --------------------
TEST = False

if __name__ == "__main__":
    start = time.perf_counter()
    config = load_config()
    if not config: 
        print("Fehler beim Laden der Konfiguration. Bitte überprüfen Sie die config.json.")
        exit(1)
    PORT = int(config.get('port'))
    REFRESH_TITLES = bool(config.get('refresh_titles'))
    START_MODE = str(config.get('autostart_mode')).lower().strip() if config.get('autostart_mode') else None
    ANILOADER_TXT_BACKUP = bool(config.get('aniloader_txt_backup'))


    init_db()
    update_index()

    if REFRESH_TITLES:
        update_title()
    if START_MODE in ["default", "german", "new", "check-missing"]:
        download(START_MODE)

    aniloader_txt = read_aniloader_txt(PATH_ANILOADER_TXT)
    if len(aniloader_txt) > 0:
        print(f"Füge {len(aniloader_txt)} Einträge aus aniloader.txt zur Datenbank hinzu...")
        sanitize_urls = []
        for url in aniloader_txt:
            sanitized_url = sanitize_url(url)
            sanitize_urls.append(sanitized_url)
            add_url_to_db(sanitized_url)
            
        if ANILOADER_TXT_BACKUP:
            print("Creating backup of AniLoader.txt...")
            write_to_aniloader_txt_bak(PATH_ANILOADER_TXT_BAK, sanitize_urls)
    
    

    if TEST:
        print("Running in test mode...")

    else:
        # Flask Server starten und laufen lassen
        print(f"Starting Better_AniLoader Server on port {PORT}...")
        print(f"API available at http://localhost:{PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
   
    elapsed = time.perf_counter() - start
    print(f"Elapsed: {elapsed:.2f}s")

