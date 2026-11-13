from moto_plan_core.parsers import Hefty74Parser


def test_hefty74_empty():
    assert Hefty74Parser().parse("") == []


def test_hefty74_parse_basic():
    html = """
    <h4>1200 KČ</h4>
    <div class="akce-wrapper">
      <div class="akce-column">
        <h2>Most</h2>
        <ul>
          <li class="termin"><span class="den">10. 5. (So)</span><a href="/detail/2026">detail</a>OBSAZENO</li>
        </ul>
      </div>
    </div>
    </div>
    </div>
    """
    events = Hefty74Parser().parse(html, agency="Hefty74", url="https://hefty74.cz")
    assert len(events) == 1
    assert events[0].track_name == "Most"
    assert events[0].sold_out is True


def test_hefty74_helpers():
    assert Hefty74Parser._parse_den("10. 5.") == {"day": 10, "month_num": 5}
    assert Hefty74Parser._parse_den("bad") is None
    assert Hefty74Parser._extract_year("https://x/2026/", 5) == 2026
    assert Hefty74Parser._parse_day_names("So") == ["Saturday"]
    assert Hefty74Parser._parse_global_prices('<h4>1200 KČ</h4>') == [{"day_label": "", "amount": 1200.0, "currency": "CZK"}]
    assert Hefty74Parser._extract_track_name("<h2>Most</h2>") == "Most"
