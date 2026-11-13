from unittest.mock import patch

from moto_plan_core.parsers import BezpecneNaMotorceParser


def test_bezpecne_parse_with_mocked_price_map():
    options = [
        {"selections": [{"id": 1, "value": "5. května"}, {"id": 2, "value": "Praha"}, {"id": 3, "value": "mám zájem"}]},
    ]
    html = f'"nextOptionsSelectionId": 1, "options": {__import__("json").dumps(options)}'
    with patch("moto_plan_core.parsers.SiteFetcher.fetch", return_value=html), \
         patch.object(BezpecneNaMotorceParser, "_build_price_map", return_value={}):
        events = BezpecneNaMotorceParser().parse(html, agency="BNM", url="https://bnm.cz")
    assert len(events) >= 1
    assert events[0].track_name == "Česká republika"
