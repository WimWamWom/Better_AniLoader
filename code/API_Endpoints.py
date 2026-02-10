import os
from flask import Blueprint, request, jsonify, render_template, send_file
from werkzeug.utils import secure_filename
import shutil
import json
import threading
from pathlib import Path 
from main import PATH_ANILOADER_TXT_BAK
from config import load_config, save_config, DATA_DIR
from database import connect, add_url_to_db
from helper import sanitize_url
from txt_manager import write_to_aniloader_txt_bak

# Blueprint erstellen
api = Blueprint('api', __name__)

# Globaler Status für Downloads
download_status = {
    'status': 'idle',
    'mode': None,
    'current_id': None,
    'current_title': None,
    'started_at': None
}

download_thread = None
download_lock = threading.Lock()  # Thread-Safety für Downloads


# -------------------- FILE UPLOAD --------------------
@api.route("/upload_txt", methods=["POST"])
@api.route("/upload", methods=["POST"])
def upload_txt():
    """
    Endpoint zum Hochladen einer TXT-Datei mit URLs.
    """
    try:
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'msg': 'Keine Datei hochgeladen'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'msg': 'Keine Datei ausgewählt'}), 400
        
        # Sicherer Dateiname (Path Traversal Protection)
        filename = secure_filename(file.filename)
        if not filename.endswith('.txt'):
            return jsonify({'status': 'error', 'msg': 'Nur TXT-Dateien erlaubt'}), 400
        
        content = file.read().decode('utf-8')
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        
        added = 0
        for line in lines:
            if line.startswith('http'):
                clean_line = sanitize_url(line)
                write_to_aniloader_txt_bak(PATH_ANILOADER_TXT_BAK, [clean_line])
                add_url_to_db(clean_line)
                added += 1
        
        return jsonify({'status': 'ok', 'msg': f'{added} URLs hinzugefügt', 'count': added}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500


# -------------------- DOWNLOAD CONTROL --------------------
@api.route("/start_download", methods=["POST", "GET"])
@api.route("/start", methods=["POST"])
def start_download():
    """
    Startet den Download-Prozess.
    """
    global download_status, download_thread
    
    # Thread-Safety: Lock verwenden um Race Conditions zu vermeiden
    with download_lock:
        try:
            data = request.get_json() or {}
            mode = data.get('mode', 'default')
            
            if download_status['status'] == 'running':
                return jsonify({'status': 'error', 'msg': 'Download läuft bereits'}), 400
        
        from downloader import download
        import time
        
        def run_download():
            global download_status
            download_status['status'] = 'running'
            download_status['mode'] = mode
            download_status['started_at'] = time.time()
            try:
                download(mode)
            finally:
                download_status['status'] = 'idle'
                download_status['mode'] = None
                download_status['current_id'] = None
                download_status['current_title'] = None
        
            download_thread = threading.Thread(target=run_download, daemon=True)
            download_thread.start()
            
            return jsonify({'status': 'ok', 'msg': f'Download gestartet ({mode})'}), 200
        except Exception as e:
            download_status['status'] = 'idle'
            return jsonify({'status': 'error', 'msg': str(e)}), 500

@api.route("/status")
def status():
    """
    Gibt den aktuellen Download-Status zurück.
    """
    return jsonify(download_status), 200

@api.route("/stop_download", methods=["POST"])
@api.route("/stop", methods=["POST"])
def stop_download():
    """
    Stoppt den laufenden Download.
    """
    global download_status
    if download_status['status'] == 'running':
        download_status['status'] = 'stopped'
        return jsonify({'status': 'ok', 'msg': 'Download wird gestoppt'}), 200
    return jsonify({'status': 'ok', 'msg': 'Kein Download aktiv'}), 200

@api.route("/health")
def health():
    """
    Health-Check Endpoint für Monitoring.
    """
    return jsonify({"status": "ok"}), 200


# -------------------- CONFIGURATION --------------------
@api.route("/config", methods=["GET", "POST"])
def config():
    """
    GET: Gibt die aktuelle Konfiguration zurück
    POST: Speichert eine neue Konfiguration
    """
    if request.method == 'GET':
        config = load_config()
        if config:
            return jsonify({'status': 'ok', 'config': config}), 200
        return jsonify({'status': 'error', 'msg': 'Config konnte nicht geladen werden'}), 500
    
    else:  # POST
        try:
            data = request.get_json()
            if save_config(data):
                return jsonify({'status': 'ok', 'msg': 'Konfiguration gespeichert', 'config': data}), 200
            return jsonify({'status': 'error', 'msg': 'Speichern fehlgeschlagen'}), 500
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)}), 500


@api.route("/pick_folder", methods=["GET"])
def pick_folder():
    """
    Öffnet einen Ordner-Auswahl-Dialog (tkinter).
    """
    try:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory()
        root.destroy()
        if folder:
            return jsonify({'status': 'ok', 'selected': folder}), 200
        return jsonify({'status': 'canceled'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500



# -------------------- SYSTEM INFO --------------------
@api.route('/disk')
def disk():
    """
    Gibt Informationen über den verfügbaren Speicherplatz zurück.
    """
    try:
        config = load_config()
        if not config:
            return jsonify({'status': 'error', 'msg': 'Config konnte nicht geladen werden', 'free_gb': None}), 500
        path = (config.get('download_path', '.'))
        stat = shutil.disk_usage(path)
        free_gb = stat.free / (1024**3)
        return jsonify({'status': 'ok', 'free_gb': round(free_gb, 2), 'path': path}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e), 'free_gb': None}), 500


