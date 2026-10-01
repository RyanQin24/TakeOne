"""The only Google Maps Platform wire shapes in TakeOne. One marked section.

Everything Google-facing for World Scout lives here: the Places API (New)
request bodies, the field masks, the response reading and the attribution the
UI must show. Nothing in this module scrapes google.com/maps or Google Search
HTML, and nothing here reads Map Tiles content — tiles are fetched by the
browser and drawn, never interpreted.

Fix any disagreement with Google's documented request shape in this file and
nowhere else.
"""

from __future__ import annotations

import http.client
import json
import socket
import time

PLACES_HOST = "places.googleapis.com"
MAX_RESPONSE_BYTES = 1_048_576

# Only the fields World Scout actually shows or scores. A narrower mask is
# cheaper and keeps place data we have no use for off this computer.
PLACE_FIELDS = (
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.types",
    "places.primaryTypeDisplayName",
    "places.editorialSummary",
    "places.businessStatus",
    "places.googleMapsUri",
)

# Place types that plausibly hold a 4-metre tracking shot. Searching every type
# in a 3 km circle returns car parks and dentists.
FILMING_TYPES = (
    "park",
    "plaza",
    "university",
    "library",
    "museum",
    "tourist_attraction",
    "historical_landmark",
    "performing_arts_theater",
    "art_gallery",
    "stadium",
    "garden",
)

ATTRIBUTION = "Place data ©Google"
TILE_ATTRIBUTION_NOTE = (
    "Photorealistic 3D Tiles carry their own per-tile copyright, aggregated and displayed by the "
    "renderer. It must stay visible and unobscured."
)


class GoogleGroundingError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def search_nearby_body(lat, lon, radius_m, *, limit):
    """places:searchNearby — used when the filmmaker gave a point on the map."""
    return {
        "includedTypes": list(FILMING_TYPES),
        "maxResultCount": limit,
        "languageCode": "en",
        "rankPreference": "DISTANCE",
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(radius_m),
            }
        },
    }


def search_text_body(query, *, limit, lat=None, lon=None, radius_m=None):
    """places:searchText — used for a place name or a written search instruction."""
    body = {
        "textQuery": query,
        "maxResultCount": limit,
        "languageCode": "en",
    }
    if lat is not None and lon is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(radius_m or 3000),
            }
        }
    return body


def read_places(result):
    """Read a Places response into plain records. Unknown fields are ignored."""
    places = result.get("places")
    if places is None:
        return []
    if not isinstance(places, list):
        raise GoogleGroundingError("malformed_result", "The place search returned unreadable data.")
    records = []
    for place in places[:20]:
        if not isinstance(place, dict):
            continue
        location = place.get("location") or {}
        lat, lon = location.get("latitude"), location.get("longitude")
        if type(lat) not in (int, float) or type(lon) not in (int, float):
            continue
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        if place.get("businessStatus") in ("CLOSED_PERMANENTLY",):
            continue
        records.append(
            {
                "place_id": str(place.get("id", ""))[:200],
                "name": str((place.get("displayName") or {}).get("text", ""))[:160] or "Unnamed place",
                "address": str(place.get("formattedAddress", ""))[:240],
                "lat_deg": float(lat),
                "lon_deg": float(lon),
                "types": [str(t)[:60] for t in (place.get("types") or [])][:12],
                "primary_type": str((place.get("primaryTypeDisplayName") or {}).get("text", ""))[:80],
                "summary": str((place.get("editorialSummary") or {}).get("text", ""))[:400],
                "maps_uri": str(place.get("googleMapsUri", ""))[:400],
            }
        )
    return records


def post(path, body, api_key, *, timeout_s, field_mask=PLACE_FIELDS):
    """One bounded HTTPS exchange. The key never appears in an error message."""
    raw = json.dumps(body, separators=(",", ":")).encode()
    started = time.monotonic()
    connection = http.client.HTTPSConnection(PLACES_HOST, timeout=timeout_s)
    try:
        connection.request(
            "POST",
            path,
            raw,
            {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": ",".join(field_mask),
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            # Never echo a provider body: it can carry key or quota details.
            raise GoogleGroundingError(
                "provider_rejected",
                f"Google Places returned HTTP {response.status}. "
                "Check that the Places API (New) is enabled for this key.",
            )
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
                raise GoogleGroundingError("response_too_large", "The place search response was too large.")
            chunks.append(chunk)
        return json.loads(b"".join(chunks))
    except (TimeoutError, socket.timeout):
        raise GoogleGroundingError("provider_timeout", "The place search timed out.") from None
    except (OSError, http.client.HTTPException):
        raise GoogleGroundingError("provider_connection", "Could not reach Google Places.") from None
    except (ValueError, UnicodeError):
        raise GoogleGroundingError("malformed_result", "Google Places returned unreadable data.") from None
    finally:
        connection.close()
