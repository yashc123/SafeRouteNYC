"""Agent tools — thin wrappers over SafeRouteNYC's EXISTING engine functions.

No routing/scoring logic is reimplemented here. Each tool calls code we already
have (router.route_pair / router.area_safety / router.reachable_area, and a
MapTiler geocode). The tool results are the ONLY source of factual values the
agent is allowed to state — that's the grounding discipline.

For Claude we return COMPACT results (numbers only, no geometry) to save tokens;
the FULL result (with geometry, for the frontend to draw) is stashed in `artifacts`.
"""

import os
from pathlib import Path
from urllib.parse import quote

import httpx
import networkx as nx
from dotenv import load_dotenv

from routing import DEFAULT_BUDGET_MIN, DEFAULT_SAFE_ALPHA, VALID_TIMES, router

load_dotenv(Path(__file__).resolve().parent / ".env")

MAPTILER_KEY = os.getenv("MAPTILER_KEY")
_GEOCODE_BASE = "https://api.maptiler.com/geocoding"
# Same Manhattan bias as the frontend geocoder.
_GEOCODE_BBOX = "-74.03,40.698,-73.90,40.882"
_GEOCODE_PROXIMITY = "-73.97,40.78"


def geocode(place_name):
    """Resolve a place name/address to a coordinate, biased to Manhattan. Returns
    {place_name, lat, lng} or None if nothing matches."""
    if not MAPTILER_KEY or MAPTILER_KEY == "your-maptiler-api-key-here":
        raise RuntimeError("MAPTILER_KEY is not configured for the backend geocoder.")
    params = {
        "key": MAPTILER_KEY,
        "autocomplete": "false",
        "limit": "1",
        "country": "us",
        "bbox": _GEOCODE_BBOX,
        "proximity": _GEOCODE_PROXIMITY,
    }
    resp = httpx.get(f"{_GEOCODE_BASE}/{quote(place_name)}.json", params=params, timeout=15)
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if not features:
        return None
    top = features[0]
    return {"place_name": top.get("place_name"), "lat": top["center"][1], "lng": top["center"][0]}


def _compact_route(route):
    return {
        "distance_m": route["distance_m"],
        "duration_min": route["duration_min"],
        "safety_score": route["safety_score"],
        "num_segments": route["num_segments"],
        "components": route["components"],
    }


# --- Anthropic tool definitions (schemas) ----------------------------------
TOOLS = [
    {
        "name": "geocode",
        "description": (
            "Resolve a Manhattan/NYC place name or address to coordinates. Call this "
            "to turn a place the user named into lat/lng before routing or an area lookup."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"place_name": {"type": "string", "description": "e.g. 'Times Square'"}},
            "required": ["place_name"],
        },
    },
    {
        "name": "get_route",
        "description": (
            "Compute BOTH the safe and fast walking routes between two coordinates. "
            "Returns distance_m, duration_min, safety_score (0-100), and safety "
            "components for each route. Use for any A-to-B request."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "object",
                    "properties": {"lat": {"type": "number"}, "lng": {"type": "number"}},
                    "required": ["lat", "lng"],
                },
                "destination": {
                    "type": "object",
                    "properties": {"lat": {"type": "number"}, "lng": {"type": "number"}},
                    "required": ["lat", "lng"],
                },
                "alpha": {
                    "type": "number",
                    "description": "Safety weighting 0-10 for the safe route (higher = safer). Default 3.",
                },
                "time_of_day": {"type": "string", "enum": list(VALID_TIMES)},
            },
            "required": ["origin", "destination"],
        },
    },
    {
        "name": "get_area_safety",
        "description": (
            "Safety profile of the area around a coordinate: overall 0-100 score plus "
            "components (incident density, lighting, coverage). Use for 'how safe is around X'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "time_of_day": {"type": "string", "enum": list(VALID_TIMES)},
            },
            "required": ["lat", "lng"],
        },
    },
    {
        "name": "get_reachable",
        "description": (
            "Area reachable on foot from a point within a walk-time budget under safety "
            "weighting. Returns reachable node count + area size. Use for 'where can I "
            "safely walk in N minutes from X'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "alpha": {"type": "number", "description": "Safety weighting 0-10. Default 3."},
                "time_of_day": {"type": "string", "enum": list(VALID_TIMES)},
                "budget_min": {"type": "number", "description": "Walk-time budget in minutes. Default 15."},
            },
            "required": ["lat", "lng"],
        },
    },
]


def dispatch_tool(name, tool_input, artifacts):
    """Map a tool name to the REAL function and return a compact result for Claude.
    The full result (with geometry) is stashed in `artifacts` for the frontend.
    Errors are returned as {"error": ...} so the agent can respond helpfully."""
    try:
        if name == "geocode":
            result = geocode(tool_input["place_name"])
            if result is None:
                return {"error": f"No match found for '{tool_input['place_name']}' in the Manhattan area."}
            return result

        if name == "get_route":
            origin = tool_input["origin"]
            dest = tool_input["destination"]
            alpha = float(tool_input.get("alpha", DEFAULT_SAFE_ALPHA))
            tod = tool_input.get("time_of_day", "night")
            full = router.route_pair((origin["lat"], origin["lng"]), (dest["lat"], dest["lng"]), alpha, tod)
            artifacts["route"] = {"time_of_day": tod, "safe_alpha": alpha, **full}
            return {
                "time_of_day": tod,
                "safe_alpha": alpha,
                "fast": _compact_route(full["fast"]),
                "safe": _compact_route(full["safe"]),
            }

        if name == "get_area_safety":
            tod = tool_input.get("time_of_day", "night")
            result = router.area_safety(tool_input["lat"], tool_input["lng"], tod)
            artifacts["area"] = result
            return result  # already compact (no geometry)

        if name == "get_reachable":
            alpha = float(tool_input.get("alpha", DEFAULT_SAFE_ALPHA))
            tod = tool_input.get("time_of_day", "night")
            budget = float(tool_input.get("budget_min", DEFAULT_BUDGET_MIN))
            full = router.reachable_area((tool_input["lat"], tool_input["lng"]), alpha, tod, budget)
            artifacts["reachable"] = full
            return {
                "time_of_day": tod,
                "alpha": alpha,
                "budget_min": budget,
                "reachable_node_count": full["reachable_node_count"],
                "area_m2": full["area_m2"],
            }

        return {"error": f"Unknown tool '{name}'."}

    except nx.NetworkXNoPath:
        return {"error": "No walking route was found between those points."}
    except Exception as exc:  # keep the agent alive on any tool failure
        return {"error": f"Tool '{name}' failed: {exc}"}
