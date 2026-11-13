from moto_plan_core.parsers import MotoFormaParser


def test_motoforma_empty():
    assert MotoFormaParser.parse("") == []


def test_motoforma_parse_basic():
    html = '''
    <div class="course-date-card">
      <div class="course-date-card__date">1. ledna</div>
      <div class="course-date-card__title">Kurz</div>
      <div class="course-date-card__price">1200 Kč</div>
      date=2026-01-01
      btn--disabled
    </div>
    '''
    events = MotoFormaParser.parse(html, agency="MotoForma", url="https://motoforma.cz")
    assert len(events) == 1
    assert events[0].sold_out is True
    assert events[0].prices[0]["amount"] == 1200.0
