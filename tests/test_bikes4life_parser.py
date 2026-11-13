from unittest.mock import patch, MagicMock

from moto_plan_core.parsers import Bikes4LifeParser


def test_bikes4life_empty():
    assert Bikes4LifeParser.parse("") == []


def test_bikes4life_parse_basic():
    html = '''
    <section id="akce">
      <div class="row mt-4">
        <div class="col-lg-6">
          <a href="/detail"><h3 class="textRed">Okruh Most 1. 6. 2026</h3></a>
          <span class="text-danger">Volno</span>
        </div>
      </div>
    </section>
    '''
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'<div class="shopBlock activeEvent" data-id="1" data-start="a" data-end="b"></div>'
    mock_resp.headers.get_content_charset.return_value = "utf-8"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    with patch("urllib.request.urlopen", return_value=mock_resp), patch("moto_plan_core.parsers.Bikes4LifeParser._fetch_price", return_value=1200):
        events = Bikes4LifeParser.parse(html, agency="Bikes4Life", url="https://bikes4life.cz")
    assert len(events) == 1
    assert events[0].track_name == "Most"
    assert events[0].prices[0]["amount"] == 1200.0
