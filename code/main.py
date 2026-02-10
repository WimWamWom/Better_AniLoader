import os
import time
from flask import Flask
from flask_cors import CORS
from API_Endpoints import api
from config import load_config
from database import init_db, update_index, update_title
from downloader import download


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

# -------------------- START --------------------
TEST = True

if __name__ == "__main__":
    start = time.perf_counter()
    config = load_config()
    if not config: 
        print("Fehler beim Laden der Konfiguration. Bitte überprüfen Sie die config.json.")
        exit(1)
    PORT = config.get('port')
    REFRESH_TITLES = config.get('refresh_titles')
    START_MODE = config.get('autostart_mode')
    init_db()
    update_index()

    if REFRESH_TITLES:
        update_title()
    if START_MODE.lower().strip() in ["default", "german", "new", "check-missing"]:
        download(START_MODE.lower().strip())



    if TEST:
        print("Running in test mode...")

    else:
        # Flask Server starten und laufen lassen
        print(f"Starting Better_AniLoader Server on port {PORT}...")
        print(f"API available at http://localhost:{PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
   
    elapsed = time.perf_counter() - start
    print(f"Elapsed: {elapsed:.2f}s")

