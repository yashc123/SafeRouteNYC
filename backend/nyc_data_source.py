"""NYC concrete implementation of the CityDataSource interface.

Phase 1 implements only get_street_graph(); it downloads Manhattan's walkable
street network via OSMnx and caches it to disk so we never re-download on every
run. The other three data sources (crime, streetlights, light outages) arrive in
later phases and currently raise NotImplementedError.

This is the first real use of the CityDataSource extensibility seam defined in
Phase 0: the rest of the app depends on the interface, not on OSMnx directly.
"""

from pathlib import Path

import osmnx as ox

from city_data_source import CityDataSource

# Cache lives under <repo_root>/data/cache/ (gitignored — the graph file is large
# and re-downloadable). We also point OSMnx's own HTTP response cache here so all
# downloaded artifacts sit in one ignored place.
_REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = _REPO_ROOT / "data" / "cache"
GRAPH_CACHE_PATH = CACHE_DIR / "manhattan_walk.graphml"

ox.settings.cache_folder = str(CACHE_DIR / "osmnx")

# Geocodes to the Manhattan borough polygon; "walk" builds the pedestrian-walkable
# network (sidewalks, footpaths, crossings — not just drivable roads).
MANHATTAN_PLACE = "Manhattan, New York, USA"
NETWORK_TYPE = "walk"


class NYCDataSource(CityDataSource):
    """CityDataSource backed by NYC Open Data + OpenStreetMap."""

    def __init__(self, graph_cache_path: Path = GRAPH_CACHE_PATH):
        self.graph_cache_path = Path(graph_cache_path)

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

    def get_crime_points(self):
        raise NotImplementedError("Crime data ingestion arrives in Phase 2.")

    def get_streetlights(self):
        raise NotImplementedError("Streetlight data ingestion arrives in Phase 2.")

    def get_light_outages(self):
        raise NotImplementedError("311 light-outage ingestion arrives in Phase 2.")
