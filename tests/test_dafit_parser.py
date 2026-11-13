from unittest.mock import patch

from moto_plan_core.parsers import DafitMotoRacingParser


def test_dafit_empty():
    assert DafitMotoRacingParser.parse("") == []


def test_dafit_parse_with_mocked_detail():
    html = '''
    <a href="/race1" class="hpcalendar__races__race">
      <span class="hpcalendar__races__race__title"><strong>1. - 2. 6. 2026</strong> Most</span>
      <span class="hpcalendar__races__race__location">Most VYPRODÁNO</span>
    </a>
    '''
    with patch("moto_plan_core.parsers.SiteFetcher.fetch", return_value="1200 CZK"):
        events = DafitMotoRacingParser.parse(html, agency="Dafit", url="https://dafit.cz")
    assert len(events) == 1
    assert events[0].track_name == "Most"
    assert events[0].sold_out is True
    assert events[0].prices[0]["amount"] == 1200.0
