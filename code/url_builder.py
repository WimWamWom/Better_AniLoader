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
