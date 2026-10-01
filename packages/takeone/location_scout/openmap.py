"""Open map geometry for the planning world. OpenStreetMap, ODbL, attributed.

This is where the robot's metric world comes from when nobody has measured the
site: building footprints, barriers, water and pedestrian ways from
OpenStreetMap, under the Open Database Licence, which permits derived use with
attribution. It is the legally compatible counterpart to Google's tiles — one
can be planned against, the other can only be drawn.

Everything returned here is in WGS-84 degrees. Conversion to TakeOne metres
happens once, in ``planning_world.build``, through the geo anchor.
"""

from __future__ import annotations

import http.client
import json
import socket
import time
from urllib.parse import urlencode

# overpass-api.de is the busiest instance and answers 504 under load, which
# would leave a real location with no planning geometry at all. These are
# equivalent public mirrors of the same ODbL data, tried in order.
OVERPASS_ENDPOINTS = (
    ("overpass-api.de", "/api/interpreter"),
    ("overpass.kumi.systems", "/api/interpreter"),
    ("overpass.private.coffee", "/api/interpreter"),
    ("overpass.osm.jp", "/api/interpreter"),
)
OVERPASS_HOST = OVERPASS_ENDPOINTS[0][0]
OVERPASS_PATH = OVERPASS_ENDPOINTS[0][1]
MAX_RESPONSE_BYTES = 8_388_608
ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"

WALKABLE_HIGHWAYS = ("footway", "path", "pedestrian", "living_street", "service", "cycleway", "track")
BLOCKING_BARRIERS = ("wall", "fence", "hedge", "retaining_wall", "guard_rail", "city_wall")
DEFAULT_WAY_WIDTH_M = 2.0


class OpenMapError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def query_text(lat, lon, radius_m):
    """One bounded Overpass query. Ways only, geometry inline, hard timeout."""
    around = f"(around:{int(radius_m)},{lat:.7f},{lon:.7f})"
    highways = "|".join(WALKABLE_HIGHWAYS)
    return (
        "[out:json][timeout:25];("
        f'way["building"]{around};'
        f'way["building:part"]{around};'
        f'way["barrier"]{around};'
        f'way["natural"="water"]{around};'
        f'way["highway"~"^({highways})$"]{around};'
        f'way["area:highway"]{around};'
        f'way["landuse"~"^(grass|recreation_ground|village_green)$"]{around};'
        f'way["leisure"~"^(park|garden|pitch)$"]{around};'
        ");out geom 600;"
    )


def fetch(lat, lon, radius_m, *, timeout_s=25.0, endpoints=OVERPASS_ENDPOINTS):
    """Try each mirror in turn. Only a failure on every one is a failure."""
    outcomes = []
    for host, path in endpoints:
        try:
            return _fetch_one(host, path, lat, lon, radius_m, timeout_s=timeout_s)
        except OpenMapError as error:
            outcomes.append(f"{host}: {error}")
            continue
    # Report every mirror. One 504 and three unreachable hosts is a different
    # problem from four refusals, and the operator has to be able to tell.
    detail = "; ".join(outcomes) or "no endpoints configured"
    transient = any(code in detail for code in ("429", "504", "503", "timed out"))
    raise OpenMapError(
        "provider_unavailable",
        f"No open map service answered ({detail})."
        + (" Those are load errors, so a retry in a minute usually works." if transient else ""),
    )


def _fetch_one(host, path, lat, lon, radius_m, *, timeout_s=25.0):
    body = urlencode({"data": query_text(lat, lon, radius_m)}).encode()
    started = time.monotonic()
    connection = http.client.HTTPSConnection(host, timeout=timeout_s)
    try:
        connection.request(
            "POST",
            path,
            body,
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "TakeOne-WorldScout/1.0 (local rehearsal tool)",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise OpenMapError("provider_rejected", f"The open map service returned HTTP {response.status}.")
        chunks, size = [], 0
        while True:
            remaining = timeout_s - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError()
            if connection.sock:
                connection.sock.settimeout(remaining)
            chunk = response.read1(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise OpenMapError("response_too_large", "The open map response was too large.")
            chunks.append(chunk)
        return json.loads(b"".join(chunks))
    except (TimeoutError, socket.timeout):
        raise OpenMapError("provider_timeout", "timed out") from None
    except (OSError, http.client.HTTPException):
        raise OpenMapError("provider_connection", "unreachable") from None
    except (ValueError, UnicodeError):
        raise OpenMapError("malformed_result", "The open map service returned unreadable data.") from None
    finally:
        connection.close()


def _height_m(tags):
    for key, scale in (("height", 1.0), ("building:levels", 3.2), ("est_height", 1.0)):
        raw = tags.get(key)
        if raw is None:
            continue
        try:
            value = float(str(raw).split()[0].replace("'", ""))
        except (TypeError, ValueError):
            continue
        if 0 < value * scale < 400:
            return value * scale
    return None


def _width_m(tags):
    for key in ("width", "est_width"):
        raw = tags.get(key)
        if raw is None:
            continue
        try:
            value = float(str(raw).split()[0])
        except (TypeError, ValueError):
            continue
        if 0.4 <= value <= 30:
            return value
    return DEFAULT_WAY_WIDTH_M


def classify(result):
    """Split an Overpass result into the categories the planning world needs.

    Returns plain dictionaries of geodetic rings and lines, not geometry — the
    metre conversion is the anchor's job, and doing it here would create a
    second coordinate boundary.
    """
    if not isinstance(result, dict) or not isinstance(result.get("elements"), list):
        raise OpenMapError("malformed_result", "The open map service returned unreadable data.")
    obstacles, ways, surfaces = [], [], []
    for element in result["elements"][:900]:
        if not isinstance(element, dict) or element.get("type") != "way":
            continue
        geometry = element.get("geometry")
        if not isinstance(geometry, list) or len(geometry) < 2:
            continue
        points = [
            (float(node["lat"]), float(node["lon"]))
            for node in geometry
            if isinstance(node, dict) and type(node.get("lat")) in (int, float)
        ]
        if len(points) < 2:
            continue
        tags = element.get("tags") or {}
        if not isinstance(tags, dict):
            continue
        identity = f"osm-way-{element.get('id', len(obstacles) + len(ways) + len(surfaces))}"
        closed = len(points) >= 4 and points[0] == points[-1]
        if "building" in tags or "building:part" in tags:
            if closed:
                obstacles.append(
                    {
                        "id": identity,
                        "kind": "building",
                        "ring": points[:-1],
                        "height_m": _height_m(tags),
                        "name": str(tags.get("name", ""))[:80],
                    }
                )
        elif tags.get("natural") == "water" and closed:
            obstacles.append({"id": identity, "kind": "water", "ring": points[:-1], "height_m": 0.0})
        elif tags.get("barrier") in BLOCKING_BARRIERS:
            ways.append(
                {
                    "id": identity,
                    "kind": "barrier",
                    "line": points,
                    "width_m": 0.4,
                    "height_m": _height_m(tags) or 1.8,
                }
            )
        elif "highway" in tags or "area:highway" in tags:
            if closed:
                surfaces.append({"id": identity, "kind": "paved", "ring": points[:-1], "walkable": True})
            else:
                ways.append({"id": identity, "kind": "path", "line": points, "width_m": _width_m(tags)})
        elif closed:
            surfaces.append(
                {
                    "id": identity,
                    "kind": "grass" if tags.get("landuse") or tags.get("leisure") else "unpaved",
                    "ring": points[:-1],
                    "walkable": True,
                }
            )
    return {"obstacles": obstacles, "ways": ways, "surfaces": surfaces, "attribution": ATTRIBUTION}
