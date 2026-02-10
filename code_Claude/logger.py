"""
logger.py – Thread-sicheres Logging-System für AniLoader.

Schreibt in all_logs.txt (Gesamthistorie) und last_run.txt (aktueller Lauf).
"""

import os
import sys
import time
import threading
from datetime import datetime, timedelta

from config import all_logs_path, log_path

_lock = threading.Lock()
_log_lines: list[str] = []     # In-Memory-Kopie für Abwärtskompatibilität


def log(msg: str) -> None:
    """Thread-safe: Schreibt Zeitstempel + Nachricht in Dateien und stdout."""
    ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{ts} {msg}"

    with _lock:
        _log_lines.append(line)
        try:
            with open(all_logs_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
            with open(log_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    try:
        print(line, flush=True)
    except Exception:
        try:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except Exception:
            pass


def clear_last_run() -> None:
    """Leert last_run.txt zu Beginn eines neuen Laufs."""
    try:
        with open(log_path(), "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass


def read_last_run() -> str:
    """Gibt den Inhalt von last_run.txt zurück."""
    lp = log_path()
    if os.path.exists(lp):
        with open(lp, "r", encoding="utf-8") as f:
            return f.read()
    return "No previous log available."


def read_all_logs() -> list[str]:
    """Gibt alle Log-Zeilen aus all_logs.txt zurück."""
    alp = all_logs_path()
    if os.path.exists(alp):
        with open(alp, "r", encoding="utf-8") as f:
            content = f.read()
        lines = content.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        return lines
    return []


def cleanup_old_logs(days: int = 7) -> None:
    """Entfernt Log-Einträge älter als `days` Tage aus all_logs.txt."""
    alp = all_logs_path()
    if not os.path.exists(alp):
        return

    try:
        cutoff = datetime.now() - timedelta(days=days)
        with open(alp, "r", encoding="utf-8") as f:
            lines = f.readlines()

        kept: list[str] = []
        for line in lines:
            try:
                if line.startswith("["):
                    ts_str = line[1:20]
                    log_date = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    if log_date >= cutoff:
                        kept.append(line)
                else:
                    kept.append(line)
            except (ValueError, IndexError):
                kept.append(line)

        if len(kept) < len(lines):
            with open(alp, "w", encoding="utf-8") as f:
                f.writelines(kept)
            removed = len(lines) - len(kept)
            print(f"[CLEANUP] {removed} alte Log-Einträge entfernt (älter als {days} Tage)")
    except Exception as e:
        print(f"[CLEANUP-ERROR] {e}")
