import sqlite3
from pathlib import Path
from config import load_config
from html_request import get_series_title

def get_db_path():
    try:
        config_data = load_config()
        if config_data is False:
            raise Exception("Fehler beim Laden der Konfiguration. Bitte überprüfen Sie die config.json.")
        data_path =  str(config_data.get('data_folder_path'))
        db_path = f"{data_path}/AniLoader.db"
        db_path = Path(db_path)
    except Exception as e:
        print(f"[CONFIG-ERROR] database.py: {e}")
    return db_path

def connect() -> sqlite3.Connection:
    return sqlite3.connect(get_db_path())

def init_db() -> None:
    """Erstellt/migriert die Tabellen und reindiziert anime-IDs sequentiell."""
    database = connect()
    cursor = database.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anime (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            url TEXT UNIQUE,
            complete INTEGER DEFAULT 0,
            deutsch_komplett INTEGER DEFAULT 0,
            deleted INTEGER DEFAULT 0,
            fehlende_deutsch_folgen TEXT DEFAULT '[]',
            last_film INTEGER DEFAULT 0,
            last_episode INTEGER DEFAULT 0,
            last_season INTEGER DEFAULT 0,
            folder_name TEXT DEFAULT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_id INTEGER,
            anime_url TEXT UNIQUE,
            added_at INTEGER DEFAULT (strftime('%s','now'))
        )
    """)

    # Migration: position-Spalte in queue
    try:
        cursor.execute("PRAGMA table_info(queue)")
        cols = [r[1] for r in cursor.fetchall()]
        if "position" not in cols:
            cursor.execute("ALTER TABLE queue ADD COLUMN position INTEGER")
            cursor.execute("SELECT id FROM queue ORDER BY added_at ASC, id ASC")
            for idx, (qid,) in enumerate(cursor.fetchall(), start=1):
                cursor.execute("UPDATE queue SET position = ? WHERE id = ?", (idx, qid))
            database.commit()
            print("[DB] queue.position Spalte hinzugefügt und initialisiert")
    except Exception as exception:
        print(f"[DB-ERROR] Migration queue.position: {exception}")

    # Migration: folder_name-Spalte in anime
    try:
        cursor.execute("PRAGMA table_info(anime)")
        cols = [r[1] for r in cursor.fetchall()]
        if "folder_name" not in cols:
            cursor.execute("ALTER TABLE anime ADD COLUMN folder_name TEXT DEFAULT NULL")
            database.commit()
            print("[DB] anime.folder_name Spalte hinzugefügt")
    except Exception as exception:
        print(f"[DB-ERROR] Migration anime.folder_name: {exception}")

    database.commit()
    database.close()

def update_index():
    """Reindexiert die anime-Tabelle sequentiell (mit Transaktions-Sicherheit)"""
    database = connect()
    cursor = database.cursor()
    try:
        database.execute("BEGIN TRANSACTION")
        cursor.execute("CREATE TEMPORARY TABLE anime_backup AS SELECT * FROM anime;")
        cursor.execute("DROP TABLE anime;")
        cursor.execute("""
            CREATE TABLE anime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, url TEXT UNIQUE,
                complete INTEGER DEFAULT 0,
                deutsch_komplett INTEGER DEFAULT 0,
                deleted INTEGER DEFAULT 0,
                fehlende_deutsch_folgen TEXT DEFAULT '[]',
                last_film INTEGER DEFAULT 0,
                last_episode INTEGER DEFAULT 0,
                last_season INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            INSERT INTO anime (title, url, complete, deutsch_komplett, deleted, fehlende_deutsch_folgen, last_film, last_episode, last_season)
            SELECT title, url, complete, deutsch_komplett, deleted, fehlende_deutsch_folgen, last_film, last_episode, last_season
            FROM anime_backup
        """)
        cursor.execute("DROP TABLE anime_backup;")
        database.commit()
        print("[DB] Index reindexiert")
    except Exception as e:
        database.rollback()
        print(f"[DB-ERROR] update_index fehlgeschlagen, Rollback übernommen: {e}")
    finally:
        database.close()

def add_url_to_db(url):
    if url.startswith("https://s.to") or url.startswith("https://aniworld.to"): 
        database = connect()
        cursor = database.cursor()
        title = get_series_title(url)
        if not title:
            print(f"[ERROR] Konnte Titel für URL nicht abrufen: {url}")
            title = url
        cursor.execute("INSERT OR IGNORE INTO anime (url, title) VALUES (?, ?)", (url, title))
        database.commit()
        database.close()
    else:
        print(f"Ungültige URL: {url}. Nur s.to und aniworld.to URLs werden unterstützt.")

def set_completion_status(db_id: int, complete: bool) -> None:
    database = connect()
    cursor = database.cursor()
    cursor.execute("UPDATE anime SET complete = ? WHERE id = ?", (1 if complete else 0, id))
    database.commit()
    database.close()

def set_last_downloaded_episode(db_id: int, season: int, episode: int) -> None:
    database = connect()
    cursor = database.cursor()
    cursor.execute("UPDATE anime SET last_season = ?, last_episode = ? WHERE id = ?", (season, episode, db_id))
    database.commit()
    database.close()

def set_last_downloaded_season(db_id: int, season: int) -> None:
    database = connect()
    cursor = database.cursor()
    cursor.execute("UPDATE anime SET last_season = ? WHERE id = ?", (season, db_id))
    database.commit()
    database.close()

def set_last_downloaded_film(db_id: int, film_number: int) -> None:
    database = connect()
    cursor = database.cursor()
    cursor.execute("UPDATE anime SET last_film = ? WHERE id = ?", (film_number, db_id))
    database.commit()
    database.close()

def set_deutsch_completion(db_id: int, complete: bool) -> None:
    database = connect()
    cursor = database.cursor()
    cursor.execute("UPDATE anime SET deutsch_komplett = ? WHERE id = ?", (1 if complete else 0, id))
    database.commit()
    database.close()

def set_missing_german_episodes(db_id: int, fehlende_folgen: list) -> None:
    database = connect()
    cursor = database.cursor()
    cursor.execute("UPDATE anime SET fehlende_deutsch_folgen = ? WHERE id = ?", (str(fehlende_folgen), id))
    database.commit()
    database.close()

def update_title():
    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT db_id, url, title FROM anime")
    for anime_id, url, current_title in cursor.fetchall():
        if not current_title or current_title == url:
            title = get_series_title(url)
            if title:
                cursor.execute("UPDATE anime SET title = ? WHERE id = ?", (title, anime_id))
    database.commit()
    database.close()

def get_last_downloaded_episode(db_id: int) ->int:
    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT last_episode FROM anime WHERE id = ?", (db_id,))
    result = cursor.fetchone()
    database.close()
    if result:
        return result[0]
    raise Exception(f"Keine Serie mit ID {db_id} gefunden.")

def get_last_downloaded_season(db_id: int) ->int:
    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT last_season FROM anime WHERE id = ?", (db_id,))
    result = cursor.fetchone()
    database.close()
    if result:
        return result[0]
    raise Exception(f"Keine Serie mit ID {db_id} gefunden.")

def get_last_downloaded_film(db_id: int) ->int:
    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT last_film FROM anime WHERE id = ?", (db_id,))
    result = cursor.fetchone()
    database.close()
    if result:
        return result[0]
    raise Exception(f"Keine Serie mit ID {db_id} gefunden.")

def get_completion_status(db_id: int) -> bool:
    """
    Docstring for get_completion_status
    
    :param db_id: ID der Serie
    :type db_id: int
    :return: Status der Vollständigkeit (True wenn komplett, False wenn nicht)
    :rtype: bool
    """
    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT complete FROM anime WHERE id = ?", (db_id,))
    result = cursor.fetchone()
    database.close()
    if result is not None:
        return bool(result[0])
    raise Exception(f"Keine Serie mit ID {db_id} gefunden.")

def get_deutsch_completion_status(db_id: int) -> bool:
    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT deutsch_komplett FROM anime WHERE id = ?", (db_id,))
    result = cursor.fetchone()
    database.close()
    if result is not None:
        return bool(result[0])
    raise Exception(f"Keine Serie mit ID {db_id} gefunden.")

def get_missing_german_episodes(db_id: int) -> list:
    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT fehlende_deutsch_folgen FROM anime WHERE id = ?", (db_id,))
    result = cursor.fetchone()
    database.close()
    if result is not None:
        return eval(result[0])  # Achtung: eval kann gefährlich sein, wenn die Daten nicht vertrauenswürdig sind
    raise Exception(f"Keine Serie mit ID {db_id} gefunden.")

def get_series_url_from_db(db_id: int) -> str:
    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT url FROM anime WHERE id = ?", (db_id,))
    result = cursor.fetchone()
    database.close()
    if result:
        return result[0]
    raise Exception(f"Keine Serie mit ID {db_id} gefunden.")

def get_series_title_from_db(db_id: int) -> str:

    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT title FROM anime WHERE id = ?", (db_id,))
    result = cursor.fetchone()
    database.close()
    if result:
        return result[0]
    raise Exception(f"Keine Serie mit ID {db_id} gefunden.")

def check_index_exist(index: int) -> bool:
    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT id FROM anime WHERE id = ?", (index,))
    result = cursor.fetchone()
    database.close()
    if result is not None:
        return True
    return False

def get_folder_name_from_db(db_id: int) -> str | None:
    """Gibt den gespeicherten Ordnernamen für eine Serie zurück (z.B. 'Titel (2020) [tt1234567]')."""
    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT folder_name FROM anime WHERE id = ?", (db_id,))
    result = cursor.fetchone()
    database.close()
    if result:
        return result[0]
    return None

def set_folder_name_in_db(db_id: int, folder_name: str) -> None:
    """Speichert den Ordnernamen für eine Serie in der Datenbank."""
    database = connect()
    cursor = database.cursor()
    cursor.execute("UPDATE anime SET folder_name = ? WHERE id = ?", (folder_name, db_id))
    database.commit()
    database.close()

def get_db_id_by_url(url: str) -> int | None:
    """Gibt die Datenbank-ID für eine URL zurück."""
    database = connect()
    cursor = database.cursor()
    cursor.execute("SELECT id FROM anime WHERE url = ?", (url,))
    result = cursor.fetchone()
    database.close()
    if result:
        return result[0]
    return None
