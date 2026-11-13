import pathlib
from unittest.mock import patch

from moto_plan_core.registry import _PARSERS, _SITES


def _agency_for(key):
    for _url, agency, k in _SITES:
        if k == key:
            return agency
    return ""


def test_parsers_handle_fixture_html():
    with patch("moto_plan_core.fetcher.SiteFetcher.fetch", return_value=""):
        for path in sorted(pathlib.Path("tests/fixtures").glob("*.html")):
            key = path.stem
            if key not in _PARSERS:
                continue
            html = path.read_text(encoding="utf-8", errors="replace")
            parser = _PARSERS[key]
            events = parser.parse(html, agency=_agency_for(key), url=f"https://example.com/{key}")
            assert isinstance(events, list)
