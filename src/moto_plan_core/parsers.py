import datetime
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

from .concurrency import scrape_workers
from .constants import _CZECH_MONTHS, _CZECH_DAYS, _DAY_ABBREV, _ENG_DAYS, _PRICE_LABEL_MAP
from .fetcher import SiteFetcher
from .helpers import HtmlHelper
from .models import Event


_HTML_PARSER = "html.parser"
_TAG_RE = r"<[^>]+>"

_PISEK = "Písek"
_SOSNOVA = "Sosnová"
_VYSOKE_MYTO = "Vysoké Mýto"
_POLYGON_MOST = "Polygon Most"
_ITALIE = "Itálie"
_LETISTE_MNICHOVO_HRADISTE = "Mnichovo Hradiště, letiště"
_LETISTE_HRADCANY = "Hradčany, letiště"
_CHOTEC = "Choteč"
_KAVCAK_BENESOV = "Kavčák – Benešov"
_BOSNA_CERNA_HORA = "Bosna a Černá hora"
_ALMERIA = "Almería"
_LETISTE_VYSKOV = "Vyškov, letiště"
_LETISTE_LHOTA_PLZNE = "Lhota u Plzně, letiště"
_FULL_DAY = "full day"
_NEMAM_ZAJEM = "nemám zájem"
_VYPRODANO = "vyprodáno"
_AT_TYPE = "@type"
_DATE_KEY = "$date"
_UTC_OFFSET = "+00:00"
_DATE_RE = r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})"


def _category_from_track_and_title(track: str, title: str) -> str:
    if "volné" in title.lower() or "volny" in title.lower():
        return "free_ride"
    if _ITALIE in track or "Italy" in track:
        return "public_roads"
    return "closed_track"


def _simple_track(name: str) -> str:
    if _PISEK in name:
        return _PISEK
    if "Most" in name:
        return "Most"
    return "?"


class DateParser:
    @staticmethod
    def parse(raw: str) -> dict | None:
        cleaned = HtmlHelper.decode_entities(raw)
        cleaned = " ".join(re.sub(_TAG_RE, " ", cleaned).split())

        m_range = re.search(
            r"(\d{1,2})\.\s+(\d{1,2})\.?\s*[–\-—]\s*(\d{1,2})\.\s+(\d{1,2})\.?\s+(\d{4})", cleaned
        )
        if m_range:
            d1, mo1 = int(m_range.group(1)), int(m_range.group(2))
            d2, mo2 = int(m_range.group(3)), int(m_range.group(4))
            return {"day": d1, "day_end": d2, "month": DateParser._num_to_czech(mo1), "month_num": mo1, "month_end": mo2, "year": int(m_range.group(5))}

        m_num = re.search(r"(\d{1,2})\.\s+(\d{1,2})\.\s+(\d{4})", cleaned)
        if m_num:
            mo = int(m_num.group(2))
            return {"day": int(m_num.group(1)), "month_num": mo, "month": DateParser._num_to_czech(mo), "year": int(m_num.group(3))}

        m_single = re.search(r"(\d{1,2})\.\s+(?:(\w+)\s+)?(\d{4})", cleaned)
        if m_single:
            day = int(m_single.group(1))
            year = int(m_single.group(3))
            full = " ".join(re.sub(_TAG_RE, " ", raw).split())
            for i, name in enumerate(_CZECH_MONTHS):
                if name in full:
                    return {"day": day, "month": name, "month_num": i + 1, "year": year}
            num_month = m_single.group(2)
            if num_month and num_month.isdigit():
                return {"day": day, "month_num": int(num_month), "year": year}
            return {"day": day, "year": year}

        m_nom = re.search(r"(\d{1,2})\.\s+(\d{1,2})\.?", cleaned)
        if m_nom:
            d1, mo1 = int(m_nom.group(1)), int(m_nom.group(2))
            return {"day": d1, "month_num": mo1, "month": DateParser._num_to_czech(mo1), "year": datetime.date.today().year}

        return None

    @staticmethod
    def _num_to_czech(num: int) -> str:
        if 1 <= num <= 12:
            return _CZECH_MONTHS[num - 1]
        return ""


class DayOfWeekParser:
    @staticmethod
    def parse(raw: str) -> list[str]:
        m = re.search(r"\(([^)]+)\)", raw)
        if not m:
            return []
        parts = re.split(r"[/;–-]", m.group(1))
        days: list[str] = []
        for part in parts:
            token = part.strip().lower()
            if token in _DAY_ABBREV:
                days.append(_DAY_ABBREV[token])
                continue
            for eng, czech in zip(_ENG_DAYS, _CZECH_DAYS):
                if czech.startswith(token):
                    days.append(eng)
                    break
        return days


class PriceParser:
    @staticmethod
    def parse(raw: str) -> list[dict]:
        prices: list[dict] = []
        text = raw.upper()
        for m in re.finditer(r"(PÁTEK|SOBOTA|PONDĚLÍ|ÚTERÝ|STŘEDA|ČTVRTEK|NEDĚLE|OBA\s*DNY)?\s*(\d[\d.]+)\s*K[ČC]", text):
            raw_label = (m.group(1) or "").replace(" ", " ").lower() if m.group(1) else ""
            label = _PRICE_LABEL_MAP.get(raw_label, "")
            amount_str = m.group(2).replace(".", "")
            prices.append({"day_label": label, "amount": float(amount_str), "currency": "CZK"})
        if not prices and "PŘIPRAVUJEME" in text:
            prices.append({"day_label": "tbd", "amount": 0.0, "currency": "TBD"})
        return prices


class TrackNameParser:
    @staticmethod
    def parse(raw: str) -> str | None:
        m = re.search(r"<strong[^>]*>([\s\S]*?)</strong>", raw)
        if not m:
            return None
        name = re.sub(_TAG_RE, " ", m.group(1))
        name = " ".join(name.split())
        for suffix in ("VOLNÉ JÍZDY", "VYPRODÁNO"):
            if name.upper().endswith(suffix):
                name = name[:-len(suffix)].rstrip()
        return name


_ENG_DAYS_FULL = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]



def _compute_day_of_week(day: int | None, month: int | None, year: int | None) -> list[str]:
    if day is None or month is None or year is None:
        return []
    try:
        return [_ENG_DAYS_FULL[datetime.date(year, month, day).weekday()]]
    except (ValueError, OverflowError):
        return []


_TRACK_MAP = {
    "AUTODROM VYSOKÉ MÝTO": _VYSOKE_MYTO,
    "OKRUH PÍSEK": _PISEK,
    "OKRUH CHEB": "Cheb",
    "POLYGON MOST": _POLYGON_MOST,
    "AUTODROM SOSNOVÁ": _SOSNOVA,
    "AUTODROM MOST": "Most",
    "TRACKDAY SOSNOVÁ": _SOSNOVA,
    "PANNONIA": "Pannoniaring",
    "SLOVAKIA RING": "Slovakiaring",
    "SLOVAKIARING": "Slovakiaring",
    "LETIŠTĚ MNICHOVO HRADIŠTĚ": _LETISTE_MNICHOVO_HRADISTE,
    "HOSKOVICE": _LETISTE_MNICHOVO_HRADISTE,
    "MNICHOVO HRADIŠTĚ": _LETISTE_MNICHOVO_HRADISTE,
    "MIMOŇ": _LETISTE_HRADCANY,
    "CHOTEČ": _CHOTEC,
    "KAVČÁK – BENEŠOV": _KAVCAK_BENESOV,
    "RUMUNSKO": "Rumunsko",
    "GRUZIE": "Gruzie",
    "MAROKO": "Maroko",
    "BOSNA A ČERNÁ HORA": _BOSNA_CERNA_HORA,
    "VALENCIA": "Valencia",
    "GELNICA": "Gelnica",
    "CARTAGENA": "Cartagena",
    "ALMERÍA": _ALMERIA,
}


_TRACK_COUNTRY: dict[str, str] = {
    _VYSOKE_MYTO: "CZ",
    _PISEK: "CZ",
    "Cheb": "CZ",
    _POLYGON_MOST: "CZ",
    _SOSNOVA: "CZ",
    "Most": "CZ",
    "Brno": "CZ",
    _LETISTE_MNICHOVO_HRADISTE: "CZ",
    _CHOTEC: "CZ",
    _KAVCAK_BENESOV: "CZ",
    "Liberec": "CZ",
    "Beroun": "CZ",
    "Slovakiaring": "SK",
    "Gelnica": "SK",
    "Slovakia": "SK",
    "Pannoniaring": "HU",
    "Valencia": "ES",
    "Cartagena": "ES",
    _ALMERIA: "ES",
    "Rumunsko": "RO",
    "Gruzie": "GE",
    "Maroko": "MA",
    _BOSNA_CERNA_HORA: "BA",
    _ITALIE: "IT",
    "Italy": "IT",
    _LETISTE_VYSKOV: "CZ",
    "Pitland": "CZ",
    "Rijeka": "HR",
    "Dolomity, Itálie": "IT",
    "Misano": "IT",
    "Šumperk": "CZ",
    _LETISTE_LHOTA_PLZNE: "CZ",
    _LETISTE_HRADCANY: "CZ",
    "střední Čechy - u Kladna": "CZ",
    "Praha - jižní Čechy": "CZ",
    "Železný Brod - Jizerky a Krkonoše": "CZ",
    "Hradec Králové - Orlické hory": "CZ",
    "Strachotín - jižní Morava": "CZ",
    "Frýdek-Místek - Beskydy": "CZ",
    "jižní Morava - u Brna": "CZ",
    "České Budějovice, výstaviště": "CZ",
}


_TRACK_COORDS: dict[str, tuple[float, float]] = {
    _SOSNOVA: (50.659471, 14.539273),
    "Most": (50.519104, 13.615626),
    _POLYGON_MOST: (50.519104, 13.615626),
    _PISEK: (49.300907, 14.113901),
    "Cheb": (50.086333, 12.448952),
    _VYSOKE_MYTO: (49.935098, 16.175176),
    "Brno": (49.203578, 16.444128),
    _LETISTE_MNICHOVO_HRADISTE: (50.535096, 14.992564),
    _CHOTEC: (49.988616, 14.283061),
    _KAVCAK_BENESOV: (49.792646, 14.710572),
    "Liberec": (50.7667, 15.0500),
    "Beroun": (49.9639, 14.0722),
    "Gelnica": (48.851867, 20.933308),
    _LETISTE_VYSKOV: (49.300068, 17.021312),
    "Pitland": (50.056243, 14.296346),
    "Šumperk": (49.977841, 16.971775),
    _LETISTE_LHOTA_PLZNE: (49.675098, 13.270801),
    _LETISTE_HRADCANY: (50.619714, 14.731902),
    "Slovakiaring": (48.054258, 17.569638),
    "Pannoniaring": (47.304640, 17.047404),
    "Valencia": (39.487719, -0.628912),
    "Cartagena": (37.644295, -1.035524),
    _ALMERIA: (37.085104, -2.266724),
    "Rijeka": (45.382939, 14.508946),
    "Misano": (43.963615, 12.685706),
    "Rumunsko": (44.5000, 26.0000),
    "Gruzie": (42.0000, 43.5000),
    "Maroko": (31.5000, -7.5000),
}


def resolve_coords(track_name: str) -> tuple[float, float] | None:
    return _TRACK_COORDS.get(track_name)


def resolve_country(track_name: str) -> str:
    country = _TRACK_COUNTRY.get(track_name)
    if country:
        return country
    lower = track_name.lower()
    if any(kw in lower for kw in ("letiště", "výstaviště", "odjezd", "střední čechy", "jižní morava")):
        return "CZ"
    return ""


def _strip_track_suffix(name: str) -> str:
    stripped = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
    return stripped if stripped else name


def normalize_track_name(name: str) -> str:
    base = _strip_track_suffix(name)
    upper = base.upper().strip()
    canonical = _TRACK_MAP.get(upper, base.strip())
    return canonical if canonical else name.strip()


