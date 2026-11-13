import importlib
import os

from moto_plan_core import concurrency


def test_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("SCRAPE_MAX_WORKERS", "not-a-number")
    importlib.reload(concurrency)
    assert concurrency.scrape_workers(31) == concurrency.DEFAULT_MAX_WORKERS
