"""SafePath backend — city data source interface.

This abstract base class is SafePath's extensibility seam. All city-specific data
access (crime points, streetlights, outages, street graph) is defined here as an
abstract contract with NO implementation.

A concrete `NYCDataSource(CityDataSource)` will implement these methods in a later
phase, pulling from NYC Open Data + OSM. Supporting a new city later means adding a
new subclass (e.g. `ChicagoDataSource`) that implements the same four methods — the
rest of the app depends only on this interface, never on a specific city.
"""

from abc import ABC, abstractmethod


class CityDataSource(ABC):
    """Abstract contract every city's data source must fulfill."""

    @abstractmethod
    def get_crime_points(self):
        """Return geolocated crime incidents for the city.

        Later phases define the concrete return type (e.g. a GeoDataFrame of
        point geometries with incident metadata). No implementation in Phase 0.
        """
        ...

    @abstractmethod
    def get_streetlights(self):
        """Return the locations of streetlights (lighting infrastructure).

        Used later to score how well-lit a route is. No implementation in Phase 0.
        """
        ...

    @abstractmethod
    def get_light_outages(self):
        """Return reported streetlight outages (lights that are currently out).

        Lets routing down-weight segments where lights are known to be broken.
        No implementation in Phase 0.
        """
        ...

    @abstractmethod
    def get_street_graph(self):
        """Return the walkable street network as a routable graph.

        Later phases return an OSMnx/NetworkX graph used for pathfinding.
        No implementation in Phase 0.
        """
        ...
