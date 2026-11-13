from unittest.mock import Mock, patch

import moto_plan_core.parsers

from moto_plan_core.parsers import (
    BrnoCircuitParser,
    FacebookEventsParser,
    Hefty74Parser,
    MotoridersParser,
    GasovaMotoskolaParser,
    BezpecneNaMotorceParser,
)
from bs4 import BeautifulSoup


_HTML_PARSER = "html.parser"


def test_category_free_ride():
    assert moto_plan_core.parsers._category_from_track_and_title("Písek", "Volné jízdy") == "free_ride"
    assert moto_plan_core.parsers._category_from_track_and_title("Most", "Volny trening") == "free_ride"
    assert moto_plan_core.parsers._category_from_track_and_title("Most", "trénink volné") == "free_ride"


def test_category_public_roads():
    assert moto_plan_core.parsers._category_from_track_and_title("Itálie", "Trip") == "public_roads"
    assert moto_plan_core.parsers._category_from_track_and_title("Italy", "Road trip") == "public_roads"
    assert moto_plan_core.parsers._category_from_track_and_title("Itálie - Monza", "Tour") == "public_roads"


def test_category_default():
    assert moto_plan_core.parsers._category_from_track_and_title("Písek", "Trénink") == "closed_track"
    assert moto_plan_core.parsers._category_from_track_and_title("Most", "Kurz") == "closed_track"


def test_simple_track_pisek():
    assert moto_plan_core.parsers._simple_track("Písek") == "Písek"
    assert moto_plan_core.parsers._simple_track("Autodrom Písek") == "Písek"
    assert moto_plan_core.parsers._simple_track("okruh Písek") == "Písek"


def test_simple_track_most():
    assert moto_plan_core.parsers._simple_track("Most") == "Most"
    assert moto_plan_core.parsers._simple_track("Polygon Most") == "Most"


def test_simple_track_unknown():
    assert moto_plan_core.parsers._simple_track("Brno") == "?"
    assert moto_plan_core.parsers._simple_track("Sosnová") == "?"


def test_filter_2026_events():
    data = [
        {"disabled": True, "dates": ["2026-06-01"]},
        {"disabled": False, "dates": ["2025-06-01"]},
        {"disabled": False, "dates": ["2026-06-01"]},
        {"disabled": False, "dates": ["2026-07-15"]},
        {"disabled": True, "dates": ["2026-08-01"]},
    ]
    result = MotoridersParser._filter_2026_events(data)
    assert len(result) == 2
    assert result[0]["dates"][0] == "2026-06-01"
    assert result[1]["dates"][0] == "2026-07-15"


def test_filter_2026_events_empty():
    assert MotoridersParser._filter_2026_events([]) == []


def test_filter_2026_events_no_match():
    data = [{"disabled": False, "dates": ["2025-06-01"]}]
    assert MotoridersParser._filter_2026_events(data) == []


def test_is_sold_out():
    assert GasovaMotoskolaParser._is_sold_out("vyprodáno") is True
    assert GasovaMotoskolaParser._is_sold_out("VyProdáno") is True
    assert GasovaMotoskolaParser._is_sold_out("prodáno") is True
    assert GasovaMotoskolaParser._is_sold_out("dostupné") is False
    assert GasovaMotoskolaParser._is_sold_out("") is False


def test_category():
    assert GasovaMotoskolaParser._category("enduro kurz") == "enduro"
    assert GasovaMotoskolaParser._category("Enduro") == "enduro"
    assert GasovaMotoskolaParser._category("offroad") == "enduro"
    assert GasovaMotoskolaParser._category("OFFROAD") == "enduro"
    assert GasovaMotoskolaParser._category("skola") == "public_roads"
    assert GasovaMotoskolaParser._category("") == "public_roads"


