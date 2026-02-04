import time
from typing import List

from bs4 import BeautifulSoup


def get_languages_for_episode(episode_url: str):
    # open with utf-8 and replace undecodable bytes to avoid UnicodeDecodeError on Windows
    with open("lie_in_april.html", "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    sprachen: List[str] = []
    vorhandene_sprachen: List[str] = []
    lang_div = soup.find("div", class_="changeLanguageBox")
    if "https://aniworld.to/" in episode_url:
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

if __name__ == "__main__":
    start = time.perf_counter()

    print(get_languages_for_episode("https://aniworld.to/anime/stream/your-lie-in-april/staffel-1/episode-1"))


    elapsed = time.perf_counter() - start
    print(f"Elapsed: {elapsed:.2f}s")