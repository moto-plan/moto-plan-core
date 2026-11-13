from unittest.mock import patch

from moto_plan_core.parsers import MotoSkolaRadekandrlikParser


def _run(fake_resp):
    with patch("asyncio.run", return_value=fake_resp):
        return MotoSkolaRadekandrlikParser.parse("", agency="MS", url="https://example.com")


def test_motoskola_italy_and_soldout():
    fake_resp = [{
        "dataItems": [{
            "id": "2",
            "data": {
                "title": "Motoškola v Itálii",
                "date": {"$date": "2026-06-01T08:00:00Z"},
                "od": "08:00",
                "do": {"$date": "2026-06-03T17:00:00Z"},
                "address": "Dolomity, Itálie",
                "volnychMist": "0 osob",
            },
        }],
    }]
    events = _run(fake_resp)
    assert len(events) == 1
    assert events[0].track_name == "Dolomity, Itálie"
    assert events[0].sold_out is True
    assert events[0].date == "1. 6–3. 6. 2026"


def test_motoskola_unknown_price():
    fake_resp = [{
        "dataItems": [{
            "id": "3",
            "data": {
                "title": "Unknown title",
                "date": {"$date": "2026-07-01T08:00:00Z"},
                "od": "09:00",
                "do": "10:00",
                "address": "Písek",
                "volnychMist": "5 osob",
            },
        }],
    }]
    events = _run(fake_resp)
    assert len(events) == 1
    assert events[0].prices == []


def test_motoskola_malformed_item():
    fake_resp = [{"dataItems": [{"id": "4", "data": {}}]}]
    events = _run(fake_resp)
    assert events == []
