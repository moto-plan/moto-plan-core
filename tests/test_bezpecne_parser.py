import json

from moto_plan_core.parsers import BezpecneNaMotorceParser


def test_bezpecne_helpers():
    assert BezpecneNaMotorceParser._get_category("Most") == "closed_track" or BezpecneNaMotorceParser._get_category("Most") == "public_roads"
    assert BezpecneNaMotorceParser._has_cz_month("5. května") is True
    assert BezpecneNaMotorceParser._is_surcharge(["mám zájem", "nemám zájem"]) is True
    assert BezpecneNaMotorceParser._is_time_slot(["9-10 hod"]) is True
    assert BezpecneNaMotorceParser._parse_date("5. května") is not None
    raw = BezpecneNaMotorceParser._extract_json_array('{"a": [1, 2]}', 6)
    assert raw == "[1, 2]" or raw is None