def test_cell_text():
    html = "<table><tr><td>First</td><td>Second</td><td>Third</td></tr></table>"
    soup = BeautifulSoup(html, _HTML_PARSER)
    cells = soup.find_all("td")
    assert GasovaMotoskolaParser._cell_text(cells, 0) == "First"
    assert GasovaMotoskolaParser._cell_text(cells, 1) == "Second"
    assert GasovaMotoskolaParser._cell_text(cells, 2) == "Third"
    assert GasovaMotoskolaParser._cell_text(cells, 5) == ""


def test_extract_json_array():
    text = '{"data": [1, 2, 3], "extra": "value"}'
    start = text.index("[")
    result = BezpecneNaMotorceParser._extract_json_array(text, start)
    assert result == "[1, 2, 3]"


def test_extract_json_array_nested():
    text = '{"items": [[1, 2], [3, 4]]}'
    start = text.index("[")
    result = BezpecneNaMotorceParser._extract_json_array(text, start)
    assert result == "[[1, 2], [3, 4]]"


def test_extract_json_array_invalid():
    result = BezpecneNaMotorceParser._extract_json_array("not json", 0)
    assert result is None


def test_extract_json_array_out_of_bounds():
    result = BezpecneNaMotorceParser._extract_json_array("[]", 10)
    assert result is None


def test_fetch_page_returns_data():
    parser = MotoridersParser()
    fetcher = Mock()
    fetcher.fetch.return_value = '[{"id": 1}]'
    result = parser._fetch_page(fetcher, 1)
    assert result == [{"id": 1}]


def test_fetch_page_returns_none_on_error():
    parser = MotoridersParser()
    fetcher = Mock()
    fetcher.fetch.side_effect = Exception("fail")
    result = parser._fetch_page(fetcher, 1)
    assert result is None


def test_fetch_all_uses_fetch_page():
    parser = MotoridersParser()
    parser._API_BASE = "http://test"
    parser._fetch_page = Mock(side_effect=[
        [{"id": 1, "disabled": False, "dates": ["2026-06-01"]} for _ in range(50)],
        None,
    ])
    result = parser._fetch_all()
    assert len(result) == 50


def test_fetch_all_breaks_on_short_page():
    parser = MotoridersParser()
    parser._fetch_page = Mock(return_value=[{"id": 1, "disabled": False, "dates": ["2026-06-01"]}])
    parser._filter_2026_events = Mock(side_effect=lambda d: d)
    result = parser._fetch_all()
    assert len(result) == 1


def test_hefty_extract_track_name():
    col = '<div><h2>Test Track</h2></div>'
    result = Hefty74Parser._extract_track_name(col)
    assert result == "Test Track"


def test_hefty_extract_track_name_no_match():
    col = '<div>no h2 here</div>'
    result = Hefty74Parser._extract_track_name(col)
    assert result is None


def test_hefty_build_event():
    li = '<li class="termin"><span class="den">15. 6.</span></li>'
    parser = Hefty74Parser()
    parser._parse_den = Mock(return_value={"day": 15, "month_num": 6, "year": 2026})
    parser._extract_year = Mock(return_value=2026)
    parser._parse_day_names = Mock(return_value="Monday")
    ev = parser._build_event(li, "Test Track", [], "TestAgency", "http://url")
    assert ev is not None
    assert ev.track_name == "Test Track"
    assert ev.day == 15


def test_hefty_build_event_no_den():
    parser = Hefty74Parser()
    ev = parser._build_event("<li>no den</li>", "T", [], "A", "u")
    assert ev is None


def test_hefty_build_event_no_link():
    parser = Hefty74Parser()
    parser._parse_den = Mock(return_value={"day": 1, "month_num": 6})
    parser._extract_year = Mock(return_value=2026)
    parser._parse_day_names = Mock(return_value="Tue")
    li = '<li class="termin"><span class="den">1. 6.</span></li>'
    ev = parser._build_event(li, "Track", [], "Agency", "http://fallback")
    assert ev is not None
    assert ev.url == "http://fallback"


