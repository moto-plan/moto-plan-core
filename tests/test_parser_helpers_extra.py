import datetime

from moto_plan_core.parsers import (
    DateParser,
    DayOfWeekParser,
    PriceParser,
    TrackNameParser,
    _compute_day_of_week,
    _simple_track,
)


def test_date_parser_range():
    r = DateParser.parse("1. 6. – 3. 6. 2026")
    assert r["day"] == 1
    assert r["day_end"] == 3
    assert r["month_num"] == 6
    assert r["year"] == 2026


def test_date_parser_single():
    r = DateParser.parse("5. 7. 2026")
    assert r["day"] == 5
    assert r["month_num"] == 7
    assert r["year"] == 2026


def test_day_of_week_parser():
    assert DayOfWeekParser.parse("(So/Ne)") == ["Saturday", "Sunday"]


def test_price_parser():
    r = PriceParser.parse("SOBOTA 1200 KČ")
    assert r and r[0]["amount"] == 1200.0


def test_track_name_parser():
    r = TrackNameParser.parse("<strong>Most VOLNÉ JÍZDY</strong>")
    assert r == "Most"


def test_compute_day_of_week():
    assert _compute_day_of_week(1, 6, 2026) == ["Monday"]


def test_simple_track():
    assert _simple_track("Písek") == "Písek"
    assert _simple_track("Most") == "Most"
