from moto_plan_core.parsers import NaOkruhParser


def test_naokruh_empty():
    assert NaOkruhParser.parse("") == []


def test_naokruh_parse_basic():
    html = '''
    <li class="product">
      <h2 class="woocommerce-loop-product__title">Event 1.6.2026</h2>
      <a href="https://naokruh.eu/e1">link</a>
      <span class="woocommerce-Price-amount amount"><bdi>1200</bdi></span>
    </li>
    '''
    events = NaOkruhParser.parse(html, agency="NaOkruh", url="https://naokruh.eu")
    assert len(events) == 1
    assert events[0].prices[0]["amount"] == 1200.0
