import importlib

from moto_plan_core import concurrency


def test_default_caps_requested(monkeypatch):
    monkeypatch.delenv("SCRAPE_MAX_WORKERS", raising=False)
    importlib.reload(concurrency)
    assert concurrency.scrape_workers(31) == concurrency.DEFAULT_MAX_WORKERS
    assert concurrency.scrape_workers(2) == 2
    assert concurrency.scrape_workers(0) == 1


def test_env_override(monkeypatch):
    monkeypatch.setenv("SCRAPE_MAX_WORKERS", "10")
    importlib.reload(concurrency)
    assert concurrency.scrape_workers(31) == 10
    assert concurrency.scrape_workers(3) == 3


def test_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("SCRAPE_MAX_WORKERS", "not-a-number")
    importlib.reload(concurrency)
    assert concurrency.scrape_workers(31) == concurrency.DEFAULT_MAX_WORKERS
    importlib.reload(concurrency)
