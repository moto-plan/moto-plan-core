from moto_plan_core.models import Event


def test_event_defaults():
    e = Event(agency="Test", track_name="Test Track", date="1. 6. 2026")
    assert e.agency == "Test"
    assert e.track_name == "Test Track"
    assert e.date == "1. 6. 2026"
    assert e.prices == []
    assert e.sold_out is False
    assert e.note == ""
    assert e.url == ""


def test_event_with_all_fields():
    e = Event(
        agency="A", track_name="T", date="1. 1. 2026",
        year=2026, month_num=1, day=1,
        day_end=2, month_end=1,
        url="https://example.com",
        day_of_week=["Thursday"],
        prices=[{"day_label": "", "amount": 100, "currency": "CZK"}],
        sold_out=True,
        note="test",
    )
    assert e.year == 2026
    assert e.day_end == 2
    assert e.prices[0]["amount"] == 100
    assert e.sold_out is True