class EventParser:
    def __init__(self):
        self.date_parser = DateParser()
        self.day_parser = DayOfWeekParser()
        self.price_parser = PriceParser()
        self.track_parser = TrackNameParser()

    def parse(self, html: str, agency: str = "", url: str = "") -> list[Event]:
        events: list[Event] = []
        h4_blocks = re.findall(r"<h4[^>]*>(.*?)</h4>", html, re.DOTALL)

        for block in h4_blocks:
            text = HtmlHelper.strip_tags(block)
            if len(text) < 20:
                continue

            track = self.track_parser.parse(block)
            if not track:
                continue
            track = normalize_track_name(track)

            day_of_week = self.day_parser.parse(text)
            prices = self.price_parser.parse(text)
            date_obj = self.date_parser.parse(text)
            sold_out = "VYPRODÁNO" in text.upper()

            if date_obj:
                month_num = date_obj.get("month_num", 0)
                raw_date = re.search(r"(\d{1,2}\.\s*\S+[^.]*)\s*\d{4}", text)
                if raw_date:
                    date_str = raw_date.group(1).rstrip(".")
                else:
                    date_str = f"{date_obj['day']}. {date_obj.get('month', '?')} {date_obj.get('year', '?')}"
                if not day_of_week:
                    day_of_week = _compute_day_of_week(
                        date_obj.get("day"), date_obj.get("month_num", month_num), date_obj.get("year")
                    )
            else:
                month_num = 0
                date_str = ""

            events.append(Event(
                agency=agency, track_name=track, date=date_str, url=url,
                year=date_obj.get("year") if date_obj else None,
                month_num=month_num, month_end=date_obj.get("month_end", month_num),
                day=date_obj.get("day") if date_obj else None,
                day_end=date_obj.get("day_end") if date_obj else None,
                day_of_week=day_of_week, prices=prices, sold_out=sold_out,
            ))

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.date))
        return events


class Hefty74Parser:
    def parse(self, html: str, agency: str = "", url: str = "") -> list[Event]:
        m = re.search(r'<div\s+class="akce-wrapper">(.*?)</div>\s*</div>\s*</div>', html, re.DOTALL)
        if not m:
            return []
        wrapper_content = m.group(0)[len('<div class="akce-wrapper">'):]
        default_prices = self._parse_global_prices(html)
        events = self._parse_columns(wrapper_content, default_prices, agency, url)
        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events

    def _parse_columns(self, wrapper: str, prices: list[dict], agency: str, url: str) -> list[Event]:
        events: list[Event] = []
        for col in re.findall(r'<div\s+class="akce-column">(.*?)</div>', wrapper, re.DOTALL):
            track_name = self._extract_track_name(col)
            if not track_name:
                continue
            events.extend(self._parse_termin_items(col, track_name, prices, agency, url))
        return events

    @staticmethod
    def _extract_track_name(col: str) -> str | None:
        track_m = re.search(r'<h2>(.*?)</h2>', col)
        if not track_m:
            return None
        return normalize_track_name(HtmlHelper.strip_tags(track_m.group(1)))

    def _parse_termin_items(self, col: str, track_name: str, prices: list[dict],
                            agency: str, url: str) -> list[Event]:
        events: list[Event] = []
        for li in re.findall(r'<li[^>]*class="termin"[^>]*>(.*?)</li>', col, re.DOTALL):
            ev = self._build_event(li, track_name, prices, agency, url)
            if ev:
                events.append(ev)
        return events

    def _build_event(self, li: str, track_name: str, prices: list[dict],
                     agency: str, url: str) -> Event | None:
        den_m = re.search(r'<span[^>]*class="den"[^>]*>(.*?)</span>', li)
        if not den_m:
            return None
        den_text = HtmlHelper.strip_tags(den_m.group(1))
        date_part = self._parse_den(den_text)
        if not date_part:
            return None
        link_m = re.search(r'<a\s+href="([^"]+)"', li)
        event_url = link_m.group(1) if link_m else url
        return Event(
            agency=agency, track_name=track_name,
            date=f"{date_part['day']}. {date_part['month_num']}.",
            url=event_url, year=self._extract_year(event_url, date_part["month_num"]),
            month_num=date_part["month_num"], day=date_part["day"],
            day_of_week=self._parse_day_names(den_text),
            prices=prices, sold_out="OBSAZENO" in li.upper(),
        )

    @staticmethod
    def _parse_global_prices(html: str) -> list[dict]:
        m = re.search(r'<h4[^>]*>([\d\s]+)\s*K[ČčCc]\s*</h4>', html)
        if not m:
            return []
        amount_str = m.group(1).strip().replace(" ", "")
        try:
            amount = float(amount_str)
        except ValueError:
            return []
        return [{"day_label": "", "amount": amount, "currency": "CZK"}]

    @staticmethod
    def _parse_den(text: str) -> dict | None:
        cleaned = " ".join(text.split())
        m = re.match(r"(\d{1,2})\.\s*(\d{1,2})\.?", cleaned)
        if not m:
            return None
        return {"day": int(m.group(1)), "month_num": int(m.group(2))}

    @staticmethod
    def _extract_year(url: str, month_num: int) -> int:
        m = re.search(r"(\d{4})", url)
        if m:
            return int(m.group(1))
        today = datetime.date.today()
        fallback = today.year
        if month_num < today.month:
            fallback += 1
        return fallback

    @staticmethod
    def _parse_day_names(text: str) -> list[str]:
        text = " ".join(text.split())
        for part in text.split():
            token = part.strip().lower().rstrip(".,")
            if token in _DAY_ABBREV:
                return [_DAY_ABBREV[token]]
            for eng, czech in zip(_ENG_DAYS, _CZECH_DAYS):
                if czech.startswith(token):
                    return [eng]
        return []


class RoadLeagueParser:
    _MONTH_NUM = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    }

    def parse(self, html: str, agency: str = "", url: str = "") -> list[Event]:
        events: list[Event] = []
        event_refs = self._parse_event_refs(html)
        if not event_refs:
            return events

        detail_data = self._fetch_details([ref["url"] for ref in event_refs])

        for ref in event_refs:
            detail = detail_data.get(ref["url"], {})
            prices = detail.get("prices", [])
            sold_out = detail.get("sold_out", False)
            day, month_num, year = ref["day"], ref["month_num"], ref["year"]
            day_of_week = _compute_day_of_week(day, month_num, year)

            events.append(Event(
                agency=agency, track_name=ref["track_name"],
                date=f"{day}. {month_num}. {year}",
                url=ref["url"], year=year, month_num=month_num, day=day,
                day_of_week=day_of_week, prices=prices, sold_out=sold_out,
            ))

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events

    @staticmethod
    def _parse_event_refs(html: str) -> list[dict]:
        refs: list[dict] = []
        for m in re.finditer(
            r'<a\s+class="rlx-row"[^>]*href="([^"]+)"[^>]*>'
            r'\s*<span\s+class="rlx-where">(.*?)</span>'
            r'\s*<span\s+class="rlx-when">(.*?)</span>',
            html, re.DOTALL,
        ):
            url = m.group(1).strip()
            if not url.startswith("http"):
                url = "https://www.roadleague.cz" + url
            track = normalize_track_name(HtmlHelper.strip_tags(m.group(2)).strip())
            date_text = HtmlHelper.strip_tags(m.group(3)).strip()

            parsed = RoadLeagueParser._parse_date(date_text)
            if not parsed:
                continue
            refs.append({"url": url, "track_name": track, **parsed})
        return refs

    @staticmethod
    def _parse_date(text: str) -> dict | None:
        parts = text.replace(",", "").split()
        if len(parts) < 3:
            return None
        month_name = parts[0].strip().lower()
        day_str = parts[1].strip().rstrip(",")
        year_str = parts[2].strip()
        month_num = RoadLeagueParser._MONTH_NUM.get(month_name)
        if not month_num:
            return None
        try:
            day = int(day_str)
            year = int(year_str)
        except ValueError:
            return None
        return {"day": day, "month_num": month_num, "year": year}

    @staticmethod
    def _fetch_details(urls: list[str]) -> dict[str, dict]:
        result: dict[str, dict] = {}
        if not urls:
            return result
        fetcher = SiteFetcher()
        with ThreadPoolExecutor(max_workers=scrape_workers(len(urls))) as pool:
            fut = {pool.submit(fetcher.fetch, u): u for u in urls}
            for f in as_completed(fut):
                url = fut[f]
                try:
                    detail_html = f.result()
                    result[url] = RoadLeagueParser._parse_detail(detail_html)
                except Exception as e:
                    print(f"    Error fetching {url}: {e}")
                    result[url] = {}
        return result

    @staticmethod
    def _parse_detail(html: str) -> dict:
        prices: list[dict] = []
        m = re.search(r'<span class="prd-price-c wnd-product-price">([\d&;nbsp,.\s]+)</span>', html)
        if m:
            amount_str = m.group(1)
            amount_str = HtmlHelper.decode_entities(amount_str)
            amount_str = amount_str.replace("&nbsp;", "").replace("\u00a0", "").replace(" ", "").replace(",", ".")
            try:
                amount = float(amount_str)
                if amount > 0:
                    prices.append({"day_label": "", "amount": amount, "currency": "CZK"})
            except ValueError:
                pass
        return {"prices": prices, "sold_out": False}


class MotoridersParser:
    _API_BASE = "https://motoriders-cz.pgup.cz/api/v1"

    def parse(self, _: str, agency: str = "", url: str = "") -> list[Event]:  # NOSONAR
        events: list[Event] = []
        api_events = self._fetch_all()
        for api_ev in api_events:
            dates = api_ev.get("dates", [])
            if not dates:
                continue
            dates_2026 = sorted(d for d in dates if d.startswith("2026"))
            if not dates_2026:
                continue
            first_day, first_month, first_year = self._parse_date(dates_2026[0])
            if first_day is None:
                continue
            last_day, last_month, _ = self._parse_date(dates_2026[-1])
            day_end_val = last_day if len(dates_2026) > 1 and last_day != first_day else None
            month_end_val = last_month if day_end_val else 0
            day, month_num, year = first_day, first_month, first_year
            track = normalize_track_name(api_ev.get("racetrack", "").strip())
            price_vat = api_ev.get("priceVat", 0) or 0
            price_raw = api_ev.get("price", 0) or 0
            options = api_ev.get("signupOptions", [])
            price = 0
            if price_vat > 0:
                price = price_vat
            elif price_raw > 0:
                price = price_raw
            elif options:
                price = min(o.get("priceVat", 0) for o in options)
            prices = []
            if price > 0:
                prices.append({"day_label": "", "amount": float(price), "currency": "CZK"})
            headline = api_ev.get("headline", "").strip()
            event_url = f"https://motoriders.cz/terminy?go={api_ev.get('id')}"
            day_of_week = _compute_day_of_week(day, month_num, year)
            sold_out = api_ev.get("disabled", False) or (
                api_ev.get("capacity", 0) > 0 and api_ev.get("signups", 0) >= api_ev.get("capacity", 0)
            )
            events.append(Event(
                agency=agency, track_name=track,
                date=f"{day}. {month_num}. {year}",
                url=event_url, year=year, month_num=month_num, month_end=month_end_val,
                day=day, day_end=day_end_val,
                day_of_week=day_of_week, prices=prices, sold_out=sold_out,
                note=headline,
            ))
        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events

    def _fetch_all(self) -> list[dict]:
        fetcher = SiteFetcher()
        result: list[dict] = []
        for page in range(1, 20):
            data = self._fetch_page(fetcher, page)
            if data is None:
                break
            result.extend(self._filter_2026_events(data))
            if len(data) < 50:
                break
        return result

    def _fetch_page(self, fetcher: SiteFetcher, page: int) -> list[dict] | None:
        url = f"{self._API_BASE}/events/type/(multi|single)/page/{page}/limit/50"
        try:
            import json
            return json.loads(fetcher.fetch(url))
        except Exception as e:
            print(f"    API error (page {page}): {e}")
            return None

    @staticmethod
    def _filter_2026_events(data: list[dict]) -> list[dict]:
        result: list[dict] = []
        for ev in data:
            if ev.get("disabled"):
                continue
            dates = ev.get("dates", [])
            if dates and dates[0].startswith("2026"):
                result.append(ev)
        return result

    @staticmethod
    def _parse_date(date_str: str) -> tuple[int | None, int | None, int | None]:
        parts = date_str.split("-")
        if len(parts) != 3:
            return None, None, None
        try:
            return int(parts[2]), int(parts[1]), int(parts[0])
        except ValueError:
            return None, None, None


