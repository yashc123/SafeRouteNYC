"""SafePath routing engine (Phase 4).

Turns the per-segment safety weights (edge_safety) into actual walking routes.

Design:
  - The weighted street graph is loaded into memory (NetworkX DiGraph) ONCE at
    startup. The A* search never touches the database.
  - Edge cost blends physical distance with a NON-NEGATIVE safety penalty derived
    from the signed safety_weight, tunable by `alpha` and aware of time-of-day.
  - A* uses an admissible great-circle heuristic, so routes are provably optimal.

Cost model
----------
    penalty[time]  = max(0, safety_weight[time] - SAFETY_SHIFT)   # ReLU -> >= 0
    edge_cost      = length_m * (1 + alpha * penalty[time])       # >= length_m > 0

Signed safety_weight (~ -1.0 .. +1.5) is mapped to a non-negative penalty by
clamping at SAFETY_SHIFT: segments at/below the shift (the safe majority) add zero
cost; riskier segments add cost proportional to how far above the shift they are.
Non-negativity is what keeps A*/Dijkstra valid (no cost-reducing edges, no negative
cycles). At alpha=0 the cost is exactly length_m, so A* returns the true shortest path.
"""

import json
import math

import networkx as nx
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely import concave_hull
from shapely.geometry import MultiPoint, mapping
from shapely.ops import transform as shapely_transform

from database import get_connection

# ---- Tunable routing constants --------------------------------------------
# Preferred pedestrian walking speed (~5.0 km/h) for time estimates.
WALKING_SPEED_MPS = 1.4

# Default alpha for the "safe" route (the "fast" route is always alpha=0).
# Higher alpha => willing to walk further to avoid higher-penalty segments.
DEFAULT_SAFE_ALPHA = 3.0

# Where the signed safety_weight is clamped to 0. 0.0 means "neutral-risk and
# safer segments add no cost; only above-neutral risk is penalized".
SAFETY_SHIFT = 0.0

# Reference penalty used to map a route's length-weighted average penalty onto a
# 0-100 safety score. ~1.5 is the approximate max per-segment penalty, so a route
# entirely on worst-case segments scores ~0 and an all-safe route scores 100.
SAFETY_SCORE_PENALTY_REF = 1.5

# Metric CRS (UTM 18N, meters) for accurate nearest-node snapping.
ROUTING_SRID = 32618

VALID_TIMES = ("day", "evening", "night")

# ---- Reachability (Phase 5) constants -------------------------------------
# Default walk-time budget in minutes for the reachable-area query.
DEFAULT_BUDGET_MIN = 15.0

# Explore mode: how many graph hops around the tapped point define its "area".
# 2 hops ≈ the tapped block plus the immediately adjacent blocks.
AREA_KRING = 2

# Concave-hull tightness for turning reached nodes into a region. shapely's ratio
# is in [0, 1]: 1 == convex hull (simple but overstates reach, bridging across
# unreachable pockets); lower == more concave, hugging the true reachable extent.
# 0.4 hugs the shape without producing ragged slivers.
CONCAVE_HULL_RATIO = 0.4


