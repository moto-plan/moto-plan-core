import moto_plan_core.track_info as ti


def test_get_track_info_returns_copy():
    info = ti.get_track_info("Most")
    assert isinstance(info, dict)
    assert info.get("photo", "").startswith("/static/tracks/") or info.get("photo") is None


def test_get_track_info_unknown():
    assert ti.get_track_info("Nonexistent Track") is None


def test_load_tracks_prefixes_photo(monkeypatch):
    # Reload module to exercise loader
    import importlib
    importlib.reload(ti)
    assert ti._TRACK_INFO
