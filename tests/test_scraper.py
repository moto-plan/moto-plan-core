from unittest.mock import MagicMock, patch

from moto_plan_core.models import Event
from moto_plan_core.scraper import MotoPlanScraper


def test_run_no_events(capsys):
    fetcher = MagicMock()
    fetcher.fetch.return_value = "<html></html>"
    parser = MagicMock()
    parser.parse.return_value = []
    scraper = MotoPlanScraper("https://example.com", agency="A", fetcher=fetcher, parser=parser)
    assert scraper.run() == []
    out = capsys.readouterr().out
    assert "No events found" in out


def test_run_saves_db(tmp_path):
    fetcher = MagicMock()
    fetcher.fetch.return_value = "<html></html>"
    parser = MagicMock()
    parser.parse.return_value = [Event(agency="A", track_name="T", date="1. 1. 2026")]
    db_path = str(tmp_path / "events.db")
    scraper = MotoPlanScraper("https://example.com", agency="A", fetcher=fetcher, parser=parser, db_path=db_path)
    with patch("moto_plan_core.scraper.DatabaseWriter") as dw:
        dw.return_value.__enter__.return_value.upsert_events = MagicMock()
        events = scraper.run()
    assert len(events) == 1