def _haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Router:
    """Holds the in-memory weighted graph + a KD-tree for snapping."""

    def __init__(self):
        self.G = None
        self.coords = {}       # osmid -> (lon, lat)
        self.node_ids = []     # index-aligned with the KD-tree
        self._tree = None
        self._proj = None
        self.ready = False

    # -- startup load --------------------------------------------------------
    def load(self):
        """Build the weighted DiGraph and the snapping KD-tree from PostGIS. Called
        once at startup; raises if Phases 1-3 haven't populated the tables."""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT osmid, x, y FROM road_nodes;")
                node_rows = cur.fetchall()
                cur.execute(
                    """
                    SELECT e.id, e.u, e.v, e.length_m,
                           s.safety_weight_day, s.safety_weight_evening, s.safety_weight_night,
                           s.incident_density_day, s.incident_density_evening,
                           s.incident_density_night, s.lighting_score, s.has_lighting_data,
                           ST_AsGeoJSON(e.geom)
                    FROM road_edges e
                    JOIN edge_safety s ON s.edge_id = e.id;
                    """
                )
                edge_rows = cur.fetchall()

        graph = nx.DiGraph()
        coords = {}
        for osmid, x, y in node_rows:
            coords[osmid] = (x, y)
            graph.add_node(osmid, x=x, y=y)

        for (edge_id, u, v, length, sw_day, sw_eve, sw_night, iden_day, iden_eve,
             iden_night, lighting_score, has_lighting, geojson) in edge_rows:
            # Collapse rare parallel edges to the shorter one.
            if graph.has_edge(u, v) and graph[u][v]["length"] <= length:
                continue
            line = json.loads(geojson)["coordinates"]  # [[lon, lat], ...]
            graph.add_edge(
                u, v,
                edge_id=edge_id,
                length=length,
                pen_day=max(0.0, sw_day - SAFETY_SHIFT),
                pen_evening=max(0.0, sw_eve - SAFETY_SHIFT),
                pen_night=max(0.0, sw_night - SAFETY_SHIFT),
                # Component scores (for the safety breakdown + per-segment detail).
                iden_day=iden_day,
                iden_evening=iden_eve,
                iden_night=iden_night,
                lighting_score=lighting_score,
                has_lighting_data=has_lighting,
                coords=line,
            )

        self.G = graph
        self.coords = coords
        self.node_ids = list(coords.keys())

        # KD-tree in projected meters for correct nearest-node snapping.
        self._proj = Transformer.from_crs(4326, ROUTING_SRID, always_xy=True)
        lons = [coords[n][0] for n in self.node_ids]
        lats = [coords[n][1] for n in self.node_ids]
        xs, ys = self._proj.transform(lons, lats)
        self._tree = cKDTree(np.column_stack([xs, ys]))
        self.ready = True

    # -- snapping ------------------------------------------------------------
    def snap(self, lat, lng):
        """Snap an arbitrary lat/lng to the nearest graph node (O(log n) via KD-tree)."""
        x, y = self._proj.transform(lng, lat)
        _, idx = self._tree.query([x, y])
        return self.node_ids[idx]

    # -- A* heuristic --------------------------------------------------------
    def _heuristic(self, u, target):
        """Admissible heuristic: straight-line meters from u to the target. Never
        overestimates remaining cost (straight line <= path length <= path cost)."""
        lon1, lat1 = self.coords[u]
        lon2, lat2 = self.coords[target]
        return _haversine_m(lat1, lon1, lat2, lon2)

    # -- shared cost model ---------------------------------------------------
    def _edge_cost_fn(self, alpha, time_of_day):
        """The Phase 4 cost model as a NetworkX weight function:
            edge_cost = length_m * (1 + alpha * penalty[time]).
        Shared by A* routing AND Dijkstra reachability so both respect exactly the
        same safety-weighted, time-of-day-aware costs."""
        pen_key = f"pen_{time_of_day}"

        def weight(u, v, data):
            return data["length"] * (1.0 + alpha * data[pen_key])

        return weight

    # -- single route --------------------------------------------------------
    def route(self, origin, dest, alpha, time_of_day):
        """Compute one route. origin/dest are (lat, lng). Returns a dict with
        geometry, distance, walk time, and a 0-100 safety score."""
        src = self.snap(*origin)
        dst = self.snap(*dest)
        pen_key = f"pen_{time_of_day}"
        iden_key = f"iden_{time_of_day}"  # time-of-day incident density
        weight = self._edge_cost_fn(alpha, time_of_day)

        path = nx.astar_path(self.G, src, dst, heuristic=self._heuristic, weight=weight)

        total_len = 0.0
        weighted_pen = 0.0
        weighted_iden = 0.0     # for the route-level incident-density aggregate
        weighted_light = 0.0    # for the route-level lighting aggregate
        lit_len = 0.0           # route length that has real lighting data (not fallback)
        geometry = []
        segments = []
        for a, b in zip(path[:-1], path[1:]):
            data = self.G[a][b]
            length = data["length"]
            total_len += length
            weighted_pen += length * data[pen_key]
            weighted_iden += length * data[iden_key]
            weighted_light += length * data["lighting_score"]
            if data["has_lighting_data"]:
                lit_len += length

            seg = data["coords"]
            if geometry and seg and geometry[-1] == seg[0]:
                geometry.extend(seg[1:])  # avoid duplicating the shared junction
            else:
                geometry.extend(seg)

            # Per-segment record with EMBEDDED scores so the frontend needs no extra
            # request to show a clicked segment's breakdown. incident_density is the
            # time-of-day density matching this route's time_of_day.
            segments.append({
                "edge_id": data["edge_id"],
                "incident_density": round(data[iden_key], 4),
                "lighting_score": round(data["lighting_score"], 4),
                "has_lighting_data": bool(data["has_lighting_data"]),
                "geometry": {"type": "LineString", "coordinates": seg},
            })

        # Length-weighted aggregates (safe against a zero-length degenerate route).
        denom = total_len if total_len > 0 else 1.0
        avg_pen = weighted_pen / denom
        safety_score = 100.0 * (1.0 - min(avg_pen / SAFETY_SCORE_PENALTY_REF, 1.0))
        duration_min = (total_len / WALKING_SPEED_MPS) / 60.0

        return {
            "alpha": alpha,
            "distance_m": round(total_len, 1),
            "duration_min": round(duration_min, 1),
            "safety_score": round(safety_score, 1),
            "avg_penalty": round(avg_pen, 4),
            "num_segments": len(path) - 1,
            # Route-level component aggregates driving the safety score.
            "components": {
                "incident_density": round(weighted_iden / denom, 4),
                "lighting_score": round(weighted_light / denom, 4),
                "lighting_coverage": round(lit_len / denom, 4),
                "time_of_day": time_of_day,
            },
            "segments": segments,
            "snapped_origin": {"lat": self.coords[src][1], "lng": self.coords[src][0]},
            "snapped_destination": {"lat": self.coords[dst][1], "lng": self.coords[dst][0]},
            "geometry": {"type": "LineString", "coordinates": geometry},
        }

    # -- fast + safe pair ----------------------------------------------------
    def route_pair(self, origin, dest, safe_alpha, time_of_day):
        """Compute both the fast (alpha=0) and safe (alpha=safe_alpha) routes."""
        return {
            "fast": self.route(origin, dest, 0.0, time_of_day),
            "safe": self.route(origin, dest, safe_alpha, time_of_day),
        }

    # -- area safety (Explore mode) ------------------------------------------
    def area_safety(self, lat, lng, time_of_day):
        """Safety profile of the AREA around a tapped point.

        Snaps to the nearest node, takes its k-hop neighborhood (the tapped block
        plus adjacent blocks), and length-weighted-averages the same precomputed
        per-segment scores routing uses. Returns an overall 0-100 area score, the
        component scores, and a footprint radius (meters) for the frontend to shade.
        Aggregated scores only — never individual incidents.
        """
        node = self.snap(lat, lng)
        pen_key = f"pen_{time_of_day}"
        iden_key = f"iden_{time_of_day}"

        ring = nx.ego_graph(self.G, node, radius=AREA_KRING, undirected=True)
        edges = list(ring.edges(data=True))
        if not edges:  # isolated snap — fall back to the node's own incident edges
            edges = list(self.G.out_edges(node, data=True)) + list(self.G.in_edges(node, data=True))

        total_len = weighted_pen = weighted_iden = weighted_light = lit_len = 0.0
        for _a, _b, data in edges:
            length = data["length"]
            total_len += length
            weighted_pen += length * data[pen_key]
            weighted_iden += length * data[iden_key]
            weighted_light += length * data["lighting_score"]
            if data["has_lighting_data"]:
                lit_len += length

        denom = total_len if total_len > 0 else 1.0
        avg_pen = weighted_pen / denom
        area_score = 100.0 * (1.0 - min(avg_pen / SAFETY_SCORE_PENALTY_REF, 1.0))

        # Footprint radius = farthest ring node from the snapped center (min 60 m
        # so a tap always shades a visible area).
        clng, clat = self.coords[node]
        radius_m = 60.0
        for n in ring.nodes:
            nlng, nlat = self.coords[n]
            radius_m = max(radius_m, _haversine_m(clat, clng, nlat, nlng))

        return {
            "snapped": {"lat": clat, "lng": clng},
            "radius_m": round(radius_m, 1),
            "time_of_day": time_of_day,
            "area_safety_score": round(area_score, 1),
            "segment_count": len(edges),
            "components": {
                "incident_density": round(weighted_iden / denom, 4),
                "lighting_score": round(weighted_light / denom, 4),
                "lighting_coverage": round(lit_len / denom, 4),
                "time_of_day": time_of_day,
            },
        }

    # -- reachability (Dijkstra outward from origin) -------------------------
    def reachable_area(self, origin, alpha, time_of_day, budget_min):
        """"Where can I safely get from here within a walk-time budget?"

        Single-source Dijkstra over the SAME cost model as routing, capped by a
        cutoff. No target — we grow outward in all directions until the budget is
        spent (that's why this is Dijkstra, not A*: there's nothing to aim a
        heuristic at). Higher alpha and riskier (e.g. night) segments cost more,
        so the reachable region contracts.
        """
        src = self.snap(*origin)
        # Time budget -> cost budget in the model's units (safety-weighted meters).
        budget_cost = budget_min * 60.0 * WALKING_SPEED_MPS
        weight = self._edge_cost_fn(alpha, time_of_day)

        # {node: cumulative cost}; cutoff prunes anything beyond the budget.
        costs = nx.single_source_dijkstra_path_length(
            self.G, src, cutoff=budget_cost, weight=weight
        )
        reached_pts = [self.coords[n] for n in costs]  # (lon, lat)

        hull = self._reachable_hull(reached_pts)
        area_m2 = self._polygon_area_m2(hull) if hull is not None else 0.0

        return {
            "origin_node": src,
            "snapped_origin": {"lat": self.coords[src][1], "lng": self.coords[src][0]},
            "alpha": alpha,
            "time_of_day": time_of_day,
            "budget_min": budget_min,
            "budget_cost_m": round(budget_cost, 1),
            "reachable_node_count": len(costs),
            "area_m2": round(area_m2, 1),
            "geometry": mapping(hull) if hull is not None else None,
        }

    def _reachable_hull(self, points):
        """Concave hull (alpha shape) around the reached nodes. Concave hugs the
        true reachable extent; a convex hull would bridge across unreachable
        pockets and overstate reach. Falls back to convex hull for tiny sets."""
        if len(points) < 3:
            return MultiPoint(points).convex_hull if points else None
        multipoint = MultiPoint(points)
        return concave_hull(multipoint, ratio=CONCAVE_HULL_RATIO)

    def _polygon_area_m2(self, geom):
        """Area in square meters (project lon/lat -> UTM before measuring)."""
        projected = shapely_transform(self._proj.transform, geom)
        return projected.area


# Module-level singleton loaded at app startup.
router = Router()
