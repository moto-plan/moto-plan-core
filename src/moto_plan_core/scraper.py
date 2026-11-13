from .database import DatabaseWriter
from .fetcher import SiteFetcher
from .formatter import EventFormatter
from .models import Event
from .parsers import EventParser


class MotoPlanScraper:
    def __init__(self, url: str, agency: str = "", parser: object | None = None,
                 fetcher: SiteFetcher | None = None, db_path: str | None = None):
        self.url = url
        self.agency = agency
        self.fetcher = fetcher or SiteFetcher()
        self.parser = parser or EventParser()
        self.formatter = EventFormatter()
        self.db_path = db_path

    def run(self) -> list[Event]:
        print(f"Fetching {self.url} ...")
        html = self.fetcher.fetch(self.url)
        events = self.parser.parse(html, agency=self.agency, url=self.url)
        if not events:
            print("No events found.")
            return []
        self.formatter.format_events(events)

        if self.db_path:
            with DatabaseWriter(self.db_path) as db:
                db.upsert_events(events)
            print(f"Saved {len(events)} events to {self.db_path}")
        return events
