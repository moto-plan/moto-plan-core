from moto_plan_core.helpers import HtmlHelper


def test_strip_tags():
    assert HtmlHelper.strip_tags("<p>Hello&nbsp;world</p>") == "Hello world"


def test_decode_entities():
    assert HtmlHelper.decode_entities("&#65;") == "A"
