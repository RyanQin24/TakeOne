"""The stored demo world. Permission-safe, honestly labelled, no network.

World Scout must survive a dead Wi-Fi network in front of judges, so every live
provider has a stored counterpart here. What is stored is deliberately limited:

* candidate entries TakeOne authored itself, never cached Google place records;
* planning geometry TakeOne authored itself, marked ``authored_proxy`` so the
  evidence legend calls it proposed rather than surveyed or open data.

No Google Photorealistic 3D Tile content is stored, cached or reshaped here.
Tiles are always fetched live by the browser and drawn; when they are
unavailable the planning world below still renders and the shot still plays.
"""

from __future__ import annotations

import math

# The Hack the North demo area. A query with no coordinates of its own anchors
# here; a query with coordinates anchors on those instead, so the fixture works
# for any location, not only Waterloo.
DEMO_LAT = 43.466752
DEMO_LON = -80.5404672
DEMO_NAME = "Hack the North demo site"

METRES_PER_DEG_LAT = 111_320.0


def available():
    return True


def _offset(lat, lon, north_m, east_m):
    return (
        lat + north_m / METRES_PER_DEG_LAT,
        lon + east_m / (METRES_PER_DEG_LAT * math.cos(math.radians(lat))),
    )


def candidate_records(query):
    """Three authored demo entries around the query's anchor.

    These are TakeOne's own demo entries, not stored Google results. The
    provider tags them ``takeone_fixture`` and the UI badges them as stored.
    """
    lat = query.lat_deg if query.lat_deg is not None else DEMO_LAT
    lon = query.lon_deg if query.lon_deg is not None else DEMO_LON
    named = query.text if query.kind in ("place", "search") and query.lat_deg is None else ""
    origin = (lat, lon)
    entries = [
        {
            "place_id": "takeone-demo-site",
            "name": f"{named or DEMO_NAME} — main approach",
            "address": "Stored demo entry at the coordinates you gave",
            "lat_deg": lat,
            "lon_deg": lon,
            "types": ["outdoor_open_space"],
            "primary_type": "Open approach",
            "summary": (
                "TakeOne's stored demo site. A long open axis with buildings set back on one side, "
                "authored so the rehearsal works with no network."
            ),
            "maps_uri": "",
        },
        {
            "place_id": "takeone-demo-walkway",
            "name": f"{named or DEMO_NAME} — north walkway",
            "address": "Stored demo entry, 90 m north of the anchor",
            "lat_deg": _offset(lat, lon, 90.0, 0.0)[0],
            "lon_deg": _offset(lat, lon, 90.0, 0.0)[1],
            "types": ["walkway"],
            "primary_type": "Paved walkway",
            "summary": "A narrower corridor. Kept in the fixture because it fails the clearance check.",
            "maps_uri": "",
        },
        {
            "place_id": "takeone-demo-courtyard",
            "name": f"{named or DEMO_NAME} — courtyard edge",
            "address": "Stored demo entry, 60 m east and 40 m south of the anchor",
            "lat_deg": _offset(lat, lon, -40.0, 60.0)[0],
            "lon_deg": _offset(lat, lon, -40.0, 60.0)[1],
            "types": ["courtyard"],
            "primary_type": "Courtyard",
            "summary": "Deep background on one axis, a hard wall on the other.",
            "maps_uri": "",
        },
    ]
    return origin, entries


def _rect(cx, cy, width, depth, yaw_deg=0.0):
    half_w, half_d = width / 2.0, depth / 2.0
    corners = ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))
    angle = math.radians(yaw_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return [(cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a) for x, y in corners]


def planning_payload(candidate_id="takeone-demo-site"):
    """Authored planning geometry in site-local metres.

    This is a proxy set, not a survey and not open map data. It says so: the
    caller builds it with ``source="authored_proxy"``, which the evidence
    legend renders as *Proposed*, never as *Observed/open geometry*.
    """
    if candidate_id == "takeone-demo-walkway":
        # Deliberately too narrow for a 2.6 m cart standoff. The demo needs a
        # location that honestly fails.
        obstacles = [
            {
                "id": "demo-wall-west",
                "kind": "building",
                "ring": _rect(-2.4, 0.0, 1.2, 60.0),
                "height_m": 4.0,
            },
            {"id": "demo-wall-east", "kind": "building", "ring": _rect(2.4, 0.0, 1.2, 60.0), "height_m": 4.0},
        ]
        surfaces = [
            {"id": "demo-walk", "kind": "paved", "ring": _rect(0.0, 0.0, 3.0, 60.0), "walkable": True}
        ]
        ways = []
    elif candidate_id == "takeone-demo-courtyard":
        obstacles = [
            {
                "id": "demo-court-north",
                "kind": "building",
                "ring": _rect(0.0, 16.0, 44.0, 14.0),
                "height_m": 12.0,
            },
            {
                "id": "demo-court-east",
                "kind": "building",
                "ring": _rect(19.0, -6.0, 12.0, 30.0),
                "height_m": 9.0,
            },
            {"id": "demo-planter", "kind": "barrier", "ring": _rect(-4.0, 2.0, 2.2, 2.2), "height_m": 0.8},
        ]
        surfaces = [
            {"id": "demo-court-floor", "kind": "paved", "ring": _rect(0.0, 0.0, 34.0, 22.0), "walkable": True}
        ]
        ways = []
    else:
        obstacles = [
            {
                "id": "demo-hall-north",
                "kind": "building",
                "ring": _rect(0.0, 13.5, 52.0, 16.0),
                "height_m": 15.0,
            },
            {
                "id": "demo-hall-south",
                "kind": "building",
                "ring": _rect(6.0, -15.0, 34.0, 14.0),
                "height_m": 11.0,
            },
            {"id": "demo-tree-a", "kind": "barrier", "ring": _rect(-12.0, 3.4, 1.4, 1.4), "height_m": 4.5},
            {"id": "demo-tree-b", "kind": "barrier", "ring": _rect(-6.0, 3.4, 1.4, 1.4), "height_m": 4.5},
            {"id": "demo-bollard", "kind": "barrier", "ring": _rect(14.0, -3.2, 0.5, 0.5), "height_m": 0.9},
        ]
        surfaces = [
            {"id": "demo-plaza", "kind": "paved", "ring": _rect(0.0, -1.0, 46.0, 12.0), "walkable": True},
            {"id": "demo-lawn", "kind": "grass", "ring": _rect(-16.0, -12.0, 18.0, 8.0), "walkable": True},
        ]
        ways = [
            {
                "id": "demo-path-east",
                "kind": "path",
                "line": [(23.0, -1.0), (34.0, -1.0), (40.0, 4.0)],
                "width_m": 2.4,
            }
        ]
    return {
        "obstacles": obstacles,
        "ways": ways,
        "surfaces": surfaces,
        "attribution": "TakeOne authored demo proxy geometry",
    }
