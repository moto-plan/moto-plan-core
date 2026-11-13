import json
import tempfile

from moto_plan_core.database import DatabaseWriter
from moto_plan_core.models import Event


def test_schema_creation():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        with DatabaseWriter(f.name) as db:
            rows = db.query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
            )
            assert len(rows) == 1


def test_upsert_and_query():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        with DatabaseWriter(f.name) as db:
            events = [
                Event(agency="A", track_name="T1", date="1. 6. 2026",
                      year=2026, month_num=6, day=1),
                Event(agency="A", track_name="T2", date="2. 6. 2026",
                      year=2026, month_num=6, day=2),
            ]
            db.upsert_events(events)
            rows = db.query("SELECT * FROM events ORDER BY day")
            assert len(rows) == 2
            assert rows[0][2] == "T1"  # track_name
            assert rows[1][2] == "T2"


def test_upsert_dedup():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        with DatabaseWriter(f.name) as db:
            e1 = Event(agency="A", track_name="T", date="1. 6. 2026",
                       year=2026, month_num=6, day=1, note="first")
            db.upsert_events([e1])
            # Same (agency, track, date, note) → dedup (update)
            e2 = Event(agency="A", track_name="T", date="1. 6. 2026",
                       year=2026, month_num=6, day=1, note="first", prices=[{"amount": 100, "currency": "CZK"}])
            db.upsert_events([e2])
            rows = db.query("SELECT note, prices FROM events ORDER BY note")
            assert len(rows) == 1
            assert rows[0][0] == "first"
            # Different note → separate row
            e3 = Event(agency="A", track_name="T", date="1. 6. 2026",
                       year=2026, month_num=6, day=1, note="second")
            db.upsert_events([e3])
            rows = db.query("SELECT note FROM events ORDER BY note")
            assert len(rows) == 2
            assert rows[0][0] == "first"
            assert rows[1][0] == "second"


def test_prices_serialization():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        with DatabaseWriter(f.name) as db:
            prices = [{"day_label": "", "amount": 2490.0, "currency": "CZK"}]
            e = Event(agency="A", track_name="T", date="1. 6. 2026",
                      year=2026, month_num=6, day=1, prices=prices)
            db.upsert_events([e])
            rows = db.query("SELECT prices FROM events")
            loaded = json.loads(rows[0][0])
            assert loaded == prices
