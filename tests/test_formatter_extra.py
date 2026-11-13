from moto_plan_core.formatter import EventFormatter
from moto_plan_core.models import Event


def test_format_date_range():
    e = Event(agency="A", track_name="T", date="1. 6. 2026", day=1, day_end=3, month_num=6, month_end=6, year=2026)
    assert "01.06–03.06.2026" == EventFormatter.format_date(e)


def test_format_date_single():
    e = Event(agency="A", track_name="T", date="1. 6. 2026", day=1, month_num=6, year=2026)
    assert EventFormatter.format_date(e) == "01.06.2026"


def test_format_date_no_day():
    e = Event(agency="A", track_name="T", date="June 2026")
    assert EventFormatter.format_date(e) == "June 2026"


def test_format_events_tbd_and_multiple(capsys):
    e = Event(agency="A", track_name="T", date="1. 6. 2026", day=1, month_num=6, year=2026,
              prices=[{"day_label": "", "amount": 100, "currency": "TBD"},
                     {"day_label": "", "amount": 200, "currency": "CZK"}],
              note="note")
    EventFormatter.format_events([e])
    out = capsys.readouterr().out
    assert "PŘIPRAVUJEME" in out
    assert "od" in out
