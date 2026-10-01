"""World Scout: real locations, a metric planning world, and simulated shots.

Two representations, one boundary. ``visual_world`` is Google Photorealistic 3D
Tiles drawn for the filmmaker. ``planning_world`` is metre geometry from open
map data, operator measurements or authored proxies, and it is the only thing
the robot's planner may read. See :mod:`takeone.location_scout.contracts`.
"""

from .api import LocationScoutAPI, ScoutError
from .contracts import (
    Authority,
    EvidenceBoundaryError,
    GeoAnchor,
    GroundRegion,
    Obstacle,
    PlanningWorld,
    UnknownRegion,
    WorldEvidence,
    require_planning_authority,
)
from .parse import LocationQuery, QueryError, parse_location

__all__ = [
    "Authority",
    "EvidenceBoundaryError",
    "GeoAnchor",
    "GroundRegion",
    "LocationQuery",
    "LocationScoutAPI",
    "Obstacle",
    "PlanningWorld",
    "QueryError",
    "ScoutError",
    "UnknownRegion",
    "WorldEvidence",
    "parse_location",
    "require_planning_authority",
]
