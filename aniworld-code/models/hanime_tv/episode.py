class HanimeTVEpisode:
    # TODO: implement
    def __init__(self, url):
        self.url = url

    def download(self):
        print(f"Downloading Hanime TV episode from {self.url}")

    def watch(self):
        print(f"Watching Hanime TV episode from {self.url}")

    def syncplay(self):
        print(f"Syncplaying Hanime TV episode from {self.url}")
