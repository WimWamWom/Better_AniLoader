import re

def sanitize_title(name: str) -> str:
    """
    Bereinigt einen Titel für die Verwendung als Ordner- oder Dateiname.
    
    Windows erlaubt bestimmte Zeichen nicht in Datei-/Ordnernamen.
    Diese Funktion entfernt alle unzulässigen Zeichen.
    
    Args:
        name: Der zu bereinigende Titel (z.B. "One Piece: Episode 1?")
    
    Returns:
        Bereinigter Titel (z.B. "One Piece Episode 1")
    
    Beispiele:
        >>> sanitize_title("Attack on Titan: Season 2")
        'Attack on Titan Season 2'
        >>> sanitize_title("Naruto/Shippuden?")
        'NarutoShippuden'
    """
    # Entferne unzulässige Windows-Zeichen: < > : " / \ | ? *
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    
    # Entferne führende/abschließende Leerzeichen
    name = name.strip()
    
    return name

def sanitize_episode_title(name: str) -> str:
    """
    Bereinigt einen Episoden- oder Filmtitel für Dateinamen.
    
    Zusätzlich zur Standard-Bereinigung werden auch redundante
    Bezeichnungen wie "Movie", "[Movie]" oder "The Movie" entfernt.
    
    Args:
        name: Der zu bereinigende Episoden-/Filmtitel
    
    Returns:
        Bereinigter Titel ohne redundante Zusätze
    
    Beispiele:
        >>> sanitize_episode_title("Demon Slayer: The Movie")
        'Demon Slayer'
        >>> sanitize_episode_title("Naruto [Movie]")
        'Naruto'
    """
    # Erst die Standard-Bereinigung durchführen
    name = sanitize_title(name)
    
    # Entferne "Movie", "[Movie]" oder "The Movie" (case-insensitive)
    name = re.sub(r'\s*\[?The\s+Movie\]?\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\[?Movie\]?\s*', '', name, flags=re.IGNORECASE)
    
    # Entferne mehrfache Leerzeichen und trimme erneut
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

