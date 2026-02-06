from typing import List, Dict
import requests
from bs4 import BeautifulSoup
from url_build import get_season_url

headers = {"User-Agent": "Mozilla/5.0 (compatible; AniLoaderBot/1.0)"}

def get_season_numbers(url: str):
    season_numbers: List[str] = []
    serien_html = requests.get(url, headers=headers, timeout=5)
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
    seasons_with_episode_count: Dict[str, List[str]] = {}
    staffeln = get_season_numbers(url)
    
    for staffel in staffeln:
        staffel_url = get_season_url(url, staffel)
        staffel_html = requests.get(staffel_url, headers=headers, timeout=5)
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
    episode_html = requests.get(episode_url, headers=headers, timeout=5)
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

        staffel_html = requests.get(url, headers=headers, timeout=10)
        staffel_html.raise_for_status()
        soup = BeautifulSoup(staffel_html.text, "html.parser")
        title_elem = (
            soup.select_one("div.series-title h1 span")
            or soup.select_one("div.series-title h1")
            or soup.select_one("h1.h2.mb-1.fw-bold")
        )
        if title_elem and title_elem.text and title_elem.text.strip():
            return title_elem.text.strip()
    except Exception as e:
        print(f"[FEHLER] Konnte Serien-Titel nicht abrufen ({url}): {e}")

def get_title_for_episode(episode_url: str):
    episode_html = requests.get(episode_url, headers=headers, timeout=5)
    episode_html.raise_for_status()
    soup = BeautifulSoup(episode_html.text, "html.parser")
    title = None
    if "https://s.to/" in episode_url:
        title_tag = soup.find("h1", class_="title")
        if title_tag:
            title = title_tag.get_text(strip=True)
    elif "https://aniworld.to/" in episode_url:
        title_tag = soup.find("h1", class_="title")
        if title_tag:
            title = title_tag.get_text(strip=True)
    return title