class CarsJetParser:
    _TRACK_PREFIX = "Trackday "

    def parse(self, html: str, agency: str = "", url: str = "") -> list[Event]:
        # First pass: collect raw event data and detail URLs
        raw_events: list[dict] = []
        detail_urls: list[str] = []
        for article_m in re.finditer(r'<article\s+class="item">(.*?)</article>', html, re.DOTALL):
            item = article_m.group(1)
            if "Balíček" in item:
                continue
            track_m = re.search(r"<strong>([^<]+)</strong>", item)
            if not track_m:
                continue
            track = track_m.group(1).strip()
            if track.startswith(self._TRACK_PREFIX):
                track = track[len(self._TRACK_PREFIX):]
            track = normalize_track_name(track)

            date_m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", item)
            if not date_m:
                continue
            day, month_num, year = int(date_m.group(1)), int(date_m.group(2)), int(date_m.group(3))

            price_m = re.search(r"Cena:\s*([\d\s]+),-", item)
            prices: list[dict] = []
            if price_m:
                amount_str = price_m.group(1).strip().replace(" ", "")
                try:
                    amount = float(amount_str)
                    if amount > 0:
                        prices.append({"day_label": "", "amount": amount, "currency": "CZK"})
                except ValueError:
                    pass

            time_m = re.search(r"Čas:\s*([\d:]+\s*[-–]\s*[\d:]+)", item)
            note = f"({time_m.group(1)})" if time_m else ""

            link_m = re.search(r'href="([^"]+)"', item)
            detail_url = f"https://www.carsjet.cz{link_m.group(1)}" if link_m else None

            raw_events.append({
                "track": track, "day": day, "month_num": month_num, "year": year,
                "prices": prices, "note": note, "detail_url": detail_url,
            })
            if detail_url:
                detail_urls.append(detail_url)

        # Second pass: fetch detail pages for sold out status
        sold_out_map: dict[str, bool] = {}
        if detail_urls:
            fetcher = SiteFetcher()
            with ThreadPoolExecutor(max_workers=scrape_workers(len(detail_urls))) as pool:
                fut = {pool.submit(fetcher.fetch, u): u for u in detail_urls}
                for f in as_completed(fut):
                    detail_url = fut[f]
                    try:
                        detail_html = f.result()
                        sold_out_map[detail_url] = "100% obsazeno" in detail_html.lower()
                    except Exception:
                        sold_out_map[detail_url] = False

        events: list[Event] = []
        for ev in raw_events:
            sold_out = sold_out_map.get(ev["detail_url"], False) if ev["detail_url"] else False
            day_of_week = _compute_day_of_week(ev["day"], ev["month_num"], ev["year"])
            events.append(Event(
                agency=agency, track_name=ev["track"],
                date=f"{ev['day']}. {ev['month_num']}. {ev['year']}",
                url=ev["detail_url"] or url, year=ev["year"],
                month_num=ev["month_num"], day=ev["day"],
                day_of_week=day_of_week, prices=ev["prices"], note=ev["note"],
                sold_out=sold_out,
            ))

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events


_MT_PRICE_MAP: dict[str, float] = {
    "moto trénink na letišti": 6000,
    "moto přípravka na letišti": 6000,
    "moto trénink pro skútry": 5000,
    "individuální trénink na uzavřené trati": 6000,
    "volný trénink na uzavřené trati": 3000,
    "mt series": 3000,
    "enduro kurz": 6000,
}


class MotoTrainingParser:
    @staticmethod
    def parse(html: str, agency: str = "MotoTraining", url: str = "") -> list[Event]:
        events: list[Event] = []
        # Split on loop-item divs: each chunk is one event
        parts = html.split('<div data-elementor-type="loop-item"')
        for part in parts[1:]:
            # Each part starts after the <div ...> and goes until the next split point
            # Find where this event block ends — at the next <div data-elementor-type or at the containing section end
            end_idx = part.find('<div data-elementor-type="loop-item"')
            if end_idx < 0:
                end_idx = part.find('</div>', part.rfind('</div>'))
                if end_idx < 0:
                    continue
            block = part[:end_idx]

            try:
                day_m = re.search(r'<div class="elementor-shortcode">(\d{1,2})\.(\d{1,2})\.</div>', block)
                year_m = re.search(r'<div class="elementor-shortcode">(\d{4})</div>', block)
                if not day_m or not year_m:
                    continue
                day, month_num = int(day_m.group(1)), int(day_m.group(2))
                year = int(year_m.group(1))

                h2s = re.findall(r'<h2[^>]*class="elementor-heading-title[^"]*"[^>]*>(.*?)</h2>', block, re.DOTALL)
                track_raw = HtmlHelper.decode_entities(re.sub(_TAG_RE, ' ', h2s[0]).strip()) if len(h2s) > 0 else ""
                track = normalize_track_name(track_raw)
                training_type = HtmlHelper.decode_entities(
                    re.sub(_TAG_RE, ' ', h2s[1]).strip()
                ) if len(h2s) > 1 else ""

                url_m = re.search(r'href="(https://mototraining\.rsystem\.cz/\?op=activity\d+)"', block)
                event_url = url_m.group(1) if url_m else url

                tl = training_type.lower()
                amount = 0.0
                for key, val in _MT_PRICE_MAP.items():
                    if key in tl:
                        amount = val
                        break
                prices: list[dict] = []
                if amount > 0:
                    prices.append({"day_label": "", "amount": amount, "currency": "CZK"})

                day_of_week = _compute_day_of_week(day, month_num, year)
                cat = "free_ride" if ("volný" in tl or tl == "mt series") else "closed_track"
                events.append(Event(
                    agency=agency, track_name=track,
                    date=f"{day}. {month_num}. {year}",
                    url=event_url, year=year, month_num=month_num, day=day,
                    day_of_week=day_of_week, prices=prices,
                    note=training_type,
                    category=cat,
                ))
            except Exception:
                continue

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events


class OkruhariSkParser:
    @staticmethod
    def parse(html: str, agency: str = "Okruhári.sk", url: str = "") -> list[Event]:
        events: list[Event] = []
        soup = BeautifulSoup(html, _HTML_PARSER)
        products = soup.find_all("div", class_=lambda c: c and "product" in c and "type-product" in c)
        for prod in products:
            try:
                link_tag = prod.find("h2", class_="product-title")
                if not link_tag:
                    continue
                a_tag = link_tag.find("a")
                if not a_tag:
                    continue
                name = HtmlHelper.decode_entities(a_tag.get_text(strip=True))

                date_m = re.search(r'(\d{1,2})\.(\d{1,2})\.-(\d{1,2})\.(\d{1,2})\.(\d{4})', name)
                month_only_m = re.search(r'(\d{1,2})/(\d{4})', name)
                if not date_m and not month_only_m:
                    continue

                href = a_tag.get("href", "")
                event_url = HtmlHelper.decode_entities(href) if href else url

                amount_tag = prod.find("span", class_="woocommerce-Price-amount")
                prices: list[dict] = []
                if amount_tag:
                    bdi = amount_tag.find("bdi")
                    if bdi:
                        text = bdi.get_text(strip=True)
                        amount_m = re.search(r'([\d\s,]+)', text)
                        if amount_m:
                            try:
                                amount = float(amount_m.group(1).strip().replace(" ", "").replace(",", "."))
                                if amount > 0:
                                    prices.append({"day_label": "", "amount": amount, "currency": "EUR"})
                            except ValueError:
                                pass

                cats_div = prod.find("div", class_="products-page-cats")
                cat_text = cats_div.get_text(" ", strip=True).lower() if cats_div else ""
                category = "closed_track" if "racing" in cat_text else "free_ride"

                classes = " ".join(prod.get("class", []))
                sold_out = "outofstock" in classes

                if date_m:
                    day = int(date_m.group(1))
                    month_num = int(date_m.group(2))
                    day_end = int(date_m.group(3))
                    month_end = int(date_m.group(4))
                    year = int(date_m.group(5))
                else:
                    month_num = int(month_only_m.group(1))
                    year = int(month_only_m.group(2))
                    day = 1
                    day_end = None
                    month_end = None

                track_name = "Valencia" if "valencia" in name.lower() else "Slovakiaring"
                day_of_week = _compute_day_of_week(day, month_num, year)
                events.append(Event(
                    agency=agency, track_name=track_name,
                    date=f"{day}. {month_num}. {year}",
                    url=event_url, year=year, month_num=month_num, day=day,
                    day_end=day_end, month_end=month_end,
                    day_of_week=day_of_week, prices=prices, sold_out=sold_out,
                    note=name, category=category,
                ))
            except Exception:
                continue

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events


class RmotoAcademyParser:
    _DATE_REGEX = re.compile(r'(\d{1,2})\.\s*-\s*(\d{1,2})\.\s*(\d{1,2})\.(\d{4})')
    _CATEGORY_MAP: dict[str, str] = {
        "trackdays": "free_ride",
        "riding experience": "free_ride",
        "adventure výjazd": "enduro",
        "on-road výjazd": "free_ride",
        "enduro výjazd": "enduro",
        "endurokemp": "enduro",
    }
    _TRACK_PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r'\bbrno\b'), "Brno"),
        (re.compile(r'\bmost\b'), "Most"),
        (re.compile(r'\bcartagena\b'), "Cartagena"),
        (re.compile(r'\bgelnica\b'), "Gelnica"),
        (re.compile(r'\bšpanielsko\b|\balmer[ií]a\b'), _ALMERIA),
        (re.compile(r'\bcesta okolo slovenska\b'), "Slovakia"),
    ]

    @staticmethod
    def parse(html: str, agency: str = "RMoto Academy", url: str = "") -> list[Event]:
        events: list[Event] = []
        soup = BeautifulSoup(html, _HTML_PARSER)
        product_cards = soup.find_all("div", class_=lambda c: c and "grid-product" in c.split())
        if not product_cards:
            return events

        products_data = RmotoAcademyParser._fetch_products_json()

        for card in product_cards:
            try:
                handle = card.get("data-product-handle", "")
                title_tag = card.find("div", class_="grid-product__title")
                if not title_tag:
                    continue
                title = HtmlHelper.decode_entities(title_tag.get_text(strip=True))

                vendor_tag = card.find("div", class_="grid-product__vendor")
                vendor = vendor_tag.get_text(strip=True).lower() if vendor_tag else ""

                date_tag = card.find("div", class_="grid-product__tag--custom")
                if not date_tag:
                    continue
                date_text = date_tag.get_text(strip=True)

                date_m = RmotoAcademyParser._DATE_REGEX.search(date_text)
                if not date_m:
                    continue

                day = int(date_m.group(1))
                day_end = int(date_m.group(2))
                month_num = int(date_m.group(3))
                month_end = month_num
                year = int(date_m.group(4))

                track_name = RmotoAcademyParser._determine_track(title)

                category = RmotoAcademyParser._CATEGORY_MAP.get(vendor, "free_ride")
                prices, all_sold = RmotoAcademyParser._get_variant_info(products_data, handle)
                sold_out = all_sold

                day_of_week = _compute_day_of_week(day, month_num, year)
                events.append(Event(
                    agency=agency, track_name=track_name,
                    date=f"{day}. {month_num}. {year}",
                    url=url, year=year, month_num=month_num, day=day,
                    day_end=day_end, month_end=month_end,
                    day_of_week=day_of_week, prices=prices, sold_out=sold_out,
                    note=title, category=category,
                ))
            except Exception:
                continue

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events

    @staticmethod
    def _determine_track(title: str) -> str:
        title_lower = title.lower()
        for pattern, track in RmotoAcademyParser._TRACK_PATTERNS:
            if pattern.search(title_lower):
                return normalize_track_name(track)
        return "?"

    @staticmethod
    def _fetch_products_json() -> list[dict]:
        import json as _json
        fetcher = SiteFetcher()
        raw: list[dict] = []
        page = 1
        while True:
            json_url = f"https://rmoto.sk/collections/skupinove-terminy/products.json?page={page}"
            try:
                body = fetcher.fetch(json_url)
            except Exception:
                break
            try:
                data = _json.loads(body)
            except Exception:
                break
            products = data.get("products", [])
            if not products:
                break
            raw.extend(products)
            page += 1
        return raw

    @staticmethod
    def _get_variant_info(products_data: list[dict], handle: str) -> tuple[list[dict], bool]:
        for prod in products_data:
            if prod.get("handle") == handle:
                min_price = 0.0
                any_available = False
                for v in prod.get("variants", []):
                    try:
                        price = float(v.get("price", 0))
                    except (ValueError, TypeError):
                        continue
                    if price > 0 and (min_price == 0 or price < min_price):
                        min_price = price
                    if v.get("available"):
                        any_available = True
                prices = [{"day_label": "", "amount": min_price, "currency": "EUR"}] if min_price > 0 else []
                return prices, not any_available
        return [], False


