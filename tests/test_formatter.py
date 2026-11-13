from moto_plan_core.formatter import EventFormatter
from moto_plan_core.models import Event


def test_format_events(capsys):
    fmt = EventFormatter()
    events = [
        Event(agency="A", track_name="T1", date="1. 6. 2026",
              year=2026, month_num=6, day=1, url="https://a.com"),
        Event(agency="B", track_name="T2", date="2. 6. 2026",
              year=2026, month_num=6, day=2, url="https://b.com",
              prices=[{"day_label": "", "amount": 100, "currency": "CZK"}]),
    ]
    fmt.format_events(events)
    captured = capsys.readouterr()
    assert "T1" in captured.out
    assert "100" in captured.out


def test_track_name_normalize():
    from moto_plan_core.parsers import normalize_track_name
    assert normalize_track_name("AUTODROM SOSNOVÁ") == "Sosnová"
    assert normalize_track_name("autodrom most") == "Most"


def test_date_parser():
    from moto_plan_core.parsers import DateParser
    result = DateParser.parse("13. 6. 2026")
    assert result["day"] == 13
    assert result["month_num"] == 6
