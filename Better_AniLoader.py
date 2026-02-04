from typing import List, Dict
import time
import requests
from bs4 import BeautifulSoup
languages = [
    "German Dub",
    "German Sub",
    "English Dub",
    "English Sub",
]
headers = {"User-Agent": "Mozilla/5.0 (compatible; AniLoaderBot/1.0)"}

def get_season_url(url: str, staffel: str) -> str:
        if "https://s.to/" in url: 
            staffel_url = url.rstrip('/') + '/staffel-' + staffel
        elif int(staffel) > 0 and "https://aniworld.to/" in url:
            staffel_url = url.rstrip('/') + '/staffel-' + staffel
        elif staffel.strip().lower() == "filme" and "https://aniworld.to/" in url:
            staffel_url = url.rstrip('/') + '/filme'
        else:
            return ""
        return staffel_url

def get_episode_url(url: str, staffel: str, episode: str) -> str:
        staffel_url = get_season_url(url, staffel)
        if "https://s.to/" in url: 
            episode_url = staffel_url.rstrip('/') + '/episode-' + episode
        elif int(staffel) > 0 and "https://aniworld.to/" in url:
            episode_url = staffel_url.rstrip('/') + '/episode-' + episode
        elif staffel.strip().lower() == "filme" and "https://aniworld.to/" in url:
            episode_url = staffel_url.rstrip('/') + '/episode-' + episode
        else:
            return ""
        return episode_url

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
    # find svg language icons (class may contain multiple tokens)
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
    if "https://aniworld.to/" in episode_url:
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

    return sprachen

def build_CLI_download(url: str):
    seasons = get_seasons_with_episode_count(url)
    if seasons == -1:
        print("Error retrieving seasons or episodes.")
        return 1
    for season in seasons:
        for episode in seasons[season]:
            episode_url = get_episode_url(url, season, episode)
            sprachen = get_languages_for_episode(episode_url)
            if sprachen:
                if languages[0] in sprachen:
                    sprache = languages[0]
                elif languages[1] in sprachen:
                    sprache = languages[1]
                elif languages[2] in sprachen:
                    sprache = languages[2]
                elif languages[3] in sprachen:
                    sprache = languages[3]
                else:
                    return -1
                print("aniworld", "--language", sprache, "-o", "C:\\Users\\wroehner\\Desktop\\Git\\AniLoader Test\\Downloads", "--episode", episode_url)
    return 0 


def check_new_german(episode_url: str) -> bool:
    sprachen = get_languages_for_episode(episode_url)
    if sprachen:
        if "German Dub" in sprachen:
            return True
    return False


if __name__ == "__main__":
    start = time.perf_counter()

    test_urls = [
                    "https://s.to/serie/the-rookie",
                    "https://s.to/serie/die-drachenreiter-von-berk",
                 ]
    #for url in test_urls:
    #    print(f"Seasons with episodes from {url}:", get_seasons_with_episode_count(url))
    #print(get_languages_for_episode("https://s.to/serie/patience/staffel-1/episode-1"))
    build_CLI_download("https://s.to/serie/the-rookie")


    elapsed = time.perf_counter() - start
    print(f"Elapsed: {elapsed:.2f}s")