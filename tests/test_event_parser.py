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


def test_event_parser_short_block():
    html = "<h4>short</h4>"
    assert EventParser().parse(html, agency="A") == []


def test_event_parser_no_track():
    html = "<h4>This is a long enough block without strong</h4>"
    assert EventParser().parse(html, agency="A") == []


def test_event_parser_sold_out():
    html = """
    <h4><strong>Most</strong> 1. 6. 2026 (So) 1200 KČ VYPRODÁNO</h4>
    """
    events = EventParser().parse(html, agency="A")
    assert events and events[0].sold_out is True


def test_event_parser_no_date():
    html = """
    <h4><strong>Most</strong> no date here at all long enough</h4>
    """
    events = EventParser().parse(html, agency="A")
    assert events and events[0].date == ""