class NaOkruhParser:
    @staticmethod
    def parse(html: str, agency: str = "NaOkruh", url: str = "") -> list[Event]:
        events: list[Event] = []
        products = re.findall(r'<li[^>]*class="[^"]*product[^"]*"[^>]*>.*?</li>', html, re.DOTALL)
        for prod in products:
            try:
                name_m = re.search(
                    r'<h2[^>]*class="[^"]*woocommerce-loop-product__title[^"]*"[^>]*>(.*?)</h2>',
                    prod, re.DOTALL,
                )
                if not name_m:
                    continue
                name = HtmlHelper.decode_entities(name_m.group(1).strip())
                if "Voucher" in name or "voucher" in name:
                    continue

                link_m = re.search(r'<a href="([^"]+)"', prod)
                event_url = HtmlHelper.decode_entities(link_m.group(1)) if link_m else url

                amount_m = re.search(
                    r'<span class="woocommerce-Price-amount[^"]*"[^>]*><bdi>([\d\s]+)',
                    prod,
                )
                prices: list[dict] = []
                if amount_m:
                    try:
                        amount = float(amount_m.group(1).strip().replace(" ", ""))
                        if amount > 0:
                            prices.append({"day_label": "", "amount": amount, "currency": "CZK"})
                    except ValueError:
                        pass

                time_m = re.search(r'(\d{1,2}:\d{2})\s*[–\-—]\s*(\d{1,2}:\d{2})', name)
                time_str = f"{time_m.group(1)}–{time_m.group(2)}" if time_m else ""

                date_m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', name)
                if not date_m:
                    continue
                day = int(date_m.group(1))
                month_num = int(date_m.group(2))
                year = int(date_m.group(3))

                track = _SOSNOVA
                sold_out = "outofstock" in prod or "out-of-stock" in prod

                day_of_week = _compute_day_of_week(day, month_num, year)
                events.append(Event(
                    agency=agency, track_name=track,
                    date=f"{day}. {month_num}. {year}",
                    url=event_url, year=year, month_num=month_num, day=day,
                    day_of_week=day_of_week, prices=prices, sold_out=sold_out,
                    note=time_str,
                    category="closed_track",
                ))
            except Exception:
                continue

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events


class StopNehodamParser:
    _PRICES: dict[str, float] = {
        "Hoškovice": 2900,
    }
    _DEFAULT_PRICE = 2490

    @staticmethod
    def parse(html: str, agency: str = "StopNehodam", url: str = "") -> list[Event]:
        events: list[Event] = []

        for m in re.finditer(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        ):
            try:
                data = json.loads(m.group(1))
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict) or item.get(_AT_TYPE) != "Event":
                        continue
                    name = item.get("name", "")
                    start = item.get("startDate", "")
                    if not start:
                        continue
                    dt = datetime.datetime.fromisoformat(start.replace("Z", _UTC_OFFSET))
                    day = dt.day
                    month_num = dt.month
                    year = dt.year

                    end_raw = item.get("endDate", "")
                    day_end = None
                    month_end = None
                    if end_raw:
                        end_dt = datetime.datetime.fromisoformat(end_raw.replace("Z", _UTC_OFFSET))
                        if end_dt.date() != dt.date():
                            day_end = end_dt.day
                            month_end = end_dt.month

                    loc = item.get("location", {})
                    loc_name = loc.get("name", "") if isinstance(loc, dict) else ""
                    track = normalize_track_name(loc_name) if loc_name else "?"

                    price = StopNehodamParser._DEFAULT_PRICE
                    for k, v in StopNehodamParser._PRICES.items():
                        if k.lower() in name.lower() or k.lower() in loc_name.lower():
                            price = v
                            break

                    day_of_week = _compute_day_of_week(day, month_num, year)
                    slug = re.sub(r'[^a-z0-9\s-]', '', name.lower().strip())
                    slug = re.sub(r'\s+', '-', slug)
                    event_url = f"https://www.stopnehodam.cz/{day:02d}-{month_num:02d}-{slug}/"
                    events.append(Event(
                        agency=agency, track_name=track,
                        date=f"{day}. {month_num}. {year}",
                        url=event_url,
                        year=year, month_num=month_num, day=day,
                        day_end=day_end, month_end=month_end,
                        day_of_week=day_of_week,
                        prices=[{"day_label": "", "amount": price, "currency": "CZK"}],
                        note=name,
                        category="public_roads",
                    ))
            except Exception:
                continue

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events


class HondaExperienceParser:
    @staticmethod
    def parse(html: str, agency: str = "Honda Experience", url: str = "") -> list[Event]:
        events: list[Event] = []
        soup = BeautifulSoup(html, _HTML_PARSER)

        product_links: list[str] = []
        for a in soup.select(".product-grid a.product-name"):
            href = a.get("href", "")
            if href and "hmst" in href:
                if href.startswith("/"):
                    href = f"https://www.honda-experience.cz{href}"
                product_links.append(href)

        product_links = list(dict.fromkeys(product_links))
        if not product_links:
            return events

        fetcher = SiteFetcher()
        with ThreadPoolExecutor(max_workers=scrape_workers(len(product_links))) as pool:
            futures = {pool.submit(fetcher.fetch, u): u for u in product_links}
            for f in as_completed(futures):
                try:
                    events.extend(HondaExperienceParser._parse_detail(
                        f.result(), url or futures[f], agency
                    ))
                except Exception as e:
                    print(f"    Error fetching HMST detail {futures[f]}: {e}")

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events

    @staticmethod
    def _parse_detail(html: str, page_url: str, agency: str) -> list[Event]:
        events: list[Event] = []
        soup = BeautifulSoup(html, _HTML_PARSER)

        price_m = re.search(r'<meta itemprop="lowPrice" content="(\d+)"', html)
        prices: list[dict] = []
        if price_m:
            try:
                amount = float(price_m.group(1))
                if amount > 0:
                    prices.append({"day_label": "", "amount": amount, "currency": "CZK"})
            except ValueError:
                pass

        select = soup.find("select", attrs={"name": "product"})
        if not select:
            return events

        for option in select.find_all("option"):
            text = option.get_text(strip=True)
            m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s+(\d+:\d+)", text)
            if not m:
                continue
            day = int(m.group(1))
            month_num = int(m.group(2))
            year = int(m.group(3))
            time_str = m.group(4)

            track = normalize_track_name("Brno")
            day_of_week = _compute_day_of_week(day, month_num, year)
            events.append(Event(
                agency=agency, track_name=track,
                date=f"{day}. {month_num}. {year}",
                url=page_url, year=year, month_num=month_num, day=day,
                day_of_week=day_of_week, prices=prices,
                sold_out=option.has_attr("disabled"),
                note=f"HMST ROAD {time_str}",
                category="closed_track",
            ))

        return events


_CZECH_MONTH_NAMES_GENITIVE = {
    "ledna": 1, "února": 2, "března": 3, "dubna": 4, "května": 5, "června": 6,
    "července": 7, "srpna": 8, "září": 9, "října": 10, "listopadu": 11, "prosince": 12,
}


class MotoSkolaRadekandrlikParser:
    @staticmethod
    def parse(html: str, agency: str = "MotoŠkolaRadekAndrlík", url: str = "") -> list[Event]:
        events: list[Event] = []
        try:
            import asyncio
            from playwright.async_api import async_playwright

            async def _fetch():
                api_data = []
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    async def on_response(response):
                        if 'cloud-data/v2/items/query' in response.url:
                            try:
                                body = await response.json()
                                api_data.append(body)
                            except Exception:
                                pass
                    page.on('response', on_response)
                    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(5)
                    await browser.close()
                return api_data

            api_responses = asyncio.run(_fetch())
        except ImportError:
            return events
        except Exception:
            return events

        seen_ids: set[str] = set()
        for resp in api_responses:
            for item in resp.get('dataItems', []):
                try:
                    item_id = item.get('id', '') or item.get('data', {}).get('_id', '')
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)
                    d = item['data']
                    title = d.get('title', '')
                    date_val = d.get('date', {}).get(_DATE_KEY, '')
                    if not date_val:
                        continue
                    dt = datetime.datetime.fromisoformat(date_val.replace('Z', _UTC_OFFSET))
                    day = dt.day
                    month_num = dt.month
                    year = dt.year

                    od_raw = d.get('od', '')
                    od_str = od_raw[:5] if od_raw and len(od_raw) >= 5 else ''

                    do_raw = d.get('do', {})
                    if isinstance(do_raw, dict):
                        do_val = do_raw.get(_DATE_KEY, '')
                        do_dt = datetime.datetime.fromisoformat(do_val.replace('Z', _UTC_OFFSET)) if do_val else None
                    else:
                        do_dt = None

                    do_t = ""
                    if do_dt and do_dt.date() != dt.date():
                        do_t = od_str or ""
                    elif do_raw:
                        if isinstance(do_raw, dict):
                            do_iso = do_raw.get(_DATE_KEY, '')
                            if do_iso:
                                do_t_dt = datetime.datetime.fromisoformat(do_iso.replace('Z', _UTC_OFFSET))
                                do_t = do_t_dt.strftime('%H:%M')
                        else:
                            do_t = str(do_raw)[:5]

                    if od_str and do_t:
                        time_range = f"{od_str}–{do_t}"
                    elif od_str:
                        time_range = f"od {od_str}"
                    else:
                        time_range = ""

                    address = d.get('address', '')
                    if _PISEK in address:
                        track = _PISEK
                    elif _ITALIE in address or "Italy" in address:
                        track = address.strip()
                    else:
                        track = address.strip() if address else _PISEK
                    track = normalize_track_name(track)

                    spots = d.get('volnychMist', '')
                    sold_out = "Vyprodáno" in spots or spots.strip() == "0 osob"

                    note_parts = [title]
                    if time_range:
                        note_parts.append(time_range)
                    note = ", ".join(note_parts)

                    date_label = f"{day}. {month_num}. {year}"
                    if do_dt and do_dt.date() != dt.date():
                        date_label = f"{dt.day}. {dt.month}–{do_dt.day}. {do_dt.month}. {do_dt.year}"

                    _PRICE_MAP: dict[str, float] = {
                        "Motoškola v Itálii": 23500,
                        "Motoškola na okruhu": 4000,
                        "Volné jízdy na okruhu": 2500,
                    }
                    price_amount = _PRICE_MAP.get(title, 0)
                    prices_list: list[dict] = []
                    if price_amount > 0:
                        prices_list.append({"day_label": "", "amount": price_amount, "currency": "CZK"})

                    cat = _category_from_track_and_title(track, title)

                    day_of_week = _compute_day_of_week(day, month_num, year)
                    events.append(Event(
                        agency=agency,
                        track_name=track,
                        date=date_label,
                        url=url,
                        year=year,
                        month_num=month_num,
                        day=day,
                        day_of_week=day_of_week,
                        prices=prices_list,
                        sold_out=sold_out,
                        note=note,
                        category=cat,
                    ))
                except Exception:
                    continue

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events


