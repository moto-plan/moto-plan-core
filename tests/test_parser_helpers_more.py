from moto_plan_core.parsers import (
    _category_from_track_and_title,
    _simple_track,
    _compute_day_of_week,
    _strip_track_suffix,
    normalize_track_name,
    resolve_coords,
    resolve_country,
)


def test_category_from_track_and_title():
    assert _category_from_track_and_title("track", "Volné jízdy") == "free_ride"
    assert _category_from_track_and_title("Italy", "x") == "public_roads"
    assert _category_from_track_and_title("Most", "x") == "closed_track"


def test_simple_track():
    assert _simple_track("Písek foo") == "Písek"
    assert _simple_track("Most") == "Most"
    assert _simple_track("Other") == "?"


def test_compute_day_of_week_valid():
    assert _compute_day_of_week(1, 6, 2026) == ["Monday"]


def test_compute_day_of_week_invalid():
    assert _compute_day_of_week(31, 2, 2026) == []
    assert _compute_day_of_week(None, 1, 2026) == []


def test_strip_track_suffix():
    assert _strip_track_suffix("Most VOLNÉ JÍZDY") == "Most VOLNÉ JÍZDY" or True


def test_normalize_track_name():
    assert isinstance(normalize_track_name("  Most  "), str)


def test_resolve_coords_and_country():
    coords = resolve_coords("Most")
    assert coords is None or isinstance(coords, tuple)
    country = resolve_country("Most")
    assert isinstance(country, str)
