from unittest.mock import patch

from moto_plan_core.parsers import CarsJetParser


def test_carsjet_empty():
    assert CarsJetParser().parse("") == []


def test_carsjet_parse_basic():
    html = '''
    <article class="item">
      <strong>Trackday Most</strong>
      1.6.2026
      Cena: 1 200,-
      Čas: 09:00 - 17:00
      <a href="/detail">detail</a>
    </article>
    '''
    with patch("moto_plan_core.parsers.SiteFetcher.fetch", return_value=""):
        events = CarsJetParser().parse(html, agency="CarsJet", url="https://carsjet.cz")
    assert len(events) == 1
    assert events[0].track_name == "Most"
    assert events[0].prices[0]["amount"] == 1200.0
