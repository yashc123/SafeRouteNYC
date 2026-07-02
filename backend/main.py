"""SafePath backend — FastAPI application entrypoint.

Endpoints: /health, /graph/stats (Phase 1), /segment/{id}/safety (Phase 3),
POST /route (Phase 4), GET /reachable (Phase 5). Phase 6 adds the tier-3 Redis
cache (see cache.py) and per-request timing.

Three-tier caching:
  Tier 1: per-segment safety weights precomputed in PostGIS (edge_safety).
  Tier 2: the weighted graph held in memory (routing.py) — loaded once below.
  Tier 3: Redis cache of full route/reachable results (cache.py).
"""

import os
from contextlib import asynccontextmanager
from time import perf_counter

import networkx as nx
import psycopg2
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import agent_available, run_agent
from cache import cache, reachable_key, route_key
from database import get_connection
from routing import DEFAULT_BUDGET_MIN, DEFAULT_SAFE_ALPHA, VALID_TIMES, router

# Validation bounds (named + tunable). Kept generous; snapping handles off-graph points.
ALPHA_MAX = 100.0
BUDGET_MIN_MAX = 120.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the in-memory weighted graph once at startup. If the tables aren't
    populated yet, log and continue — /route will report 503 until they are."""
    try:
        router.load()
        print(f"Routing graph loaded: {router.G.number_of_nodes():,} nodes, "
              f"{router.G.number_of_edges():,} edges.")
    except psycopg2.errors.UndefinedTable:
        print("Routing graph NOT loaded (road_edges/edge_safety missing). "
              "Run Phases 1-3, then restart.")
    print(f"Redis cache reachable: {cache.ping()}")
    yield


app = FastAPI(title="SafePath API", version="0.0.0", lifespan=lifespan)

# CORS origins come from env (comma-separated), defaulting to the Vite dev server.
_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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


class Coord(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class RouteRequest(BaseModel):
    origin: Coord
    destination: Coord
    # alpha applies to the "safe" route; the "fast" route is always alpha=0.
    alpha: float = Field(default=DEFAULT_SAFE_ALPHA, ge=0, le=ALPHA_MAX)
    time_of_day: str = "night"


def _require_ready():
    if not router.ready:
        raise HTTPException(
            status_code=503,
            detail="Routing graph not loaded. Ensure Phases 1-3 have run, then restart the API.",
        )


def _validate_time(time_of_day):
    tod = time_of_day.lower()
    if tod not in VALID_TIMES:
        raise HTTPException(status_code=422, detail=f"time_of_day must be one of {list(VALID_TIMES)}.")
    return tod


@app.post("/route")
def route(req: RouteRequest):
    """Compute BOTH a fast route (alpha=0, shortest) and a safe route
    (alpha=req.alpha, safety-weighted) between two lat/lng points, for the given
    time_of_day. Returns GeoJSON geometry, distance, walk time, and a 0-100 safety
    score per route. Results are cached in Redis (tier 3), keyed on the snapped
    node ids so nearby coordinates reuse one entry.
    """
    _require_ready()
    tod = _validate_time(req.time_of_day)
    t0 = perf_counter()

    origin = (req.origin.lat, req.origin.lng)
    destination = (req.destination.lat, req.destination.lng)

    # Key on snapped nodes: many nearby clicks/GPS points map to the same nodes.
    src = router.snap(*origin)
    dst = router.snap(*destination)
    key = route_key(src, dst, req.alpha, tod)

    cached = cache.get(key)
    if cached is not None:
        return {**cached, "cache": {"status": "hit", "server_ms": _ms(t0)}}

    try:
        routes = router.route_pair(origin, destination, req.alpha, tod)
    except nx.NetworkXNoPath:
        raise HTTPException(status_code=422, detail="No walking path between origin and destination.")

    payload = {"time_of_day": tod, "safe_alpha": req.alpha, **routes}
    cache.set(key, payload)
    return {**payload, "cache": {"status": "miss", "server_ms": _ms(t0)}}


@app.get("/reachable")
def reachable(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    time_of_day: str = "night",
    alpha: float = Query(default=DEFAULT_SAFE_ALPHA, ge=0, le=ALPHA_MAX),
    budget_min: float = Query(default=DEFAULT_BUDGET_MIN, gt=0, le=BUDGET_MIN_MAX),
):
    """Reachable-area (isochrone-like) polygon: everywhere reachable on foot from
    (lat, lng) within a `budget_min` walk-time budget under the safety-weighted
    cost model. Returns a GeoJSON polygon plus reachable-node count. Raising alpha
    or using a riskier time_of_day contracts the area. Cached in Redis (tier 3).
    """
    _require_ready()
    tod = _validate_time(time_of_day)
    t0 = perf_counter()

    src = router.snap(lat, lng)
    key = reachable_key(src, alpha, tod, budget_min)

    cached = cache.get(key)
    if cached is not None:
        return {**cached, "cache": {"status": "hit", "server_ms": _ms(t0)}}

    result = router.reachable_area((lat, lng), alpha, tod, budget_min)
    cache.set(key, result)
    return {**result, "cache": {"status": "miss", "server_ms": _ms(t0)}}


def _ms(t0):
    return round((perf_counter() - t0) * 1000, 2)


@app.get("/area-safety")
def area_safety(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    time_of_day: str = "night",
):
    """Explore mode: safety profile of the area around a tapped point. Snaps to the
    nearest segment, aggregates its k-hop neighborhood's precomputed scores, and
    returns an overall 0-100 area score plus component scores + footprint radius.
    Aggregated scores only — no individual incidents.
    """
    _require_ready()
    tod = _validate_time(time_of_day)
    return router.area_safety(lat, lng, tod)


class AgentRequest(BaseModel):
    message: str
    history: list | None = None


@app.post("/agent")
def agent(req: AgentRequest):
    """Natural-language agent: a single Claude tool-using agent that orchestrates
    the routing engine via tools. Returns the grounded text answer plus any
    structured route/area data it produced (so the frontend can draw it).
    """
    _require_ready()
    if not agent_available():
        raise HTTPException(
            status_code=503,
            detail="Agent unavailable: set ANTHROPIC_API_KEY in backend/.env and restart.",
        )
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty.")

    try:
        result = run_agent(req.message.strip(), req.history)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent error: {exc}")

    artifacts = result["artifacts"]
    return {
        "answer": result["answer"],
        "route": artifacts.get("route"),
        "area": artifacts.get("area"),
        "reachable": artifacts.get("reachable"),
        "history": result["history"],
    }