def test_hefty_build_event_no_date_part():
    parser = Hefty74Parser()
    parser._parse_den = Mock(return_value=None)
    li = '<li class="termin"><span class="den">1. 6.</span></li>'
    ev = parser._build_event(li, "Track", [], "A", "u")
    assert ev is None


def test_hefty_parse_with_html():
    html = """
    <div class="akce-wrapper">
      <div class="akce-column">
        <h2>Test Track</h2>
        <li class="termin"><span class="den">15. 6.</span></li>
      </div>
    </div></div></div>
    """
    parser = Hefty74Parser()
    parser._parse_global_prices = Mock(return_value=[])
    parser._parse_den = Mock(return_value={"day": 15, "month_num": 6})
    parser._extract_year = Mock(return_value=2026)
    parser._parse_day_names = Mock(return_value="Monday")
    result = parser.parse(html, "Agency", "http://url")
    assert len(result) == 1
    assert result[0].track_name == "Test Track"


def test_hefty_parse_no_wrapper():
    result = Hefty74Parser().parse("<div>nothing</div>")
    assert result == []


def test_gasova_parse_with_html():
    html = "<table><tr><th>Header</th></tr><tr><td>15. 6. 2026</td><td>Kurz</td><td>dostupné</td></tr></table>"
    result = GasovaMotoskolaParser().parse(html)
    assert len(result) == 1
    assert result[0].year == 2026


def test_gasova_parse_no_table():
    result = GasovaMotoskolaParser().parse("<div>nothing</div>")
    assert result == []


def test_gasova_parse_row():
    parser = GasovaMotoskolaParser()
    html = "<table><tr><td>15. 6. 2026</td><td>Kurz</td><td>dostupné</td></tr></table>"
    soup = BeautifulSoup(html, "html.parser")
    row = soup.find("tr")
    ev = parser._parse_row(row, "Gasova Motoškola", "http://url")
    assert ev is not None
    assert ev.day == 15
    assert ev.month_num == 6
    assert ev.year == 2026


def test_scrape_single_event():
    page = Mock()
    page.content.return_value = "<html>detail</html>"
    with patch.object(FacebookEventsParser, "_process_detail", return_value=[Mock()]):
        result = FacebookEventsParser._scrape_single_event(page, "123", "A")
    assert len(result) == 1


def test_scrape_single_event_error():
    page = Mock()
    page.goto.side_effect = Exception("fail")
    result = FacebookEventsParser._scrape_single_event(page, "123", "A")
    assert result is None


def test_parse_columns_empty():
    result = Hefty74Parser()._parse_columns("<div>no columns</div>", [], "A", "u")
    assert result == []


def test_parse_columns_skips_no_h2():
    result = Hefty74Parser()._parse_columns('<div class="akce-column"><p>no h2</p></div>', [], "A", "u")
    assert result == []


def test_hefty_parse_termin_items():
    col = '<li class="termin"><span class="den">15. 6.</span></li><li class="termin"><span class="den">16. 6.</span></li>'
    parser = Hefty74Parser()
    parser._build_event = Mock(side_effect=[Mock(), None])
    result = parser._parse_termin_items(col, "Track", [], "A", "u")
    assert len(result) == 1


def test_hefty_parse_columns():
    wrapper = '<div class="akce-column"><h2>Track A</h2><div class="termin">15. 6.</div></div>'
    parser = Hefty74Parser()
    with patch.object(parser, "_parse_termin_items", return_value=[]):
        result = parser._parse_columns(wrapper, [], "A", "u")
    assert len(result) == 0


def test_scrape_events():
    page = Mock()
    with patch.object(FacebookEventsParser, "_scrape_single_event", side_effect=[
        [Mock()], None, [Mock(), Mock()]
    ]):
        result = FacebookEventsParser._scrape_events(page, {"1", "2", "3"}, "A")
    assert len(result) == 3


