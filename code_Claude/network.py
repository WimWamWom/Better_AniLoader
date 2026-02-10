"""
network.py – Netzwerk- und HTML-Parsing-Funktionen für AniLoader.

Nutzt html_request-Logik (BeautifulSoup) für:
  - Staffeln + Episoden-Counts ermitteln
  - Verfügbare Sprachen pro Episode
  - Serien- und Episodentitel abrufen
  - Suche auf aniworld.to / s.to

DNS-Override über Cloudflare (1.1.1.1) für zuverlässige Auflösung.
"""

import html
import json
import random
import re
import socket
from typing import Any
from urllib.parse import urlparse, quote

import requests
from bs4 import BeautifulSoup

from logger import log
from url_builder import season_url

# ── User-Agents ────────────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 OPR/102.0.0.0",
]


def _headers() -> dict[str, str]:
    return {"User-Agent": random.choice(USER_AGENTS)}


def _get(url: str, timeout: int = 10) -> requests.Response:
    """GET mit DNS-Override und zufälligem User-Agent."""
    host = urlparse(url).hostname
    ips = _resolve_cloudflare(host)
    with _DnsOverride(host, ips):
        r = requests.get(url, headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r


# ═══════════════════════════════════════════════════════════════════════════════
#  Staffeln + Episoden über HTML ermitteln
# ═══════════════════════════════════════════════════════════════════════════════

def get_season_numbers(url: str) -> list[str]:
    """Gibt die verfügbaren Staffel-Nummern zurück (inkl. 'Filme' bei aniworld)."""
    r = _get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    seasons: list[str] = []

    if "s.to" in url:
        nav = soup.find("nav", id="season-nav")
        scope = nav if nav else soup
        for a in scope.find_all("a", attrs={"data-season-pill": True}):
            val = str(a.get("data-season-pill", "")).strip()
            if val:
                seasons.append(val)

    elif "aniworld.to" in url:
        nav_div = soup.find("div", class_="hosterSiteDirectNav")
        scope = nav_div if nav_div else soup
        for ul in scope.find_all("ul"):
            text = ul.get_text(" ", strip=True)
            if "Staffeln" in text:
                for a in ul.find_all("a"):
                    for part in a.get_text(strip=True).split():
                        seasons.append(part.strip())

    return seasons


def get_seasons_with_episodes(url: str) -> dict[str, list[str]]:
    """Gibt {staffel: [episoden-nummern]} zurück. Überspringt 'upcoming'-Episoden."""
    season_nums = get_season_numbers(url)
    result: dict[str, list[str]] = {}

    for s in season_nums:
        s_url = season_url(url, s)
        r = _get(s_url)
        soup = BeautifulSoup(r.text, "html.parser")
        episodes: list[str] = []
        for row in soup.find_all("tr", class_="episode-row"):
            if "upcoming" in str(row.get("class", "")):
                continue
            th = row.select_one("th.episode-number-cell")
            num = th.get_text(strip=True) if th else None
            if num:
                episodes.append(num)
        result[s] = episodes

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Sprachen pro Episode ermitteln
# ═══════════════════════════════════════════════════════════════════════════════

def get_languages(episode_url: str) -> list[str]:
    """Gibt die verfügbaren Sprachen als Liste zurück, z.B. ['German Dub', 'English Sub']."""
    r = _get(episode_url, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    seen: list[str] = []
    langs: list[str] = []

    if "s.to" in episode_url:
        for svg in soup.find_all("svg", class_="watch-language"):
            use = svg.find("use")
            if not use:
                continue
            href = str(use.get("href", ""))
            raw = href.removeprefix("#icon-flag-")
            if not raw or raw in seen:
                continue
            seen.append(raw)
            langs.append(_normalize_lang_sto(raw))

    elif "aniworld.to" in episode_url:
        lang_div = soup.find("div", class_="changeLanguageBox")
        if lang_div:
            for img in lang_div.find_all("img"):
                raw = str(img.get("src", "")).removeprefix("/public/img/").removesuffix(".svg")
                if not raw or raw in seen:
                    continue
                seen.append(raw)
                langs.append(_normalize_lang_aniworld(raw))

    return langs


def _normalize_lang_sto(raw: str) -> str:
    mapping = {
        "german": "German Dub",
        "english": "English Dub",
        "english-german": "German Sub",
    }
    return mapping.get(raw.lower(), raw)


def _normalize_lang_aniworld(raw: str) -> str:
    mapping = {
        "german": "German Dub",
        "english": "English Dub",
        "japanese-german": "German Sub",
        "japanese-english": "English Sub",
    }
    return mapping.get(raw.lower(), raw)


def select_language(available: list[str], preferred: list[str], german_only: bool = False) -> str | None:
    """Wählt die beste verfügbare Sprache gemäß Prioritätsliste."""
    pool = ["German Dub"] if german_only else preferred
    for lang in pool:
        if lang in available:
            return lang
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Titel abrufen
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_series_title(url: str) -> str | None:
    """Ruft den Serien-/Anime-Titel von der Übersichtsseite ab."""
    try:
        r = _get(url)
        soup = BeautifulSoup(r.text, "html.parser")
        elem = (
            soup.select_one("div.series-title h1 span")
            or soup.select_one("div.series-title h1")
            or soup.select_one("h1.h2.mb-1.fw-bold")
        )
        if elem and elem.text.strip():
            from file_ops import sanitize_title
            return sanitize_title(elem.text.strip())
    except Exception as e:
        log(f"[FEHLER] Konnte Serien-Titel nicht abrufen ({url}): {e}")
    return None


def fetch_episode_title(episode_url: str) -> str | None:
    """Ruft den Episodentitel (deutsch bevorzugt, sonst englisch) ab."""
    try:
        r = _get(episode_url)
        soup = BeautifulSoup(r.text, "html.parser")

        de = soup.select_one("span.episodeGermanTitle")
        if de and de.text.strip():
            from file_ops import sanitize_episode_title
            return sanitize_episode_title(de.text.strip())

        en = soup.select_one("small.episodeEnglishTitle")
        if en and en.text.strip():
            from file_ops import sanitize_episode_title
            return sanitize_episode_title(en.text.strip())
    except Exception as e:
        log(f"[FEHLER] Konnte Episodentitel nicht abrufen ({episode_url}): {e}")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Suche auf aniworld.to / s.to
# ═══════════════════════════════════════════════════════════════════════════════

def search_provider(query: str, provider_name: str, base_url: str) -> list[dict]:
    """Sucht auf einem Provider (aniworld / sto) und gibt Ergebnisliste zurück."""
    try:
        search_url = f"{base_url}/ajax/seriesSearch?keyword={quote(query)}"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": base_url,
        }

        hostname = urlparse(base_url).hostname
        if not hostname:
            return []
        ips = _resolve_cloudflare(hostname)

        with _DnsOverride(hostname, ips):
            response = requests.get(search_url, headers=headers, timeout=10)

        if response.status_code != 200:
            log(f"[SEARCH-{provider_name.upper()}] HTTP {response.status_code}")
            return []

        text = response.text.strip()
        # Unvollständige JSON reparieren
        if not text.endswith("]") and not text.endswith("}"):
            if text.endswith(","):
                text = text[:-1] + "]"
            elif "[" in text and "]" not in text:
                text += "]"

        text = text.encode("utf-8").decode("utf-8-sig")
        text = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]", "", text)
        data = json.loads(html.unescape(text))

        if not isinstance(data, list):
            return []

        results = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "").strip()
            link = item.get("link", "").strip()
            year = item.get("productionYear", "")
            cover = item.get("cover", "").strip()
            if not name or not link:
                continue

            if link.startswith("http"):
                full_url = link
            elif link.startswith("/"):
                full_url = base_url + link
            else:
                prefix = "/serie/stream/" if provider_name == "sto" else "/anime/stream/"
                full_url = f"{base_url}{prefix}{link}"

            cover_url = ""
            if cover:
                if cover.startswith("http"):
                    cover_url = cover
                elif cover.startswith("/"):
                    cover_url = base_url + cover
                else:
                    cover_url = f"{base_url}/public/img/cover/{cover}"

            display = f"{name} ({year})" if year else name
            results.append({
                "title": display, "url": full_url, "name": name,
                "year": year, "cover": cover_url, "provider": provider_name,
            })

        return results
    except Exception as e:
        log(f"[SEARCH-{provider_name.upper()}-ERROR] {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  DNS-Override (Cloudflare 1.1.1.1)
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_cloudflare(hostname: str | None) -> list[str] | None:
    """DNS-Auflösung über Cloudflare (1.1.1.1)."""
    if not hostname:
        return None
    try:
        import dns.resolver  # type: ignore
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = ["1.1.1.1"]
        ips: list[str] = []
        for rrtype in ("A", "AAAA"):
            try:
                ans = resolver.resolve(hostname, rrtype, lifetime=2.0)
                ips.extend(rdata.address for rdata in ans)
            except Exception:
                pass
        return ips or None
    except Exception:
        return None


class _DnsOverride:
    """Kontextmanager der socket.getaddrinfo patcht für gezielte DNS-Auflösung."""

    def __init__(self, hostname: str | None, ips: list[str] | None):
        self._host = hostname
        self._ips = ips or []
        self._orig: Any = None

    def __enter__(self):
        if not self._host or not self._ips:
            return self
        self._orig = socket.getaddrinfo

        host_ref = self._host
        ips_ref = self._ips
        orig_ref = self._orig

        def _patched(host, port, family=0, type_=0, proto=0, flags=0):
            if host == host_ref:
                results = []
                for ip in ips_ref:
                    if ":" in ip:
                        results.append((socket.AF_INET6, socket.SOCK_STREAM, proto or 0, "", (ip, port, 0, 0)))
                    else:
                        results.append((socket.AF_INET, socket.SOCK_STREAM, proto or 0, "", (ip, port)))
                return results
            return orig_ref(host, port, family, type_, proto, flags)

        socket.getaddrinfo = _patched
        return self

    def __exit__(self, *_):
        if self._orig:
            try:
                socket.getaddrinfo = self._orig
            except Exception:
                pass
        return False
