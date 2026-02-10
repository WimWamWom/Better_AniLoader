"""
url_builder.py – URL-Konstruktion für Staffeln und Episoden.
"""


def season_url(base_url: str, season: int | str) -> str:
    """Erzeugt die URL einer Staffel (oder des Filme-Bereichs)."""
    base = base_url.rstrip("/")
    s = str(season).strip().lower()
    if s == "filme" or s == "0":
        return f"{base}/filme"
    return f"{base}/staffel-{s}"


def episode_url(base_url: str, season: int | str, episode: int | str) -> str:
    """Erzeugt die URL einer konkreten Episode."""
    s_url = season_url(base_url, season)
    s = str(season).strip().lower()
    if s == "filme" or s == "0":
        return f"{s_url}/film-{episode}"
    return f"{s_url}/episode-{episode}"
