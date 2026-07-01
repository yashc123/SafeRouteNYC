"""Phase 2 ETL: pull NYC crime, streetlight, and light-outage data into PostGIS.

Pipeline:
  1. Pull all THREE datasets CONCURRENTLY (asyncio.gather over async HTTP).
  2. Create crime_incidents / streetlights / light_outages tables + GiST indexes.
  3. Truncate-and-reload each table (idempotent, consistent with Phase 1).
  4. Report row counts, crime date range, Manhattan-bbox validation, and rough
     coverage vs the Phase 1 street graph.

Usage (run from anywhere; the DB from `docker compose up -d` must be running):
  python data/ingest_nyc_data.py                 # 3-year window, Manhattan
  python data/ingest_nyc_data.py --years 5       # widen the window
  python data/ingest_nyc_data.py --borough BROOKLYN

Config (DATABASE_URL, optional SOCRATA_APP_TOKEN) comes from backend/.env.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Make backend/ importable no matter where this script is launched from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from psycopg2.extras import execute_values

from database import get_connection
from nyc_data_source import DEFAULT_BOROUGH, DEFAULT_YEARS, MANHATTAN_BBOX, NYCDataSource

# --- Schema -----------------------------------------------------------------
# Three point tables, one per dataset. Each stores its domain attributes plus a
# PostGIS Point geometry (SRID 4326) built from lon/lat. GiST spatial indexes are
# added for the same reason as Phase 1: Phase 3 will run heavy spatial lookups
# (snapping each point to the nearest street segment), and without a spatial index
# every such lookup would scan the whole table.
DDL = """
CREATE TABLE IF NOT EXISTS crime_incidents (
    id            BIGSERIAL PRIMARY KEY,
    cmplnt_num    TEXT,
    occurred_at   TIMESTAMP,                    -- complaint date + time
    offense_desc  TEXT,                         -- ofns_desc (human-readable)
    law_category  TEXT,                         -- law_cat_cd: FELONY/MISDEMEANOR/VIOLATION
    lon           DOUBLE PRECISION NOT NULL,
    lat           DOUBLE PRECISION NOT NULL,
    geom          geometry(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS streetlights (
    id      BIGSERIAL PRIMARY KEY,
    osm_id  BIGINT,                             -- OpenStreetMap node id
    lon     DOUBLE PRECISION NOT NULL,
    lat     DOUBLE PRECISION NOT NULL,
    geom    geometry(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS light_outages (
    id          BIGSERIAL PRIMARY KEY,
    unique_key  TEXT,                           -- 311 service request id
    created_at  TIMESTAMP,                      -- when the report was filed
    status      TEXT,
    lon         DOUBLE PRECISION NOT NULL,
    lat         DOUBLE PRECISION NOT NULL,
    geom        geometry(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_crime_geom        ON crime_incidents USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_streetlights_geom ON streetlights     USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_light_outages_geom ON light_outages   USING GIST (geom);
"""

# Point geometry is built from lon/lat with ST_MakePoint (faster than parsing WKT).
# lon/lat are passed twice per row: once for the columns, once for the geometry.
_CRIME_TEMPLATE = "(%s, %s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))"
_LIGHT_TEMPLATE = "(%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))"
_OUTAGE_TEMPLATE = "(%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))"


def create_schema(cur):
    cur.execute(DDL)


def load_all(cur, crime, lights, outages):
    """Truncate all three tables and bulk-insert the freshly pulled points."""
    cur.execute("TRUNCATE crime_incidents, streetlights, light_outages RESTART IDENTITY;")

    execute_values(
        cur,
        "INSERT INTO crime_incidents "
        "(cmplnt_num, occurred_at, offense_desc, law_category, lon, lat, geom) VALUES %s",
        [
            (c["cmplnt_num"], c["occurred_at"], c["offense_desc"], c["law_category"],
             c["lon"], c["lat"], c["lon"], c["lat"])
            for c in crime
        ],
        template=_CRIME_TEMPLATE,
        page_size=5000,
    )

    execute_values(
        cur,
        "INSERT INTO streetlights (osm_id, lon, lat, geom) VALUES %s",
        [(s["osm_id"], s["lon"], s["lat"], s["lon"], s["lat"]) for s in lights],
        template=_LIGHT_TEMPLATE,
        page_size=5000,
    )

    execute_values(
        cur,
        "INSERT INTO light_outages (unique_key, created_at, status, lon, lat, geom) VALUES %s",
        [
            (o["unique_key"], o["created_at"], o["status"], o["lon"], o["lat"], o["lon"], o["lat"])
            for o in outages
        ],
        template=_OUTAGE_TEMPLATE,
        page_size=5000,
    )


def _count(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()[0]


def report(cur):
    """Print row counts, crime date range, bbox validation, and coverage."""
    min_lon, min_lat, max_lon, max_lat = MANHATTAN_BBOX

    n_crime = _count(cur, "SELECT count(*) FROM crime_incidents")
    n_lights = _count(cur, "SELECT count(*) FROM streetlights")
    n_outages = _count(cur, "SELECT count(*) FROM light_outages")

    print("\n===== PHASE 2 COVERAGE + SANITY REPORT =====")
    print(f"Row counts:  crime_incidents={n_crime:,}  streetlights={n_lights:,}  light_outages={n_outages:,}")

    cur.execute("SELECT min(occurred_at), max(occurred_at) FROM crime_incidents")
    dmin, dmax = cur.fetchone()
    print(f"Crime date range actually loaded: {dmin}  ->  {dmax}")

    # Bounding-box validation: how many points fall OUTSIDE Manhattan's bbox
    # (catches nulls-turned-zero, bad geocodes, cross-river outliers).
    bbox_where = "NOT (lon BETWEEN %s AND %s AND lat BETWEEN %s AND %s)"
    params = (min_lon, max_lon, min_lat, max_lat)
    print("Points outside Manhattan bbox (should be ~0):")
    for table in ("crime_incidents", "streetlights", "light_outages"):
        outliers = _count(cur, f"SELECT count(*) FROM {table} WHERE {bbox_where}", params)
        zeros = _count(cur, f"SELECT count(*) FROM {table} WHERE lon = 0 OR lat = 0")
        flag = "  <-- CHECK" if outliers else ""
        print(f"   {table}: {outliers} outliers, {zeros} at (0,0){flag}")

    # Rough coverage vs the Phase 1 street graph (nodes=intersections, edges=segments).
    try:
        n_nodes = _count(cur, "SELECT count(*) FROM road_nodes")
        n_edges = _count(cur, "SELECT count(*) FROM road_edges")
        print("Coverage vs street graph "
              f"({n_nodes:,} intersections / {n_edges:,} segments):")
        print(f"   crime per segment: {n_crime / n_edges:.2f}   "
              f"crime per intersection: {n_crime / n_nodes:.2f}")
        print(f"   streetlights per segment: {n_lights / n_edges:.3f}   "
              f"(~1 light per {n_edges / n_lights:.0f} segments)")
    except Exception:
        print("Coverage vs street graph: skipped (run Phase 1 ingestion first).")
    print("============================================\n")


async def _pull_all(source, years, borough):
    """Kick off all three source pulls at once and wait for all to finish."""
    return await asyncio.gather(
        source.get_crime_points(years=years, borough=borough),
        source.get_streetlights(),
        source.get_light_outages(years=years, borough=borough),
    )


def main():
    parser = argparse.ArgumentParser(description="Ingest NYC crime/light data into PostGIS.")
    parser.add_argument("--years", type=int, default=DEFAULT_YEARS,
                        help="Date window in years for crime and outages (default: 3).")
    parser.add_argument("--borough", default=DEFAULT_BOROUGH,
                        help="Borough filter for the Socrata datasets (default: MANHATTAN).")
    args = parser.parse_args()

    source = NYCDataSource()

    print(f"Pulling 3 datasets concurrently (years={args.years}, borough={args.borough})...")
    crime, lights, outages = asyncio.run(_pull_all(source, args.years, args.borough))
    print(f"Pulled: {len(crime):,} crime, {len(lights):,} streetlights, {len(outages):,} outages.")

    print("Loading into PostGIS...")
    with get_connection() as conn:
        with conn.cursor() as cur:
            create_schema(cur)
            load_all(cur, crime, lights, outages)
            conn.commit()
            report(cur)


if __name__ == "__main__":
    main()
