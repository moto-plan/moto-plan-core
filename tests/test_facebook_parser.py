import json

from moto_plan_core.parsers import FacebookEventsParser


from unittest.mock import patch


def test_facebook_empty():
    with patch.object(FacebookEventsParser, "_scrape", return_value=[]):
        assert FacebookEventsParser.parse("", agency="Cones") == []


def test_facebook_parse_jsonld():
    data = {
        "@type": "Event",
        "name": "Kurz",
        "startDate": "2026-06-01",
        "location": {"name": "Most"},
        "offers": {"price": "1200"},
    }
    html = f'<script type="application/ld+json">{json.dumps(data)}</script>'
    events = FacebookEventsParser.parse(html, agency="Cones", url="https://facebook.com")
    assert len(events) == 1
    assert events[0].track_name == "Most"
    assert events[0].prices[0]["amount"] == 1200.0
