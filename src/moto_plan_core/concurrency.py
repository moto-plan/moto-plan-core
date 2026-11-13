import os

DEFAULT_MAX_WORKERS = 6


def scrape_workers(requested: int) -> int:
    try:
        limit = int(os.environ.get("SCRAPE_MAX_WORKERS", DEFAULT_MAX_WORKERS))
    except ValueError:
        limit = DEFAULT_MAX_WORKERS
    return max(1, min(requested, limit))
