"""World Scout evidence types and the licence boundary between them.

TakeOne keeps two representations of a real filming location and they are not
interchangeable:

``visual_world``
    Photorealistic context a human looks at. Google Photorealistic 3D Tiles are
    display data. Google Maps Platform terms forbid machine interpretation,
    object detection, geodata extraction and derived offline geometry, so tile
    content never becomes geometry any planner reads.

``planning_world``
    The metric world the robot's planner is allowed to reason over: open map
    geometry, operator measurements, Photo Scout reconstruction and authored
    proxies, all in local metres with explicit provenance.

The boundary is a type, not a comment. Every geometric fact carries a
:class:`WorldEvidence` whose ``authority`` is checked before planning reads it;
``visualization_only`` evidence raises :class:`EvidenceBoundaryError` instead.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import StrEnum

SCHEMA_VERSION = 1


class EvidenceBoundaryError(RuntimeError):
    """Raised when visualization-only evidence is offered to robot planning."""


class Authority(StrEnum):
    PLANNING = "planning"
    VISUALIZATION_ONLY = "visualization_only"


# Sources whose geometry the planner may read. Each is either metric data we
# own, data an operator measured, or open data under a licence that permits
# derived use with attribution.
PLANNING_SOURCES = {
    "open_map_geometry": "OpenStreetMap contributors (ODbL)",
    "operator_measurement": "Measured on site by the operator",
    "photo_scout_reconstruction": "TakeOne Photo Scout reconstruction",
    "authored_proxy": "Authored TakeOne proxy geometry",
    "operator_confirmed_extent": "Operator-confirmed site extent",
}

# Sources that may only be drawn. Nothing here reaches a planner, ever.
VISUAL_ONLY_SOURCES = {
    "google_photorealistic_tiles": "Google Photorealistic 3D Tiles",
    "google_place_summary": "Google Maps place description",
    "google_map_imagery": "Google Maps imagery",
}

SURFACE_KINDS = ("paved", "unpaved", "grass", "indoor_floor", "unsurveyed")
OBSTACLE_KINDS = ("building", "wall", "barrier", "vegetation", "furniture", "water", "level_change")


def stable_digest(value):
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest()


def _finite(value, name, limit=1e7):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > limit:
        raise ValueError(f"{name} must be a finite number within {limit:g}")
    return float(value)


def _polygon(points, name):
    if not isinstance(points, (list, tuple)) or not 3 <= len(points) <= 400:
        raise ValueError(f"{name} must be a ring of 3 to 400 points")
    ring = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f"{name} points are [x_m, y_m] pairs")
        ring.append((_finite(point[0], name, 20000), _finite(point[1], name, 20000)))
    return tuple(ring)


@dataclass(frozen=True, slots=True)
class WorldEvidence:
    """Where one geometric fact came from and what it is allowed to do."""

    source: str
    authority: Authority
    metric: bool
    note: str = ""

    def __post_init__(self):
        authority = Authority(self.authority)
        object.__setattr__(self, "authority", authority)
        if self.source in VISUAL_ONLY_SOURCES:
            if authority is not Authority.VISUALIZATION_ONLY or self.metric:
                raise EvidenceBoundaryError(
                    f"{self.source} is display data under Google Maps Platform terms; "
                    "it cannot be declared metric planning evidence."
                )
        elif self.source in PLANNING_SOURCES:
            if authority is not Authority.PLANNING:
                raise ValueError(f"{self.source} is planning evidence and must declare planning authority")
        else:
            raise ValueError(f"Unknown world evidence source: {self.source}")

    @property
    def attribution(self):
        return PLANNING_SOURCES.get(self.source) or VISUAL_ONLY_SOURCES[self.source]

    def wire(self):
        return {
            "source": self.source,
            "authority": str(self.authority),
            "metric": self.metric,
            "attribution": self.attribution,
            "note": self.note,
        }


def planning_evidence(source, note=""):
    return WorldEvidence(source=source, authority=Authority.PLANNING, metric=True, note=note)


def visual_evidence(source, note=""):
    return WorldEvidence(source=source, authority=Authority.VISUALIZATION_ONLY, metric=False, note=note)


def require_planning_authority(evidence, what="geometry"):
    """The single gate every planner input passes through.

    Call this before any geometry reaches obstacle tests, affordance extraction
    or candidate scoring. It is deliberately noisy: a caller that forgets it is
    caught by ``tests/test_location_evidence.py``.
    """
    items = evidence if isinstance(evidence, (list, tuple, set)) else [evidence]
    for item in items:
        if isinstance(item, dict):
            item = WorldEvidence(
                source=item["source"],
                authority=item["authority"],
                metric=bool(item.get("metric", False)),
                note=item.get("note", ""),
            )
        if not isinstance(item, WorldEvidence):
            raise EvidenceBoundaryError(f"{what} carries no world evidence")
        if item.authority is not Authority.PLANNING or not item.metric:
            raise EvidenceBoundaryError(
                f"{what} is {item.attribution} — visualization only. "
                "It can be drawn for the filmmaker but never planned against."
            )
    return True


@dataclass(frozen=True, slots=True)
class GeoAnchor:
    """The one conversion boundary between geodetic and TakeOne metre space.

    ``heading_deg`` is the compass bearing of the local +X axis. Local +Y is 90
    degrees counter-clockwise from +X, +Z is up, and all three are metres. Every
    robot, actor, camera and obstacle coordinate downstream of this anchor is
    ordinary TakeOne scene-local metre space; latitude and longitude never reach
    IK, the compiler or the renderer.
    """

    lat_deg: float
    lon_deg: float
    alt_m: float | None = None
    heading_deg: float = 0.0
    heading_reference: str = "local_x_axis_compass_bearing"
    source: str = "location_scout_selection"

    def __post_init__(self):
        if not -90.0 <= self.lat_deg <= 90.0 or not math.isfinite(self.lat_deg):
            raise ValueError("Latitude must be between -90 and 90 degrees")
        if not -180.0 <= self.lon_deg <= 180.0 or not math.isfinite(self.lon_deg):
            raise ValueError("Longitude must be between -180 and 180 degrees")
        if self.alt_m is not None:
            _finite(self.alt_m, "Altitude", 12000)
        _finite(self.heading_deg, "Heading", 3600)

    def wire(self):
        return {
            "lat_deg": self.lat_deg,
            "lon_deg": self.lon_deg,
            "alt_m": self.alt_m,
            "local_frame": "ENU rotated to +X = local heading, +Y = 90 deg CCW, +Z = up, metres",
            "heading_deg": self.heading_deg,
            "heading_reference": self.heading_reference,
            "source": self.source,
        }

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Geo anchor must be an object")
        return cls(
            lat_deg=_finite(value["lat_deg"], "Latitude", 90),
            lon_deg=_finite(value["lon_deg"], "Longitude", 180),
            alt_m=None if value.get("alt_m") is None else _finite(value["alt_m"], "Altitude", 12000),
            heading_deg=_finite(value.get("heading_deg", 0.0), "Heading", 3600),
            source=str(value.get("source", "location_scout_selection"))[:80],
        )


@dataclass(frozen=True, slots=True)
class Obstacle:
    """A planning proxy for something the rig must not drive into."""

    obstacle_id: str
    kind: str
    footprint_polygon_m: tuple
    min_z_m: float
    max_z_m: float
    evidence: WorldEvidence
    confidence: str = "open_data_outline"

    def __post_init__(self):
        if self.kind not in OBSTACLE_KINDS:
            raise ValueError(f"Unknown obstacle kind: {self.kind}")
        object.__setattr__(self, "footprint_polygon_m", _polygon(self.footprint_polygon_m, "Footprint"))
        require_planning_authority(self.evidence, f"obstacle {self.obstacle_id}")

    def wire(self):
        return {
            "obstacle_id": self.obstacle_id,
            "kind": self.kind,
            "footprint_polygon_m": [list(point) for point in self.footprint_polygon_m],
            "min_z_m": self.min_z_m,
            "max_z_m": self.max_z_m,
            "confidence": self.confidence,
            "evidence": self.evidence.wire(),
        }


@dataclass(frozen=True, slots=True)
class GroundRegion:
    region_id: str
    polygon_m: tuple
    surface_kind: str
    evidence: WorldEvidence
    walkable: bool = True
    slope_percent: float | None = None

    def __post_init__(self):
        if self.surface_kind not in SURFACE_KINDS:
            raise ValueError(f"Unknown surface kind: {self.surface_kind}")
        object.__setattr__(self, "polygon_m", _polygon(self.polygon_m, "Ground region"))
        require_planning_authority(self.evidence, f"ground region {self.region_id}")

    def wire(self):
        return {
            "region_id": self.region_id,
            "polygon_m": [list(point) for point in self.polygon_m],
            "surface_kind": self.surface_kind,
            "walkable": self.walkable,
            "slope_percent": self.slope_percent,
            "evidence": self.evidence.wire(),
        }


@dataclass(frozen=True, slots=True)
class UnknownRegion:
    """Ground we have no data for. This never silently becomes empty floor."""

    region_id: str
    polygon_m: tuple
    reason: str = "no_open_map_coverage"

    def __post_init__(self):
        object.__setattr__(self, "polygon_m", _polygon(self.polygon_m, "Unknown region"))

    def wire(self):
        return {
            "region_id": self.region_id,
            "polygon_m": [list(point) for point in self.polygon_m],
            "reason": self.reason,
            "evidence": {
                "source": "absence_of_evidence",
                "authority": "planning",
                "metric": True,
                "attribution": "No surveyed or open-data coverage",
                "note": "Unknown is a planning fact. It is not free space.",
            },
        }


@dataclass(frozen=True, slots=True)
class Landmark:
    landmark_id: str
    name: str
    position_m: tuple
    kind: str
    evidence: WorldEvidence

    def wire(self):
        return {
            "landmark_id": self.landmark_id,
            "name": self.name,
            "position_m": list(self.position_m),
            "kind": self.kind,
            "evidence": self.evidence.wire(),
        }


@dataclass(frozen=True, slots=True)
class PlanningWorld:
    """The metric world the robot is allowed to reason over."""

    world_id: str
    revision: int
    geo_anchor: GeoAnchor
    site_radius_m: float
    ground_regions: tuple = ()
    walkable_regions: tuple = ()
    static_obstacles: tuple = ()
    unknown_regions: tuple = ()
    semantic_landmarks: tuple = ()
    provenance: dict = field(default_factory=dict)

    def wire(self):
        body = {
            "schema_version": SCHEMA_VERSION,
            "world_id": self.world_id,
            "revision": self.revision,
            "geo_anchor": self.geo_anchor.wire(),
            "site_radius_m": self.site_radius_m,
            "coordinate_frame": (
                "scene-local X/Y floor metres, Z up; +X is the site heading, +Y is 90 deg CCW"
            ),
            "ground_regions": [region.wire() for region in self.ground_regions],
            "walkable_regions": [region.wire() for region in self.walkable_regions],
            "static_obstacles": [obstacle.wire() for obstacle in self.static_obstacles],
            "unknown_regions": [region.wire() for region in self.unknown_regions],
            "semantic_landmarks": [landmark.wire() for landmark in self.semantic_landmarks],
            "provenance": dict(self.provenance),
            "evidence_boundary": (
                "Every polygon here is metric planning evidence. Google Photorealistic 3D Tiles "
                "are drawn beside it as visual context and are never read as geometry."
            ),
        }
        body["world_digest"] = stable_digest(
            {key: value for key, value in body.items() if key != "provenance"}
        )
        return body

    @property
    def attributions(self):
        sources = {region.evidence.attribution for region in self.ground_regions}
        sources |= {region.evidence.attribution for region in self.walkable_regions}
        sources |= {obstacle.evidence.attribution for obstacle in self.static_obstacles}
        return sorted(sources)
