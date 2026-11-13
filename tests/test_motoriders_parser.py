from unittest.mock import patch

from moto_plan_core.parsers import MotoridersParser


def test_motoriders_empty():
    with patch.object(MotoridersParser, "_fetch_all", return_value=[]):
        assert MotoridersParser().parse("", agency="MR", url="https://motoriders.cz") == []


def test_motoriders_parse_with_mocked_api():
    api_events = [{
        "id": "1",
        "racetrack": "Most",
        "dates": ["2026-06-01", "2026-06-02"],
        "priceVat": 1200,
        "capacity": 10,
        "signups": 2,
        "headline": "Trackday",
        "disabled": False,
    }]
    with patch.object(MotoridersParser, "_fetch_all", return_value=api_events):
        events = MotoridersParser().parse("", agency="MR", url="https://motoriders.cz")
    assert len(events) == 1
    assert events[0].track_name == "Most"
    assert events[0].sold_out is False


def test_motoriders_helpers():
    assert MotoridersParser._filter_2026_events([{"disabled": False, "dates": ["2026-01-01"]}]) == [{"disabled": False, "dates": ["2026-01-01"]}]
    assert MotoridersParser._parse_date("2026-06-01") == (1, 6, 2026)
