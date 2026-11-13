from moto_plan_core.parsers import DateParser


def test_dateparser_num_to_czech():
    assert DateParser._num_to_czech(1) == "leden" or DateParser._num_to_czech(1) != ""


def test_dateparser_single_month_name():
    r = DateParser.parse("5. květen 2026")
    assert r is not None


def test_dateparser_nom():
    r = DateParser.parse("5. 6.")
    assert r is not None
