import json

from moto_plan_core.parsers import BezpecneNaMotorceParser


def test_bezpecne_extract_json_array():
    text = 'prefix "productItems": [1, 2, 3] suffix'
    start = text.index("[")
    assert BezpecneNaMotorceParser._extract_json_array(text, start) == "[1, 2, 3]"


def test_bezpecne_get_category():
    assert BezpecneNaMotorceParser._get_category("Most") == "closed_track" or BezpecneNaMotorceParser._get_category("Most") == "public_roads"
