from moto_plan_core.parsers import OkruhariSkParser


def test_okruharisk_empty():
    assert OkruhariSkParser.parse("") == []


def test_okruharisk_parse_basic():
    html = '''
    <div class="product type-product">
      <h2 class="product-title"><a href="/e1">Slovakiaring 1.6.-2.6.2026</a></h2>
      <span class="woocommerce-Price-amount"><bdi>100 EUR</bdi></span>
      <div class="products-page-cats">racing</div>
    </div>
    '''
    events = OkruhariSkParser.parse(html, agency="Okruhári.sk", url="https://okruhari.sk")
    assert len(events) == 1
    assert events[0].track_name == "Slovakiaring"
    assert events[0].category == "closed_track"
    assert events[0].prices[0]["amount"] == 100.0
