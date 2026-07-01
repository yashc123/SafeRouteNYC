"""Phase 3: spatial join + per-segment safety scoring (the precomputed weight store).

WHAT THIS DOES (offline, run once; Phase 4 routing reads the results fast):
  1. Project all geometries to a metric CRS (meters) with a GiST index.
  2. Spatially join each dataset onto street segments using the spatial index:
       - crime   -> nearest segment (KNN), counted per segment + per time bucket
       - outages -> nearest segment (KNN), counted per segment
       - lamps   -> all segments within LIGHTING_RADIUS_M (radius join), distance-weighted
  3. Normalize raw measures to 0-1 with PERCENTILE (empirical-CDF) normalization.
  4. Bucket crime by time of day (day / evening / night).
  5. Combine into a tunable per-segment safety weight, with a NEUTRAL lighting
     fallback so missing lighting data never makes a segment look unsafe.
  6. Persist everything into the edge_safety table (idempotent truncate-and-reload).
  7. Report real coverage: % of segments with crime / lighting / outage data.

Run (DB from `docker compose up -d` must be running; Phases 1-2 must be loaded):
  python data/compute_safety_scores.py
"""

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "backend"))

import pandas as pd
from psycopg2.extras import execute_values

from database import get_connection

# =====================================================================
# TUNABLE MODEL CONSTANTS  (edit these to retune the model — no magic
# numbers buried in the logic below)
# =====================================================================

# Lighting radius: a streetlamp within this many meters of a segment counts as
# lighting it. Chosen at 40 m because NYC lamp spacing is ~30 m (100 ft) and a
# lamp's useful illumination reaches ~15-30 m; 40 m captures lamps on the segment
# and immediately adjacent to it, while staying local enough that a lamp doesn't
# "leak" light onto unrelated blocks. It's also a pragmatic nudge up from 30 m
# given OSM's sparse lamp coverage (~1 per 20 segments) — see the coverage report.
LIGHTING_RADIUS_M = 40.0

# Crime proximity-spreading radius. Unlike the lamp radius (physical illumination),
# this corrects for NYPD's block-level coordinate TRUNCATION, which displaces an
# incident by roughly a Manhattan block. Each incident is spread across segments
# within this radius (distance-decay), with its weights normalized to sum to 1 so
# the citywide crime signal is REDISTRIBUTED, not inflated. 65 m ~= one block of
# positional uncertainty, wide enough to undo the truncation clustering without
# bleeding crime across unrelated neighborhoods.
CRIME_RADIUS_M = 65.0

# Safety-weight term coefficients (w1, w2, w3 in the model):
#   safety_weight = W_CRIME*incident_density - W_LIGHTING*lighting_score + W_OUTAGE*outage_signal
# Higher weight = LESS safe (higher routing cost later). Lighting SUBTRACTS.
# W_LIGHTING is set equal to W_CRIME on purpose (the ethical choice): good lighting
# can fully offset crime density, so raw crime counts never dominate the score.
W_CRIME = 1.0      # w1
W_LIGHTING = 1.0   # w2
W_OUTAGE = 0.5     # w3

# Neutral lighting fallback: segments with NO lamp within the radius get this
# score instead of 0. 0.5 == the median of a percentile-normalized distribution,
# i.e. "average lighting", NOT "dark". This guarantees missing lighting data can
# never increase a segment's danger.
NEUTRAL_LIGHTING_SCORE = 0.5

# Metric projection for meter-accurate distances (UTM zone 18N covers NYC).
METRIC_SRID = 32618

# Time-of-day buckets by hour-of-day (24h). Rationale: pedestrian safety concerns
# concentrate after dark, so we separate a long daytime baseline (06:00-17:59),
# a transitional evening (18:00-21:59), and night (22:00-05:59) when lighting
# matters most. Each bucket is normalized WITHIN itself, so "night density" is a
# segment's relative risk among segments at night (not swamped by daytime volume).
TIME_BUCKETS_SQL = """
    SUM(w) FILTER (WHERE EXTRACT(HOUR FROM occurred_at) BETWEEN 6 AND 17)  AS crime_weight_day,
    SUM(w) FILTER (WHERE EXTRACT(HOUR FROM occurred_at) BETWEEN 18 AND 21) AS crime_weight_evening,
    SUM(w) FILTER (WHERE EXTRACT(HOUR FROM occurred_at) >= 22
                      OR EXTRACT(HOUR FROM occurred_at) < 6)                AS crime_weight_night
"""

# =====================================================================


