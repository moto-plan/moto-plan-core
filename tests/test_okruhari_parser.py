from unittest.mock import patch

from moto_plan_core.parsers import OkruhariParser


def test_okruhari_empty():
    assert OkruhariParser.parse("") == []


def test_okruhari_parse_basic():
    html = '''
    <div class="product">
      <div class="p">
        <span data-testid="productCardName">Most 1. 6. 2026</span>
        <strong>1200 Kč</strong>
        <a href="/detail">detail</a>
      </div>
    </div>
    '''
    with patch("moto_plan_core.parsers.SiteFetcher.fetch", return_value=""):
        events = OkruhariParser.parse(html, agency="Okruháři", url="https://okruhari.cz")
    assert len(events) == 1
    assert events[0].track_name == "Most"
    assert events[0].prices[0]["amount"] == 1200.0
