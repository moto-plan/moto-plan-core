import argparse
import os
import time
from pathlib import Path

from .formatter import EventFormatter
from .registry import _PARSERS, scrape_all
from .scraper import MotoPlanScraper

_TEXTFILE_DIR = Path("/var/lib/node_exporter/textfile")
_PROM_FILE = _TEXTFILE_DIR / "moto_scrape.prom"


def _write_scrape_metric(event_count: int) -> None:
    try:
        _TEXTFILE_DIR.mkdir(parents=True, exist_ok=True)
        _PROM_FILE.write_text(
            f"# HELP moto_scrape_last_success_timestamp_seconds Unix timestamp of last successful scrape\n"
            f"# TYPE moto_scrape_last_success_timestamp_seconds gauge\n"
            f"moto_scrape_last_success_timestamp_seconds {int(time.time())}\n"
            f"# HELP moto_scrape_last_event_count Number of events found in last scrape\n"
            f"# TYPE moto_scrape_last_event_count gauge\n"
            f"moto_scrape_last_event_count {event_count}\n"
        )
    except OSError as e:
        print(f"[scraper] failed to write metric: {e}")


def _loop(db_path: str, interval_hours: int):
    import signal
    running = True

    def _stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while running:
        print("[scraper] scraping all sites ...")
        try:
            events = scrape_all(db_path=db_path)
            _write_scrape_metric(len(events))
        except Exception as e:
            print(f"[scraper] scrape failed: {e}")
        if not running:
            break
        print(f"[scraper] sleeping {interval_hours}h ...")
        for _ in range(interval_hours * 60):
            if not running:
                break
            time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Scrape moto plan events and optionally persist to SQLite.")
    parser.add_argument("url", nargs="?", help="Agency URL to scrape (omit to scrape all sites)")
    parser.add_argument("--agency", default="", help="Agency name (required with url)")
    parser.add_argument("--parser", choices=list(_PARSERS), help="Parser to use (required with url)")
    parser.add_argument("--db", default="data/events.db", help="Path to SQLite database file (default: data/events.db)")
    parser.add_argument("--loop", action="store_true", help="Run in continuous loop with interval")
    parser.add_argument("--interval", type=int,
                        default=int(os.environ.get("SCRAPE_INTERVAL_HOURS", "1")),
                        help="Scrape interval in hours (default: 1, or $SCRAPE_INTERVAL_HOURS)")
    args = parser.parse_args()

    if args.loop:
        _loop(args.db, args.interval)
        return

    if args.url:
        if not args.agency or not args.parser:
            parser.error("--agency and --parser are required when scraping a single URL")
        MotoPlanScraper(args.url, agency=args.agency, parser=_PARSERS[args.parser], db_path=args.db).run()
    else:
        events = scrape_all(db_path=args.db)
        if not events:
            print("No events found.")
            return
        _write_scrape_metric(len(events))
        EventFormatter.format_events(events)


if __name__ == "__main__":
    main()
