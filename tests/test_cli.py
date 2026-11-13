import os
from unittest.mock import MagicMock, patch

import pytest


def test_loop_calls_scrape_all():
    mock_scrape_all = MagicMock()
    handlers = {}

    def capture_signal(sig, handler):
        handlers[sig] = handler

    with patch("signal.signal", capture_signal):
        with patch("moto_plan_core.cli.scrape_all", mock_scrape_all):
            with patch("moto_plan_core.cli.time.sleep", side_effect=lambda s: None):
                import moto_plan_core.cli
                from threading import Thread
                import time as time_module
                t = Thread(target=moto_plan_core.cli._loop, args=("test.db", 1))
                t.start()
                time_module.sleep(0.01)
                for sig, handler in handlers.items():
                    handler(None, None)
                t.join(timeout=2)

    assert mock_scrape_all.call_count >= 1
    for call in mock_scrape_all.call_args_list:
        assert call.kwargs == {"db_path": "test.db"}


def test_loop_handles_scrape_exception():
    handlers = {}

    def capture_signal(sig, handler):
        handlers[sig] = handler

    with patch("signal.signal", capture_signal):
        with patch("moto_plan_core.cli.scrape_all", side_effect=ValueError("boom")):
            with patch("moto_plan_core.cli.time.sleep"):
                import moto_plan_core.cli
                from threading import Thread
                import time as time_module
                t = Thread(target=moto_plan_core.cli._loop, args=("test.db", 1))
                t.start()
                time_module.sleep(0.05)
                for sig, handler in handlers.items():
                    handler(None, None)
                t.join(timeout=2)


def test_loop_with_interval():
    mock_scrape_all = MagicMock()
    mock_sleep = MagicMock()
    handlers = {}

    def capture_signal(sig, handler):
        handlers[sig] = handler

    with patch("signal.signal", capture_signal):
        with patch("moto_plan_core.cli.scrape_all", mock_scrape_all):
            with patch("moto_plan_core.cli.time.sleep", mock_sleep):
                import moto_plan_core.cli
                from threading import Thread
                import time as time_module
                t = Thread(target=moto_plan_core.cli._loop, args=("test.db", 1))
                t.start()
                time_module.sleep(0.05)
                for sig, handler in handlers.items():
                    handler(None, None)
                t.join(timeout=2)

    assert mock_scrape_all.call_count >= 1


def test_stop_handler_from_scrape():
    stop_handler = None

    def capture_signal(sig, handler):
        nonlocal stop_handler
        stop_handler = handler

    with patch("signal.signal", capture_signal):
        with patch("moto_plan_core.cli.time.sleep"):
            with patch("moto_plan_core.cli.scrape_all") as mock_scrape:
                mock_scrape.side_effect = lambda db_path=None: (
                    stop_handler(None, None) if stop_handler else None
                )
                import moto_plan_core.cli
                moto_plan_core.cli._loop("test.db", 0)

    mock_scrape.assert_called_once()


def test_main_with_loop_flag():
    with patch("moto_plan_core.cli._loop") as mock_loop:
        with patch("moto_plan_core.cli.scrape_all") as mock_scrape:
            with patch("sys.argv", ["prog", "--loop"]):
                import moto_plan_core.cli
                moto_plan_core.cli.main()

    mock_loop.assert_called_once()
    mock_scrape.assert_not_called()


def test_main_with_loop_and_interval():
    with patch("moto_plan_core.cli._loop") as mock_loop:
        with patch("sys.argv", ["prog", "--loop", "--interval", "3"]):
            import moto_plan_core.cli
            moto_plan_core.cli.main()

    mock_loop.assert_called_once_with("data/events.db", 3)


def test_main_with_loop_and_env_interval():
    old = os.environ.get("SCRAPE_INTERVAL_HOURS")
    try:
        os.environ["SCRAPE_INTERVAL_HOURS"] = "5"
        with patch("moto_plan_core.cli._loop") as mock_loop:
            with patch("sys.argv", ["prog", "--loop"]):
                import moto_plan_core.cli
                moto_plan_core.cli.main()
        mock_loop.assert_called_once()
        assert mock_loop.call_args[0][1] == 5
    finally:
        if old is None:
            os.environ.pop("SCRAPE_INTERVAL_HOURS", None)
        else:
            os.environ["SCRAPE_INTERVAL_HOURS"] = old


def test_main_with_url_no_args():
    with patch("sys.argv", ["prog", "http://example.com"]):
        import moto_plan_core.cli
        with pytest.raises(SystemExit):
            moto_plan_core.cli.main()


def test_main_with_url_and_args():
    mock_scraper = MagicMock()
    with patch("moto_plan_core.cli.MotoPlanScraper", return_value=mock_scraper):
        with patch("sys.argv", ["prog", "http://example.com", "--agency", "Test", "--parser", "gripandgas"]):
            import moto_plan_core.cli
            moto_plan_core.cli.main()

    mock_scraper.run.assert_called_once()


def test_main_scrape_all():
    mock_events = [MagicMock(), MagicMock()]
    mock_formatter = MagicMock()
    with patch("moto_plan_core.cli.scrape_all", return_value=mock_events):
        with patch("moto_plan_core.cli.EventFormatter.format_events", mock_formatter):
            with patch("sys.argv", ["prog"]):
                import moto_plan_core.cli
                moto_plan_core.cli.main()

    mock_formatter.assert_called_once_with(mock_events)


def test_main_scrape_all_no_events():
    with patch("moto_plan_core.cli.scrape_all", return_value=[]):
        with patch("sys.argv", ["prog"]):
            import moto_plan_core.cli
            moto_plan_core.cli.main()
