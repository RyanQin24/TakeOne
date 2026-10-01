"""Build the metric world the robot is allowed to reason over.

Sources are open map geometry, operator measurements, Photo Scout
reconstruction and authored proxies. Google Photorealistic 3D Tiles are not a
source here and cannot become one: every polygon carries
:class:`~takeone.location_scout.contracts.WorldEvidence`, and the evidence
constructor refuses to mark tile content as metric planning data.

Unknown stays unknown. The site disc is tiled at a coarse grid and every cell
that no source covers becomes an explicit ``UnknownRegion``. A planner that
wants to drive through one has to decide to, visibly.
"""

from __future__ import annotations

import math

from . import geometry, openmap
from .contracts import (
    GeoAnchor,
    GroundRegion,
    Landmark,
    Obstacle,
    PlanningWorld,
    UnknownRegion,
    planning_evidence,
    stable_digest,
    visual_evidence,
)
from .geodesy import geodetic_to_local

DEFAULT_SITE_RADIUS_M = 140.0
UNKNOWN_CELL_M = 6.0
MAX_UNKNOWN_REGIONS = 120
MAX_OBSTACLES = 160
DEFAULT_BUILDING_HEIGHT_M = 6.0


def _to_local(anchor, points):
    return [geodetic_to_local(anchor, lat, lon, anchor.alt_m or 0.0)[:2] for lat, lon in points]


def _within(ring, radius_m):
    return any(math.hypot(x, y) <= radius_m for x, y in ring)


def _simplify(ring, tolerance_m=0.35):
    """Drop collinear and near-duplicate vertices. Keeps payloads small."""
    if len(ring) <= 4:
        return ring
    out = [ring[0]]
    for point in ring[1:]:
        if math.dist(point, out[-1]) >= tolerance_m:
            out.append(point)
    if len(out) >= 4 and math.dist(out[0], out[-1]) < tolerance_m:
        out.pop()
    return out if len(out) >= 3 else ring


def build(
    anchor: GeoAnchor,
    classified,
    *,
    world_id,
    revision=1,
    site_radius_m=DEFAULT_SITE_RADIUS_M,
    place_name="",
    source="open_map_geometry",
    geodetic=True,
    notes=(),
):
    """Assemble a :class:`PlanningWorld` from classified geometry.

    ``geodetic`` says whether the incoming rings are (lat, lon) degrees, which
    the anchor converts once, or already local metres, which stored fixtures
    use. There is still only one conversion boundary; this just says whether a
    given payload has already crossed it.
    """
    evidence = planning_evidence(source, note=f"Fetched for {place_name or world_id}" if place_name else "")
    obstacles, ground, walkable = [], [], []

    def to_local(points):
        if geodetic:
            return _to_local(anchor, points)
        return [(float(a), float(b)) for a, b in points]

    for item in classified.get("obstacles", [])[:MAX_OBSTACLES]:
        ring = _simplify(to_local(item["ring"]))
        if len(ring) < 3 or not _within(ring, site_radius_m * 1.25):
            continue
        height = item.get("height_m")
        obstacles.append(
            Obstacle(
                obstacle_id=item["id"],
                kind="water" if item["kind"] == "water" else "building",
                footprint_polygon_m=ring,
                min_z_m=0.0,
                max_z_m=0.0 if item["kind"] == "water" else (height or DEFAULT_BUILDING_HEIGHT_M),
                evidence=evidence,
                confidence="open_data_outline" if height else "open_data_outline_assumed_height",
            )
        )

    for item in classified.get("ways", []):
        line = to_local(item["line"])
        if len(line) < 2 or not _within(line, site_radius_m * 1.25):
            continue
        rings = geometry.buffer_polyline(line, item.get("width_m", 2.0))
        for index, ring in enumerate(rings[:40]):
            if item["kind"] == "barrier":
                if len(obstacles) >= MAX_OBSTACLES:
                    break
                obstacles.append(
                    Obstacle(
                        obstacle_id=f"{item['id']}-{index}",
                        kind="barrier",
                        footprint_polygon_m=ring,
                        min_z_m=0.0,
                        max_z_m=item.get("height_m", 1.8),
                        evidence=evidence,
                        confidence="open_data_centreline_buffered",
                    )
                )
            else:
                walkable.append(
                    GroundRegion(
                        region_id=f"{item['id']}-{index}",
                        polygon_m=ring,
                        surface_kind="paved",
                        evidence=evidence,
                        walkable=True,
                    )
                )

    for item in classified.get("surfaces", []):
        ring = _simplify(to_local(item["ring"]))
        if len(ring) < 3 or not _within(ring, site_radius_m * 1.25):
            continue
        region = GroundRegion(
            region_id=item["id"],
            polygon_m=ring,
            surface_kind=item.get("kind", "unpaved"),
            evidence=evidence,
            walkable=bool(item.get("walkable", True)),
        )
        ground.append(region)
        if region.walkable:
            walkable.append(region)

    unknown = _unknown_regions(obstacles, ground, walkable, site_radius_m)
    landmarks = []
    if place_name:
        landmarks.append(
            Landmark(
                landmark_id="site-origin",
                name=place_name,
                position_m=(0.0, 0.0),
                kind="selected_location",
                # The place's identity comes from Google. Its position in metres
                # comes from the anchor, which the operator can correct on site.
                evidence=visual_evidence("google_place_summary", note="Place identity only"),
            )
        )
    world = PlanningWorld(
        world_id=world_id,
        revision=revision,
        geo_anchor=anchor,
        site_radius_m=site_radius_m,
        ground_regions=tuple(ground),
        walkable_regions=tuple(walkable),
        static_obstacles=tuple(obstacles),
        unknown_regions=tuple(unknown),
        semantic_landmarks=tuple(landmarks),
        provenance={
            "geometry_source": source,
            "attribution": classified.get("attribution", openmap.ATTRIBUTION),
            "notes": list(notes),
            "unknown_cell_m": UNKNOWN_CELL_M,
            "physical_registration": "operator_required",
            "input_digest": stable_digest(
                {
                    "obstacles": len(classified.get("obstacles", [])),
                    "ways": len(classified.get("ways", [])),
                    "surfaces": len(classified.get("surfaces", [])),
                    "anchor": [anchor.lat_deg, anchor.lon_deg, anchor.heading_deg],
                    "radius": site_radius_m,
                }
            ),
        },
    )
    return world


