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


@app.get("/segment/{edge_id}/safety")
def segment_safety(edge_id: int):
    """Inspect one street segment's Phase 3 safety data: raw counts, normalized
    0-1 scores, time-of-day incident densities, and the final safety weights.
    (Verification aid for Phase 3 — not the real UI.)
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.u, e.v, e.length_m,
                           s.crime_weight, s.crime_weight_day, s.crime_weight_evening,
                           s.crime_weight_night,
                           s.lamp_count, s.lamp_weight, s.outage_count,
                           s.incident_density, s.incident_density_day,
                           s.incident_density_evening, s.incident_density_night,
                           s.lighting_score, s.has_lighting_data, s.outage_signal,
                           s.safety_weight_day, s.safety_weight_evening,
                           s.safety_weight_night, s.safety_weight_overall
                    FROM road_edges e
                    JOIN edge_safety s ON s.edge_id = e.id
                    WHERE e.id = %s
                    """,
                    (edge_id,),
                )
                row = cur.fetchone()
    except psycopg2.errors.UndefinedTable:
        raise HTTPException(
            status_code=503,
            detail="Safety scores not computed yet. Run data/compute_safety_scores.py first.",
        )

    if row is None:
        raise HTTPException(status_code=404, detail=f"No scored segment with edge_id={edge_id}.")

    (u, v, length_m, crime_weight, crime_weight_day, crime_weight_evening,
     crime_weight_night, lamp_count, lamp_weight, outage_count, incident_density,
     incident_density_day, incident_density_evening, incident_density_night,
     lighting_score, has_lighting_data, outage_signal,
     sw_day, sw_evening, sw_night, sw_overall) = row

    def r(x, n=4):
        return round(x, n) if x is not None else None

    return {
        "edge_id": edge_id,
        "u": u,
        "v": v,
        "length_m": r(length_m, 2),
        "raw_counts": {
            # crime_weight is a fractional, distance-spread signal (each incident
            # contributes a total of 1 across nearby segments), not an integer count.
            "crime_weight": r(crime_weight, 3),
            "crime_weight_by_time": {
                "day": r(crime_weight_day, 3),
                "evening": r(crime_weight_evening, 3),
                "night": r(crime_weight_night, 3),
            },
            "lamp_count": lamp_count,
            "lamp_weight": r(lamp_weight),
            "outage_count": outage_count,
        },
        "normalized_scores": {
            "incident_density": r(incident_density),
            "lighting_score": r(lighting_score),
            "has_lighting_data": has_lighting_data,
            "on_neutral_lighting_fallback": not has_lighting_data,
            "outage_signal": r(outage_signal),
        },
        "incident_density_by_time": {
            "day": r(incident_density_day),
            "evening": r(incident_density_evening),
            "night": r(incident_density_night),
        },
        "safety_weight_by_time": {
            "day": r(sw_day),
            "evening": r(sw_evening),
            "night": r(sw_night),
            "overall": r(sw_overall),
        },
    }
