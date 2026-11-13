import json
import sqlite3

from .models import Event

_TRACK_RENAME = {
    "letiště Vyškov": "Vyškov, letiště",
    "letiště Hradčany": "Hradčany, letiště",
    "letiště Mnichovo Hradiště": "Mnichovo Hradiště, letiště",
    "výstaviště České Budějovice": "České Budějovice, výstaviště",
    "letiště Lhota u Plzně": "Lhota u Plzně, letiště",
    "odjezd z Frýdku-Místku - Beskydy": "Frýdek-Místek - Beskydy",
    "odjezd z Hradce Králové - Orlické hory": "Hradec Králové - Orlické hory",
    "odjezd z Železného Brodu - Jizerky a Krkonoše": "Železný Brod - Jizerky a Krkonoše",
    "odjezd ze Strachotína - jižní Morava": "Strachotín - jižní Morava",
    "odjezd z Prahy - směr jižní Čechy": "Praha - jižní Čechy",
}


class DatabaseWriter:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def __enter__(self):
        self._conn = sqlite3.connect(self.db_path)
        self._ensure_schema()
        return self

    def __exit__(self, *args):
        if self._conn:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def _ensure_schema(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agency      TEXT    NOT NULL DEFAULT '',
                track_name  TEXT    NOT NULL,
                date        TEXT    NOT NULL,
                url         TEXT    NOT NULL DEFAULT '',
                year        INTEGER,
                month_num   INTEGER NOT NULL DEFAULT 0,
                month_end   INTEGER NOT NULL DEFAULT 0,
                day         INTEGER,
                day_end     INTEGER,
                day_of_week TEXT    NOT NULL DEFAULT '[]',
                prices      TEXT    NOT NULL DEFAULT '[]',
                sold_out    INTEGER NOT NULL DEFAULT 0,
                note        TEXT    NOT NULL DEFAULT '',
                fetched_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                category    TEXT    NOT NULL DEFAULT 'free_ride',
                UNIQUE(agency, track_name, date, note)
            )
        """)
        try:
            self._conn.execute("ALTER TABLE events ADD COLUMN category TEXT NOT NULL DEFAULT 'free_ride'")
        except sqlite3.OperationalError:
            pass
        try:
            self._conn.execute("ALTER TABLE events ADD COLUMN country TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            self._conn.execute("ALTER TABLE events ADD COLUMN lat REAL")
        except sqlite3.OperationalError:
            pass
        try:
            self._conn.execute("ALTER TABLE events ADD COLUMN lon REAL")
        except sqlite3.OperationalError:
            pass

        self._migrate_categories()
        self._migrate_track_rename()
        self._migrate_merge_tracks()

    def _migrate_categories(self):
        cur = self._conn.execute("SELECT DISTINCT category FROM events")
        existing = {r[0] for r in cur.fetchall()}
        if "training" not in existing:
            return

        self._conn.execute("""
            UPDATE events SET category = 'closed_track'
            WHERE category = 'training' AND (
                agency IN ('Bikes4Life', 'Honda Experience', 'MotoForma', 'MotoTraining',
                           'NaOkruh', 'Silniční Motoškola Brno', 'Moto Lisý')
                OR (agency = 'MotoŠkolaRadekAndrlík' AND track_name = 'Písek')
                OR (agency = 'Bezpečně na motorce' AND track_name IN (
                    'Mnichovo Hradiště, letiště', 'Vyškov, letiště',
                    'Lhota u Plzně, letiště', 'Hradčany, letiště',
                    'České Budějovice, výstaviště'
                ))
            )
        """)
        self._conn.execute("""
            UPDATE events SET category = 'public_roads'
            WHERE category = 'training' AND (
                agency IN ('Gasova Motoškola', 'StopNehodam')
                OR (agency = 'MotoŠkolaRadekAndrlík' AND track_name = 'Dolomity, Itálie')
                OR (agency = 'Bezpečně na motorce' AND track_name IN (
                    'jižní Morava - u Brna', 'střední Čechy - u Kladna',
                    'Frýdek-Místek - Beskydy',
                    'Hradec Králové - Orlické hory',
                    'Praha - jižní Čechy',
                    'Železný Brod - Jizerky a Krkonoše',
                    'Strachotín - jižní Morava'
                ))
                OR (agency = 'Bezpečně na motorce' AND track_name NOT IN (
                    'Mnichovo Hradiště, letiště', 'Vyškov, letiště',
                    'Lhota u Plzně, letiště', 'Hradčany, letiště',
                    'České Budějovice, výstaviště'
                ))
            )
        """)
        self._migrate_v1_to_v2()

    def _migrate_v1_to_v2(self):
        try:
            result = self._conn.execute("PRAGMA table_info(events)").fetchall()
            cols = [r[1] for r in result]
            if "category" not in cols:
                self._conn.execute(
                    "ALTER TABLE events ADD COLUMN category TEXT NOT NULL DEFAULT 'free_ride'"
                )
        except sqlite3.OperationalError:
            pass
        try:
            # Check if the old UNIQUE constraint exists (no 'note' in it)
            idx_info = self._conn.execute("PRAGMA index_list(events)").fetchall()
            old_unique = None
            for idx in idx_info:
                if idx[2] == 1:  # unique index
                    idx_cols = self._conn.execute(f"PRAGMA index_info({idx[1]})").fetchall()
                    col_names = [cols_info[2] for cols_info in idx_cols]
                    if sorted(col_names) == sorted(["agency", "track_name", "date"]):
                        old_unique = idx[1]
                        break
            if old_unique:
                self._conn.execute("ALTER TABLE events RENAME TO events_old")
                self._conn.execute("""
                    CREATE TABLE events (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        agency      TEXT    NOT NULL DEFAULT '',
                        track_name  TEXT    NOT NULL,
                        date        TEXT    NOT NULL,
                        url         TEXT    NOT NULL DEFAULT '',
                        year        INTEGER,
                        month_num   INTEGER NOT NULL DEFAULT 0,
                        month_end   INTEGER NOT NULL DEFAULT 0,
                        day         INTEGER,
                        day_end     INTEGER,
                        day_of_week TEXT    NOT NULL DEFAULT '[]',
                        prices      TEXT    NOT NULL DEFAULT '[]',
                        sold_out    INTEGER NOT NULL DEFAULT 0,
                        note        TEXT    NOT NULL DEFAULT '',
                        fetched_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                        category    TEXT    NOT NULL DEFAULT 'free_ride',
                        country     TEXT    NOT NULL DEFAULT '',
                        UNIQUE(agency, track_name, date, note)
                    )
                """)
                self._conn.execute("""
                    INSERT INTO events (agency, track_name, date, url, year, month_num, month_end,
                                        day, day_end, day_of_week, prices, sold_out, note, category, country)
                    SELECT agency, track_name, date, url, year, month_num, month_end,
                           day, day_end, day_of_week, prices, sold_out, note, category, ''
                    FROM events_old
                    GROUP BY agency, track_name, date, note
                """)
                self._conn.execute("DROP TABLE events_old")
        except sqlite3.OperationalError:
            pass
        self._conn.execute(
            "DELETE FROM events WHERE agency = 'Bezpečně na motorce'"
            " AND note NOT LIKE '%(half day)%' AND note NOT LIKE '%(full day)%'"
        )
        self._conn.execute(
            "DELETE FROM events WHERE track_name = 'Mnichovo Hradiště, letiště'"
        )

    def _migrate_track_rename(self):
        self._conn.execute(
            "UPDATE events SET track_name = 'Sosnová' WHERE track_name = 'Autodrom Sosnová'"
        )
        self._conn.execute(
            "UPDATE events SET track_name = 'Praha - jižní Čechy' WHERE track_name = 'odjezd z Prahy - směr jižní Čechy'"
        )
        self._conn.execute(
            "UPDATE events SET track_name = 'České Budějovice, výstaviště' WHERE track_name = 'výstaviště České Budějovice'"
        )
        self._conn.execute(
            "UPDATE events SET track_name = 'Mnichovo Hradiště, letiště' WHERE track_name = 'letiště Mnichovo Hradiště'"
        )
        self._conn.execute(
            "UPDATE events SET track_name = 'Vyškov, letiště' WHERE track_name = 'letiště Vyškov'"
        )
        self._conn.execute(
            "UPDATE events SET track_name = 'Vyškov, letiště' WHERE track_name = 'Vyškov'"
        )
        for old, new in _TRACK_RENAME.items():
            self._conn.execute(
                "UPDATE events SET track_name = ? WHERE track_name = ?", (new, old)
            )

    def _migrate_merge_tracks(self):
        self._conn.execute(
            "UPDATE events SET track_name = 'Mnichovo Hradiště, letiště' WHERE track_name = 'Hoškovice'"
        )
        self._conn.execute(
            "UPDATE events SET track_name = 'Mnichovo Hradiště, letiště' WHERE track_name = 'Mnichovo Hradiště'"
        )
        self._conn.execute(
            "UPDATE events SET track_name = 'Hradčany, letiště' WHERE track_name = 'letiště Hradčany'"
        )
        self._conn.execute(
            "UPDATE events SET track_name = 'Hradčany, letiště' WHERE track_name = 'letiště Mimoň'"
        )

    def delete_stale_events(self, events: list[Event]) -> None:
        for e in events:
            self._conn.execute(
                "DELETE FROM events WHERE agency=? AND date=? AND note=? AND track_name!=?",
                (e.agency, e.date, e.note, e.track_name),
            )

    def upsert_events(self, events: list[Event]):
        sql = """
            INSERT INTO events (agency, track_name, date, url, year, month_num, month_end,
                                day, day_end, day_of_week, prices, sold_out, note, category, country,
                                lat, lon)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agency, track_name, date, note) DO UPDATE SET
                url        = excluded.url, year = excluded.year, month_num = excluded.month_num,
                month_end  = excluded.month_end, day = excluded.day, day_end = excluded.day_end,
                day_of_week = excluded.day_of_week, prices = excluded.prices,
                sold_out   = excluded.sold_out, note = excluded.note,
                category   = excluded.category, country = excluded.country,
                lat        = excluded.lat, lon = excluded.lon,
                fetched_at = datetime('now')
        """
        rows = [
            (e.agency, _TRACK_RENAME.get(e.track_name, e.track_name), e.date, e.url, e.year, e.month_num, e.month_end if e.month_end else 0,
             e.day, e.day_end, json.dumps(e.day_of_week), json.dumps(e.prices), int(e.sold_out), e.note, e.category, e.country,
             e.lat, e.lon)
            for e in events
        ]
        self._conn.executemany(sql, rows)

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self._conn.execute(sql, params).fetchall()
