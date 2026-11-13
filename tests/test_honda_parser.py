from unittest.mock import patch

from moto_plan_core.parsers import HondaExperienceParser


def test_honda_empty():
    assert HondaExperienceParser.parse("") == []


def test_honda_parse_with_mocked_detail():
    listing = '<div class="product-grid"><a class="product-name" href="/hmst/detail">HMST</a></div>'
    detail = '''
    <meta itemprop="lowPrice" content="1200">
    <select name="product">
      <option>1. 6. 2026 09:00</option>
    </select>
    '''
    with patch("moto_plan_core.parsers.SiteFetcher.fetch", return_value=detail):
        events = HondaExperienceParser.parse(listing, agency="Honda", url="https://honda.cz")
    assert len(events) == 1
    assert events[0].prices[0]["amount"] == 1200.0