class DafitMotoRacingParser:
    @staticmethod
    def parse(html: str, agency: str = "Dafit Moto Racing", url: str = "") -> list[Event]:
        events: list[Event] = []
        detail_urls: list[str] = []
        raw_events: list[dict] = []

        for card in re.finditer(
            r'<a href="(/[^"]+)"\s*class="hpcalendar__races__race[^"]*"[^>]*>.*?</a>',
            html, re.DOTALL,
        ):
            try:
                content = card.group(0)
                href = card.group(1)

                if "cela-sezona" in href.lower():
                    continue

                title_el = re.search(
                    r'class="hpcalendar__races__race__title">(.*?)</span>',
                    content, re.DOTALL,
                )
                if not title_el:
                    continue
                title_html = title_el.group(1)

                strong_m = re.search(r'<strong>(.*?)</strong>', title_html, re.DOTALL)
                if not strong_m:
                    continue
                date_str = strong_m.group(1).strip()

                track_html = title_html.replace(strong_m.group(0), "")
                track = re.sub(_TAG_RE, '', track_html).strip()

                m = re.search(
                    r'(\d{1,2})\.\s*-?\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{2,4})',
                    date_str,
                )
                if not m:
                    continue
                day_start = int(m.group(1))
                day_end = int(m.group(2))
                month_num = int(m.group(3))
                year_raw = m.group(4)
                year = int(year_raw) if len(year_raw) == 4 else 2000 + int(year_raw)

                loc_el = re.search(
                    r'class="hpcalendar__races__race__location">(.*?)</span>',
                    content, re.DOTALL,
                )
                loc_text = loc_el.group(1).strip() if loc_el else ""

                sold_out = bool(re.search(r'VYPRODÁN[OA]', loc_text, re.IGNORECASE))

                detail_url = f"https://www.dafitmotoracing.com{href}"
                raw_events.append({
                    "track": normalize_track_name(track),
                    "day_start": day_start, "day_end": day_end,
                    "month_num": month_num, "year": year,
                    "loc_text": loc_text, "sold_out": sold_out,
                    "detail_url": detail_url,
                })
                detail_urls.append(detail_url)
            except Exception:
                continue

        price_map: dict[str, float] = {}
        if detail_urls:
            fetcher = SiteFetcher()
            with ThreadPoolExecutor(max_workers=scrape_workers(len(detail_urls))) as pool:
                fut = {pool.submit(fetcher.fetch, u): u for u in detail_urls}
                for f in as_completed(fut):
                    u = fut[f]
                    try:
                        detail_html = f.result()
                        amounts = re.findall(r'(\d[\d\s]*)\s*CZK', detail_html)
                        czk_values = []
                        for a in amounts:
                            try:
                                czk_values.append(float(a.strip().replace(" ", "")))
                            except ValueError:
                                pass
                        if czk_values:
                            price_map[u] = min(czk_values)
                    except Exception:
                        price_map[u] = 0.0

        for ev in raw_events:
            amount = price_map.get(ev["detail_url"], 0.0)
            prices: list[dict] = []
            if amount > 0:
                prices.append({"day_label": "", "amount": amount, "currency": "CZK"})

            date_label = f"{ev['day_start']}. {ev['month_num']}. {ev['year']}"
            day_of_week = _compute_day_of_week(ev["day_start"], ev["month_num"], ev["year"])
            events.append(Event(
                agency=agency, track_name=ev["track"],
                date=date_label,
                url=ev["detail_url"],
                year=ev["year"], month_num=ev["month_num"], day=ev["day_start"],
                day_end=ev["day_end"], month_end=ev["month_num"],
                day_of_week=day_of_week, prices=prices,
                sold_out=ev["sold_out"], note=ev["loc_text"],
            ))

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events


class OkruhariParser:
    @staticmethod
    def parse(html: str, agency: str = "Okruháři", url: str = "") -> list[Event]:
        events: list[Event] = []
        detail_urls: list[str] = []

        raw_events: list[dict] = []
        for card in re.finditer(
            r'<div class="product">.*?<div class="p"[^>]*>(.*?)</div>\s*</div>',
            html, re.DOTALL,
        ):
            try:
                content = card.group(1)

                name_m = re.search(
                    r'data-testid="productCardName">\s*(.*?)\s*</span>', content,
                )
                name = name_m.group(1).strip() if name_m else ""
                if not name:
                    continue

                m = re.search(r'(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})', name)
                if not m:
                    continue
                day, month_num, year = int(m.group(1)), int(m.group(2)), int(m.group(3))

                track = "Brno" if "brno" in name.lower() else "Most"

                price_m = re.search(r'<strong[^>]*>([\d\s]+)\s*Kč', content)
                prices: list[dict] = []
                if price_m:
                    amount_str = price_m.group(1).strip().replace(" ", "")
                    try:
                        amount = float(amount_str)
                        if amount > 0:
                            prices.append({"day_label": "", "amount": amount, "currency": "CZK"})
                    except ValueError:
                        pass

                url_m = re.search(r'href="(/[^"]+)"', content)
                detail_url = f"https://www.okruhari.cz{url_m.group(1)}" if url_m else ""
                sold_out = bool(re.search(r'alt="SOLD', content, re.IGNORECASE))

                date_label = f"{day}. {month_num}. {year}"

                raw_events.append({
                    "day": day, "month_num": month_num, "year": year,
                    "track": track, "prices": prices, "name": name,
                    "detail_url": detail_url, "sold_out": sold_out,
                    "date_label": date_label,
                })
                if detail_url:
                    detail_urls.append(detail_url)
            except Exception:
                continue

        sold_out_map: dict[str, bool] = {}
        if detail_urls:
            fetcher = SiteFetcher()
            with ThreadPoolExecutor(max_workers=scrape_workers(len(detail_urls))) as pool:
                fut = {pool.submit(fetcher.fetch, u): u for u in detail_urls}
                for f in as_completed(fut):
                    u = fut[f]
                    try:
                        detail_html = f.result()
                        sold_out_map[u] = _VYPRODANO in detail_html.lower()
                    except Exception:
                        sold_out_map[u] = False

        for ev in raw_events:
            if ev["detail_url"]:
                ev["sold_out"] = sold_out_map.get(ev["detail_url"], ev["sold_out"])

            day_of_week = _compute_day_of_week(ev["day"], ev["month_num"], ev["year"])
            events.append(Event(
                agency=agency, track_name=ev["track"],
                date=ev["date_label"],
                url=ev["detail_url"] or url,
                year=ev["year"], month_num=ev["month_num"], day=ev["day"],
                day_of_week=day_of_week, prices=ev["prices"],
                sold_out=ev["sold_out"], note=ev["name"],
            ))

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events


class MotoFormaParser:
    @staticmethod
    def parse(html: str, agency: str = "MotoForma", url: str = "") -> list[Event]:
        events: list[Event] = []
        parts = html.split('<div class="course-date-card">')
        for part in parts[1:]:
            try:
                # Find the matching closing </div> for the card
                depth = 0
                end = 0
                for i, ch in enumerate(part):
                    if ch == '<':
                        if part[i:i+4] == '</di':
                            end = part.find('>', i) + 1
                            if depth == 0:
                                break
                            depth -= 1
                        elif part[i:i+3] == '<di' and '/div' not in part[i:i+6]:
                            depth += 1
                card = part[:end]
                date_m = re.search(r'course-date-card__date">(\d{1,2})\.\s*(\w+)', card)
                if not date_m:
                    continue
                day = int(date_m.group(1))
                month_name = date_m.group(2).strip().lower()
                month_num = _CZECH_MONTH_NAMES_GENITIVE.get(month_name)
                if not month_num:
                    continue

                year_m = re.search(r'date=(\d{4})-\d{2}-\d{2}', card)
                year = int(year_m.group(1)) if year_m else datetime.date.today().year

                title_m = re.search(r'course-date-card__title">(.*?)</div>', card)
                title = title_m.group(1).strip() if title_m else "Volné jízdy"

                price_m = re.search(r'course-date-card__price">([\d\s]+)\s*Kč', card)
                prices: list[dict] = []
                if price_m:
                    amount_str = price_m.group(1).strip().replace(" ", "")
                    try:
                        amount = float(amount_str)
                        if amount > 0:
                            prices.append({"day_label": "", "amount": amount, "currency": "CZK"})
                    except ValueError:
                        pass

                sold_out = "btn--disabled" in card or bool(re.search(r'\bObsazeno\b', card))

                day_of_week = _compute_day_of_week(day, month_num, year)
                events.append(Event(
                    agency=agency, track_name=_PISEK,
                    date=f"{day}. {month_num}. {year}",
                    url=url, year=year, month_num=month_num, day=day,
                    day_of_week=day_of_week, prices=prices, sold_out=sold_out,
                    note=title,
                    category="closed_track",
                ))
            except Exception:
                continue

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events


class MotoskolaLandaParser:
    @staticmethod
    def parse(html: str, agency: str = "Motoškola Landa", url: str = "") -> list[Event]:
        events: list[Event] = []
        for card in re.finditer(
            r'<div class="card">\s*<img[^>]*>\s*<div class="card-content">(.*?)</div>\s*</div>',
            html, re.DOTALL,
        ):
            try:
                content = card.group(1)
                m = re.search(r'KDY:\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})', content)
                if not m:
                    continue
                day, month_num, year = int(m.group(1)), int(m.group(2)), int(m.group(3))

                track_m = re.search(r'<h3>(.*?)</h3>', content)
                track_raw = track_m.group(1).strip() if track_m else ""
                track = normalize_track_name(track_raw) if track_raw else "?"

                type_m = re.search(r'</h3>\s*(.*?)<br>', content, re.DOTALL)
                note = type_m.group(1).strip() if type_m else ""

                date_label = f"{day}. {month_num}. {year}"

                price_m = re.search(r'<strong>([\d\s]+)\s*Kč</strong>', content)
                prices: list[dict] = []
                if price_m:
                    amount_str = price_m.group(1).strip().replace(" ", "")
                    try:
                        amount = float(amount_str)
                        if amount > 0:
                            prices.append({"day_label": "", "amount": amount, "currency": "CZK"})
                    except ValueError:
                        pass

                places_m = re.search(r'míst:\s*(\d+)', content)
                sold_out = places_m and int(places_m.group(1)) == 0

                day_of_week = _compute_day_of_week(day, month_num, year)
                events.append(Event(
                    agency=agency, track_name=track,
                    date=date_label,
                    url=url, year=year, month_num=month_num, day=day,
                    day_of_week=day_of_week, prices=prices, sold_out=sold_out, note=note,
                ))
            except Exception:
                continue

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events


