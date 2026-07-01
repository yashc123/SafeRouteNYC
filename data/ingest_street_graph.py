"""Phase 1 ETL: load Manhattan's walkable street graph into PostGIS.

Pipeline:
  1. Obtain the OSMnx street graph via NYCDataSource (download + disk cache).
  2. Create the road_nodes / road_edges tables and spatial indexes if absent.
  3. Truncate and reload both tables from the graph (idempotent — see below).

Usage (run from anywhere; paths are resolved absolutely):
  python data/ingest_street_graph.py            # use cached graph if present
  python data/ingest_street_graph.py --refresh  # force re-download from OSM

Idempotency: we TRUNCATE both tables before every load and re-insert the full
graph. Re-running therefore never creates duplicates and always leaves the tables
matching the current graph exactly. The graph is small enough (tens of thousands
of rows) that a full reload is simpler and safer than diffing/upserting.

Requires the PostGIS database (docker compose up -d) to be running.
"""

import argparse
import sys
from pathlib import Path

# Make backend/ importable no matter where this script is launched from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "backend"))

import osmnx as ox
from psycopg2.extras import execute_values

from database import get_connection
from nyc_data_source import NYCDataSource

# --- Schema -----------------------------------------------------------------
# Geometries use SRID 4326 (WGS84 lon/lat), which is OSMnx's default CRS.
#
# road_nodes: one row per intersection. osmid is OSM's global id (natural PK);
#   x/y are lon/lat, and geom is the same coordinate as a PostGIS Point so we can
#   run spatial queries (e.g. "nearest intersection to this click") later.
#
# road_edges: one row per directed street segment. u/v are the source/target
#   node ids; a MultiDiGraph can have parallel edges between the same nodes, so
#   `key` disambiguates them and `id` is a simple surrogate PK. length_m is the
#   real along-the-curve length in meters; geom is the street's LineString shape.
DDL = """
CREATE TABLE IF NOT EXISTS road_nodes (
    osmid  BIGINT PRIMARY KEY,
    x      DOUBLE PRECISION NOT NULL,          -- longitude
    y      DOUBLE PRECISION NOT NULL,          -- latitude
    geom   geometry(Point, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS road_edges (
    id        BIGSERIAL PRIMARY KEY,
    u         BIGINT NOT NULL REFERENCES road_nodes(osmid),   -- source node
    v         BIGINT NOT NULL REFERENCES road_nodes(osmid),   -- target node
    key       INTEGER NOT NULL DEFAULT 0,                     -- parallel-edge disambiguator
    length_m  DOUBLE PRECISION NOT NULL,                      -- segment length, meters
    geom      geometry(LineString, 4326) NOT NULL
);

-- Spatial (GiST) indexes on the geometry columns. Without them, any spatial
-- query (nearest node, edges within a bounding box / polygon) scans every row.
-- The GiST index stores each geometry's bounding box in a tree so PostGIS can
-- prune to a handful of candidates first. Later phases lean on this constantly
-- (snapping GPS points to the nearest intersection, spatially joining crime and
-- lighting data onto edges), so we build the indexes now.
CREATE INDEX IF NOT EXISTS idx_road_nodes_geom ON road_nodes USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_road_edges_geom ON road_edges USING GIST (geom);
"""


def create_schema(cur):
    cur.execute(DDL)


def load_graph(cur, graph):
    """Truncate both tables and bulk-insert every node and edge from `graph`."""
    nodes_gdf, edges_gdf = ox.graph_to_gdfs(graph, nodes=True, edges=True)

    # Reset to empty first so a re-run reflects the graph exactly (no duplicates).
    # Listing both tables lets TRUNCATE ignore the edges->nodes foreign key.
    cur.execute("TRUNCATE road_edges, road_nodes RESTART IDENTITY;")

    # Nodes: index is the osmid; columns include x, y, and a Point geometry.
    node_rows = [
        (int(osmid), float(row["x"]), float(row["y"]), row["geometry"].wkt)
        for osmid, row in nodes_gdf.iterrows()
    ]
    execute_values(
        cur,
        "INSERT INTO road_nodes (osmid, x, y, geom) VALUES %s",
        node_rows,
        template="(%s, %s, %s, ST_GeomFromText(%s, 4326))",
    )

    # Edges: index is the (u, v, key) tuple. graph_to_gdfs guarantees every edge
    # has a geometry (it builds a straight LineString from the endpoints when the
    # OSM way had no explicit shape), so geom is never null.
    edge_rows = [
        (int(u), int(v), int(k), float(row["length"]), row["geometry"].wkt)
        for (u, v, k), row in edges_gdf.iterrows()
    ]
    execute_values(
        cur,
        "INSERT INTO road_edges (u, v, key, length_m, geom) VALUES %s",
        edge_rows,
        template="(%s, %s, %s, %s, ST_GeomFromText(%s, 4326))",
    )

    return len(node_rows), len(edge_rows)


def main():
    parser = argparse.ArgumentParser(description="Load Manhattan street graph into PostGIS.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force a fresh download from OpenStreetMap instead of using the cache.",
    )
    args = parser.parse_args()

    source = NYCDataSource()

    print("Obtaining street graph (this downloads from OSM only if not cached)...")
    graph = source.get_street_graph(refresh=args.refresh)
    print(f"Graph in memory: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges.")

    print("Loading into PostGIS...")
    with get_connection() as conn:
        with conn.cursor() as cur:
            create_schema(cur)
            n_nodes, n_edges = load_graph(cur, graph)
        conn.commit()

    print(f"Done. Inserted {n_nodes} nodes and {n_edges} edges into PostGIS.")


if __name__ == "__main__":
    main()
