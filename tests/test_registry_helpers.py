from unittest.mock import patch

from moto_plan_core.models import Event
from moto_plan_core.registry import _resolve_geo, scrape_all


@patch("moto_plan_core.registry.resolve_country", return_value="CZ")
@patch("moto_plan_core.registry.resolve_coords", return_value=(50.0, 14.0))
def test_resolve_geo_sets_country(mock_coords, mock_country):
    e = Event(agency="A", track_name="Test Track", date="1. 6. 2026")
    _resolve_geo([e])
    assert e.country == "CZ"
    assert e.lat == 50.0
    assert e.lon == 14.0


@patch("moto_plan_core.registry.resolve_country", return_value="CZ")
@patch("moto_plan_core.registry.resolve_coords", return_value=None)
def test_resolve_geo_skips_coords_when_none(mock_coords, mock_country):
    e = Event(agency="A", track_name="Test Track", date="1. 6. 2026")
    _resolve_geo([e])
    assert e.country == "CZ"
    assert e.lat is None
    assert e.lon is None


@patch("moto_plan_core.registry.resolve_country", return_value="CZ")
@patch("moto_plan_core.registry.resolve_coords", return_value=(50.0, 14.0))
def test_resolve_geo_skips_when_already_set(mock_coords, mock_country):
    e = Event(agency="A", track_name="Test Track", date="1. 6. 2026",
              country="DE", lat=51.0, lon=10.0)
    _resolve_geo([e])
    assert e.country == "DE"
    assert e.lat == 51.0
    assert e.lon == 10.0
    mock_country.assert_not_called()
    mock_coords.assert_not_called()


@patch("moto_plan_core.registry.DatabaseWriter")
def test_scrape_all_with_db_path(mock_db):
    event = Event(agency="TestAgency", track_name="Test", date="1. 6. 2026")
    with (
        patch("moto_plan_core.registry._SITES", [("http://test", "TestAgency", "test")]),
        patch("moto_plan_core.registry.scrape_site", return_value=[event]),
        patch("moto_plan_core.registry.resolve_country", return_value="CZ"),
        patch("moto_plan_core.registry.resolve_coords", return_value=(50.0, 14.0)),
    ):
        scrape_all(db_path=":memory:")
    mock_db.assert_called_once()
    mock_db.return_value.__enter__.return_value.delete_stale_events.assert_called_once()


def test_scrape_all_error():
    with (
        patch("moto_plan_core.registry._SITES", [("http://test", "TestAgency", "test")]),
        patch("moto_plan_core.registry.scrape_site", side_effect=Exception("fail")),
        patch("moto_plan_core.registry.resolve_country"),
        patch("moto_plan_core.registry.resolve_coords"),
    ):
        scrape_all()
    event = Event(agency="TestAgency", track_name="Test", date="1. 6. 2026")
    with (
        patch("moto_plan_core.registry._SITES", [("http://test", "TestAgency", "test")]),
        patch("moto_plan_core.registry.scrape_site", return_value=[event]),
        patch("moto_plan_core.registry.resolve_country", return_value="CZ"),
        patch("moto_plan_core.registry.resolve_coords", return_value=(50.0, 14.0)),
    ):
        scrape_all()
    assert event.country == "CZ"
    assert event.lat == 50.0
    assert event.lon == 14.0