@api.route("/last_run")
def last_run():
    """
    Gibt die Logs vom letzten Download-Run zurück.
    """
    try:
        config =load_config()
        if not config:
            return jsonify({'status': 'error', 'msg': 'Config konnte nicht geladen werden'}), 500
        data_dir = Path(config.get('data_dir'))
        
        log_file = Path(data_dir / 'last_run.txt')
        if not log_file.exists():
            return jsonify([]), 200
        
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        return jsonify([line.strip() for line in lines]), 200
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500


# -------------------- DATABASE --------------------
@api.route("/database")
@api.route("/overview")
def database():
    """
    Gibt alle Datenbank-Einträge zurück.
    """
    try:
        db = connect()
        cursor = db.cursor()
        
        q = request.args.get('q', '').strip()
        complete = request.args.get('complete', '').strip()
        deutsch = request.args.get('deutsch', '').strip()
        sort_by = request.args.get('sort_by', 'id')
        order = request.args.get('order', 'asc')
        
        # SQL-Injection Protection: Whitelist für sort_by und order
        allowed_sort = ['id', 'title', 'last_film', 'last_episode', 'last_season', 'complete', 'deutsch_komplett']
        sort_by = sort_by if sort_by in allowed_sort else 'id'
        order = 'ASC' if order.upper() == 'ASC' else 'DESC'
        
        query = "SELECT * FROM anime WHERE 1=1"
        params = []
        
        if q:
            query += " AND (title LIKE ? OR url LIKE ?)"
            params.extend([f'%{q}%', f'%{q}%'])
        
        if complete == '1':
            query += " AND complete = 1"
        elif complete == '0':
            query += " AND complete = 0"
        elif complete == 'deleted':
            query += " AND deleted = 1"
        
        if deutsch == '1':
            query += " AND deutsch_komplett = 1"
        elif deutsch == '0':
            query += " AND deutsch_komplett = 0"
        
        query += f" ORDER BY {sort_by} {order}"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        result = []
        for row in rows:
            item = dict(zip(columns, row))
            try:
                item['fehlende'] = eval(item.get('fehlende_deutsch_folgen', '[]'))
            except:
                item['fehlende'] = []
            result.append(item)
        
        db.close()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500


@api.route("/counts")
def counts():
    """
    Gibt verschiedene Statistiken zurück.
    """
    try:
        db = connect()
        cursor = db.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM anime")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM anime WHERE complete = 1")
        complete = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM anime WHERE deutsch_komplett = 1")
        deutsch = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM anime WHERE deleted = 1")
        deleted = cursor.fetchone()[0]
        
        db.close()
        return jsonify({
            'total': total,
            'complete': complete,
            'deutsch_komplett': deutsch,
            'deleted': deleted,
            'active': total - deleted
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500



@api.route("/export", methods=["POST"])
def export():
    """
    Exportiert die Datenbank als JSON-Datei zum Download.
    """
    try:
        config =load_config()
        if not config:
            return jsonify({'status': 'error', 'msg': 'Config konnte nicht geladen werden'}), 500
        data_dir = Path(config.get('data_dir'))
        
        db = connect()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM anime")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        result = [dict(zip(columns, row)) for row in rows]
        db.close()
        
        export_file = Path(data_dir / 'AniLoader_DB_export.json')
        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        return send_file(export_file, as_attachment=True, download_name='anime_export.json')
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500


# -------------------- ANIME MANAGEMENT --------------------
@api.route("/add_link", methods=["POST"])
@api.route("/add", methods=["POST"])
def add_link():
    """
    Fügt einen neuen Anime/Serie zur Datenbank hinzu.
    """
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'status': 'error', 'msg': 'Keine URL angegeben'}), 400
        
        if not (url.startswith('https://aniworld.to') or url.startswith('https://s.to')):
            return jsonify({'status': 'error', 'msg': 'Ungültige URL'}), 400
        
        clean_url = sanitize_url(url)
        add_url_to_db(clean_url)
        
        return jsonify({'status': 'ok', 'msg': 'URL erfolgreich hinzugefügt'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500


@api.route("/search", methods=["POST", "GET"])
def search():
    """
    Sucht nach Animes/Serien.
    """
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            query = data.get('query', '').strip()
        else:
            query = request.args.get('q', '').strip()
        
        if not query:
            return jsonify({'status': 'error', 'msg': 'Kein Suchbegriff'}), 400
        
        # Dummy-Ergebnisse (kann später mit echten Suchergebnissen ersetzt werden)
        results = []
        return jsonify({'status': 'ok', 'results': results, 'count': len(results)}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500


@api.route("/delete", methods=["DELETE"])
@api.route("/anime", methods=["DELETE"])
def delete_anime():
    """
    Markiert einen Anime als gelöscht.
    """
    try:
        anime_id = request.args.get('id', type=int)
        if not anime_id:
            return jsonify({'status': 'error', 'msg': 'Keine ID angegeben'}), 400
        
        db = connect()
        cursor = db.cursor()
        cursor.execute("UPDATE anime SET deleted = 1 WHERE id = ?", (anime_id,))
        db.commit()
        db.close()
        
        return jsonify({'status': 'ok', 'msg': 'Anime als gelöscht markiert'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500


@api.route("/restore", methods=["POST"])
@api.route("/anime/restore", methods=["POST"])
def restore_anime():
    """
    Stellt einen gelöschten Anime wieder her.
    """
    try:
        data = request.get_json()
        anime_id = data.get('id')
        if not anime_id:
            return jsonify({'status': 'error', 'msg': 'Keine ID angegeben'}), 400
        
        db = connect()
        cursor = db.cursor()
        cursor.execute("UPDATE anime SET deleted = 0 WHERE id = ?", (anime_id,))
        db.commit()
        db.close()
        
        return jsonify({'status': 'ok', 'msg': 'Anime wiederhergestellt'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500



# -------------------- MAIN PAGE --------------------
@api.route("/")
def index():
    return render_template("index.html")
