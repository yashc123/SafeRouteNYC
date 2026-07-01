"""SafePath backend — FastAPI application entrypoint.

Phase 0: a single health-check endpoint plus CORS so the Vite frontend
(running on localhost) can call this API during development. Routing,
data, and city endpoints arrive in later phases.
"""

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import get_connection

app = FastAPI(title="SafePath API", version="0.0.0")

# Allow the local Vite dev server (and common localhost variants) to call the API.
# Tighten / parameterize this for production deployment later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Liveness probe. Returns a static payload so uptime checks (and later,
    load balancers / container orchestrators) can confirm the API is up."""
    return {"status": "ok"}


@app.get("/graph/stats")
def graph_stats():
    """Summary counts for the loaded street graph: number of nodes, number of
    edges, and total street length. Lets you confirm a real, complete graph is
    in the database.

    Note: this is a walkable network, so each physical street segment is stored
    as two directed edges (one per direction). total_length therefore roughly
    double-counts physical centerline distance — expected, not a bug.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM road_nodes;")
                node_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM road_edges;")
                edge_count = cur.fetchone()[0]
                cur.execute("SELECT COALESCE(SUM(length_m), 0) FROM road_edges;")
                total_meters = cur.fetchone()[0]
    except psycopg2.errors.UndefinedTable:
        raise HTTPException(
            status_code=503,
            detail="Street graph not loaded yet. Run data/ingest_street_graph.py first.",
        )

    total_km = total_meters / 1000.0
    return {
        "nodes": node_count,
        "edges": edge_count,
        "total_length_km": round(total_km, 2),
        "total_length_miles": round(total_km * 0.621371, 2),
    }
