from unittest.mock import patch, MagicMock

from moto_plan_core.fetcher import SiteFetcher


def test_fetch_decodes_charset():
    mock_resp = MagicMock()
    mock_resp.headers.get_content_charset.return_value = "utf-8"
    mock_resp.read.return_value = b"hello"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert SiteFetcher().fetch("https://example.com") == "hello"


def test_fetch_default_timeout():
    f = SiteFetcher(timeout=5)
    assert f.timeout == 5
