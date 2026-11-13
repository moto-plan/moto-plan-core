from unittest.mock import patch

from moto_plan_core.parsers import RoadLeagueParser


def test_roadleague_empty():
    assert RoadLeagueParser().parse("") == []


def test_roadleague_helpers():
    assert RoadLeagueParser._parse_date("january 1, 2026") == {"day": 1, "month_num": 1, "year": 2026}
    assert RoadLeagueParser._parse_date("bad") is None
    assert RoadLeagueParser._parse_detail("<span class=\"prd-price-c wnd-product-price\">1200</span>")["prices"][0]["amount"] == 1200.0


def test_roadleague_parse_with_mocked_details():
    html = '<a class="rlx-row" href="https://example.com/e1"><span class="rlx-where">Most</span><span class="rlx-when">january 1, 2026</span></a>'
    with patch.object(RoadLeagueParser, "_fetch_details", return_value={"https://example.com/e1": {"prices": [], "sold_out": False}}):
        events = RoadLeagueParser().parse(html, agency="RL", url="https://roadleague.cz")
    assert len(events) == 1
    assert events[0].track_name == "Most"
