import json

from moto_plan_core.parsers import StopNehodamParser


def test_stopnehodam_empty():
    assert StopNehodamParser.parse("") == []


def test_stopnehodam_parse_basic():
    data = {
        "@type": "Event",
        "name": "Hoškovice",
        "startDate": "2026-06-01T08:00:00Z",
        "location": {"name": "Hoškovice"},
    }
    html = f'<script type="application/ld+json">{json.dumps(data)}</script>'
    events = StopNehodamParser.parse(html, agency="StopNehodam", url="https://stopnehodam.cz")
    assert len(events) == 1
    assert events[0].prices[0]["amount"] == 2900.0
