"""Candidate discovery: a live Google path, an offline fixture path, one shape.

``scout(query, config)`` always answers. When the key is missing, the network is
down, Google refuses or the search returns nothing, it falls back to the stored
fixture and says so in ``mode`` and ``notes`` rather than failing the Director.
A live demo that loses Wi-Fi keeps working; it just stops claiming to be live.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from . import fixtures, grounding_google
from .geodesy import bearing_deg, great_circle_m
from .parse import LocationQuery

KEY_ENVIRONMENT = "GOOGLE_MAPS_API_KEY"
MIN_CANDIDATES = 5
MAX_CANDIDATES = 8


@dataclass(frozen=True, slots=True)
class GroundedCandidate:
    """One real place, as reported by a grounding provider. Facts only.

    Nothing here is a cinematic judgement and nothing here is a physical claim.
    Scoring happens later; feasibility happens only after simulation.
    """

    candidate_id: str
    name: str
    lat_deg: float
    lon_deg: float
    address: str = ""
    primary_type: str = ""
    types: tuple = ()
    summary: str = ""
    maps_uri: str = ""
    straight_line_m: float = 0.0
    bearing_deg: float = 0.0
    source: str = "google_places"

    def wire(self):
        return {
            "candidate_id": self.candidate_id,
            "name": self.name,
            "lat_deg": self.lat_deg,
            "lon_deg": self.lon_deg,
            "address": self.address,
            "primary_type": self.primary_type,
            "types": list(self.types),
            # Google's own words about the place. Display data, never planning data.
            "summary": self.summary,
            "maps_uri": self.maps_uri,
            "straight_line_m": round(self.straight_line_m, 1),
            "distance_basis": "straight_line_not_walking_route",
            "bearing_deg": round(self.bearing_deg, 1),
            "source": self.source,
            "attribution": grounding_google.ATTRIBUTION
            if self.source == "google_places"
            else "TakeOne stored demo fixture",
        }


def _candidate(record, origin, index, source):
    lat, lon = record["lat_deg"], record["lon_deg"]
    distance = great_circle_m(origin[0], origin[1], lat, lon) if origin else 0.0
    heading = bearing_deg(origin[0], origin[1], lat, lon) if origin else 0.0
    return GroundedCandidate(
        candidate_id=record.get("place_id") or f"{source}-{index}",
        name=record["name"],
        lat_deg=lat,
        lon_deg=lon,
        address=record.get("address", ""),
        primary_type=record.get("primary_type", ""),
        types=tuple(record.get("types", ())),
        summary=record.get("summary", ""),
        maps_uri=record.get("maps_uri", ""),
        straight_line_m=distance,
        bearing_deg=heading,
        source=source,
    )


def api_key(explicit=None):
    return explicit if explicit is not None else os.environ.get(KEY_ENVIRONMENT, "")


def status(config, *, key=None):
    resolved = api_key(key)
    return {
        "live_available": bool(resolved) and bool(config.get("grounding_enabled", True)),
        "key_environment": KEY_ENVIRONMENT,
        "fixture_available": fixtures.available(),
        "default_mode": config.get("mode", "live"),
        "radius_choices_m": list(config.get("radius_choices_m", (1000, 3000, 5000))),
        "message": "Live place search is checked when you scout."
        if resolved
        else f"Set {KEY_ENVIRONMENT} before starting the server to search real places. "
        "The stored demo location still works without it.",
    }


def _live(query: LocationQuery, config, key):
    timeout = float(config.get("timeout_seconds", 20))
    limit = int(config.get("max_candidates", MAX_CANDIDATES))
    origin = (query.lat_deg, query.lon_deg) if query.lat_deg is not None else None
    if query.kind == "coordinates":
        body = grounding_google.search_nearby_body(query.lat_deg, query.lon_deg, query.radius_m, limit=limit)
        result = grounding_google.post("/v1/places:searchNearby", body, key, timeout_s=timeout)
        records = grounding_google.read_places(result)
    else:
        body = grounding_google.search_text_body(
            query.text, limit=limit, lat=query.lat_deg, lon=query.lon_deg, radius_m=query.radius_m
        )
        result = grounding_google.post("/v1/places:searchText", body, key, timeout_s=timeout)
        records = grounding_google.read_places(result)
        if records and origin is None:
            origin = (records[0]["lat_deg"], records[0]["lon_deg"])
        # A named area gives one pin. Widen it into a shortlist around that pin.
        if origin and len(records) < MIN_CANDIDATES:
            nearby = grounding_google.post(
                "/v1/places:searchNearby",
                grounding_google.search_nearby_body(origin[0], origin[1], query.radius_m, limit=limit),
                key,
                timeout_s=timeout,
            )
            seen = {record["place_id"] for record in records}
            for record in grounding_google.read_places(nearby):
                if record["place_id"] not in seen and len(records) < limit:
                    records.append(record)
    if origin and query.kind != "coordinates":
        records = [
            r for r in records if great_circle_m(*origin, r["lat_deg"], r["lon_deg"]) <= query.radius_m * 1.35
        ]
    return origin, records[:limit]


def scout(query: LocationQuery, config, *, key=None):
    """Return a bounded shortlist of real candidate locations, live or stored."""
    resolved = api_key(key)
    notes, mode = [], "live"
    origin, records = None, []
    if config.get("mode") == "fixture":
        mode, notes = "fixture", ["Demo fixture mode is selected in the local configuration."]
    elif not resolved:
        mode = "fixture"
        notes = [f"No {KEY_ENVIRONMENT} on this server, so the stored demo location is being used."]
    elif not config.get("grounding_enabled", True):
        mode, notes = "fixture", ["Live place grounding is disabled in the local configuration."]
    else:
        try:
            origin, records = _live(query, config, resolved)
            if not records:
                mode = "fixture"
                notes = ["Google returned no places for that search, so the stored demo location is shown."]
        except grounding_google.GoogleGroundingError as error:
            mode = "fixture"
            notes = [f"{error}. The stored demo location is shown instead."]
    if mode == "fixture":
        origin, records = fixtures.candidate_records(query)
    source = "google_places" if mode == "live" else "takeone_fixture"
    candidates = [_candidate(record, origin, i, source) for i, record in enumerate(records)]
    candidates.sort(key=lambda c: (c.straight_line_m, c.name))
    return {
        "mode": mode,
        "notes": notes,
        "origin": {"lat_deg": origin[0], "lon_deg": origin[1]} if origin else None,
        "query": query.wire(),
        "candidates": [candidate.wire() for candidate in candidates],
        "attribution": grounding_google.ATTRIBUTION
        if mode == "live"
        else "TakeOne stored demo fixture (OpenStreetMap contributors, ODbL)",
        "evidence_boundary": (
            "Place identity, coordinates and summaries are Google Maps data shown to the filmmaker. "
            "None of it is metric planning geometry."
        ),
    }
