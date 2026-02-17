# Better AniLoader

<div align="center">
  <img src="https://raw.githubusercontent.com/WimWamWom/AniLoader/main/static/AniLoader.png" alt="AniLoader Logo" width="128" height="128">
  
  **Ein moderner Anime & Serien Download-Manager mit Web-Interface**
  
  [![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://docker.com)
  [![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
  [![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
  [![Unraid](https://img.shields.io/badge/Unraid-Compatible-orange.svg)](https://unraid.net)
</div>

## 📋 Inhaltsverzeichnis

- [Überblick](#überblick)
- [Features](#features)
- [Installation](#installation)
  - [Docker (empfohlen)](#docker-empfohlen)
  - [Manuelle Installation](#manuelle-installation)
- [Konfiguration](#konfiguration)
- [Verwendung](#verwendung)
  - [Web-Interface](#web-interface)
  - [Download-Modi](#download-modi)
  - [Tampermonkey-Skript](#tampermonkey-skript)
- [API-Dokumentation](#api-dokumentation)
- [Ordnerstruktur](#ordnerstruktur)
- [Entwicklung](#entwicklung)
- [FAQ & Troubleshooting](#faq--troubleshooting)
- [Unterstützung](#unterstützung)

## 🎯 Überblick

Better AniLoader ist ein verbesserter Download-Manager für Anime und Serien von **aniworld.to** und **s.to**. Das Projekt bietet ein benutzerfreundliches Web-Interface und automatisiert den Download-Prozess mit intelligenter Dateiorganisation.

### Hauptvorteile:
- 🌐 **Web-Interface**: Moderne Benutzeroberfläche für einfache Verwaltung
- 🐳 **Docker-Ready**: Einfache Installation auf Unraid, Synology, etc.
- 🔄 **Automatisierung**: Batch-Downloads mit verschiedenen Modi
- 📁 **Intelligente Organisation**: Flexible Ordnerstrukturen für Ihre Mediensammlung
- 🌍 **Browser-Integration**: Tampermonkey-Skript für One-Click-Downloads
- 🎥 **Multi-Format**: Unterstützt .mkv und .mp4 Downloads

## ✨ Features

### Core-Funktionen
- **Multi-Site Support**: aniworld.to und s.to Unterstützung
- **Download-Modi**: 
  - `default`: Standarddownloads in bevorzugter Sprache
  - `german`: Nur deutsche Synchronisation
  - `new`: Nur neue, noch nicht heruntergeladene Episoden
  - `check-missing`: Überprüfung auf fehlende deutsche Versionen
- **Intelligente Dateiorganisation**: 
  - Standard-Modus: Alles in einem Ordner
  - Separater Modus: Getrennte Ordner für Animes/Serien/Filme
- **Fortschritts-Tracking**: Automatische Verfolgung heruntergeladener Episoden
- **Sprachpriorisierung**: Configurable Sprachpräferenzen
- **Backup-Funktion**: Automatische Sicherung der URL-Listen

### Web-Interface
- **Dashboard**: Übersicht über alle Serien und Download-Status
- **Serie-Management**: Hinzufügen, Entfernen und Verwalten von Serien
- **Download-Kontrolle**: Starten/Stoppen von Downloads mit verschiedenen Modi
- **Konfiguration**: Einfache Einstellungsverwaltung über das Web-Interface
- **Status-Monitoring**: Live-Updates über laufende Downloads

### Browser-Integration
- **Tampermonkey-Skript**: One-Click-Downloads direkt von aniworld.to/s.to
- **Status-Anzeige**: Zeigt an ob Serie bereits heruntergeladen wurde
- **Auto-Detection**: Erkennt automatisch Serie-URLs auf unterstützten Seiten

## 🚀 Installation

### Docker (empfohlen)

#### Mit Docker Compose:

1. **Repository clonen:**
```bash
git clone https://github.com/WimWamWom/Better_AniLoader.git
cd Better_AniLoader
```

2. **Docker Compose starten:**
```bash
docker-compose up -d
```

3. **Web-Interface aufrufen:**
```
http://localhost:5050
```

#### Mit Docker Run:

```bash
docker run -d \\
  --name better-aniloader \\
  -p 5050:5050 \\
  -v ./data:/app/data \\
  -v ./Downloads:/app/Downloads \\
  --restart unless-stopped \\
  better-aniloader:latest
```

#### Unraid Installation:

1. **Container hinzufügen** über das Docker-Tab
2. **Repository**: `your-dockerhub/better-aniloader`
3. **Port Mapping**: `5050:5050`
4. **Volume Mappings**:
   - `/mnt/user/appdata/aniloader/data` → `/app/data`
   - `/mnt/user/Downloads/AniLoader` → `/app/Downloads`
5. **Container starten**

### Manuelle Installation

#### Voraussetzungen:
- Python 3.11+
- pip
- Git

#### Schritte:

1. **Repository clonen:**
```bash
git clone https://github.com/WimWamWom/Better_AniLoader.git
cd Better_AniLoader
```

2. **Virtuelle Umgebung erstellen:**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder
venv\\Scripts\\activate   # Windows
```

3. **Dependencies installieren:**
```bash
pip install -r requirements.txt
```

4. **Anwendung starten:**
```bash
python code/main.py
```

5. **Web-Interface aufrufen:**
```
http://localhost:5050
```

## ⚙️ Konfiguration

### Konfigurationsdatei (config.json)

Die Konfiguration erfolgt über `data/config.json`:

```json
{
  "languages": ["German Dub", "German Sub", "English Dub", "English Sub"],
  "min_free_gb": 2.0,
  "download_path": "/app/Downloads",
  "storage_mode": "standard",
  "movies_path": "/app/Downloads/Movies",
  "series_path": "/app/Downloads/Series",
  "anime_path": "/app/Downloads/Anime", 
  "serien_path": "/app/Downloads/Serien",
  "anime_separate_movies": false,
  "serien_separate_movies": false,
  "dedicated_movies_folder": false,
  "data_folder_path": "/app/data",
  "server_port": 5050,
  "autostart_mode": null,
  "refresh_titles": true
}
```

### Konfigurationsoptionen:

| Option | Beschreibung | Standard |
|--------|--------------|----------|
| `languages` | Sprachpriorität für Downloads | `["German Dub", "German Sub", "English Dub", "English Sub"]` |
| `storage_mode` | Organisationsmodus (`standard`/`separate`) | `standard` |
| `download_path` | Basis-Download-Verzeichnis | `/app/Downloads` |
| `server_port` | Web-Interface Port | `5050` |
| `min_free_gb` | Minimum freier Speicherplatz (GB) | `2.0` |
| `autostart_mode` | Automatischer Download-Modus beim Start | `null` |

### Storage-Modi:

#### Standard-Modus
Alle Downloads landen in einem Basis-Ordner mit Unterordnern pro Serie:
```
Downloads/
├── Naruto (2002) [tt0409591]/
│   ├── Staffel 1/
│   └── Filme/
└── Attack on Titan (2013) [tt2560140]/
    └── Staffel 1/
```

#### Separater Modus
Getrennte Ordner für verschiedene Inhaltstypen:
```
Downloads/
├── Anime/
│   └── Naruto (2002) [tt0409591]/
├── Serien/
│   └── Breaking Bad (2008) [tt0903747]/
└── Movies/ (optional)
```

## 🎮 Verwendung

### Web-Interface

#### Dashboard
- **Serie-Übersicht**: Alle hinzugefügten Serien mit Status-Anzeige
- **Download-Kontrolle**: Start/Stop-Buttons für verschiedene Modi
- **Progress-Tracking**: Anzeige der letzten heruntergeladenen Episoden

#### Serie hinzufügen
1. URL von aniworld.to oder s.to in das Eingabefeld einfügen
2. "Serie hinzufügen" klicken
3. Serie wird zur Datenbank hinzugefügt und erscheint im Dashboard

#### Downloads starten
1. **Download-Modus wählen**:
   - `Standard`: Lädt alle fehlenden Episoden herunter
   - `Deutsch`: Lädt nur deutsche Versionen fehlender Episoden
   - `Neu`: Lädt nur noch nicht erfasste Episoden
   - `Überprüfung`: Sucht nach fehlenden deutschen Versionen

2. **Download starten** über entsprechenden Button
3. **Progress verfolgen** über das Dashboard

### Download-Modi

#### Standard-Modus (`default`)
- Lädt alle Episoden basierend auf Sprachpriorität herunter
- Markiert Serie als vollständig wenn alle Episoden heruntergeladen
- Verwendet erste verfügbare Sprache aus der Prioritätsliste

#### Deutsch-Modus (`german`) 
- Fokussiert sich nur auf deutsche Synchronisation
- Ersetzt automatisch nicht-deutsche Versionen
- Ideal für nachträgliche Verbesserung der Sammlung

#### Neu-Modus (`new`)
- Lädt nur Episoden herunter, die noch nicht in der Datenbank erfasst sind
- Perfekt für regelmäßige Updates bestehender Serien

#### Überprüfungs-Modus (`check-missing`)
- Scannt vorhandene Dateien nach nicht-deutschen Versionen
- Erstellt Liste für späteren Deutsch-Modus Download
- Hilfreich für Qualitätsverbesserung der Sammlung

### Tampermonkey-Skript

#### Installation:
1. **Tampermonkey-Extension** in Chrome/Firefox installieren
2. **Skript hinzufügen**: `Tampermonkey.user.js` aus dem Repository
3. **Server-Konfiguration anpassen**:
   ```javascript
   const SERVER_IP = "YOUR-SERVER-IP";
   const SERVER_PORT = 5050;
   ```

#### Funktionen:
- **Automatische Erkennung**: Erkennt unterstützte Seiten automatisch
- **Status-Anzeige**: Zeigt Download-Status der aktuellen Serie
- **One-Click-Download**: Direkte Integration in aniworld.to/s.to
- **Server-Monitoring**: Zeigt Server-Status an

#### Button-Zustände:
- 🔵 **"📤 Downloaden"**: Serie nicht in Datenbank, bereit zum Hinzufügen
- 🟢 **"✅ Gedownloaded"**: Serie vollständig heruntergeladen
- 🟡 **"⬇️ Downloaded"**: Serie wird gerade heruntergeladen
- 🟦 **"📄 In der Liste"**: Serie in Waiting-Liste
- 🔴 **"⛔ Server offline"**: Keine Verbindung zum Server

## 📚 API-Dokumentation

### Endpunkte

#### Serie-Management
```http
POST /export
Content-Type: application/json

{
  "url": "https://aniworld.to/anime/stream/serie-name"
}
```

#### Download-Kontrolle
```http
POST /start_download
Content-Type: application/json

{
  "mode": "default"  // default|german|new|check-missing
}
```

#### Status-Abfrage
```http
GET /status
```

Antwort:
```json
{
  "status": "running",
  "current_title": "Naruto",
  "progress": "S01E05"
}
```

#### Datenbank-Abfrage
```http
GET /database?q=https://aniworld.to/anime/stream/serie-name
```

#### Konfiguration
```http
GET /config
POST /config
```

## 📁 Ordnerstruktur

```
Better_AniLoader/
├── code/                    # Hauptanwendung
│   ├── main.py             # Einstiegspunkt
│   ├── API_Endpoints.py    # REST API
│   ├── config.py           # Konfigurationsmanagement
│   ├── database.py         # SQLite Datenbankoperationen
│   ├── downloader.py       # Download-Engine
│   ├── file_management.py  # Dateiverwaltung
│   ├── html_request.py     # Web-Scraping
│   ├── logger.py          # Logging-System
│   ├── txt_manager.py     # AniLoader.txt Verwaltung
│   └── url_builder.py     # URL-Generierung
├── data/                   # Persistente Daten
│   ├── config.json        # Konfigurationsdatei
│   ├── AniLoader.db       # SQLite Datenbank
│   └── logs/              # Log-Dateien
├── Downloads/              # Download-Zielverzeichnis
├── static/                 # Web-Assets
│   ├── style.css          # CSS-Styling
│   └── script.js          # JavaScript
├── templates/              # HTML-Templates
│   └── index.html         # Haupt-Interface
├── Dockerfile             # Container-Definition
├── docker-compose.yaml    # Compose-Konfiguration
├── requirements.txt       # Python-Dependencies
└── Tampermonkey.user.js   # Browser-Skript
```

## 🛠️ Entwicklung

### Lokale Entwicklung

1. **Development-Setup**:
```bash
git clone https://github.com/WimWamWom/Better_AniLoader.git
cd Better_AniLoader
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **Anwendung starten**:
```bash
python code/main.py
```

3. **Testing**:
```bash
# Manuelle Tests über Web-Interface
curl http://localhost:5050/status
```

### Docker Development

```bash
# Image bauen
docker build -t better-aniloader:dev .

# Development Container
docker run -it --rm \\
  -p 5050:5050 \\
  -v $(pwd)/data:/app/data \\
  -v $(pwd)/Downloads:/app/Downloads \\
  better-aniloader:dev
```

### Beitragen

1. Fork das Repository
2. Feature-Branch erstellen: `git checkout -b feature/amazing-feature`
3. Änderungen committen: `git commit -m 'Add amazing feature'`
4. Branch pushen: `git push origin feature/amazing-feature`
5. Pull Request öffnen

## 🔧 FAQ & Troubleshooting

### Häufige Probleme

#### Downloads starten nicht
- **Grund**: Server offline oder aniworld.to nicht erreichbar
- **Lösung**: Internet-Verbindung und Server-Status prüfen

#### Dateien werden nicht gefunden
- **Grund**: Ordnernamen haben sich geändert (neues aniworld-cli Format)
- **Lösung**: Manual-Rescan oder Downloads neu starten

#### Web-Interface lädt nicht
- **Grund**: Port bereits belegt oder Firewall-Blockade
- **Lösung**: Port in config.json ändern oder Firewall-Regeln anpassen

#### Tampermonkey-Skript funktioniert nicht
- **Grund**: Server-IP falsch konfiguriert oder CORS-Probleme
- **Lösung**: Server-Konfiguration im Skript überprüfen

### Debug-Modi

#### Logging aktivieren:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### Verbose Output:
```bash
python code/main.py --verbose
```

### Performance-Optimierung

#### Für große Sammlungen:
- `min_free_gb` erhöhen
- Separate Storage-Modi verwenden
- Regelmäßige Datenbankbereinigung

#### Docker-Optimierung:
```yaml
services:
  aniloader:
    # ... andere Konfiguration
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
```

## 🆘 Unterstützung

### Community
- **GitHub Issues**: Bug-Reports und Feature-Requests
- **Diskussionen**: GitHub Discussions für Fragen und Ideen

### Systemanforderungen
- **Minimum**: 
  - 1 GB RAM
  - 5 GB freier Speicherplatz
  - Internet-Verbindung
- **Empfohlen**:
  - 2 GB RAM
  - 50 GB+ freier Speicherplatz (je nach Downloads)
  - Stabile Breitband-Verbindung

### Bekannte Limitationen
- Abhängig von aniworld.to/s.to Verfügbarkeit
- Download-Geschwindigkeit durch externe Server begrenzt
- Keine automatische Qualitätsauswahl (verwendet Server-Standard)

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert. Siehe [LICENSE](LICENSE) für Details.

---

<div align="center">
  <b>⭐ Wenn dir das Projekt gefällt, gib ihm einen Stern! ⭐</b>
  
  Entwickelt mit ❤️ für die Anime & Serien Community
</div>