def ensure_projected_geometry(cur):
    """Add + populate a metric (meters) geometry column on every table, and a GiST
    index on the segments. Idempotent: only new/unprojected rows get transformed.
    """
    for table, subtype in [
        ("road_edges", "LineString"),
        ("crime_incidents", "Point"),
        ("streetlights", "Point"),
        ("light_outages", "Point"),
    ]:
        cur.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
            f"geom_m geometry({subtype}, {METRIC_SRID});"
        )
        cur.execute(
            f"UPDATE {table} SET geom_m = ST_Transform(geom, {METRIC_SRID}) "
            f"WHERE geom_m IS NULL;"
        )
    # The spatial index that makes the joins O(m*log n) instead of O(m*n).
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_road_edges_geom_m "
        "ON road_edges USING GIST (geom_m);"
    )
    cur.execute("ANALYZE road_edges;")  # fresh stats so the planner picks the index


def confirm_index_usage(cur):
    """Print the query plan for the crime proximity (radius) join, so we can SEE the
    spatial index (GiST on geom_m) is used rather than a brute-force scan.
    """
    cur.execute(
        """
        EXPLAIN
        SELECT c.id, e.id
        FROM crime_incidents c
        JOIN road_edges e
          ON ST_DWithin(e.geom_m, c.geom_m, %(radius)s)
        """,
        {"radius": CRIME_RADIUS_M},
    )
    print("Query plan for crime -> segments within radius (look for a GiST Index Scan):")
    for (line,) in cur.fetchall():
        print("   " + line)


def build_edge_aggregates(cur):
    """Run the spatial joins and return a per-segment aggregate DataFrame (one row
    per edge, including edges with no nearby data)."""
    # --- Crime: proximity spreading with per-incident conservation ------------
    # Step 1: every (incident, segment-within-CRIME_RADIUS_M) pair, with a linear
    # distance-decay raw weight (1 on the segment -> ~0 at the radius edge). The
    # weight is floored just above 0 so no incident can end up with a zero total.
    # Uses the GiST index on road_edges.geom_m (index-assisted, not brute force).
    cur.execute(
        """
        CREATE TEMP TABLE tmp_crime_seg ON COMMIT DROP AS
        SELECT c.id AS crime_id, e.id AS edge_id, c.occurred_at,
               GREATEST(1.0 - ST_Distance(e.geom_m, c.geom_m) / %(radius)s, 0.0001) AS w_raw
        FROM crime_incidents c
        JOIN road_edges e
          ON ST_DWithin(e.geom_m, c.geom_m, %(radius)s);
        """,
        {"radius": CRIME_RADIUS_M},
    )
    cur.execute("CREATE INDEX ON tmp_crime_seg (crime_id);")

    # Step 2: fallback — incidents with NO segment within the radius get attached
    # to their single nearest segment (raw weight 1), so nothing is dropped.
    cur.execute(
        """
        CREATE TEMP TABLE tmp_crime_fallback ON COMMIT DROP AS
        SELECT c.id AS crime_id, ne.edge_id, c.occurred_at, 1.0 AS w_raw
        FROM crime_incidents c
        LEFT JOIN (SELECT DISTINCT crime_id FROM tmp_crime_seg) hit
          ON hit.crime_id = c.id
        CROSS JOIN LATERAL (
            SELECT e.id AS edge_id
            FROM road_edges e
            ORDER BY e.geom_m <-> c.geom_m
            LIMIT 1
        ) ne
        WHERE hit.crime_id IS NULL;
        """
    )

    # Step 3: normalize each incident's weights to sum to 1 (redistribute, not
    # inflate). After this, SUM(w) over ALL rows == number of incidents, and each
    # incident's total contribution is exactly 1, split across its nearby segments.
    cur.execute(
        """
        CREATE TEMP TABLE tmp_crime_weighted ON COMMIT DROP AS
        SELECT crime_id, edge_id, occurred_at,
               w_raw / SUM(w_raw) OVER (PARTITION BY crime_id) AS w
        FROM (
            SELECT crime_id, edge_id, occurred_at, w_raw FROM tmp_crime_seg
            UNION ALL
            SELECT crime_id, edge_id, occurred_at, w_raw FROM tmp_crime_fallback
        ) u;
        """
    )

    # Outage reports assigned to their nearest segment.
    cur.execute(
        """
        CREATE TEMP TABLE tmp_outage_edge ON COMMIT DROP AS
        SELECT ne.edge_id
        FROM light_outages o
        CROSS JOIN LATERAL (
            SELECT e.id AS edge_id
            FROM road_edges e
            ORDER BY e.geom_m <-> o.geom_m
            LIMIT 1
        ) ne;
        """
    )

    # One LEFT JOIN per edge, so EVERY segment gets a row (0 where no nearby data).
    cur.execute(
        f"""
        SELECT
            e.id AS edge_id,
            COALESCE(cr.crime_weight, 0.0)         AS crime_weight,
            COALESCE(cr.crime_weight_day, 0.0)     AS crime_weight_day,
            COALESCE(cr.crime_weight_evening, 0.0) AS crime_weight_evening,
            COALESCE(cr.crime_weight_night, 0.0)   AS crime_weight_night,
            COALESCE(lg.lamp_count, 0)    AS lamp_count,
            COALESCE(lg.lamp_weight, 0.0) AS lamp_weight,
            COALESCE(ou.outage_count, 0)  AS outage_count
        FROM road_edges e
        LEFT JOIN (
            SELECT edge_id, SUM(w) AS crime_weight, {TIME_BUCKETS_SQL}
            FROM tmp_crime_weighted GROUP BY edge_id
        ) cr ON cr.edge_id = e.id
        LEFT JOIN (
            -- Radius join: lamps within LIGHTING_RADIUS_M of a segment, with a
            -- linear distance decay (1 on the segment -> 0 at the radius edge).
            SELECT e2.id AS edge_id,
                   count(*) AS lamp_count,
                   SUM(1.0 - ST_Distance(e2.geom_m, l.geom_m) / %(radius)s) AS lamp_weight
            FROM road_edges e2
            JOIN streetlights l
              ON ST_DWithin(e2.geom_m, l.geom_m, %(radius)s)
            GROUP BY e2.id
        ) lg ON lg.edge_id = e.id
        LEFT JOIN (
            SELECT edge_id, count(*) AS outage_count
            FROM tmp_outage_edge GROUP BY edge_id
        ) ou ON ou.edge_id = e.id;
        """,
        {"radius": LIGHTING_RADIUS_M},
    )
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def _percentile_among_present(series):
    """PERCENTILE (empirical-CDF) normalization, computed ONLY over segments that
    actually have the signal (value > 0); segments with none get 0.0.

    Why percentile at all: min-max would let a few extreme segments (e.g. Times
    Square) crush everyone else toward 0; percentile ranking is robust to those
    outliers and spreads scores evenly across the segments that do have data.

    Why "among present, zeros -> 0": ~90% of segments have zero crime. Ranking the
    zeros together with everything else would hand a no-crime segment a mid-range
    score. Instead, absence of a reported signal reads as ~0 danger, and only the
    segments that carry the signal are graded 0..1 relative to each other.
    """
    out = pd.Series(0.0, index=series.index)
    mask = series > 0
    if mask.any():
        out.loc[mask] = series.loc[mask].rank(pct=True)
    return out