def test_scrape_events_empty():
    result = FacebookEventsParser._scrape_events(Mock(), set(), "A")
    assert result == []


def test_collect_event_ids():
    page = Mock()
    page.content.return_value = '<a href="/events/123">event</a><a href="/events/456">event2</a>'
    page.goto.return_value = None
    page.wait_for_load_state.return_value = None
    page.wait_for_timeout.return_value = None
    ids = FacebookEventsParser._collect_event_ids(page)
    assert "123" in ids
    assert "456" in ids


def test_collect_event_ids_error():
    page = Mock()
    page.goto.side_effect = Exception("fail")
    ids = FacebookEventsParser._collect_event_ids(page)
    assert ids == set()


def test_process_detail_uses_parse_soup():
    mock_ev = Mock(url="")
    with patch.object(FacebookEventsParser, "_parse_soup", return_value=[mock_ev]):
        result = FacebookEventsParser._process_detail("<html></html>", "A", "http://url")
    assert len(result) == 1
    assert result[0].url == "http://url"


def test_process_detail_fallback_to_extract():
    with patch.object(FacebookEventsParser, "_parse_soup", return_value=None):
        with patch.object(FacebookEventsParser, "_extract_from_text", return_value=Mock()):
            with patch.object(FacebookEventsParser, "_maybe_split_event", return_value=[Mock()]):
                result = FacebookEventsParser._process_detail("<html></html>", "A", "http://url")
    assert len(result) == 1


def test_process_detail_no_result():
    with patch.object(FacebookEventsParser, "_parse_soup", return_value=None):
        with patch.object(FacebookEventsParser, "_extract_from_text", return_value=None):
            result = FacebookEventsParser._process_detail("<html></html>", "A", "http://url")
    assert result == []


def test_gasova_parse_row_too_few_cells():
    row = BeautifulSoup("<tr><td>only</td></tr>", "html.parser")
    assert GasovaMotoskolaParser()._parse_row(row, "A", "u") is None


def test_gasova_parse_row_no_date():
    parser = GasovaMotoskolaParser()
    html = "<table><tr><td>invalid</td><td>Kurz</td><td>dostupné</td></tr></table>"
    soup = BeautifulSoup(html, "html.parser")
    row = soup.find("tr")
    ev = parser._parse_row(row, "Gasova Motoškola", "http://url")
    assert ev is None


_LISTING_HTML = """
<div class="box-list row">
  <div class="col-md-12 col-xl-6">
    <div class="box box-image box-horizontal box__item js-clickable">
      <div class="box__item-text">
        <h4 class="box__item-title box__item-title--huge">Open Track For Public MOTO 31.7.2026</h4>
      </div>
      <div class="box__item-image">
        <picture><img alt="Open Track For Public MOTO 31.7.2026" /></picture>
      </div>
      <a href="/open-track-for-public-moto-31-7-2026/" class="link-hidden">Open Track For Public MOTO 31.7.2026</a>
    </div>
  </div>
  <div class="col-md-12 col-xl-6">
    <div class="box box-image box-horizontal box__item js-clickable">
      <div class="box__item-text">
        <h4 class="box__item-title box__item-title--huge">Open Track For Public MOTO 5.8.2026</h4>
      </div>
      <div class="box__item-image">
        <picture><img alt="Open Track For Public MOTO 5.8.2026" /></picture>
      </div>
      <a href="/open-track-for-public-moto-5-8-2026/" class="link-hidden">Open Track For Public MOTO 5.8.2026</a>
    </div>
  </div>
</div>
"""


