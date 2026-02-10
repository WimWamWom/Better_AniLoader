# Better_AniLoader

Better_AniLoader ist ein Python-basiertes Tool zur Verwaltung und zum Download von Anime-Serien und -Filmen von verschiedenen Streaming-Seiten. Es bietet eine einfache Möglichkeit, Serien- und Filminformationen zu verwalten, Downloads zu automatisieren und die Datenbank aktuell zu halten.

## Grundfunktionen

- **Anime- und Serienverwaltung:**
  - Verwaltung von Serien- und Filmlisten über Textdateien (AniLoader.txt).
  - Automatisches Hinzufügen neuer Einträge, Vermeidung von Duplikaten.

- **Automatischer Download:**
  - Herunterladen von Episoden oder Filmen anhand der gespeicherten URLs.
  - Unterstützung verschiedener Download-Modi (z.B. nur neue Folgen, bestimmte Sprachen).

- **Backup und Wiederherstellung:**
  - Automatische Backups der AniLoader.txt zur Datensicherung.

- **Web-API:**
  - Bereitstellung einer REST-API (mittels Flask), um Funktionen auch über das Netzwerk zu steuern.

- **Konfigurierbarkeit:**
  - Einstellungen wie Port, Download-Modus und Backup-Verhalten über config.json anpassbar.

## Verzeichnisstruktur

- `code/` – Python-Quellcode und Module
- `data/` – Konfigurations- und Logdateien
- `Downloads/` – Zielordner für heruntergeladene Dateien
- `templates/` und `static/` – Web-Frontend (optional)

## Nutzung

1. **Konfiguration:**
   - Passe die Datei `data/config.json` nach deinen Bedürfnissen an.
2. **Start:**
   - Starte das Programm mit `python code/main.py`.
3. **Web-API:**
   - Nach dem Start ist die API unter der in der Konfiguration angegebenen Adresse erreichbar.

## Voraussetzungen

- Python 3.8+
- Abhängigkeiten aus `requirements.txt` (mit `pip install -r requirements.txt` installieren)

## Hinweise

- Die Nutzung erfolgt auf eigene Verantwortung. Beachte die rechtlichen Rahmenbedingungen deines Landes.
- Für Support oder Erweiterungen siehe die Quellcodedateien im `code/`-Verzeichnis.
