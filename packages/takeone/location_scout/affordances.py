"""Turn metre geometry into filmmaking descriptors. Deterministic, local, bounded.

This is the bridge between 3D geometry and AI direction. The planner never sees
polygons: it sees "a 12.4 m tracking axis with 1.9 m of clearance and 38 m of
background depth, 3 % of it over unsurveyed ground". Geometry stays here where
it can be checked; the model reasons about filmmaking affordances.

Every number below is nominal screening on open-data or authored proxy outlines.
None of it is a physical clearance qualification, and nothing here consults
Google tile geometry — it cannot, the evidence gate would refuse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import geometry
from .contracts import require_planning_authority

SAMPLE_STEP_M = 0.5
HEADING_COUNT = 12
SEED_GRID_M = 4.0
MAX_SEEDS = 120
MAX_AXES = 6
MAX_RAY_M = 120.0
RAY_STEP_M = 2.0
MIN_AXIS_LENGTH_M = 2.0


@dataclass(frozen=True, slots=True)
class FilmingAffordance:
    kind: str
    affordance_id: str
    start_m: tuple
    end_m: tuple
    heading_rad: float
    usable_length_m: float
    min_clearance_m: float
    background_depth_m: float
    unknown_fraction: float
    surface_kinds: tuple
    evidence: tuple

    def wire(self):
        return {
            "kind": self.kind,
            "affordance_id": self.affordance_id,
            "start_m": [round(v, 3) for v in self.start_m],
            "end_m": [round(v, 3) for v in self.end_m],
            "heading_rad": round(self.heading_rad, 6),
            "usable_length_m": round(self.usable_length_m, 2),
            "min_clearance_m": round(self.min_clearance_m, 2),
            "background_depth_m": round(self.background_depth_m, 1),
            "unknown_fraction": round(self.unknown_fraction, 3),
            "surface_kinds": list(self.surface_kinds),
            "evidence": list(self.evidence),
            "basis": "nominal_polygon_screening_not_physical_clearance",
        }


class WorldIndex:
    """Ring lists pulled out of a planning world once, after the evidence gate."""

    def __init__(self, world):
        for obstacle in world.static_obstacles:
            require_planning_authority(obstacle.evidence, f"obstacle {obstacle.obstacle_id}")
        for region in world.walkable_regions:
            require_planning_authority(region.evidence, f"walkable region {region.region_id}")
        self.world = world
        self.obstacles = [obstacle.footprint_polygon_m for obstacle in world.static_obstacles]
        self.walkable = [region.polygon_m for region in world.walkable_regions]
        self.surface_of = {region.region_id: region.surface_kind for region in world.walkable_regions}
        self.walkable_ids = [region.region_id for region in world.walkable_regions]
        self.unknown = [region.polygon_m for region in world.unknown_regions]
        self.site_radius_m = world.site_radius_m
        self.attributions = world.attributions

    def surface_at(self, point):
        for index, ring in enumerate(self.walkable):
            if geometry.point_in_polygon(point, ring):
                return self.surface_of[self.walkable_ids[index]]
        return None

    def is_unknown(self, point):
        # A point standing on a known surface is known, whatever the coarse
        # unknown grid says about the cell around it.
        if self.surface_at(point) is not None:
            return False
        return any(geometry.point_in_polygon(point, ring) for ring in self.unknown)

    def clearance(self, point):
        return geometry.clearance_to_rings(point, self.obstacles)

    def inside_site(self, point):
        return math.hypot(point[0], point[1]) <= self.site_radius_m

    def free_at(self, point, min_clearance_m):
        """Usable ground: on a known walkable surface with room for the rig."""
        if not self.inside_site(point):
            return False
        if self.surface_at(point) is None:
            return False
        return self.clearance(point) >= min_clearance_m

    def ray_depth(self, origin, heading_rad, limit_m=None):
        """How far the eye travels before the first obstacle. Background depth.

        Capped at the site radius: past that edge TakeOne holds no geometry, so
        a longer number would be a claim about ground nobody looked at.
        """
        limit_m = min(MAX_RAY_M, self.site_radius_m) if limit_m is None else limit_m
        dx, dy = math.cos(heading_rad), math.sin(heading_rad)
        travelled = RAY_STEP_M
        while travelled <= limit_m:
            point = (origin[0] + dx * travelled, origin[1] + dy * travelled)
            if self.clearance(point) <= 0.0:
                return travelled
            travelled += RAY_STEP_M
        return limit_m


def _seeds(index):
    points = []
    for ring in index.walkable:
        points.append(geometry.centroid(ring))
        min_x, min_y, max_x, max_y = geometry.bounds(ring)
        x = min_x + SEED_GRID_M / 2
        while x < max_x and len(points) < MAX_SEEDS:
            y = min_y + SEED_GRID_M / 2
            while y < max_y and len(points) < MAX_SEEDS:
                if geometry.point_in_polygon((x, y), ring):
                    points.append((x, y))
                y += SEED_GRID_M
            x += SEED_GRID_M
        if len(points) >= MAX_SEEDS:
            break
    # Deterministic order regardless of how the world was assembled.
    return sorted({(round(p[0], 2), round(p[1], 2)) for p in points})[:MAX_SEEDS]


def _march(index, seed, heading_rad, min_clearance_m, direction):
    dx, dy = math.cos(heading_rad) * direction, math.sin(heading_rad) * direction
    travelled = 0.0
    last = seed
    worst = index.clearance(seed)
    unknown_hits = 0
    samples = 0
    while travelled < 60.0:
        travelled += SAMPLE_STEP_M
        point = (seed[0] + dx * travelled, seed[1] + dy * travelled)
        if not index.free_at(point, min_clearance_m):
            break
        samples += 1
        if index.is_unknown(point):
            unknown_hits += 1
        worst = min(worst, index.clearance(point))
        last = point
    return last, worst, unknown_hits, samples


def tracking_axes(world, *, min_clearance_m=1.0, limit=MAX_AXES):
    """Straight runs of usable ground, longest and roomiest first."""
    index = WorldIndex(world)
    found = []
    for seed in _seeds(index):
        if not index.free_at(seed, min_clearance_m):
            continue
        for step in range(HEADING_COUNT):
            heading = math.pi * step / HEADING_COUNT
            ahead, worst_a, unknown_a, samples_a = _march(index, seed, heading, min_clearance_m, 1)
            behind, worst_b, unknown_b, samples_b = _march(index, seed, heading, min_clearance_m, -1)
            length = math.dist(ahead, behind)
            if length < MIN_AXIS_LENGTH_M:
                continue
            samples = max(1, samples_a + samples_b)
            found.append(
                {
                    "start": behind,
                    "end": ahead,
                    "heading": heading,
                    "length": length,
                    "clearance": min(worst_a, worst_b),
                    "unknown": (unknown_a + unknown_b) / samples,
                }
            )
    found.sort(key=lambda a: (-a["length"], -a["clearance"], a["start"], a["heading"]))
    chosen = []
    for axis in found:
        midpoint = ((axis["start"][0] + axis["end"][0]) / 2, (axis["start"][1] + axis["end"][1]) / 2)
        duplicate = False
        for other in chosen:
            other_mid = ((other["start"][0] + other["end"][0]) / 2, (other["start"][1] + other["end"][1]) / 2)
            angle = abs(axis["heading"] - other["heading"]) % math.pi
            angle = min(angle, math.pi - angle)
            if math.dist(midpoint, other_mid) < 4.0 and angle < math.radians(25):
                duplicate = True
                break
        if not duplicate:
            chosen.append(axis)
        if len(chosen) >= limit:
            break

    affordances = []
    for order, axis in enumerate(chosen):
        forward = math.atan2(axis["end"][1] - axis["start"][1], axis["end"][0] - axis["start"][0])
        depth = max(
            index.ray_depth(axis["end"], forward),
            index.ray_depth(axis["start"], forward + math.pi),
        )
        surface = index.surface_at(axis["start"]) or "unsurveyed"
        affordances.append(
            FilmingAffordance(
                kind="tracking_axis",
                affordance_id=f"axis-{order}",
                start_m=tuple(round(v, 3) for v in axis["start"]),
                end_m=tuple(round(v, 3) for v in axis["end"]),
                heading_rad=forward,
                usable_length_m=axis["length"],
                min_clearance_m=max(0.0, axis["clearance"]),
                background_depth_m=depth,
                unknown_fraction=axis["unknown"],
                surface_kinds=(surface,),
                evidence=tuple(index.attributions),
            )
        )
    return affordances


def site_summary(world, *, min_clearance_m=1.0):
    """The compact world description the planner is allowed to see."""
    index = WorldIndex(world)
    axes = tracking_axes(world, min_clearance_m=min_clearance_m)
    turning = 0.0
    for ring in index.walkable:
        turning = max(turning, abs(geometry.point_polygon_distance(geometry.centroid(ring), ring)))
    longest = axes[0] if axes else None
    return {
        "walkable_regions": len(index.walkable),
        "known_obstacles": len(index.obstacles),
        "unknown_regions": len(index.unknown),
        "site_radius_m": world.site_radius_m,
        "turning_room_m": round(min(turning, 25.0), 2),
        "longest_axis_m": round(longest.usable_length_m, 2) if longest else 0.0,
        "best_background_depth_m": round(max((a.background_depth_m for a in axes), default=0.0), 1),
        "background_depth_limit_m": round(min(MAX_RAY_M, world.site_radius_m), 1),
        "min_clearance_used_m": min_clearance_m,
        "candidate_axes": [affordance.wire() for affordance in axes],
        "attribution": list(index.attributions),
        "basis": "nominal_polygon_screening_not_physical_clearance",
    }
