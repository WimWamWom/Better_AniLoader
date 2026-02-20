"""HTML scraper for aniworld.to and s.to.

Extracts series metadata, season listings, episode listings,
available languages and episode titles from the streaming sites.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from core.constants import (
    ANIWORLD_BASE,
    ANIWORLD_LANGUAGE_MAP,
    STO_BASE,
    STO_LANGUAGE_MAP,
    Language,
    Site,
)
from core.exceptions import NetworkError, ScrapingError
from core.logging_setup import get_logger
from utils.helpers import (
    build_episode_url,
    build_season_url,
    detect_site,
    sanitize_episode_title,
    sanitize_title,
)
from utils.http_client import http

log = get_logger("scraper")


# ═══════════════════════════════════════════════════════════════════════
# Series title
# ═══════════════════════════════════════════════════════════════════════

def fetch_series_title(url: str) -> Optional[str]:
    """Fetch and return the display title from a series page."""
    try:
        resp = http.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # aniworld.to: <div class="series-title"><h1><span>Title</span></h1></div>
        el = (
            soup.select_one("div.series-title h1 span")
            or soup.select_one("div.series-title h1")
            # s.to: <h1 class="h2 mb-1 fw-bold">Title</h1>
            or soup.select_one("h1.h2.mb-1.fw-bold")
        )
        if el and el.get_text(strip=True):
            return sanitize_title(el.get_text(strip=True))
    except Exception as exc:
        log.error("Cannot fetch title for %s: %s", url, exc)
    return None


# ═══════════════════════════════════════════════════════════════════════
# Season discovery
# ═══════════════════════════════════════════════════════════════════════

def fetch_season_numbers(url: str) -> List[str]:
    """Return a list of season numbers (as strings) for a series URL.

    For aniworld.to, if a "Filme" link is present, ``"0"`` is appended.
    """
    try:
        resp = http.get(url)
        resp.raise_for_status()
    except Exception as exc:
        raise NetworkError(f"Cannot fetch series page {url}: {exc}") from exc

    soup = BeautifulSoup(resp.text, "html.parser")
    site = detect_site(url)
    seasons: List[str] = []

    if site == Site.SERIENSTREAM:
        nav = soup.find("nav", id="season-nav")
        scope = nav if nav else soup
        for a in scope.find_all("a", attrs={"data-season-pill": True}):
            val = str(a.get("data-season-pill", "")).strip()
            if val:
                seasons.append(val)

    elif site == Site.ANIWORLD:
        nav = soup.find("div", class_="hosterSiteDirectNav")
        scope = nav if nav else soup
        for ul in scope.find_all("ul"):
            text = ul.get_text(" ", strip=True)
            if "Staffeln" in text:
                for a in ul.find_all("a"):
                    for num in a.get_text(strip=True).split():
                        if num.isdigit():
                            seasons.append(num)

        # Check for movies (Filme)
        has_movies = soup.find("a", attrs={"title": "Alle Filme"})
        if not has_movies:
            for a_tag in soup.find_all("a"):
                if a_tag.string and "Filme" in a_tag.string:
                    has_movies = True
                    break
        if has_movies and "0" not in seasons:
            seasons.append("0")

    log.debug("Seasons for %s: %s", url, seasons)
    return seasons


# ═══════════════════════════════════════════════════════════════════════
# Episode discovery
# ═══════════════════════════════════════════════════════════════════════

def fetch_episodes_for_season(
    base_url: str, season: str
) -> List[Dict[str, str]]:
    """Scrape episode numbers for a season.

    Returns a list of dicts: ``[{"number": "1", "url": "..."}, ...]``
    """
    season_url = build_season_url(base_url, season)
    try:
        resp = http.get(season_url)
        resp.raise_for_status()
    except Exception as exc:
        raise NetworkError(f"Cannot fetch season page {season_url}: {exc}") from exc

    soup = BeautifulSoup(resp.text, "html.parser")
    site = detect_site(base_url)
    episodes: List[Dict[str, str]] = []
    seen: set[str] = set()

    if site == Site.SERIENSTREAM:
        for row in soup.find_all("tr", class_="episode-row"):
            row_classes = row.get("class") or []
            if "upcoming" in str(row_classes):
                continue
            th = row.select_one("th.episode-number-cell")
            num = th.get_text(strip=True) if th else None
            if num and num not in seen:
                seen.add(num)
                ep_url = build_episode_url(base_url, season, num)
                episodes.append({"number": num, "url": ep_url})

    elif site == Site.ANIWORLD:
        table = soup.find("table", class_="seasonEpisodesList")
        if table:
            # Season key: aniworld uses tbody id="season{N}"
            s_key = "0" if str(season).strip().lower() in ("0", "filme") else str(season)
            tbody_id = f"season{s_key}" if s_key != "0" else None

            # For movies, there may not be a specific tbody
            tbody = None
            if tbody_id:
                tbody = table.find("tbody", id=tbody_id)
            if not tbody:
                tbody = table.find("tbody")

            if tbody:
                for tr in tbody.find_all("tr"):
                    meta = tr.find("meta", attrs={"itemprop": "episodeNumber"})
                    if meta:
                        num = str(meta.get("content", "")).strip()
                        if num and num not in seen:
                            seen.add(num)
                            ep_url = build_episode_url(base_url, season, num)
                            episodes.append({"number": num, "url": ep_url})

    log.debug("Episodes for %s S%s: %d found", base_url, season, len(episodes))
    return episodes


def fetch_all_seasons_with_episodes(
    base_url: str,
) -> Dict[str, List[Dict[str, str]]]:
    """Fetch a complete map of ``{season_number: [episode_dicts]}``."""
    seasons = fetch_season_numbers(base_url)
    result: Dict[str, List[Dict[str, str]]] = {}
    for s in seasons:
        eps = fetch_episodes_for_season(base_url, s)
        result[s] = eps
    return result


# ═══════════════════════════════════════════════════════════════════════
# Language detection
# ═══════════════════════════════════════════════════════════════════════

def fetch_languages_for_episode(episode_url: str) -> List[str]:
    """Return list of available language labels for an episode.

    Example return: ``["German Dub", "German Sub", "English Sub"]``
    """
    try:
        resp = http.get(episode_url)
        resp.raise_for_status()
    except Exception as exc:
        log.error("Cannot fetch episode page %s: %s", episode_url, exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    site = detect_site(episode_url)

    if site == Site.SERIENSTREAM:
        return _parse_languages_sto(soup)
    elif site == Site.ANIWORLD:
        return _parse_languages_aniworld(soup)
    return []


def _parse_languages_sto(soup: BeautifulSoup) -> List[str]:
    languages: List[str] = []
    seen: set[str] = set()
    for svg in soup.find_all("svg", class_="watch-language"):
        use = svg.find("use")
        if not use:
            continue
        href = str(use.get("href", ""))
        key = href.removeprefix("#icon-flag-").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        lang = STO_LANGUAGE_MAP.get(key.lower())
        if lang:
            languages.append(lang.value)
        else:
            languages.append(key)
    return languages


def _parse_languages_aniworld(soup: BeautifulSoup) -> List[str]:
    languages: List[str] = []
    seen: set[str] = set()
    lang_div = soup.find("div", class_="changeLanguageBox")
    if not lang_div:
        return languages
    for img in lang_div.find_all("img"):
        src = str(img.get("src", ""))
        key = src.removeprefix("/public/img/").removesuffix(".svg").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        lang = ANIWORLD_LANGUAGE_MAP.get(key.lower())
        if lang:
            languages.append(lang.value)
        else:
            languages.append(key)
    return languages


# ═══════════════════════════════════════════════════════════════════════
# Episode title
# ═══════════════════════════════════════════════════════════════════════

def fetch_episode_title(
    episode_url: str, *, english: bool = False
) -> Optional[str]:
    """Fetch the German (default) or English episode title."""
    try:
        resp = http.get(episode_url)
        resp.raise_for_status()
    except Exception as exc:
        log.error("Cannot fetch episode title from %s: %s", episode_url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    site = detect_site(episode_url)

    if site == Site.SERIENSTREAM:
        return _episode_title_sto(soup, english)
    elif site == Site.ANIWORLD:
        return _episode_title_aniworld(soup, english)
    return None


def _episode_title_sto(soup: BeautifulSoup, english: bool) -> Optional[str]:
    tag = soup.find("h2", class_="h4 mb-1")
    if not tag:
        return None
    text = tag.get_text(strip=True)
    # Strip "S01E01: " prefix
    cleaned = re.sub(r"^S\d{2}E\d{2}:\s*", "", text)
    if english:
        m = re.search(r"\(([^)]*)\)", cleaned)
        return sanitize_episode_title(m.group(1)) if m else None
    # German title = everything before parentheses
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", cleaned)
    return sanitize_episode_title(cleaned) if cleaned else None


def _episode_title_aniworld(soup: BeautifulSoup, english: bool) -> Optional[str]:
    if english:
        tag = soup.find("small", class_="episodeEnglishTitle")
    else:
        tag = soup.find("span", class_="episodeGermanTitle")
    if tag:
        return sanitize_episode_title(tag.get_text(strip=True))
    return None


# ═══════════════════════════════════════════════════════════════════════
# Search
# ═══════════════════════════════════════════════════════════════════════

def search_aniworld(keyword: str) -> List[Dict[str, str]]:
    """Search aniworld.to.  Returns ``[{title, url, description}, ...]``."""
    try:
        resp = http.post(
            f"{ANIWORLD_BASE}/ajax/search",
            data={"keyword": keyword},
        )
        resp.raise_for_status()
        data = resp.json()
        results: List[Dict[str, str]] = []
        for item in data:
            link = item.get("link", "")
            title = item.get("title", "")
            desc = item.get("description", "")
            if "/anime/stream/" in link:
                full_url = f"{ANIWORLD_BASE}{link}" if not link.startswith("http") else link
                results.append({"title": title, "url": full_url, "description": desc})
        return results
    except Exception as exc:
        log.error("aniworld search failed: %s", exc)
        return []


def search_sto(keyword: str) -> List[Dict[str, str]]:
    """Search s.to.  Returns ``[{title, url}, ...]``."""
    try:
        resp = http.get(
            f"{STO_BASE}/api/search/suggest",
            params={"term": keyword},
        )
        resp.raise_for_status()
        data = resp.json()
        results: List[Dict[str, str]] = []
        for item in data:
            link = item.get("link", "")
            title = item.get("title", item.get("name", ""))
            if "/serie/" in link:
                full_url = f"{STO_BASE}{link}" if not link.startswith("http") else link
                results.append({"title": title, "url": full_url})
        return results
    except Exception as exc:
        log.error("s.to search failed: %s", exc)
        return []