def _unknown_regions(obstacles, ground, walkable, site_radius_m):
    """Every cell of the site disc no source covers, as explicit unknown ground."""
    covered = [obstacle.footprint_polygon_m for obstacle in obstacles]
    covered += [region.polygon_m for region in ground]
    covered += [region.polygon_m for region in walkable]
    if not covered:
        return [
            UnknownRegion(
                region_id="unknown-site",
                polygon_m=geometry.circle_ring((0.0, 0.0), site_radius_m, 32),
                reason="no_planning_geometry_available",
            )
        ]
    step = UNKNOWN_CELL_M
    steps = int(site_radius_m // step)
    regions = []
    for row in range(-steps, steps):
        run_start = None
        y0 = row * step
        y1 = y0 + step
        for column in range(-steps, steps + 1):
            x0 = column * step
            centre = (x0 + step / 2, y0 + step / 2)
            outside_site = math.hypot(*centre) > site_radius_m
            # A cell is unknown only when no source covers ANY part of it. A
            # centre-only test would mark a 3 m walkway's own cell unknown.
            probes = [(x0 + step * u, y0 + step * v) for u in (0.15, 0.5, 0.85) for v in (0.15, 0.5, 0.85)]
            known = outside_site or any(
                geometry.point_in_polygon(probe, ring) for ring in covered for probe in probes
            )
            if not known and column < steps:
                if run_start is None:
                    run_start = x0
                continue
            if run_start is not None:
                regions.append(
                    UnknownRegion(
                        region_id=f"unknown-{row}-{int(run_start)}",
                        polygon_m=(
                            (run_start, y0),
                            (x0, y0),
                            (x0, y1),
                            (run_start, y1),
                        ),
                    )
                )
                run_start = None
                if len(regions) >= MAX_UNKNOWN_REGIONS:
                    return regions
    return regions


def from_fixture(anchor, payload, *, world_id, place_name="", site_radius_m=DEFAULT_SITE_RADIUS_M):
    return build(
        anchor,
        payload,
        world_id=world_id,
        site_radius_m=site_radius_m,
        place_name=place_name,
        source="open_map_geometry",
        notes=["Stored open-map extract; no network was used for this world."],
    )


def fetch_and_build(anchor, *, world_id, place_name="", site_radius_m=DEFAULT_SITE_RADIUS_M, timeout_s=25.0):
    """Live path. Raises :class:`openmap.OpenMapError`; the caller decides the fallback."""
    result = openmap.fetch(anchor.lat_deg, anchor.lon_deg, int(site_radius_m * 1.3), timeout_s=timeout_s)
    classified = openmap.classify(result)
    return build(
        anchor,
        classified,
        world_id=world_id,
        site_radius_m=site_radius_m,
        place_name=place_name,
        source="open_map_geometry",
        notes=["Fetched live from the open map service."],
    )