_DETAIL_HTML = """
<div class="terms-list">
  <div class="terms-list__item is-active-all">
    <div class="terms-list__item-columns">
      <div class="terms-list__item-col terms-list__item-headline">
        <span>18:00 - 18:25</span>
      </div>
      <div class="terms-list__item-col terms-list__item-price">€36.00</div>
      <div class="terms-list__item-col terms-list__item-button">
        <button class="btn btn--green mdi mdi-cart-off" disabled><span>Vlozit</span></button>
      </div>
    </div>
  </div>
  <div class="terms-list__item is-active-all">
    <div class="terms-list__item-columns">
      <div class="terms-list__item-col terms-list__item-headline">
        <span>19:00 - 19:25</span>
        <div class="free_capacity" title="Sold out"></div>
      </div>
      <div class="terms-list__item-col terms-list__item-price">€36.00</div>
      <div class="terms-list__item-col terms-list__item-button">
        <button class="btn btn--green mdi"><span>Vlozit</span></button>
      </div>
    </div>
  </div>
</div>
"""

_DETAIL_AVAILABLE_HTML = """
<div class="terms-list">
  <div class="terms-list__item is-active-all">
    <div class="terms-list__item-columns">
      <div class="terms-list__item-col terms-list__item-headline">
        <span>10:00 - 10:25</span>
      </div>
      <div class="terms-list__item-col terms-list__item-price">€28.00</div>
      <div class="terms-list__item-col terms-list__item-button">
        <button class="btn btn--green mdi mdi-cart"><span>Vlozit</span></button>
      </div>
    </div>
  </div>
</div>
"""


def test_brno_circuit_parse_detail_sold_out():
    prices, sold_out = BrnoCircuitParser._parse_detail(_DETAIL_HTML)
    assert sold_out is True
    assert len(prices) == 2
    assert prices[0]["amount"] == 36.0
    assert prices[0]["currency"] == "EUR"
    assert prices[0]["day_label"] == "18:00 - 18:25"
    assert prices[1]["day_label"] == "19:00 - 19:25"


def test_brno_circuit_parse_detail_available():
    prices, sold_out = BrnoCircuitParser._parse_detail(_DETAIL_AVAILABLE_HTML)
    assert sold_out is False
    assert len(prices) == 1
    assert prices[0]["amount"] == 28.0
    assert prices[0]["currency"] == "EUR"


def test_brno_circuit_parse_detail_empty():
    prices, sold_out = BrnoCircuitParser._parse_detail("<div>nothing</div>")
    assert sold_out is True
    assert prices == []


def test_brno_circuit_parse_listing():
    fetcher = Mock()
    fetcher.fetch.return_value = _DETAIL_AVAILABLE_HTML
    with patch("moto_plan_core.fetcher.SiteFetcher", return_value=fetcher):
        result = BrnoCircuitParser().parse(_LISTING_HTML)
    assert len(result) == 2
    assert result[0].track_name == "Brno"
    assert result[0].day == 31
    assert result[0].month_num == 7
    assert result[0].year == 2026
    assert result[0].category == "free_ride"
    assert result[0].sold_out is False
    assert result[0].prices[0]["amount"] == 28.0
    assert result[1].day == 5
    assert result[1].month_num == 8


def test_brno_circuit_parse_listing_empty():
    fetcher = Mock()
    with patch("moto_plan_core.fetcher.SiteFetcher", return_value=fetcher):
        result = BrnoCircuitParser().parse("<div>nothing</div>")
    assert result == []


def test_brno_circuit_parse_listing_fetch_error():
    fetcher = Mock()
    fetcher.fetch.side_effect = Exception("network error")
    with patch("moto_plan_core.fetcher.SiteFetcher", return_value=fetcher):
        result = BrnoCircuitParser().parse(_LISTING_HTML)
    assert len(result) == 2
    assert result[0].sold_out is True
    assert result[0].prices == []


def test_brno_circuit_title_re():
    m = BrnoCircuitParser._TITLE_RE.search("Open Track For Public MOTO 31.7.2026")
    assert m is not None
    assert m.group(1) == "31"
    assert m.group(2) == "7"
    assert m.group(3) == "2026"


def test_brno_circuit_title_re_no_match():
    assert BrnoCircuitParser._TITLE_RE.search("Some other event") is None
