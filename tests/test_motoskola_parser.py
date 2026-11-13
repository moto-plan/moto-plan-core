from unittest.mock import patch

from moto_plan_core.parsers import MotoSkolaRadekandrlikParser


def test_motoskola_empty_without_playwright():
    # Playwright is not available in test env, so parse returns []
    assert MotoSkolaRadekandrlikParser.parse("") == []


def test_motoskola_with_mocked_api():
    fake_resp = [{
        "dataItems": [{
            "id": "1",
            "data": {
                "title": "Motoškola na okruhu",
                "date": {"$date": "2026-06-01T08:00:00Z"},
                "od": "08:00",
                "do": {"$date": "2026-06-01T17:00:00Z"},
                "address": "Písek",
                "volnychMist": "5 osob",
            },
        }],
    }]
    with patch("asyncio.run", return_value=fake_resp):
        events = MotoSkolaRadekandrlikParser.parse("", agency="MS", url="https://example.com")
    assert len(events) == 1
    assert events[0].track_name == "Písek"
