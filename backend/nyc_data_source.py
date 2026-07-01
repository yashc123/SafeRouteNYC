"""NYC concrete implementation of the CityDataSource interface.

Phase 1 implemented get_street_graph() (OSMnx, disk-cached).
Phase 2 implements the three data pulls:
  - get_crime_points()  -> NYPD Complaint Data (Historic) via NYC Open Data / Socrata
  - get_light_outages() -> 311 "Street Light Condition" requests via Socrata
  - get_streetlights()  -> OpenStreetMap street_lamp nodes via Overpass

All three are async so the ingestion script can pull them CONCURRENTLY (see
data/ingest_nyc_data.py). Concurrency is the win here: while one dataset's HTTP
response is in flight, the others' requests are also in flight, so total wall
time is roughly the slowest single dataset instead of the sum of all three.

Note: NYC has no streetlight-location dataset on the Socrata portal (only crime
and 311 are there), so streetlights come from OpenStreetMap's `highway=street_lamp`
nodes (decision made in Phase 2). That keeps all three pulls as async HTTP.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import osmnx as ox

from city_data_source import CityDataSource

# --- Phase 1: street-graph cache -------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = _REPO_ROOT / "data" / "cache"
GRAPH_CACHE_PATH = CACHE_DIR / "manhattan_walk.graphml"

ox.settings.cache_folder = str(CACHE_DIR / "osmnx")

MANHATTAN_PLACE = "Manhattan, New York, USA"
NETWORK_TYPE = "walk"

# --- Phase 2: data sources --------------------------------------------------
SOCRATA_DOMAIN = "https://data.cityofnewyork.us"
CRIME_DATASET = "qgea-i56i"        # NYPD Complaint Data Historic
SERVICE_311_DATASET = "erm2-nwe9"  # 311 Service Requests (2010-present)
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Rough Manhattan bounding box (min_lon, min_lat, max_lon, max_lat) used to sanity
# check that loaded points really land on the island.
MANHATTAN_BBOX = (-74.03, 40.68, -73.90, 40.88)

# Defaults are parameters, not hardcoded magic, so the window/borough are easy to
# change later (e.g. expand to 5 years or another borough).
DEFAULT_YEARS = 3
DEFAULT_BOROUGH = "MANHATTAN"

_SOCRATA_PAGE_SIZE = 50000  # Socrata's max rows per request; we page past it.
_USER_AGENT = "SafePath/0.1 (walking-safety routing; dev)"


def _window_start(years: int) -> str:
    """ISO timestamp for `years` ago, used as the Socrata date-filter lower bound."""
    return (datetime.now() - timedelta(days=365 * years)).strftime("%Y-%m-%dT00:00:00")


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_crime_datetime(date_str, time_str):
    """Combine NYPD's separate date + time fields into one timestamp.

    NYPD stores date (cmplnt_fr_dt, e.g. '2023-07-15T00:00:00.000') and time
    (cmplnt_fr_tm, e.g. '14:30:00') separately, and has a quirk where time can be
    '24:00:00'. We fall back to midnight when the time is missing or invalid.
    """
    if not date_str:
        return None
    day = date_str[:10]
    time_str = time_str or "00:00:00"
    for candidate in (f"{day} {time_str}", f"{day} 00:00:00"):
        try:
            return datetime.strptime(candidate, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def _fetch_socrata_all(client, dataset_id, select, where, app_token=None):
    """Fetch EVERY row matching a SoQL query, following Socrata's pagination.

    Socrata caps how many rows a single request returns, so we page with
    $limit/$offset. We $order by the stable internal ':id' so pages never overlap
    or skip rows as we walk the offset. We stop when a page comes back with fewer
    rows than the page size — that's the last page.
    """
    url = f"{SOCRATA_DOMAIN}/resource/{dataset_id}.json"
    headers = {"X-App-Token": app_token} if app_token else {}
    rows, offset = [], 0
    while True:
        params = {
            "$select": select,
            "$where": where,
            "$order": ":id",
            "$limit": _SOCRATA_PAGE_SIZE,
            "$offset": offset,
        }
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        page = resp.json()
        rows.extend(page)
        if len(page) < _SOCRATA_PAGE_SIZE:
            break
        offset += _SOCRATA_PAGE_SIZE
    return rows


class NYCDataSource(CityDataSource):
    """CityDataSource backed by NYC Open Data (Socrata) + OpenStreetMap."""

    def __init__(self, graph_cache_path: Path = GRAPH_CACHE_PATH):
        self.graph_cache_path = Path(graph_cache_path)
        # Optional Socrata app token for higher rate limits; works fine without one.
        self.app_token = os.getenv("SOCRATA_APP_TOKEN") or None

    def get_street_graph(self, refresh: bool = False):
        """Return Manhattan's walkable street network as an OSMnx MultiDiGraph.

        Loads from the on-disk GraphML cache when it exists; downloads fresh from
        OpenStreetMap (and rewrites the cache) when the file is missing or
        refresh=True. Nodes carry osmid + x/y coordinates; edges carry length
        (meters) and a LineString geometry.
        """
        if self.graph_cache_path.exists() and not refresh:
            return ox.load_graphml(self.graph_cache_path)

        graph = ox.graph_from_place(MANHATTAN_PLACE, network_type=NETWORK_TYPE)
        self.graph_cache_path.parent.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(graph, self.graph_cache_path)
        return graph

    async def get_crime_points(self, years: int = DEFAULT_YEARS, borough: str = DEFAULT_BOROUGH):
        """NYPD Complaint Data (Historic), filtered to `borough` and the last
        `years` years by complaint date, with valid coordinates.

        We use the HISTORIC dataset (qgea-i56i) rather than the "Year To Date"
        dataset, because YTD only covers the current calendar year and can't
        provide a multi-year window on its own. Each row is a single reported
        complaint; law_cat_cd is NYPD's broad category (FELONY / MISDEMEANOR /
        VIOLATION) and ofns_desc is the human-readable offense description.

        Returns dicts: cmplnt_num, occurred_at, offense_desc, law_category, lon, lat.
        """
        where = (
            f"boro_nm='{borough}' "
            f"AND cmplnt_fr_dt >= '{_window_start(years)}' "
            f"AND latitude IS NOT NULL AND longitude IS NOT NULL"
        )
        select = "cmplnt_num,cmplnt_fr_dt,cmplnt_fr_tm,ofns_desc,law_cat_cd,latitude,longitude"

        async with httpx.AsyncClient(timeout=180, headers={"User-Agent": _USER_AGENT}) as client:
            raw = await _fetch_socrata_all(client, CRIME_DATASET, select, where, self.app_token)

        points = []
        for r in raw:
            lon, lat = _to_float(r.get("longitude")), _to_float(r.get("latitude"))
            if lon is None or lat is None:
                continue  # drop rows with missing coordinates
            points.append(
                {
                    "cmplnt_num": r.get("cmplnt_num"),
                    "occurred_at": _parse_crime_datetime(r.get("cmplnt_fr_dt"), r.get("cmplnt_fr_tm")),
                    "offense_desc": r.get("ofns_desc"),
                    "law_category": r.get("law_cat_cd"),
                    "lon": lon,
                    "lat": lat,
                }
            )
        return points

    async def get_light_outages(self, years: int = DEFAULT_YEARS, borough: str = DEFAULT_BOROUGH):
        """311 Service Requests of complaint_type 'Street Light Condition' — i.e.
        residents reporting broken / out / flickering streetlights — filtered to
        `borough` and the last `years` years by created_date, with valid coords.

        Returns dicts: unique_key, created_at, status, lon, lat.
        """
        where = (
            f"complaint_type='Street Light Condition' "
            f"AND borough='{borough}' "
            f"AND created_date >= '{_window_start(years)}' "
            f"AND latitude IS NOT NULL AND longitude IS NOT NULL"
        )
        select = "unique_key,created_date,status,descriptor,latitude,longitude"

        async with httpx.AsyncClient(timeout=180, headers={"User-Agent": _USER_AGENT}) as client:
            raw = await _fetch_socrata_all(client, SERVICE_311_DATASET, select, where, self.app_token)

        points = []
        for r in raw:
            lon, lat = _to_float(r.get("longitude")), _to_float(r.get("latitude"))
            if lon is None or lat is None:
                continue
            points.append(
                {
                    "unique_key": r.get("unique_key"),
                    "created_at": _parse_iso(r.get("created_date")),
                    "status": r.get("status"),
                    "lon": lon,
                    "lat": lat,
                }
            )
        return points

    async def get_streetlights(self, area_name: str = "New York County"):
        """Streetlight locations as OpenStreetMap `highway=street_lamp` nodes
        inside the Manhattan administrative boundary (via the Overpass API).

        We query the boundary by the name "New York County" (which is coextensive
        with the borough of Manhattan) rather than "Manhattan": Overpass matches
        area names globally, and plain "Manhattan" also pulls in Manhattan, Kansas
        and Manhattan Beach, CA. "New York County" is globally unambiguous.

        NYC's Socrata portal has no streetlight-location dataset, so OSM is our
        source (Phase 2 decision). Coverage is good but not exhaustive vs NYC's
        full DOT inventory — see the coverage report after loading.

        Returns dicts: osm_id, lon, lat.
        """
        query = (
            "[out:json][timeout:180];"
            f'area["name"="{area_name}"]["boundary"="administrative"]->.a;'
            'node["highway"="street_lamp"](area.a);'
            "out;"
        )
        async with httpx.AsyncClient(timeout=300, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.post(OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            elements = resp.json().get("elements", [])

        return [
            {"osm_id": el["id"], "lon": el["lon"], "lat": el["lat"]}
            for el in elements
            if "lon" in el and "lat" in el
        ]
