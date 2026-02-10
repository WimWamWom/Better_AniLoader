from typing import List, Dict
import requests
import re
from bs4 import BeautifulSoup
from url_builder import get_season_url
from helper import sanitize_episode_title, sanitize_title
from urllib.parse import urlparse

headers = {"User-Agent": "Mozilla/5.0 (compatible; AniLoaderBot/1.0)"}

# Cloudflare DNS-over-HTTPS Resolver
def resolve_dns_via_cloudflare(hostname: str) -> str:
    """
    Löst einen Hostnamen über Cloudflare DNS (1.1.1.1) mit DNS-over-HTTPS auf.
    
    :param hostname: Der aufzulösende Hostname
    :return: Die aufgelöste IP-Adresse oder der ursprüngliche Hostname bei Fehler
    """
    try:
        doh_url = "https://1.1.1.1/dns-query"
        params = {"name": hostname, "type": "A"}
        doh_headers = {"accept": "application/dns-json"}
        
        response = requests.get(doh_url, params=params, headers=doh_headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if "Answer" in data and len(data["Answer"]) > 0:
            ip = data["Answer"][0]["data"]
            print(f"[DNS] {hostname} → {ip} (via Cloudflare 1.1.1.1)")
            return ip
    except Exception as e:
        print(f"[DNS-WARNING] Cloudflare DNS fehlgeschlagen für {hostname}: {e}, verwende System-DNS")
    
    return hostname

# Session mit Cloudflare DNS
class CloudflareSession(requests.Session):
    """Session die DNS-Abfragen über Cloudflare 1.1.1.1 routet"""
    
    def __init__(self):
        super().__init__()
        self.headers.update(headers)
    
    def request(self, method, url, **kwargs):
        """Override request um Cloudflare DNS zu verwenden"""
        parsed = urlparse(url)
        hostname = parsed.hostname
        
        if hostname:
            # DNS über Cloudflare auflösen
            ip = resolve_dns_via_cloudflare(hostname)
            
            # URL mit IP ersetzen, aber Host-Header Original lassen
            if ip != hostname and ip:
                url_with_ip = url.replace(hostname, ip, 1)
                # Host-Header für SNI und Virtual Hosting
                if 'headers' not in kwargs:
                    kwargs['headers'] = {}
                kwargs['headers']['Host'] = hostname
                url = url_with_ip
        
        return super().request(method, url, **kwargs)

# Globale Session mit Cloudflare DNS
cloudflare_session = CloudflareSession()

def get_season_numbers(url: str):
    season_numbers: List[str] = []
    serien_html = cloudflare_session.get(url, timeout=5)
    serien_html.raise_for_status()
    soup = BeautifulSoup(serien_html.text, "html.parser")
    if "https://s.to/" in url:
        nav = soup.find("nav", id="season-nav")
        scope = nav if nav is not None else soup
        for season in scope.find_all("a", attrs={"data-season-pill": True}):
            season_number = str(season.get("data-season-pill"))
            if season_number:
                season_numbers.append(season_number.strip())

    elif "https://aniworld.to/" in url:
        nav = soup.find("div", class_="hosterSiteDirectNav")
        scope = nav if nav is not None else soup
        for ul_class in scope.find_all("ul"):
            if "Staffeln" in ul_class.get_text(" ", strip=True):
                for Anker in ul_class.find_all("a"):
                    for season_number in Anker.get_text(strip=True).split():
                        season_numbers.append(season_number.strip())

    return season_numbers

def get_seasons_with_episode_count(url: str):
    """
    Docstring for get_seasons_with_episode_count
    
    :param url: URL der Serie
    :type url: str
    :return: Ein Dictionary mit Staffeln als Schlüssel und Listen von Episodennummern als Werte, oder -1 bei Fehlern
    :rtype: Dict[str, List[str]] | int
    """
    seasons_with_episode_count: Dict[str, List[str]] = {}
    staffeln = get_season_numbers(url)
    
    for staffel in staffeln:
        staffel_url = get_season_url(url, staffel)
        staffel_html = cloudflare_session.get(staffel_url, timeout=5)
        staffel_html.raise_for_status()
        soup = BeautifulSoup(staffel_html.text, "html.parser")
        episodes: List[str] = []
        rows = soup.find_all("tr", class_="episode-row")
        
        for row in rows:
            if "upcoming"  in str(row.get("class")):
                continue
            th = row.select_one("th.episode-number-cell")
            num = th.get_text(strip=True) if th else None
            if num :
                episodes.append(num)
        seasons_with_episode_count[staffel] = episodes
    return seasons_with_episode_count

def get_languages_for_episode(episode_url: str):
    episode_html = cloudflare_session.get(episode_url, timeout=5)
    episode_html.raise_for_status()
    soup = BeautifulSoup(episode_html.text, "html.parser")
    sprachen: List[str] = []
    vorhandene_sprachen: List[str] = []
    if "https://s.to/" in episode_url:
        svg_icons = soup.find_all("svg", class_="watch-language" )
        for svg in svg_icons:
            use = svg.find("use")
            if not use:
                continue
            href = str(use.get("href"))
            sprache = href.removeprefix("#icon-flag-")
            if sprache in vorhandene_sprachen or not sprache:
                continue
            vorhandene_sprachen.append(sprache)
            if sprache.lower() == "german":
                sprachen.append("German Dub")
            elif sprache.lower() == "english":
                sprachen.append("English Dub")
            elif sprache.lower() == "english-german":
                sprachen.append("German Sub")
            else:
                sprachen.append(sprache)

    elif "https://aniworld.to/" in episode_url:
        lang_div = soup.find("div", class_="changeLanguageBox")
        if lang_div is not None:
            for img in lang_div.find_all("img"):
                sprache = str(img.get("src")).removeprefix("/public/img/").removesuffix(".svg")
                if sprache in vorhandene_sprachen or not sprache:
                    continue
                vorhandene_sprachen.append(sprache)
                print(sprache)
                if sprache.lower() == "german":
                    sprache = "German Dub"
                elif sprache.lower() == "english":
                    sprache = "English Dub"
                elif sprache.lower() == "japanese-german":
                    sprache = "German Sub"
                elif sprache.lower() == "japanese-english":
                    sprache = "English Sub"
                sprachen.append(sprache)
    else:
        return -1
    return sprachen

def get_series_title(url):
    try:

        staffel_html = cloudflare_session.get(url, timeout=10)
        staffel_html.raise_for_status()
        soup = BeautifulSoup(staffel_html.text, "html.parser")
        title_elem = (
            soup.select_one("div.series-title h1 span")
            or soup.select_one("div.series-title h1")
            or soup.select_one("h1.h2.mb-1.fw-bold")
        )
        if title_elem and title_elem.text and title_elem.text.strip():
            title = sanitize_title(str(title_elem.text.strip()))
            return title
    except Exception as e:
        print(f"[FEHLER] Konnte Serien-Titel nicht abrufen ({url}): {e}")

def get_episode_title(episode_url: str, english_title: bool = False):
    episode_html = cloudflare_session.get(episode_url, timeout=5)
    episode_html.raise_for_status()
    soup = BeautifulSoup(episode_html.text, "html.parser")
    title = None
    if "https://s.to/" in episode_url:
        title_tag = soup.find("h2", class_="h4 mb-1")
        if title_tag:
            title_element  = title_tag.get_text(strip=True)
            cleaned = re.sub(r'^S\d{2}E\d{2}:\s*', '', title_element)
            sprachen = get_languages_for_episode(episode_url)
            if sprachen != -1:
                if "German Dub" in sprachen and english_title == False:
                    cleaned = re.sub(r'\s*\([^)]*\)\s*$', '', cleaned)
                else:
                    # Extrahiere nur Text innerhalb der Klammern
                    match = re.search(r'\(([^)]*)\)', cleaned)
                    if match:
                        cleaned = match.group(1)
            title = sanitize_episode_title(cleaned)
            return title

    elif "https://aniworld.to/" in episode_url:
        # Suche nach deutschem Titel in <span class="episodeGermanTitle">
        if english_title == False:
            title_tag = soup.find("span", class_="episodeGermanTitle")
            if title_tag:
                title = sanitize_episode_title(title_tag.get_text(strip=True))
                return title
        # Fallback: englischer Titel in <small class="episodeEnglishTitle">
        title_tag = soup.find("small", class_="episodeEnglishTitle")
        if title_tag:
            title = sanitize_episode_title(title_tag.get_text(strip=True))
            return title
    
    return False
