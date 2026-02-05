from flask import Blueprint, request, jsonify, send_file
from pathlib import Path
import json

# Blueprint erstellen
api = Blueprint('api', __name__)


# -------------------- FILE UPLOAD --------------------
@api.route("/upload_txt", methods=["POST"])
def upload_txt():
    """
    Endpoint zum Hochladen einer TXT-Datei mit URLs.
    Sollte die URLs aus der hochgeladenen Datei extrahieren und in die DB einfügen.
    """
    # TODO: Implementierung
    raise NotImplementedError("upload_txt endpoint not yet implemented")


# -------------------- DOWNLOAD CONTROL --------------------
@api.route("/start_download", methods=["POST", "GET"])
def start_download():
    """
    Startet den Download-Prozess.
    Parameter (POST JSON):
    - mode: "default" | "german" | "new" | "check-missing"
    """
    # TODO: Implementierung
    raise NotImplementedError("start_download endpoint not yet implemented")


@api.route("/stop_download", methods=["POST"])
def stop_download():
    """
    Stoppt den aktuell laufenden Download-Prozess.
    """
    # TODO: Implementierung
    raise NotImplementedError("stop_download endpoint not yet implemented")


@api.route("/status")
def status():
    """
    Gibt den aktuellen Download-Status zurück.
    Returns:
    - status: "idle" | "running" | "stopped"
    - mode: aktueller Download-Modus
    - current_title: aktuell herunterladener Anime/Serie
    - current_season, current_episode, etc.
    """
    # TODO: Implementierung
    raise NotImplementedError("status endpoint not yet implemented")


@api.route("/health")
def health():
    """
    Health-Check Endpoint für Monitoring.
    """
    # TODO: Implementierung
    return jsonify({"status": "ok"}), 200


# -------------------- CONFIGURATION --------------------
@api.route("/config", methods=["GET", "POST"])
def config():
    """
    GET: Gibt die aktuelle Konfiguration zurück
    POST: Speichert eine neue Konfiguration
    
    Config-Parameter:
    - languages: Liste der bevorzugten Sprachen
    - min_free_gb: Minimaler freier Speicherplatz
    - autostart_mode: Auto-Start Modus
    - download_dir: Download-Verzeichnis
    - server_port: Server-Port
    - storage_mode: "standard" | "separate"
    - etc.
    """
    # TODO: Implementierung
    raise NotImplementedError("config endpoint not yet implemented")


@api.route("/pick_folder", methods=["GET"])
def pick_folder():
    """
    Öffnet einen Ordner-Auswahl-Dialog (tkinter).
    Returns: ausgewählter Ordnerpfad
    """
    # TODO: Implementierung
    raise NotImplementedError("pick_folder endpoint not yet implemented")


# -------------------- QUEUE MANAGEMENT --------------------
@api.route('/queue', methods=['GET', 'POST', 'DELETE'])
def queue():
    """
    GET: Liste aller Queue-Einträge
    POST: Fügt einen Anime zur Queue hinzu oder ordnet Queue neu
        - anime_id: ID des hinzuzufügenden Anime
        - order: Liste von Queue-IDs für Neuordnung
    DELETE: Löscht Queue-Eintrag
        - id: Queue-ID zum Löschen
        - clear: True um alle zu löschen
    """
    # TODO: Implementierung
    raise NotImplementedError("queue endpoint not yet implemented")


# -------------------- SYSTEM INFO --------------------
@api.route('/disk')
def disk():
    """
    Gibt Informationen über den verfügbaren Speicherplatz zurück.
    Returns:
    - free_gb: Freier Speicher in GB
    - path: Geprüfter Pfad
    """
    # TODO: Implementierung
    raise NotImplementedError("disk endpoint not yet implemented")


@api.route("/logs")
def logs():
    """
    Gibt die letzten Log-Einträge zurück.
    Query-Parameter:
    - limit: Anzahl der zurückzugebenden Einträge (optional)
    """
    # TODO: Implementierung
    raise NotImplementedError("logs endpoint not yet implemented")


@api.route("/last_run")
def last_run():
    """
    Gibt die Logs des letzten Durchlaufs zurück.
    """
    # TODO: Implementierung
    raise NotImplementedError("last_run endpoint not yet implemented")


# -------------------- DATABASE --------------------
@api.route("/database")
def database():
    """
    Gibt alle Datenbank-Einträge zurück.
    Query-Parameter:
    - include_deleted: True/False um gelöschte Einträge einzuschließen
    """
    # TODO: Implementierung
    raise NotImplementedError("database endpoint not yet implemented")


@api.route("/counts")
def counts():
    """
    Gibt verschiedene Statistiken zurück:
    - Anzahl aller Animes
    - Anzahl kompletter Animes
    - Anzahl deutsch-kompletter Animes
    - Anzahl gelöschter Animes
    - etc.
    """
    # TODO: Implementierung
    raise NotImplementedError("counts endpoint not yet implemented")


@api.route("/export", methods=["POST"])
def export():
    """
    Exportiert die Datenbank als JSON-Datei zum Download.
    """
    # TODO: Implementierung
    raise NotImplementedError("export endpoint not yet implemented")


# -------------------- ANIME MANAGEMENT --------------------
@api.route("/add_link", methods=["POST"])
def add_link():
    """
    Fügt einen neuen Anime/Serie zur Datenbank hinzu.
    POST JSON:
    - url: URL des Anime/Serie
    - title: Titel (optional, wird sonst von URL extrahiert)
    """
    # TODO: Implementierung
    raise NotImplementedError("add_link endpoint not yet implemented")


@api.route("/search", methods=["POST"])
def search():
    """
    Sucht nach Animes/Serien auf verschiedenen Providern.
    POST JSON:
    - query: Suchbegriff
    - provider: "aniworld" | "sto" | "both"
    """
    # TODO: Implementierung
    raise NotImplementedError("search endpoint not yet implemented")


@api.route("/anime", methods=["DELETE"])
def delete_anime():
    """
    Markiert einen Anime als gelöscht.
    Query-Parameter:
    - id: Anime-ID
    """
    # TODO: Implementierung
    raise NotImplementedError("delete_anime endpoint not yet implemented")


@api.route("/anime/restore", methods=["POST"])
def restore_anime():
    """
    Stellt einen gelöschten Anime wieder her.
    POST JSON:
    - id: Anime-ID
    """
    # TODO: Implementierung
    raise NotImplementedError("restore_anime endpoint not yet implemented")


# -------------------- CHECKING --------------------
@api.route("/check")
def check():
    """
    Führt einen Check auf neue Episoden/Filme durch.
    Query-Parameter:
    - id: Anime-ID (optional, sonst alle)
    """
    # TODO: Implementierung
    raise NotImplementedError("check endpoint not yet implemented")


# -------------------- MAIN PAGE --------------------
@api.route("/")
def index():
    """
    Haupt-Seite (HTML Template oder React App).
    """
    # TODO: Implementierung - render_template() oder send_file() für SPA
    raise NotImplementedError("index endpoint not yet implemented")
