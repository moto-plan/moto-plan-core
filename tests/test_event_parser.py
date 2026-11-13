from moto_plan_core.parsers import EventParser


def test_event_parser_empty():
    assert EventParser().parse("") == []


def test_event_parser_basic():
    html = """
    <h4><strong>Most</strong> 1. 6. 2026 (So) 1200 KČ</h4>
    """
    events = EventParser().parse(html, agency="A", url="https://example.com")
    assert len(events) == 1
    assert events[0].track_name == "Most"
