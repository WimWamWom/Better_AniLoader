"""
database.py – SQLite-Datenbankoperationen für AniLoader.

Verwaltet die anime- und queue-Tabellen.
Alle Funktionen arbeiten mit der DB aus config.db_path().
"""

import json
import sqlite3
from typing import Any

from config import db_path
from logger import log


# ═══════════════════════════════════════════════════════════════════════════════
#  Initialisierung
# ═══════════════════════════════════════════════════════════════════════════════

def _connect() -> sqlite3.Connection:
    return sqlite3.connect(db_path())


def init_db() -> None:
    """Erstellt/migriert die Tabellen und reindiziert anime-IDs sequentiell."""
    conn = _connect()
    c = conn.cursor()

    c.execute("""
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
            last_season INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_id INTEGER,
            anime_url TEXT UNIQUE,
            added_at INTEGER DEFAULT (strftime('%s','now'))
        )
    """)

    # Migration: position-Spalte in queue
    try:
        c.execute("PRAGMA table_info(queue)")
        cols = [r[1] for r in c.fetchall()]
        if "position" not in cols:
            c.execute("ALTER TABLE queue ADD COLUMN position INTEGER")
            c.execute("SELECT id FROM queue ORDER BY added_at ASC, id ASC")
            for idx, (qid,) in enumerate(c.fetchall(), start=1):
                c.execute("UPDATE queue SET position = ? WHERE id = ?", (idx, qid))
            conn.commit()
            log("[DB] queue.position Spalte hinzugefügt und initialisiert")
    except Exception as e:
        log(f"[DB-ERROR] Migration queue.position: {e}")

    # IDs sequentiell neu vergeben
    c.execute("CREATE TEMPORARY TABLE anime_backup AS SELECT * FROM anime;")
    c.execute("DROP TABLE anime;")
    c.execute("""
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
    c.execute("""
        INSERT INTO anime (title, url, complete, deutsch_komplett, deleted,
                           fehlende_deutsch_folgen, last_film, last_episode, last_season)
        SELECT title, url, complete, deutsch_komplett, deleted,
               fehlende_deutsch_folgen, last_film, last_episode, last_season
        FROM anime_backup
    """)
    c.execute("DROP TABLE anime_backup;")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  Anime CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def insert_anime(url: str, title: str | None = None) -> bool:
    """Fügt einen Anime ein oder reaktiviert ihn falls deleted."""
    from network import fetch_series_title  # Lazy import um Zirkeldependenz zu vermeiden

    conn = _connect()
    c = conn.cursor()
    try:
        if not title:
            try:
                title = fetch_series_title(url)
            except Exception:
                title = None
            if not title:
                import re
                m = re.search(r"/(?:anime|serie)/stream/([^/]+)", url)
                title = m.group(1).replace("-", " ").title() if m else url

        c.execute("SELECT id, deleted FROM anime WHERE url = ?", (url,))
        row = c.fetchone()
        if row:
            aid, deleted = row
            if deleted:
                c.execute("UPDATE anime SET deleted = 0, title = ? WHERE id = ?", (title, aid))
                conn.commit()
                log(f"[DB] Anime reaktiviert: {title} (ID {aid})")
            else:
                log(f"[DB] Anime existiert bereits: {title} (ID {aid})")
        else:
            c.execute("INSERT INTO anime (url, title) VALUES (?, ?)", (url, title))
            conn.commit()
            log(f"[DB] Neuer Anime eingefügt: {title}")
        return True
    except Exception as e:
        log(f"[DB-ERROR] insert_anime: {e}")
        return False
    finally:
        conn.close()


def update_anime(anime_id: int, **kwargs: Any) -> None:
    """Aktualisiert beliebige Felder eines Anime-Eintrags."""
    conn = _connect()
    c = conn.cursor()
    fields, values = [], []
    will_complete = False

    for key, val in kwargs.items():
        if key == "fehlende_deutsch_folgen":
            val = json.dumps(val)
        fields.append(f"{key} = ?")
        values.append(val)
        if key == "complete" and bool(val):
            will_complete = True

    values.append(anime_id)
    if fields:
        c.execute(f"UPDATE anime SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
    conn.close()

    if will_complete:
        try:
            queue_delete_by_anime_id(anime_id)
            queue_prune_completed()
        except Exception as e:
            log(f"[QUEUE] Entfernen nach Abschluss fehlgeschlagen: {e}")


def load_anime() -> list[dict]:
    """Lädt alle Anime-Einträge als Liste von Dicts."""
    conn = _connect()
    c = conn.cursor()
    c.execute("""
        SELECT id, title, url, complete, deutsch_komplett, deleted,
               fehlende_deutsch_folgen, last_film, last_episode, last_season
        FROM anime ORDER BY id
    """)
    rows = c.fetchall()
    conn.close()

    return [
        {
            "id": r[0], "title": r[1], "url": r[2],
            "complete": bool(r[3]), "deutsch_komplett": bool(r[4]),
            "deleted": bool(r[5]),
            "fehlende_deutsch_folgen": json.loads(r[6] or "[]"),
            "last_film": r[7], "last_episode": r[8], "last_season": r[9],
        }
        for r in rows
    ]


def check_deutsch_komplett(anime_id: int) -> bool:
    """Setzt deutsch_komplett=1 wenn keine fehlenden deutschen Folgen mehr vorliegen."""
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT fehlende_deutsch_folgen FROM anime WHERE id = ?", (anime_id,))
    row = c.fetchone()
    conn.close()
    fehlende = json.loads(row[0]) if row and row[0] else []
    if not fehlende:
        update_anime(anime_id, deutsch_komplett=1)
        log(f"[INFO] Serien-ID {anime_id} komplett auf Deutsch markiert")
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
#  Queue
# ═══════════════════════════════════════════════════════════════════════════════

def queue_add(anime_id: int) -> bool:
    try:
        conn = _connect()
        c = conn.cursor()
        c.execute("SELECT id, url, complete FROM anime WHERE id = ?", (anime_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False
        _, aurl, complete_flag = row
        if complete_flag:
            log(f"[QUEUE] Anime {anime_id} ist bereits komplett.")
            conn.close()
            return False
        c.execute("SELECT id FROM queue WHERE anime_url = ?", (aurl,))
        if c.fetchone():
            conn.close()
            return True
        c.execute("SELECT COALESCE(MAX(position), 0) FROM queue")
        next_pos = (c.fetchone() or [0])[0] + 1
        c.execute("INSERT INTO queue (anime_id, anime_url, position) VALUES (?, ?, ?)",
                  (anime_id, aurl, next_pos))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log(f"[DB-ERROR] queue_add: {e}")
        return False


def queue_list() -> list[dict]:
    try:
        conn = _connect()
        c = conn.cursor()
        c.execute("""
            SELECT q.id, a.id, a.title, COALESCE(q.position, 0)
            FROM queue q LEFT JOIN anime a ON a.url = q.anime_url
            ORDER BY position ASC, q.added_at ASC, q.id ASC
        """)
        rows = c.fetchall()
        conn.close()
        return [{"id": r[0], "anime_id": r[1], "title": r[2], "position": r[3]} for r in rows]
    except Exception as e:
        log(f"[DB-ERROR] queue_list: {e}")
        return []


def queue_clear() -> bool:
    try:
        conn = _connect()
        c = conn.cursor()
        c.execute("DELETE FROM queue")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log(f"[DB-ERROR] queue_clear: {e}")
        return False


def queue_pop_next() -> int | None:
    """Entnimmt das erste Queue-Element und gibt anime_id zurück."""
    try:
        conn = _connect()
        c = conn.cursor()
        c.execute("SELECT id, anime_url FROM queue ORDER BY position ASC, added_at ASC, id ASC LIMIT 1")
        row = c.fetchone()
        if not row:
            conn.close()
            return None
        qid, aurl = row
        c.execute("DELETE FROM queue WHERE id = ?", (qid,))
        conn.commit()
        conn.close()
        # URL → aktuelle anime_id mappen
        conn2 = _connect()
        c2 = conn2.cursor()
        c2.execute("SELECT id FROM anime WHERE url = ?", (aurl,))
        r2 = c2.fetchone()
        conn2.close()
        return r2[0] if r2 else None
    except Exception as e:
        log(f"[DB-ERROR] queue_pop_next: {e}")
        return None


def queue_prune_completed() -> bool:
    try:
        conn = _connect()
        c = conn.cursor()
        c.execute("DELETE FROM queue WHERE anime_url IN (SELECT url FROM anime WHERE complete = 1)")
        c.execute("DELETE FROM queue WHERE anime_url NOT IN (SELECT url FROM anime)")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log(f"[DB-ERROR] queue_prune_completed: {e}")
        return False


def queue_delete_by_anime_id(anime_id: int) -> bool:
    try:
        conn = _connect()
        c = conn.cursor()
        c.execute("DELETE FROM queue WHERE anime_id = ?", (anime_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log(f"[DB-ERROR] queue_delete_by_anime_id: {e}")
        return False


def queue_delete(qid: int) -> bool:
    try:
        conn = _connect()
        c = conn.cursor()
        c.execute("DELETE FROM queue WHERE id = ?", (qid,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log(f"[DB-ERROR] queue_delete: {e}")
        return False


def queue_reorder(order_ids: list[int]) -> bool:
    try:
        if not isinstance(order_ids, list) or not all(isinstance(x, int) for x in order_ids):
            return False
        conn = _connect()
        c = conn.cursor()
        for pos, qid in enumerate(order_ids, start=1):
            c.execute("UPDATE queue SET position = ? WHERE id = ?", (pos, qid))
        placeholders = ",".join(["?"] * len(order_ids)) if order_ids else None
        if placeholders:
            c.execute(f"SELECT id FROM queue WHERE id NOT IN ({placeholders}) ORDER BY position ASC, added_at ASC, id ASC",
                      order_ids)
        else:
            c.execute("SELECT id FROM queue ORDER BY position ASC, added_at ASC, id ASC")
        rest = [r[0] for r in c.fetchall()]
        for idx, qid in enumerate(rest, start=len(order_ids) + 1):
            c.execute("UPDATE queue SET position = ? WHERE id = ?", (idx, qid))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        log(f"[DB-ERROR] queue_reorder: {e}")
        return False


def queue_cleanup_ids(anime_ids: list[int]) -> None:
    """Entfernt alle Queue-Einträge für gegebene anime_ids."""
    if not anime_ids:
        return
    try:
        conn = _connect()
        c = conn.cursor()
        placeholders = ",".join(["?"] * len(anime_ids))
        c.execute(f"DELETE FROM queue WHERE anime_id IN ({placeholders})", anime_ids)
        conn.commit()
        conn.close()
        log("[QUEUE] Verarbeitete Einträge aus der Warteschlange entfernt.")
    except Exception as e:
        log(f"[DB-ERROR] queue cleanup: {e}")
