# SafeRouteNYC

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?logo=react&logoColor=black)
![PostGIS](https://img.shields.io/badge/PostGIS-336791?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![AWS](https://img.shields.io/badge/AWS_EC2-FF9900?logo=amazonaws&logoColor=white)

**Live app: [saferoutenyc.com](http://saferoutenyc.com)**

SafeRouteNYC is a safety-aware pedestrian routing platform for Manhattan that computes walking routes optimized for safety rather than just distance, using real NYC open data. It combines a geospatial data pipeline, a safety-scoring model built from crime, lighting, and infrastructure data, graph-based pathfinding (A\* and Dijkstra), a three-tier caching layer, and a grounded natural-language agent served through a responsive map interface. Every safety score is derived from real data; the app never invents a value.

### Safety-optimized routing

The safe route (teal) diverges from the fastest route (gray), trading a little distance for a meaningfully higher safety score, with a transparent breakdown of why.

<img width="1360" height="896" alt="image" src="https://github.com/user-attachments/assets/622d1568-b48c-4b85-a4b7-a004dc44818a" />


### Explore mode — area safety lookup

Tap anywhere in Manhattan for a grounded safety assessment of that area : overall score, incident density, lighting, and an honest note on data coverage.

<img width="1153" height="912" alt="image" src="https://github.com/user-attachments/assets/419c6bf3-36d5-4a34-a57e-dc8a3da5cf27" />


---

## Features

**Safety-Optimized Routing** — Computes both a fastest route and a safety-weighted route between any two points in Manhattan, using an A\* search over a real street graph with a tunable cost function that blends distance against a data-derived safety penalty. A slider lets the user trade off speed vs. safety.

**Time-of-Day Awareness** — Safety scores are bucketed by time of day (day / evening / night), so routes and area assessments reflect that the same street carries different risk at 2pm versus 2am.

**Explore Mode (Area Safety Lookup)** — Tap anywhere in Manhattan to get a grounded safety assessment for that area : incident density, lighting, and an overall score without needing a full route.

**Reachability Analysis** — A Dijkstra-based reachability computation answers "how far can I safely get from here in N minutes," building a reachable-area polygon under a safety-weighted cost budget.

**Grounded Natural-Language Agent** — An "Ask SafeRouteNYC" box accepts plain-English requests ("safest way home to the East Village from Times Square at 1am"). A Claude-powered tool-using agent decomposes the request, calls the real routing/geocoding/area-safety functions, and explains the result, reporting only values the real engine computed, never inventing safety numbers.

**Transparent Scoring** — Every route surfaces a "why this route" breakdown (incident density, lighting coverage, time factor) so the safety score is explainable rather than a black box, including honest "limited data" notes where lighting coverage is sparse.

**Coverage-Aware UX** — Manhattan-only coverage is enforced at the point of interaction: out-of-bounds taps (rivers, other boroughs) get a friendly message rather than an error, using a snap-distance threshold against the street graph.

---

## Tech Stack

**Frontend:** React (Vite) + MapLibre GL JS for the interactive map, MapTiler for tiles and geocoding

**Backend:** Python + FastAPI

**Database:** PostgreSQL + PostGIS (geospatial queries and precomputed safety weights)

**Cache:** Redis (route/area result caching)

**Routing / Geospatial:** OSMnx + NetworkX (street graph, A\*, Dijkstra), SciPy cKDTree (spatial indexing)

**AI Agent:** Claude API (tool-using, function-calling agent)

**Deployment:** Docker + Docker Compose on AWS EC2, served behind an nginx reverse proxy

**Data Sources:** NYPD complaint data (Socrata), OpenStreetMap streetlamps (Overpass), NYC 311 streetlight-outage reports, OpenStreetMap street network

---

## How It Works (end-to-end)

The system is split into an **offline preprocessing** stage (expensive, run once) and an **online serving** stage (fast, per-request). This split is the core architectural idea: all the heavy spatial computation is done ahead of time and baked into the database and an in-memory graph, so live requests are just fast graph search over pre-weighted data.

**Offline (built once):**

1. **Street graph** — Manhattan's walkable network is pulled via OSMnx into a graph of ~36,000 nodes (intersections) and ~115,000 edges (street segments).
2. **Data ingestion** — ~340,000 NYPD crime incidents (a 3-year window), ~5,000 OpenStreetMap streetlamps, and ~14,600 NYC 311 outage reports are ingested from their respective APIs.
3. **Geospatial join + scoring** — Each incident and streetlamp is snapped to its nearest street segment using a cKDTree spatial index. Because NYPD truncates incident coordinates to block level, each incident's weight is spread across nearby segments within a fixed radius (distance-weighted and signal-conserving), which raises crime coverage from ~60% of segments to ~92%. Each segment gets a normalized incident-density and lighting score, bucketed by time of day, combined into a signed safety weight.
4. **Persistence** — All computed safety weights are stored back into PostGIS.

**Online (per request):**

1. The weighted graph is loaded into memory at startup (NetworkX).
2. A route request first checks Redis; on a miss, A\* runs over the in-memory weighted graph, computing both the fast and safety-weighted routes.
3. The result is cached to Redis (keyed on snapped node IDs, time of day, and the safety weighting) and returned as GeoJSON, which MapLibre draws on the map.

---

## System Architecture

### 1. Data & Scoring Layer (offline)

Raw open data becomes a safety model here. Three data sources are ingested asynchronously and joined against the street graph via a cKDTree spatial index (O(log n) nearest-segment lookups instead of brute force).

**The coordinate-truncation fix:** NYPD publishes incident coordinates truncated to block level, so a naive join leaves most segments with no data. Each incident's weight is spread across nearby segments within a 65m radius, distance-weighted and normalized so the total signal is conserved rather than inflated, raising crime coverage from ~9.6% to ~91.8% of segments while keeping the aggregate incident count exact.

**Lighting** uses the same proximity approach within a smaller radius, with a neutral fallback for segments lacking lamp data, so missing lighting is never misread as "dangerous."

### 2. Routing Layer (online)

**A\*** handles point-to-point routing, computing a fast route (pure shortest path) and a safe route (safety-weighted) with a tunable `alpha` blending distance against safety cost. Signed safety weights are mapped to a non-negative penalty to satisfy A\*'s requirement of non-negative edge costs.

**Dijkstra** handles reachability — no single target, so it explores outward under a time/cost budget and builds a reachable-area polygon.

Both run over the same in-memory weighted graph and the same scoring model.

### 3. Caching Layer (three tiers)

Each tier avoids a different kind of expensive recomputation:

- **Tier 1 — PostGIS:** precomputed safety weights, so the geospatial join is never redone at request time.
- **Tier 2 — In-memory graph:** the weighted graph is held in RAM, so A\* never round-trips to the database for edge weights during a search.
- **Tier 3 — Redis:** full route/area results are cached, keyed on snapped node IDs (so near-identical clicks share a cache entry). The cache is fail-safe, so if Redis is unavailable, the app degrades to direct computation rather than erroring.

Measured on the deployed server: a full cross-Manhattan route computes in **~357ms cold** and returns in **~72ms warm** from cache — roughly a **5× speedup** on repeat routes.

### 4. Agent Layer

A single Claude-powered tool-using agent wraps the existing functions (geocode, get_route, get_area_safety) as tools. It decomposes a natural-language request into a sequence of tool calls and explains the result. A strict grounding rulee is enforced in the system prompt and by only surfacing tool-returned data means the agent never generates safety values itself; it translates language and reports real computed numbers.

---

## Deployment

SafeRouteNYC runs as a single-instance Docker Compose deployment on an **AWS EC2** instance:

- An **nginx** container serves the built React frontend at `/` and reverse-proxies `/api/*` to the FastAPI backend — one origin, no CORS.
- The **backend**, **PostGIS**, and **Redis** run as internal containers, never exposed to the internet directly; only nginx publishes a port.
- The production database is populated on the server by running the ingestion + scoring pipeline once after the stack is up.
- A stable **Elastic IP** and the **saferoutenyc.com** domain point at the instance.

This single-instance approach matches the project's scale and is simpler and more reliable than full container orchestration, with a clear migration path to ECS if horizontal scaling were ever needed.

---

## Key Numbers

| Metric | Value |
|---|---|
| Street graph | ~36,000 nodes / ~115,000 edges |
| Crime incidents ingested | ~340,000 (3-year window) |
| Crime coverage after proximity-spreading | ~59.6% → ~91.8% of segments |
| Streetlamps / 311 outage reports | ~5,000 / ~14,600 |
| Cache speedup (long route) | ~5× (~357ms → ~72ms, measured on deployed server) |

---

## Limitations

- Coverage is Manhattan-only; the architecture supports additional boroughs via a `CityDataSource` interface, with in-memory graph RAM being the main scaling consideration.
- NYPD coordinates are block-level, so the safety model reflects area-level risk, not exact incident locations; the proximity-spreading approach is an honest response to this, not a claim of precise placement.

---