def compute_scores(df):
    """Normalize raw measures, apply the neutral lighting fallback, and combine
    into per-time safety weights."""
    df["incident_density"]         = _percentile_among_present(df["crime_weight"])
    df["incident_density_day"]     = _percentile_among_present(df["crime_weight_day"])
    df["incident_density_evening"] = _percentile_among_present(df["crime_weight_evening"])
    df["incident_density_night"]   = _percentile_among_present(df["crime_weight_night"])
    df["outage_signal"]            = _percentile_among_present(df["outage_count"])

    # Lighting is the ETHICAL exception. Segments with no lamp in range are NOT
    # scored 0 (which would read as "dark" and inflate danger) — they get the
    # NEUTRAL fallback (0.5, "average lighting, unknown"). Only segments with a
    # lamp are percentile-graded. This guarantees missing lighting data can never
    # make a segment look less safe. has_lighting_data == NOT on the fallback.
    has_light = df["lamp_count"] > 0
    df["has_lighting_data"] = has_light
    df["lighting_score"] = NEUTRAL_LIGHTING_SCORE
    df.loc[has_light, "lighting_score"] = df.loc[has_light, "lamp_weight"].rank(pct=True)

    # Safety weight per time bucket (and overall). Higher = less safe.
    for bucket in ("day", "evening", "night"):
        df[f"safety_weight_{bucket}"] = (
            W_CRIME * df[f"incident_density_{bucket}"]
            - W_LIGHTING * df["lighting_score"]
            + W_OUTAGE * df["outage_signal"]
        )
    df["safety_weight_overall"] = (
        W_CRIME * df["incident_density"]
        - W_LIGHTING * df["lighting_score"]
        + W_OUTAGE * df["outage_signal"]
    )
    return df


