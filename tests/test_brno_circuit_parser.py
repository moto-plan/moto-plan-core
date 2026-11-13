from unittest.mock import patch

from moto_plan_core.parsers import BrnoCircuitParser


def test_brno_circuit_empty():
    assert BrnoCircuitParser().parse("") == []


def test_brno_circuit_parse_with_mocked_detail():
    listing = '<div class="box__item"><h4>Open Track For Public MOTO 1.6.2026</h4><a class="link-hidden" href="/detail">detail</a></div>'
    detail = '''
    <div class="terms-list__item">
      <div class="terms-list__item-price">1200 Kč</div>
      <div class="terms-list__item-headline"><span>09:00</span></div>
      <button class="mdi-cart"></button>
      <div class="free_capacity" title="Available"></div>
    </div>
    '''
    with patch("moto_plan_core.parsers.SiteFetcher.fetch", return_value=detail):
        events = BrnoCircuitParser().parse(listing, agency="Brno", url="https://brno.cz")
    assert len(events) == 1
    assert events[0].prices[0]["amount"] == 1200.0
    assert events[0].sold_out is False
