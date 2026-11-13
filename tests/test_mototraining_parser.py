from moto_plan_core.parsers import MotoTrainingParser


def test_mototraining_empty():
    assert MotoTrainingParser.parse("") == []


def test_mototraining_parse_basic():
    html = '''
    <div data-elementor-type="loop-item">
      <div class="elementor-shortcode">1.6.</div>
      <div class="elementor-shortcode">2026</div>
      <h2 class="elementor-heading-title">Most</h2>
      <h2 class="elementor-heading-title">Moto trénink na letišti</h2>
      <a href="https://mototraining.rsystem.cz/?op=activity1">detail</a>
    </div>
    '''
    # The parser splits on loop-item; reconstruct expected wrapper
    html = '<div data-elementor-type="loop-item"' + html.split('<div data-elementor-type="loop-item">', 1)[1]
    events = MotoTrainingParser.parse(html, agency="MT", url="https://mototraining.cz")
    assert len(events) == 1
    assert events[0].track_name == "Most"
