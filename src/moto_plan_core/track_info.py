import json
from pathlib import Path

_STATIC_PREFIX = "/static/tracks/"
_JSON_PATH = Path(__file__).resolve().parent / "tracks.json"


def _load_tracks() -> dict[str, dict]:
    with open(_JSON_PATH) as f:
        raw = json.load(f)
    result: dict[str, dict] = {}
    for key, info in raw.items():
        info = dict(info)
        if info.get("photo"):
            info["photo"] = _STATIC_PREFIX + info["photo"]
        result[key] = info
    return result


_TRACK_INFO = _load_tracks()


def get_track_info(track_name: str) -> dict | None:
    info = _TRACK_INFO.get(track_name)
    if info:
        return dict(info)
    return None
