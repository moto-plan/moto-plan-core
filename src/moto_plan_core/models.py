from dataclasses import dataclass, field


@dataclass
class Event:
    agency: str
    track_name: str
    date: str
    year: int | None = None
    month_num: int = 0
    month_end: int = 0
    day: int | None = None
    day_end: int | None = None
    url: str = ""
    day_of_week: list[str] = field(default_factory=list)
    prices: list[dict] = field(default_factory=list)
    sold_out: bool = False
    note: str = ""
    category: str = "free_ride"
    country: str = ""
    lat: float | None = None
    lon: float | None = None