EDGE_SAFETY_DDL = """
CREATE TABLE IF NOT EXISTS edge_safety (
    edge_id                  BIGINT PRIMARY KEY REFERENCES road_edges(id),
    crime_weight             DOUBLE PRECISION NOT NULL,
    crime_weight_day         DOUBLE PRECISION NOT NULL,
    crime_weight_evening     DOUBLE PRECISION NOT NULL,
    crime_weight_night       DOUBLE PRECISION NOT NULL,
    lamp_count               INTEGER NOT NULL,
    lamp_weight              DOUBLE PRECISION NOT NULL,
    outage_count             INTEGER NOT NULL,
    incident_density         DOUBLE PRECISION NOT NULL,
    incident_density_day     DOUBLE PRECISION NOT NULL,
    incident_density_evening DOUBLE PRECISION NOT NULL,
    incident_density_night   DOUBLE PRECISION NOT NULL,
    lighting_score           DOUBLE PRECISION NOT NULL,
    has_lighting_data        BOOLEAN NOT NULL,
    outage_signal            DOUBLE PRECISION NOT NULL,
    safety_weight_day        DOUBLE PRECISION NOT NULL,
    safety_weight_evening    DOUBLE PRECISION NOT NULL,
    safety_weight_night      DOUBLE PRECISION NOT NULL,
    safety_weight_overall    DOUBLE PRECISION NOT NULL
);
"""

_INSERT_COLUMNS = [
    "edge_id", "crime_weight", "crime_weight_day", "crime_weight_evening",
    "crime_weight_night", "lamp_count", "lamp_weight", "outage_count",
    "incident_density", "incident_density_day", "incident_density_evening",
    "incident_density_night", "lighting_score", "has_lighting_data", "outage_signal",
    "safety_weight_day", "safety_weight_evening", "safety_weight_night",
    "safety_weight_overall",
]


def persist(cur, df):
    """Idempotent rebuild of the precomputed weight store (drop + recreate so
    schema changes take effect; it's a pure derived cache)."""
    cur.execute("DROP TABLE IF EXISTS edge_safety;")
    cur.execute(EDGE_SAFETY_DDL)
    # Build tuples of NATIVE python types (Series.tolist() converts numpy scalars).
    columns = {c: df[c].tolist() for c in _INSERT_COLUMNS}
    rows = list(zip(*[columns[c] for c in _INSERT_COLUMNS]))
    execute_values(
        cur,
        f"INSERT INTO edge_safety ({', '.join(_INSERT_COLUMNS)}) VALUES %s",
        rows,
        page_size=5000,
    )


def report_coverage(df, n_incidents):
    n = len(df)
    pct_crime = (df["crime_weight"] > 0).mean() * 100
    pct_light = df["has_lighting_data"].mean() * 100
    pct_outage = (df["outage_count"] > 0).mean() * 100
    total_weight = df["crime_weight"].sum()

    print("\n===== PHASE 3 COVERAGE REPORT =====")
    print(f"Total segments scored: {n:,}")
    print(f"  % with crime signal (crime_weight > 0, {CRIME_RADIUS_M:.0f} m spread): {pct_crime:5.1f}%")
    print(f"  % with lighting data (>=1 lamp within {LIGHTING_RADIUS_M:.0f} m, "
          f"i.e. NOT on neutral fallback): {pct_light:5.1f}%")
    print(f"  % with outage signal (>=1 report):                   {pct_outage:5.1f}%")
    print(f"Segments on the neutral lighting fallback (0.5):       {100 - pct_light:5.1f}%")
    print("  --- crime conservation (redistributed, not inflated) ---")
    print(f"  SUM(crime_weight) = {total_weight:,.2f}   incidents = {n_incidents:,}   "
          f"diff = {total_weight - n_incidents:+.2f}")
    print("===================================\n")


def main():
    t0 = time.time()
    with get_connection() as conn:
        with conn.cursor() as cur:
            print("Projecting geometries to metric CRS + building spatial index...")
            ensure_projected_geometry(cur)

            confirm_index_usage(cur)

            print("\nRunning spatial joins (crime radius spread, outages KNN, lamps radius join)...")
            df = build_edge_aggregates(cur)
            print(f"Aggregated {len(df):,} segments.")

            df = compute_scores(df)

            print("Persisting scores into edge_safety...")
            persist(cur, df)
            conn.commit()

            cur.execute("SELECT count(*) FROM crime_incidents;")
            n_incidents = cur.fetchone()[0]

    report_coverage(df, n_incidents)
    print(f"Done in {time.time() - t0:.1f}s.")


if __name__ == "__main__":
    main()