class Bikes4LifeParser:
    _UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

    @staticmethod
    def _fetch_price(detail_url: str, product_id: str, data_start: str, data_end: str) -> int | None:
        post_data = urllib.parse.urlencode({
            "action": "loadBuyBlock",
            "id": product_id,
            "start": data_start,
            "end": data_end,
        }).encode()
        req = urllib.request.Request(
            "https://bikes4life.cz/wp-content/themes/fns_template/php/shop/ajax/loadBuyBlock.php",
            data=post_data,
            headers={
                "User-Agent": Bikes4LifeParser._UA,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": detail_url,
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        m = re.search(r'<span class="font-weight-bold">([\d\s]+),- Kč</span>', body)
        if m:
            return int(m.group(1).strip().replace(" ", ""))
        return None

    @staticmethod
    def parse(html: str, agency: str = "Bikes4Life", url: str = "") -> list[Event]:
        events: list[Event] = []
        soup = BeautifulSoup(html, _HTML_PARSER)

        akce = soup.find("section", id="akce")
        if not akce:
            return events

        row_mt4 = akce.find("div", class_="row mt-4")
        if not row_mt4:
            return events

        for card in row_mt4.find_all("div", class_=True, recursive=False):
            classes = card.get("class", [])
            if not any("col-lg-6" in c for c in classes):
                continue
            try:
                h3 = card.find("h3", class_="textRed")
                if not h3:
                    continue
                title = h3.get_text(strip=True)

                link = h3.find_parent("a")
                detail_url = link.get("href", "") if link else ""
                if detail_url and not detail_url.startswith("http"):
                    detail_url = f"https://bikes4life.cz{detail_url}"

                m = re.match(
                    r'^Okruh\s+(.+?)\s+(\d{1,2})\.\s*-?\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$',
                    title,
                )
                if m:
                    track_raw, day_s, day_e, month_s, year_s = m.groups()
                    day, day_end, month_num, year = int(day_s), int(day_e), int(month_s), int(year_s)
                else:
                    m2 = re.match(
                        r'^Okruh\s+(.+?)\s+(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$', title,
                    )
                    if not m2:
                        continue
                    track_raw, day_s, month_s, year_s = m2.groups()
                    day = day_end = int(day_s)
                    month_num, year = int(month_s), int(year_s)

                track = normalize_track_name(track_raw)
                date_str = f"{day}. {month_num}. {year}"

                status_el = card.find("span", class_="text-danger")
                sold_out = bool(status_el and "Vyprodáno" in status_el.get_text())

                prices: list[dict] = []
                if detail_url:
                    try:
                        req = urllib.request.Request(detail_url, headers={"User-Agent": Bikes4LifeParser._UA})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            detail_html = resp.read().decode(resp.headers.get_content_charset() or "utf-8")
                        shop_div = re.search(
                            r'<div[^>]*class="[^"]*shopBlock[^"]*activeEvent[^"]*"[^>]*>', detail_html,
                        )
                        if shop_div:
                            div_content = shop_div.group(0)
                            id_m = re.search(r'data-id="(\d+)"', div_content)
                            start_m = re.search(r'data-start="([^"]+)"', div_content)
                            end_m = re.search(r'data-end="([^"]+)"', div_content)
                            if id_m and start_m and end_m:
                                price = Bikes4LifeParser._fetch_price(
                                    detail_url, id_m.group(1), start_m.group(1), end_m.group(1),
                                )
                                if price is not None:
                                    prices.append({"day_label": "", "amount": price, "currency": "CZK"})
                        time.sleep(1.5)
                    except Exception as e:
                        print(f"    Bikes4Life price fetch error: {e}")

                events.append(Event(
                    agency=agency, track_name=track, url=detail_url,
                    date=date_str, year=year, month_num=month_num,
                    month_end=month_num if day_end != day else 0,
                    day=day, day_end=day_end,
                    day_of_week=[], prices=prices, sold_out=sold_out, note=title,
                    category="free_ride",
                ))
            except Exception:
                continue

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events


class FacebookEventsParser:
    AGENCY_NAME = "Cones Bike Racers"
    PAGE_URL = "https://www.facebook.com/KurzyShowZavody/events/"

    @staticmethod
    def parse(html: str, agency: str = AGENCY_NAME, url: str = "") -> list[Event]:
        if html:
            events = FacebookEventsParser._parse_soup(html, agency)
            if events:
                return events
        try:
            return FacebookEventsParser._scrape(agency)
        except Exception as e:
            print(f"    Facebook scraper error: {e}")
            return []

    @staticmethod
    def _parse_soup(html: str, agency: str) -> list[Event]:
        soup = BeautifulSoup(html, _HTML_PARSER)
        events: list[Event] = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict) and data.get(_AT_TYPE) == "Event":
                e = FacebookEventsParser._from_jsonld(data, agency)
                if e:
                    events.extend(FacebookEventsParser._maybe_split_event(e))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get(_AT_TYPE) == "Event":
                        e = FacebookEventsParser._from_jsonld(item, agency)
                        if e:
                            events.extend(FacebookEventsParser._maybe_split_event(e))

        return events

    _TRAINING_KEYWORDS = {
        "kurz", "kurzy", "škola", "školení", "trénink", "tréninky",
        "zdokonalovací", "instruktáž", "workshop", "seminář", "výcvik",
    }

    @staticmethod
    def _categorize(name: str) -> str:
        lower = name.lower()
        for kw in FacebookEventsParser._TRAINING_KEYWORDS:
            if kw in lower:
                return "closed_track"
        return "free_ride"

    @staticmethod
    def _maybe_split_event(event: Event) -> list[Event]:
        lower = event.note.lower()
        has_training = any(kw in lower for kw in FacebookEventsParser._TRAINING_KEYWORDS)
        has_free_ride = "volné jízdy" in lower
        if not (has_training and has_free_ride):
            return [event]

        prices = sorted(event.prices, key=lambda p: p.get("amount", 0), reverse=True)
        training_price = [prices[0]] if prices else []
        freeride_price = [prices[1]] if len(prices) > 1 else []

        kw = Event(
            agency=event.agency, track_name=event.track_name,
            date=event.date, url=event.url,
            year=event.year, month_num=event.month_num, month_end=event.month_end,
            day=event.day, day_end=event.day_end, day_of_week=event.day_of_week,
            prices=training_price, sold_out=event.sold_out,
            note=event.note, category="closed_track",
        )
        fr = Event(
            agency=event.agency, track_name=event.track_name,
            date=event.date, url=event.url,
            year=event.year, month_num=event.month_num, month_end=event.month_end,
            day=event.day, day_end=event.day_end, day_of_week=event.day_of_week,
            prices=freeride_price, sold_out=event.sold_out,
            note=f"{event.note} (volné jízdy)", category="free_ride",
        )
        return [kw, fr]

    @staticmethod
    def _from_jsonld(data: dict, agency: str) -> Event | None:
        name = data.get("name", "")
        if not name:
            return None

        start = data.get("startDate", "")
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(start))
        if not m:
            return None
        year, month_num, day = int(m.group(1)), int(m.group(2)), int(m.group(3))

        location = ""
        loc = data.get("location", {}) or {}
        if isinstance(loc, dict):
            location = loc.get("name", "") or loc.get("address", "") or ""
        if isinstance(loc, str):
            location = loc

        prices: list[dict] = []
        offers = data.get("offers", {}) or {}
        if isinstance(offers, dict):
            price_str = offers.get("price", "")
            try:
                amount = float(price_str)
                prices.append({"day_label": "", "amount": amount, "currency": "CZK"})
            except (ValueError, TypeError):
                pass

        track = normalize_track_name(location or _VYSOKE_MYTO)
        day_of_week = _compute_day_of_week(day, month_num, year)

        return Event(
            agency=agency, track_name=track,
            date=f"{day}. {month_num}. {year}",
            year=year, month_num=month_num, day=day,
            day_of_week=day_of_week, prices=prices,
            note=name, category=FacebookEventsParser._categorize(name),
        )

    @staticmethod
    def _scrape(agency: str) -> list[Event]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
                locale="cs-CZ",
            )
            page = context.new_page()
            event_ids = FacebookEventsParser._collect_event_ids(page)
            events = FacebookEventsParser._scrape_events(page, event_ids, agency)
            browser.close()
        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events

    @staticmethod
    def _collect_event_ids(page) -> set[str]:
        ids: set[str] = set()
        try:
            page.goto(FacebookEventsParser.PAGE_URL, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(3000)
            content = page.content()
            soup = BeautifulSoup(content, _HTML_PARSER)
            for a in soup.find_all("a", href=re.compile(r"/events/\d+")):
                m = re.search(r"/events/(\d+)", a.get("href", ""))
                if m:
                    ids.add(m.group(1))
        except Exception as e:
            print(f"    Facebook listing page error: {e}")
        return ids

    @staticmethod
    def _scrape_events(page, event_ids: set[str], agency: str) -> list[Event]:
        events: list[Event] = []
        for eid in list(event_ids)[:20]:
            ev = FacebookEventsParser._scrape_single_event(page, eid, agency)
            if ev:
                events.extend(ev)
        return events

    @staticmethod
    def _scrape_single_event(page, eid: str, agency: str) -> list[Event] | None:
        try:
            detail_url = f"https://www.facebook.com/events/{eid}/"
            page.goto(detail_url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(3000)
            page.evaluate("""() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if (el.children.length === 0 && el.textContent) {
                        const t = el.textContent.trim().toLowerCase();
                        if ((t.includes('zobrazit') && t.includes('víc')) || t.includes('zobrazit celý')) {
                            let p = el;
                            for (let i = 0; i < 5; i++) { if (p.click) { p.click(); break; } p = p.parentElement; }
                        }
                    }
                }
            }""")
            page.wait_for_timeout(2000)
            return FacebookEventsParser._process_detail(page.content(), agency, detail_url)
        except Exception as e:
            print(f"    Facebook event {eid} error: {e}")
            return None

    @staticmethod
    def _process_detail(html: str, agency: str, url: str) -> list[Event]:
        parsed = FacebookEventsParser._parse_soup(html, agency)
        if parsed:
            for ev in parsed:
                ev.url = url
            return parsed
        ev = FacebookEventsParser._extract_from_text(html, agency, url)
        if ev:
            return FacebookEventsParser._maybe_split_event(ev)
        return []

    @staticmethod
    def _extract_from_text(html: str, agency: str, url: str) -> Event | None:
        soup = BeautifulSoup(html, _HTML_PARSER)

        event_name = ""
        track_location = ""
        for meta in soup.find_all("meta"):
            prop = (meta.get("property", "") or meta.get("name", "") or "")
            if prop in ("og:title", "twitter:title"):
                event_name = meta.get("content", "") or event_name
            elif prop in ("og:description", "description", "twitter:description"):
                desc = meta.get("content", "")
                if not event_name:
                    m = re.search(r"^([^,]+)", desc)
                    if m:
                        event_name = m.group(1).strip()
                loc_m = re.search(r"ve městě\s+([^,]+)", desc)
                if loc_m:
                    track_location = loc_m.group(1).strip()

        if not event_name:
            title = soup.find("title")
            event_name = title.get_text(strip=True) if title else ""

        text = soup.get_text(separator=" ", strip=True)
        date_m = re.search(_DATE_RE, text)
        if not date_m:
            date_m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        day, month_num, year = None, None, None
        if date_m:
            if date_m.lastindex == 3 and len(date_m.group(1)) == 4:
                year, month_num, day = int(date_m.group(1)), int(date_m.group(2)), int(date_m.group(3))
            else:
                day, month_num, year = int(date_m.group(1)), int(date_m.group(2)), int(date_m.group(3))
        if not day or not month_num or not year:
            cz_months = _CZECH_MONTH_NAMES_GENITIVE
            cz_m = re.search(r"(\d{1,2})\.\s*(" + "|".join(cz_months) + r")\s*(\d{4})", text, re.I)
            if cz_m:
                day = int(cz_m.group(1))
                month_num = cz_months[cz_m.group(2).lower()]
                year = int(cz_m.group(3))
        if not day or not month_num or not year:
            return None

        if not event_name:
            event_name = f"Event {day}.{month_num}.{year}"

        prices: list[dict] = []
        for price_m in re.finditer(r"(\d[\d\s]*)\s*,?\s*-?\s*[Kk][Čč]", text):
            try:
                amount = float(price_m.group(1).replace(" ", ""))
                prices.append({"day_label": "", "amount": amount, "currency": "CZK"})
            except ValueError:
                pass

        track = normalize_track_name(track_location or _VYSOKE_MYTO)
        day_of_week = _compute_day_of_week(day, month_num, year)

        return Event(
            agency=agency, track_name=track, url=url,
            date=f"{day}. {month_num}. {year}",
            year=year, month_num=month_num, day=day,
            day_of_week=day_of_week, prices=prices,
            note=event_name, category=FacebookEventsParser._categorize(event_name),
        )


class MotoLisyParser:
    def parse(self, html: str, agency: str = "Moto Lisý", url: str = "") -> list[Event]:
        events: list[Event] = []
        soup = BeautifulSoup(html, _HTML_PARSER)
        section = soup.find(string=lambda t: t and "Nejbližší volné akce" in t)
        if not section:
            return events
        parent = section.find_parent()
        if not parent:
            return events
        container = parent.find_next("div", class_="ct-ultimate-event-item")
        if container:
            items = parent.find_all("div", class_="ct-ultimate-event-item")
        else:
            container = parent.find_next("div")
            items = container.find_all("div") if container else []
        if not items:
            text = parent.get_text() if parent else ""
            for m in re.finditer(r"(\d{2})\.(\d{2})\.(\d{4})\s*(.+)", text):
                day, month_num, year, name = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4).strip()
                track = "?"
                for t in [_PISEK, "Most", "Beroun"]:
                    if t in name:
                        track = t
                        break
                track = normalize_track_name(track)
                day_of_week = _compute_day_of_week(day, month_num, year)
                cat = "enduro" if "enduro" in name.lower() else "closed_track"
                events.append(Event(
                    agency=agency, track_name=track, url=url,
                    date=f"{day}. {month_num}. {year}",
                    year=year, month_num=month_num, day=day,
                    day_of_week=day_of_week, prices=[], note=name,
                    category=cat,
                ))
        else:
            for item in items:
                text = item.get_text(" ", strip=True)
                m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})\s*(.+)", text)
                if not m:
                    continue
                day, month_num, year, name = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4).strip()
                track = _simple_track(name)
                track = normalize_track_name(track)
                day_of_week = _compute_day_of_week(day, month_num, year)
                cat = "enduro" if "enduro" in name.lower() else "closed_track"
                events.append(Event(
                    agency=agency, track_name=track, url=url,
                    date=f"{day}. {month_num}. {year}",
                    year=year, month_num=month_num, day=day,
                    day_of_week=day_of_week, prices=[], note=name,
                    category=cat,
                ))
        return events


