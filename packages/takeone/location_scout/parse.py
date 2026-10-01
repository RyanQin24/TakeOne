"""Turn whatever the filmmaker pasted into a bounded, validated scout query.

Four accepted shapes: a Google Maps URL, a bare coordinate pair, a place name,
and a free-text search instruction. Nothing here fetches anything and nothing
here scrapes Google Maps or Google Search HTML — a URL is parsed for the
coordinates it already contains, and every other shape becomes a length-capped
text query handed to a grounding provider as JSON data, never as instructions.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, unquote, urlparse

MAX_TEXT = 300
RADIUS_CHOICES_M = (1000, 3000, 5000)
DEFAULT_RADIUS_M = 3000

# "@43.466752,-80.5404672,17z" and "@43.466752,-80.5404672,17.5z/data=..."
AT_PATTERN = re.compile(r"@(-?\d{1,3}(?:\.\d+)?),(-?\d{1,3}(?:\.\d+)?)")
# "!3d43.466752!4d-80.5404672" inside a Maps data payload
DATA_PATTERN = re.compile(r"!3d(-?\d{1,3}(?:\.\d+)?)!4d(-?\d{1,3}(?:\.\d+)?)")
PAIR_PATTERN = re.compile(r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")

MAPS_HOSTS = (
    "google.com",
    "www.google.com",
    "maps.google.com",
    "earth.google.com",
)
SHORT_HOSTS = ("goo.gl", "maps.app.goo.gl", "g.co")

# A search instruction says what to look for; a place name only names a place.
INSTRUCTION_HINTS = (
    "find",
    "look for",
    "somewhere",
    "within",
    "near",
    "that supports",
    "suitable",
    "location for",
    "needs",
    "with room",
    "space for",
)


class QueryError(ValueError):
    """The input could not be read as a location. The message is shown to the user."""


@dataclass(frozen=True, slots=True)
class LocationQuery:
    kind: str  # coordinates | place | search
    text: str
    lat_deg: float | None = None
    lon_deg: float | None = None
    radius_m: int = DEFAULT_RADIUS_M
    source: str = "typed"

    def wire(self):
        return {
            "kind": self.kind,
            "text": self.text,
            "lat_deg": self.lat_deg,
            "lon_deg": self.lon_deg,
            "radius_m": self.radius_m,
            "source": self.source,
        }


def _clean(value):
    if not isinstance(value, str):
        raise QueryError("Type a place, a coordinate pair or paste a Google Maps link.")
    text = " ".join(CONTROL.sub(" ", value).split())
    if not text:
        raise QueryError("Type a place, a coordinate pair or paste a Google Maps link.")
    if len(text) > 2000:
        raise QueryError("That input is too long. Paste a link, a coordinate pair or a short description.")
    return text


def _coordinates(lat, lon):
    lat, lon = float(lat), float(lon)
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise QueryError("Those coordinates are not finite numbers.")
    if not -90.0 <= lat <= 90.0:
        raise QueryError("Latitude must be between -90 and 90.")
    if not -180.0 <= lon <= 180.0:
        raise QueryError("Longitude must be between -180 and 180.")
    return lat, lon


def validate_radius(value):
    if value is None:
        return DEFAULT_RADIUS_M
    if type(value) not in (int, float) or not math.isfinite(value):
        raise QueryError("Search radius must be a number of metres.")
    radius = int(value)
    if radius not in RADIUS_CHOICES_M:
        raise QueryError(f"Search radius must be one of {', '.join(str(r) for r in RADIUS_CHOICES_M)} m.")
    return radius


def _from_url(text):
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if host in SHORT_HOSTS:
        raise QueryError(
            "Shortened Maps links cannot be resolved here. Open the link in Maps and paste the full "
            "URL from the address bar, or paste the coordinates."
        )
    if not (host in MAPS_HOSTS or host.endswith(".google.com") or host.endswith(".google.ca")):
        raise QueryError("That link is not a Google Maps URL. Paste a Maps link, coordinates or a place.")
    whole = unquote(parsed.path) + "?" + parsed.query + "#" + parsed.fragment
    match = AT_PATTERN.search(whole) or DATA_PATTERN.search(whole)
    if match:
        lat, lon = _coordinates(match.group(1), match.group(2))
        return LocationQuery("coordinates", f"{lat:.6f}, {lon:.6f}", lat, lon, source="google_maps_url")
    query = parse_qs(parsed.query)
    for key in ("q", "ll", "center", "query", "viewpoint"):
        for candidate in query.get(key, []):
            pair = PAIR_PATTERN.match(unquote(candidate))
            if pair:
                lat, lon = _coordinates(pair.group(1), pair.group(2))
                return LocationQuery(
                    "coordinates", f"{lat:.6f}, {lon:.6f}", lat, lon, source="google_maps_url"
                )
    place = re.search(r"/maps/place/([^/@?]+)", unquote(parsed.path))
    if place:
        name = place.group(1).replace("+", " ").strip()[:MAX_TEXT]
        if name:
            return LocationQuery("place", name, source="google_maps_url")
    raise QueryError(
        "That Maps link carries no coordinates. Open the place in Maps and copy the link from the "
        "address bar, or paste the latitude and longitude."
    )


def parse_location(value, radius_m=None):
    """Parse untrusted filmmaker input into a bounded query. Never raises IOError."""
    text = _clean(value)
    radius = validate_radius(radius_m)
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", text):
        return replace(_from_url(text), radius_m=radius)
    if text.lower().startswith(("google.com/maps", "www.google.com/maps", "maps.google.com")):
        return replace(_from_url("https://" + text), radius_m=radius)
    pair = PAIR_PATTERN.match(text)
    if pair:
        lat, lon = _coordinates(pair.group(1), pair.group(2))
        return LocationQuery(
            "coordinates", f"{lat:.6f}, {lon:.6f}", lat, lon, radius_m=radius, source="typed_coordinates"
        )
    if len(text) > MAX_TEXT:
        raise QueryError(f"Keep the location description under {MAX_TEXT} characters.")
    lowered = text.lower()
    kind = "search" if any(hint in lowered for hint in INSTRUCTION_HINTS) or len(text) > 60 else "place"
    return LocationQuery(kind, text, radius_m=radius, source="typed")
