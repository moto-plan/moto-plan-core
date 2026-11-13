from concurrent.futures import ThreadPoolExecutor, as_completed

from .concurrency import scrape_workers
from .database import DatabaseWriter
from .fetcher import SiteFetcher
from .models import Event
from .parsers import BezpecneNaMotorceParser, Bikes4LifeParser, BrnoCircuitParser, BrnoMotoskolaParser, CarsJetParser, DafitMotoRacingParser, EnduroCampParser, EnduroSkolaParser, EventParser, FacebookEventsParser, GasovaMotoskolaParser, Hefty74Parser, HondaExperienceParser, MotoFormaParser, MotoLisyParser, MotoSkolaRadekandrlikParser, MotoTrainingParser, MotokoucParser, MotoskolaLandaParser, MotoridersParser, NaOkruhParser, OkruhariParser, OkruhariSkParser, RmotoAcademyParser, RoadLeagueParser, StopNehodamParser, resolve_coords, resolve_country

_BRNO_MOTOSKOLA = "Silniční Motoškola Brno"

_SITES: list[tuple[str, str, str]] = [
    ("https://motokouc.cz/project/okruh-sosnova/", "Motokouč", "motokouc"),
    ("https://motokouc.cz/project/okruh-sosnova-odpoledne/", "Motokouč", "motokouc"),

    ("https://gripandgas.cz", "GripAndGas", "gripandgas"),
    ("https://hefty74.cz/okruh-volne-jizdy/", "Hefty74", "hefty74"),
    ("https://www.roadleague.cz/en/", "RoadLeague", "roadleague"),
    ("https://motoriders.cz/terminy", "Motoriders", "motoriders"),
    ("https://www.carsjet.cz/terminy-pro-motorky/", "CarsJet", "carsjet"),
    ("https://www.mototraining.cz/#terminy", "MotoTraining", "mototraining"),
    ("https://motoforma.cz/volne-jizdy", "MotoForma", "motoforma"),
    ("https://naokruh.eu/kategorie-produktu/moto-akce/", "NaOkruh", "naokruh"),
    ("https://www.motoskolaradekandrlik.cz/terminy", "MotoŠkolaRadekAndrlík", "motoskola"),
    ("https://stopnehodam.cz/events/", "StopNehodam", "stopnehodam"),
    ("https://www.motoskola-landa.cz/kalendar-kurzu-motoskola#kalendar", "Motoškola Landa", "motoskolalanda"),
    ("https://www.okruhari.cz/okruhove-eventy/", "Okruháři", "okruhari"),
    ("https://www.dafitmotoracing.com/#calendar", "Dafit Moto Racing", "dafit"),
    ("https://bikes4life.cz", "Bikes4Life", "bikes4life"),
    ("https://www.honda-experience.cz/cs/katalog/honda-motorcycle-safety-training", "Honda Experience", "honda"),
    ("https://www.facebook.com/KurzyShowZavody/events/", "Cones Bike Racers", "conesbikeracers"),
    ("https://motolisy.cz", "Moto Lisý", "motolisy"),
    ("https://gasovamotoskola.cz/2018/11/13/volne-terminy-v-roce-2021/", "Gasova Motoškola", "gasovamotoskola"),
    ("https://vstupenky.brno-circuit.com/motoskola-start/", _BRNO_MOTOSKOLA, "brnomotoskola"),
    ("https://vstupenky.brno-circuit.com/motoskola-road/", _BRNO_MOTOSKOLA, "brnomotoskola"),
    ("https://vstupenky.brno-circuit.com/motoskola-po-zadnim-2/", _BRNO_MOTOSKOLA, "brnomotoskola"),
    ("https://vstupenky.brno-circuit.com/motoskola-pro-zeny/", _BRNO_MOTOSKOLA, "brnomotoskola"),
    ("https://vstupenky.brno-circuit.com/motoskola-po-zadnim-level-pro/", _BRNO_MOTOSKOLA, "brnomotoskola"),
    ("https://www.bezpecne-na-motorce.cz/skupinove-kurzy", "Bezpečně na motorce", "bezpecnenamotorce"),
    ("https://enduroskola.cz/akce/", "Enduroškola", "enduroskola"),
    ("https://endurocamp.cz", "Enduro Camp", "endurocamp"),
    ("https://okruhari.sk/eshop", "Okruhári.sk", "okruharisk"),
    ("https://rmoto.sk/collections/skupinove-terminy", "RMoto Academy", "rmotoacademy"),
    ("https://tickets.brno-circuit.com/moto-open-track-for-public/", "Brno Circuit", "brnocircuit"),
]

_PARSERS: dict[str, object] = {
    "gripandgas": EventParser(),
    "hefty74": Hefty74Parser(),
    "roadleague": RoadLeagueParser(),
    "motoriders": MotoridersParser(),
    "carsjet": CarsJetParser(),
    "mototraining": MotoTrainingParser(),
    "motoforma": MotoFormaParser(),
    "naokruh": NaOkruhParser(),
    "motoskola": MotoSkolaRadekandrlikParser(),
    "stopnehodam": StopNehodamParser(),
    "motoskolalanda": MotoskolaLandaParser(),
    "okruhari": OkruhariParser(),
    "dafit": DafitMotoRacingParser(),
    "bikes4life": Bikes4LifeParser(),
    "honda": HondaExperienceParser(),
    "conesbikeracers": FacebookEventsParser(),
    "motolisy": MotoLisyParser(),
    "gasovamotoskola": GasovaMotoskolaParser(),
    "brnomotoskola": BrnoMotoskolaParser(),
    "bezpecnenamotorce": BezpecneNaMotorceParser(),
    "motokouc": MotokoucParser(),
    "enduroskola": EnduroSkolaParser(),
    "endurocamp": EnduroCampParser(),
    "okruharisk": OkruhariSkParser(),
    "rmotoacademy": RmotoAcademyParser(),
    "brnocircuit": BrnoCircuitParser(),
}


def scrape_site(url: str, agency: str, parser_key: str,
                fetcher: SiteFetcher | None = None) -> list[Event]:
    fetcher = fetcher or SiteFetcher()
    parser = _PARSERS[parser_key]
    print(f"  {agency:10} {url}")
    try:
        html = fetcher.fetch(url)
    except Exception as e:
        print(f"    Fetch failed ({e}), parser may use browser")
        html = ""
    return parser.parse(html, agency=agency, url=url)


def scrape_all(db_path: str | None = None) -> list[Event]:
    all_events: list[Event] = []
    print(f"Fetching {len(_SITES)} sites ...")
    with ThreadPoolExecutor(max_workers=scrape_workers(len(_SITES))) as pool:
        fut = {pool.submit(scrape_site, url, agency, key): agency for url, agency, key in _SITES}
        for f in as_completed(fut):
            try:
                all_events.extend(f.result())
            except Exception as e:
                print(f"  Error scraping {fut[f]}: {e}")

    _resolve_geo(all_events)

    all_events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0, e.track_name))

    if db_path and all_events:
        with DatabaseWriter(db_path) as db:
            db.delete_stale_events(all_events)
            db.upsert_events(all_events)

    return all_events


def _resolve_geo(events: list[Event]):
    for e in events:
        if not e.country:
            e.country = resolve_country(e.track_name)
        if e.lat is None or e.lon is None:
            coords = resolve_coords(e.track_name)
            if coords:
                e.lat, e.lon = coords
