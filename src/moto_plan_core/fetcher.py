import urllib.request


class SiteFetcher:
    def __init__(self, user_agent: str = "MotoPlanCalendar/0.1", timeout: int = 15):
        self.user_agent = user_agent
        self.timeout = timeout

    def fetch(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read().decode(resp.headers.get_content_charset() or "utf-8")