class GasovaMotoskolaParser:
    def parse(self, html: str, agency: str = "Gasova Motoškola", url: str = "") -> list[Event]:
        soup = BeautifulSoup(html, _HTML_PARSER)
        table = soup.find("table")
        if not table:
            return []
        return [ev for row in table.find_all("tr")[1:]
                if (ev := self._parse_row(row, agency, url)) is not None]

    def _parse_row(self, row, agency: str, url: str) -> Event | None:
        cells = row.find_all("td")
        if len(cells) < 3:
            return None
        date_text = cells[0].get_text(strip=True)
        m = re.search(_DATE_RE, date_text)
        if not m:
            return None
        day, month_num, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return Event(
            agency=agency, track_name=normalize_track_name("Liberec"), url=url,
            date=f"{day}. {month_num}. {year}",
            year=year, month_num=month_num, day=day,
            day_of_week=_compute_day_of_week(day, month_num, year),
            prices=[{"day_label": "", "amount": 3470, "currency": "CZK"}],
            sold_out=self._is_sold_out(self._cell_text(cells, 2)),
            note=self._cell_text(cells, 1),
            category=self._category(self._cell_text(cells, 1)),
        )

    @staticmethod
    def _cell_text(cells, idx: int) -> str:
        return cells[idx].get_text(" ", strip=True) if len(cells) > idx else ""

    @staticmethod
    def _is_sold_out(avail: str) -> bool:
        return _VYPRODANO in avail.lower() or "prodáno" in avail.lower()

    @staticmethod
    def _category(desc: str) -> str:
        return "enduro" if ("enduro" in desc.lower() or "offroad" in desc.lower()) else "public_roads"


