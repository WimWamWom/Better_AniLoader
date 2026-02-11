import sys
from datetime import datetime
from config import DATA_DIR

class Logger:
    def __init__(self):
        self.log_file = DATA_DIR / "last_run.txt"
        self.backup_dir = DATA_DIR / "run_logs_bak"
        self.file_handle = None
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
    def start_logging(self):
        """Startet das Logging für einen neuen Run."""
        # Backup der alten last_run.txt erstellen
        if self.log_file.exists() and self.log_file.stat().st_size > 0:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_file = self.backup_dir / f"run_{timestamp}.txt"
            try:
                self.log_file.rename(backup_file)
            except Exception as e:
                print(f"[LOGGER-ERROR] Backup fehlgeschlagen: {e}")
        
        # Neue last_run.txt öffnen
        try:
            self.file_handle = open(self.log_file, 'w', encoding='utf-8')
            sys.stdout = self
            sys.stderr = self
            self.log(f"=== Run gestartet: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
        except Exception as e:
            print(f"[LOGGER-ERROR] Konnte Log-Datei nicht öffnen: {e}")
    
    def stop_logging(self):
        """Stoppt das Logging."""
        if self.file_handle:
            self.log(f"=== Run beendet: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
            sys.stdout = self.original_stdout
            sys.stderr = self.original_stderr
            self.file_handle.close()
            self.file_handle = None
    
    def write(self, message):
        """Schreibt in Console und Datei."""
        self.original_stdout.write(message)
        if self.file_handle:
            self.file_handle.write(message)
            self.file_handle.flush()
    
    def flush(self):
        """Flush für stdout-Kompatibilität."""
        self.original_stdout.flush()
        if self.file_handle:
            self.file_handle.flush()
    
    def log(self, message):
        """Loggt eine Nachricht mit Timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

# Globale Logger-Instanz
_logger = Logger()

def start_run_logging():
    """Startet das Logging für einen neuen Download-Run."""
    _logger.start_logging()

def stop_run_logging():
    """Stoppt das Logging."""
    _logger.stop_logging()

def log(message):
    """Loggt eine Nachricht."""
    _logger.log(message)