class BrnoMotoskolaParser:
    URLS = [
        "https://vstupenky.brno-circuit.com/motoskola-start/",
        "https://vstupenky.brno-circuit.com/motoskola-road/",
        "https://vstupenky.brno-circuit.com/motoskola-po-zadnim-2/",
        "https://vstupenky.brno-circuit.com/motoskola-pro-zeny/",
        "https://vstupenky.brno-circuit.com/motoskola-po-zadnim-level-pro/",
    ]

    def parse(self, html: str, agency: str = "Silniční Motoškola Brno", url: str = "") -> list[Event]:
        events: list[Event] = []
        soup = BeautifulSoup(html, _HTML_PARSER)
        items = soup.find_all("div", class_="terms-list__item")
        if not items:
            items = soup.find_all("div", class_="terms-list__item is-active-all")
        for item in items:
            headline = item.find("div", class_="terms-list__item-headline")
            if not headline:
                continue
            date_span = headline.find("span")
            if not date_span:
                continue
            date_text = date_span.get_text(strip=True)
            m = re.search(_DATE_RE, date_text)
            if not m:
                continue
            day, month_num, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            price_el = item.find("div", class_="terms-list__item-price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            price_text = price_text.replace("\xa0", " ")
            amount = None
            currency = "CZK"
            if price_text:
                pm = re.search(r"([\d\s]+)\s*,?\s*(\d+)\s*[KkČč]", price_text)
                if pm:
                    amount = float(pm.group(1).replace(" ", ""))
                em = re.search(r"€\s*([\d\s]+)\s*,?\s*(\d+)", price_text)
                if em:
                    amount = float(em.group(1).replace(" ", ""))
                    currency = "EUR"
            prices = []
            if amount:
                prices.append({"day_label": "", "amount": amount, "currency": currency})
            sold_out = False
            track = normalize_track_name("Brno")
            day_of_week = _compute_day_of_week(day, month_num, year)
            note = ""
            desc_el = item.find("div", class_="terms-list__item-desc")
            if desc_el:
                note = desc_el.get_text(" ", strip=True)
            events.append(Event(
                agency=agency, track_name=track, url=url,
                date=f"{day}. {month_num}. {year}",
                year=year, month_num=month_num, day=day,
                day_of_week=day_of_week, prices=prices,
                sold_out=sold_out, note=note,
                category="closed_track",
            ))
        return events


class BrnoCircuitParser:
    _LISTING_URLS = [
        "https://tickets.brno-circuit.com/moto-open-track-for-public/",
    ]

    _TITLE_RE = re.compile(
        r"Open Track For Public MOTO\s+(\d{1,2})\.(\d{1,2})\.(\d{4})", re.IGNORECASE
    )

    def parse(self, html: str, agency: str = "Brno Circuit", url: str = "") -> list[Event]:
        from .fetcher import SiteFetcher
        fetcher = SiteFetcher()
        events: list[Event] = []

        soup = BeautifulSoup(html, _HTML_PARSER)
        items = soup.find_all("div", class_="box__item")
        for item in items:
            h4 = item.find("h4")
            if not h4:
                continue
            title = h4.get_text(strip=True)
            m = self._TITLE_RE.search(title)
            if not m:
                continue
            day, month_num, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            link = item.find("a", class_="link-hidden")
            detail_url = ""
            if link:
                href = link.get("href", "")
                detail_url = href if href.startswith("http") else f"https://tickets.brno-circuit.com{href}"

            prices: list[dict] = []
            sold_out = True
            if detail_url:
                try:
                    detail_html = fetcher.fetch(detail_url)
                    prices, sold_out = self._parse_detail(detail_html)
                except Exception:
                    pass

            events.append(Event(
                agency=agency,
                track_name=normalize_track_name("Brno"),
                url=detail_url or url,
                date=f"{day}. {month_num}. {year}",
                year=year, month_num=month_num, day=day,
                day_of_week=_compute_day_of_week(day, month_num, year),
                prices=prices,
                sold_out=sold_out,
                note=title,
                category="free_ride",
            ))
        return events

    @staticmethod
    def _parse_detail(html: str) -> tuple[list[dict], bool]:
        soup = BeautifulSoup(html, _HTML_PARSER)
        items = soup.find_all("div", class_="terms-list__item")
        prices: list[dict] = []
        any_available = False
        for item in items:
            price_el = item.find("div", class_="terms-list__item-price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            headline_el = item.find("div", class_="terms-list__item-headline")
            time_label = ""
            if headline_el:
                span = headline_el.find("span")
                if span:
                    time_label = span.get_text(strip=True)

            amount = None
            currency = "CZK"
            if price_text:
                em = re.search(r"€\s*([\d\s.,]+)", price_text)
                if em:
                    amount = float(em.group(1).replace(" ", "").replace(",", "."))
                    currency = "EUR"
                else:
                    pm = re.search(r"([\d\s.,]+)", price_text)
                    if pm:
                        amount = float(pm.group(1).replace(" ", "").replace(",", "."))

            button = item.find("button")
            sold_out_item = False
            if button and "mdi-cart-off" in button.get("class", []):
                sold_out_item = True
            cap_div = item.find("div", class_="free_capacity")
            if cap_div and cap_div.get("title") == "Sold out":
                sold_out_item = True

            if not sold_out_item:
                any_available = True
            if amount is not None:
                prices.append({"day_label": time_label, "amount": amount, "currency": currency})

        return prices, not any_available


class MotokoucParser:
    URLS = [
        "https://motokouc.cz/project/okruh-sosnova/",
        "https://motokouc.cz/project/okruh-sosnova-odpoledne/",
    ]

    @staticmethod
    def parse(html: str, agency: str = "Motokouč", url: str = "") -> list[Event]:
        by_date: dict[tuple[int, int, int], dict] = {}
        for m in re.finditer(r'class="forminator-checkbox"\s+title="(.*?)"', html):
            title = m.group(1)
            dm = re.search(r"(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{4})", title)
            if not dm:
                continue
            d, mon, y = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
            if y < 100:
                y += 2000
            pm = re.search(r"(\d+),-", title)
            if not pm:
                continue
            amount = float(pm.group(1))
            key = (d, mon, y)
            sold_out = _VYPRODANO in title.lower()
            tm = re.search(r"\((\d{1,2})(?::(\d{2}))?\s*[–-]\s*(\d{1,2})(?::(\d{2}))?\s*h?\)", title)
            time_str = ""
            if tm:
                h1, m1, h2, m2 = tm.group(1), tm.group(2) or "00", tm.group(3), tm.group(4) or "00"
                time_str = f"{h1}:{m1}–{h2}:{m2}"
            if key not in by_date:
                by_date[key] = {
                    "min_avail": amount if not sold_out else float("inf"),
                    "min_all": amount,
                    "any_available": not sold_out,
                    "note": time_str,
                }
            else:
                if not sold_out and amount < by_date[key]["min_avail"]:
                    by_date[key]["min_avail"] = amount
                    if time_str:
                        by_date[key]["note"] = time_str
                if amount < by_date[key]["min_all"]:
                    by_date[key]["min_all"] = amount
                if not sold_out:
                    by_date[key]["any_available"] = True

        events: list[Event] = []
        for (d, mon, y), info in by_date.items():
            dow = _compute_day_of_week(d, mon, y)
            price = info["min_avail"] if info["any_available"] else info["min_all"]
            events.append(Event(
                agency=agency, track_name=_SOSNOVA,
                date=f"{d}. {mon}. {y}",
                url=url,
                year=y, month_num=mon, day=d,
                day_of_week=dow,
                prices=[{"day_label": "", "amount": price, "currency": "CZK"}],
                sold_out=not info["any_available"],
                note=info["note"],
                category="free_ride",
            ))
        return events


class BezpecneNaMotorceParser:
    PRODUCTS = [
        ("Celodenní silniční kurzy", "https://www.bezpecne-na-motorce.cz/product-page/silnicni-kurzy-skupinove", 5950, _FULL_DAY),
        ("Cesta z města", "https://www.bezpecne-na-motorce.cz/product-page/cesta-z-mesta", 4950, _FULL_DAY),
        ("Výlet s instruktorem", "https://www.bezpecne-na-motorce.cz/product-page/celodenni-vylet-s-instruktorem", 3950, _FULL_DAY),
        ("Pomalé rychlosti", "https://www.bezpecne-na-motorce.cz/product-page/p%C5%AFldenn%C3%AD-tr%C3%A9nink-rovnov%C3%A1ha-a-stabilita-v-pomal%C3%BDch-rychlostech", 3650, "half day"),
        ("Bezpečné zatáčky", "https://www.bezpecne-na-motorce.cz/product-page/p%C5%AFldenn%C3%AD-tr%C3%A9nink-bezpe%C4%8Dn%C3%A9-zat%C3%A1%C4%8Dky", 3650, "half day"),
    ]

    _CZ_MONTHS = _CZECH_MONTH_NAMES_GENITIVE

    _CLOSED_TRACKS = {
        _LETISTE_MNICHOVO_HRADISTE, _LETISTE_VYSKOV, _LETISTE_LHOTA_PLZNE,
        "Mimoň, letiště", _LETISTE_HRADCANY, "České Budějovice, výstaviště",
    }

    @staticmethod
    def _get_category(track_name: str) -> str:
        return "closed_track" if track_name in BezpecneNaMotorceParser._CLOSED_TRACKS else "public_roads"

    @staticmethod
    def _extract_json_array(text: str, start: int) -> str | None:
        try:
            _, end = json.JSONDecoder().raw_decode(text, start)
            return text[start:end]
        except (json.JSONDecodeError, IndexError):
            return None

    def _build_price_map(self, html: str, sel_lookup: dict[int, str]) -> dict[tuple[str, str], float]:
        import json
        m = re.search(r'"productItems"\s*:\s*(\[)', html)
        if not m:
            return {}
        raw = self._extract_json_array(html, m.start(1))
        if not raw:
            return {}
        product_items = json.loads(raw)
        price_map: dict[tuple[str, str], float] = {}
        for item in product_items:
            if not item.get("isVisible"):
                continue
            sel_values = [sel_lookup.get(sid, "") for sid in item["optionsSelections"]]
            if _NEMAM_ZAJEM not in sel_values:
                continue
            loc_val = ""
            date_val = ""
            for sv in sel_values:
                if sv in ("mám zájem", _NEMAM_ZAJEM):
                    continue
                if BezpecneNaMotorceParser._is_time_slot([sv]):
                    continue
                if re.match(r"\d{1,2}\.\s*\w+", sv):
                    date_val = sv
                else:
                    loc_val = sv
            if date_val:
                loc_val = loc_val or "Česká republika"
                key = (loc_val, date_val)
                if key not in price_map or item["price"] < price_map[key]:
                    price_map[key] = item["price"]
        return price_map

    def parse(self, _: str, agency: str = "Bezpečně na motorce", url: str = "") -> list[Event]:  # NOSONAR
        events: list[Event] = []
        from .fetcher import SiteFetcher
        fetcher = SiteFetcher()

        for product_name, product_url, hardcoded_price, duration in self.PRODUCTS:
            try:
                product_html = fetcher.fetch(product_url)
                m = re.search(r'"nextOptionsSelectionId"\s*:\s*\d+\s*,\s*"options"\s*:\s*(\[)', product_html)
                if not m:
                    continue
                raw = self._extract_json_array(product_html, m.start(1))
                if not raw:
                    continue
                import json
                options = json.loads(raw)
                sel_lookup: dict[int, str] = {}
                for opt in options:
                    for s in opt.get("selections", []):
                        sel_lookup[s["id"]] = s["value"]
                dates: list[str] = []
                locations: list[str] = []
                time_slots: list[str] = []
                for opt in options:
                    selections = [s["value"] for s in opt.get("selections", [])]
                    if any(self._has_cz_month(s) for s in selections):
                        dates.extend(selections)
                    elif selections and not self._is_surcharge(selections):
                        if self._is_time_slot(selections):
                            time_slots.extend(selections)
                        else:
                            locations.extend(selections)
                if not dates:
                    continue
                if not locations:
                    locations = ["Česká republika"]
                price_map = self._build_price_map(product_html, sel_lookup)
                if price_map:
                    seen: set[str] = set()
                    for (loc, date_str), actual_price in price_map.items():
                        track = normalize_track_name(loc)
                        comb_key = f"{track}|{date_str}"
                        if comb_key in seen:
                            continue
                        seen.add(comb_key)
                        parsed = self._parse_date(date_str)
                        if not parsed:
                            continue
                        day, month_num, year = parsed
                        day_of_week = _compute_day_of_week(day, month_num, year)
                        events.append(Event(
                            agency=agency,
                            track_name=track,
                            date=f"{day}. {month_num}. {year}",
                            url=product_url,
                            year=year,
                            month_num=month_num,
                            day=day,
                            day_of_week=day_of_week,
                            prices=[{"day_label": "", "amount": actual_price, "currency": "CZK"}],
                            note=f"{product_name} ({duration})",
                            category=self._get_category(track),
                        ))
                else:
                    for loc in locations:
                        track = normalize_track_name(loc)
                        for date_str in dates:
                            parsed = self._parse_date(date_str)
                            if not parsed:
                                continue
                            day, month_num, year = parsed
                            day_of_week = _compute_day_of_week(day, month_num, year)
                            events.append(Event(
                                agency=agency,
                                track_name=track,
                                date=f"{day}. {month_num}. {year}",
                                url=product_url,
                                year=year,
                                month_num=month_num,
                                day=day,
                                day_of_week=day_of_week,
                                prices=[{"day_label": "", "amount": float(hardcoded_price), "currency": "CZK"}],
                                note=f"{product_name} ({duration})",
                                category=self._get_category(track),
                            ))
            except Exception as e:
                print(f"    BNM {product_name}: {e}")

        return events

    @staticmethod
    def _has_cz_month(text: str) -> bool:
        m = re.search(r"(\d{1,2})\.\s*(\w+)", text)
        return bool(m and m.group(2).lower() in BezpecneNaMotorceParser._CZ_MONTHS)

    @staticmethod
    def _is_surcharge(selections: list[str]) -> bool:
        return len(selections) == 2 and "mám zájem" in selections and _NEMAM_ZAJEM in selections

    @staticmethod
    def _is_time_slot(selections: list[str]) -> bool:
        return all(bool(re.match(r"\d{1,2}\s*[-–]\s*\d{1,2}\s*hod", s)) for s in selections)

    @staticmethod
    def _parse_date(text: str) -> tuple[int, int, int] | None:
        m = re.search(r"(\d{1,2})\.\s*(\w+)", text)
        if not m:
            return None
        day = int(m.group(1))
        month_name = m.group(2).lower()
        month_num = BezpecneNaMotorceParser._CZ_MONTHS.get(month_name)
        if not month_num:
            return None
        return (day, month_num, 2026)


class EnduroSkolaParser:
    _BASE = "https://enduroskola.cz"

    def parse(self, html: str, agency: str = "Enduroškola", url: str = "") -> list[Event]:
        from .fetcher import SiteFetcher
        fetcher = SiteFetcher()
        events: list[Event] = []

        page_htmls = [html]
        for pno in range(2, 20):
            try:
                page_htmls.append(fetcher.fetch(f"{self._BASE}/akce/?pno={pno}"))
            except Exception:
                break

        for page_html in page_htmls:
            soup = BeautifulSoup(page_html, _HTML_PARSER)
            events_div = soup.find("div", class_="css-events-list")
            if not events_div:
                continue

            found = 0
            for event_row in events_div.find_all("div", class_="row seznam-akce"):
                try:
                    cols = event_row.find_all("div", class_="col-md-3")
                    if len(cols) < 2:
                        continue

                    name = cols[0].get_text(" ", strip=True)
                    date_text = cols[1].get_text(" ", strip=True)

                    av_m = re.search(r"počet volných míst:\s*(\d+)", date_text)
                    sold_out = bool(av_m and int(av_m.group(1)) == 0)

                    range_m = re.search(
                        r"(\d{1,2})\.(\d{2})\.(\d{4})\s*[\-–]\s*(\d{1,2})\.(\d{2})\.(\d{4})",
                        date_text,
                    )
                    if range_m:
                        day = int(range_m.group(1))
                        mo = int(range_m.group(2))
                        yr = int(range_m.group(3))
                        day_end = int(range_m.group(4))
                        month_end = int(range_m.group(5))
                    else:
                        single_m = re.search(r"(\d{1,2})\.(\d{2})\.(\d{4})", date_text)
                        if not single_m:
                            continue
                        day = int(single_m.group(1))
                        mo = int(single_m.group(2))
                        yr = int(single_m.group(3))
                        day_end = None
                        month_end = 0

                    link = event_row.find_parent("a")
                    event_url = ""
                    if link:
                        href = link.get("href", "")
                        event_url = href if href.startswith("http") else f"{self._BASE}{href}"

                    detail_html = None
                    if event_url:
                        try:
                            detail_html = fetcher.fetch(event_url)
                        except Exception:
                            pass

                    prices = []
                    amount = self._extract_price(detail_html) if detail_html else None
                    if amount is not None:
                        prices = [{"day_label": "", "amount": float(amount), "currency": "CZK"}]

                    venue = self._extract_venue(detail_html) if detail_html else None
                    location = self._determine_location(name, venue)

                    dow = _compute_day_of_week(day, mo, yr)
                    events.append(Event(
                        agency=agency,
                        track_name=normalize_track_name(location),
                        date=f"{day}. {mo}. {yr}",
                        url=event_url or url,
                        year=yr,
                        month_num=mo,
                        month_end=month_end if day_end else 0,
                        day=day,
                        day_end=day_end,
                        day_of_week=dow,
                        prices=prices,
                        sold_out=sold_out,
                        note=name,
                        category="enduro",
                    ))
                    found += 1
                except Exception:
                    continue

            if found == 0:
                break

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events

    @staticmethod
    def _extract_price(html: str) -> float | None:
        m = re.search(r'<p\s+class="ticket-price">.*?<strong>(.*?)</strong>', html, re.DOTALL)
        if m:
            raw = m.group(1).strip()
            digits = re.sub(r'[^\d,]', '', raw).replace(',', '.')
            try:
                return float(digits)
            except ValueError:
                pass
        m = re.search(r'[cC]ena\s*(\d[\d\s]*)\s*Kč', html)
        if m:
            raw = re.sub(r'\s', '', m.group(1))
            try:
                return float(raw)
            except ValueError:
                pass
        return None

    @staticmethod
    def _extract_venue(html: str) -> str | None:
        m = re.search(r'Místo konání.*?<a[^>]*>([^<]+)</a>', html, re.DOTALL)
        return m.group(1).strip() if m else None

    @staticmethod
    def _determine_location(name: str, venue: str | None) -> str:
        lower = name.lower()
        if "v rumunsku" in lower or " rumunsku" in lower:
            return "Rumunsko"
        if "gruzie" in lower or "gruzii" in lower:
            return "Gruzie"
        if "maroko" in lower:
            return "Maroko"
        if lower.startswith("bosna"):
            return _BOSNA_CERNA_HORA
        return _CHOTEC


class EnduroCampParser:
    @staticmethod
    def parse(html: str, agency: str = "Enduro Camp", url: str = "") -> list[Event]:
        events: list[Event] = []
        seen_dates: set[str] = set()

        for m in re.finditer(
            r'elementor-size-default">(\d{1,2})\.\s*[-–]\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})</div>',
            html,
        ):
            day = int(m.group(1))
            day_end = int(m.group(2))
            month_num = int(m.group(3))
            year = int(m.group(4))

            date_key = f"{day}.{month_num}.{year}"
            if date_key in seen_dates:
                continue
            seen_dates.add(date_key)

            after = html[m.end():m.end() + 3000]
            sold_out = "OBSAZENO" in after

            price_m = re.search(r'(\d+)\s*Kč', after)
            amount = int(price_m.group(1)) if price_m else 4000

            track = normalize_track_name(_KAVCAK_BENESOV)
            day_of_week = _compute_day_of_week(day, month_num, year)
            events.append(Event(
                agency=agency,
                track_name=track,
                date=f"{day}. {month_num}. {year}",
                url=url,
                year=year,
                month_num=month_num,
                month_end=month_num,
                day=day,
                day_end=day_end,
                day_of_week=day_of_week,
                prices=[{"day_label": "", "amount": float(amount), "currency": "CZK"}] if amount else [],
                sold_out=sold_out,
                note="Enduro Camp",
                category="enduro",
            ))

        events.sort(key=lambda e: (e.year or 0, e.month_num, e.day or 0))
        return events
