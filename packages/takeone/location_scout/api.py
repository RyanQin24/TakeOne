"""Transport-independent World Scout use cases. The HTTP layer only routes.

The flow the Director walks: search a real area, select a location, build the
metric planning world, generate bounded staging, simulate every candidate on
the real rig, and register the robot locally before anything physical happens.
Each step answers with its own evidence and its own uncertainty.
"""

from __future__ import annotations

import math
import os
import time

from takeone.director.contracts import fields, integer, text

from . import affordances, candidates, digest, fixtures, openmap, planning_world, provider, simulate
from .contracts import GeoAnchor, stable_digest
from .parse import QueryError, parse_location
from .planner import LocationPlanner, normalise_assessments
from .store import WorldStore, valid_id

TILE_KEY_ENVIRONMENT = "GOOGLE_MAPS_BROWSER_KEY"
DEFAULT_SITE_RADIUS_M = 140.0
MIN_SITE_RADIUS_M = 40.0
MAX_SITE_RADIUS_M = 250.0
DEMO_PREFIX = "takeone-demo-"

TILE_ATTRIBUTION = "Google"
TILES_ROOT = "https://tile.googleapis.com/v1/3dtiles/root.json"


class ScoutError(ValueError):
    """A user-facing refusal. The message is shown verbatim in the Director."""


def _default_config():
    return {
        "mode": "live",
        "grounding_enabled": True,
        "timeout_seconds": 20,
        "max_candidates": 8,
        "radius_choices_m": [1000, 3000, 5000],
        "site_radius_m": DEFAULT_SITE_RADIUS_M,
        "open_map_enabled": True,
    }


def load_config():
    from takeone.config import read_json
    from takeone.paths import CONFIGS

    path = CONFIGS / "location-scout.json"
    if not path.exists():
        return _default_config()
    return {**_default_config(), **read_json(path)}


class LocationScoutAPI:
    def __init__(self, store=None, config=None, planner=None):
        self.store = store or WorldStore()
        self.config = config or load_config()
        self._planner = planner
        self._planner_error = None

    # ---------------------------------------------------------------- planner
    @property
    def planner(self):
        if self._planner is None and self._planner_error is None:
            try:
                self._planner = LocationPlanner()
            except (OSError, ValueError) as error:
                self._planner_error = str(error)
        return self._planner

    def planner_status(self):
        planner = self.planner
        if planner is None:
            return {"available": False, "state": "misconfigured", "message": self._planner_error or ""}
        return planner.status()

    # ------------------------------------------------------------------- GET
    def get(self, path):
        if path == "/api/location-scout/status":
            return self.status()
        if path == "/api/location-scout/tiles":
            return self.tiles()
        if path == "/api/location-scout/worlds":
            return {"world_ids": self.store.list_ids()}
        prefix = "/api/location-scout/worlds/"
        if path.startswith(prefix):
            record = self.store.get(valid_id(path.removeprefix(prefix)))
            if record is None:
                raise KeyError("That rehearsal world is no longer cached. Scout the location again.")
            return record
        raise KeyError("World Scout endpoint not found")

    def status(self):
        return {
            "schema_version": 1,
            "grounding": provider.status(self.config),
            "planning_model": self.planner_status(),
            "tiles": self.tiles(),
            "open_map_enabled": bool(self.config.get("open_map_enabled", True)),
            "site_radius_m": self.config.get("site_radius_m", DEFAULT_SITE_RADIUS_M),
            "worlds_cached": len(self.store.list_ids()),
            "evidence_boundary": (
                "Google Photorealistic 3D Tiles are visual context. The planning world is built from "
                "open map geometry, operator measurements or authored proxies, and only it is planned "
                "against."
            ),
        }

    def tiles(self):
        """Browser tile configuration. The key is served at runtime, never committed.

        This must be a separate, HTTP-referrer-restricted browser key scoped to
        the Map Tiles API. The server-side Places key is a different value and
        never leaves this process.
        """
        key = os.environ.get(TILE_KEY_ENVIRONMENT, "")
        return {
            "available": bool(key),
            "key": key,
            "root_url": TILES_ROOT,
            "key_environment": TILE_KEY_ENVIRONMENT,
            "attribution_required": True,
            "attribution_prefix": TILE_ATTRIBUTION,
            "policy": (
                "Display only. Tile content must not be machine interpreted, converted to geometry, "
                "stored beyond permitted HTTP caching, or used for collision or planning."
            ),
            "message": ""
            if key
            else f"Set {TILE_KEY_ENVIRONMENT} to a referrer-restricted browser key with the Map Tiles "
            "API enabled. Without it the planning world still renders.",
        }

    # ------------------------------------------------------------------ POST
    def post(self, path, body):
        if not isinstance(body, dict):
            raise ScoutError("Expected a JSON object.")
        if path == "/api/location-scout/search":
            return self.search(body)
        if path == "/api/location-scout/select":
            return self.select(body)
        if path == "/api/location-scout/staging":
            return self.staging(body)
        if path == "/api/location-scout/simulate":
            return self.simulate_world(body)
        if path == "/api/location-scout/direct":
            return self.direct(body)
        if path == "/api/location-scout/registration":
            return self.registration(body)
        raise KeyError("World Scout endpoint not found")

    def search(self, body):
        fields(body, ("query",), ("radius_m", "mode"))
        try:
            query = parse_location(body["query"], body.get("radius_m"))
        except QueryError as error:
            raise ScoutError(str(error)) from None
        config = dict(self.config)
        if body.get("mode") in ("live", "fixture"):
            config["mode"] = body["mode"]
        result = provider.scout(query, config)
        result["schema_version"] = 1
        return result

    def select(self, body):
        fields(
            body,
            ("candidate_id", "name", "lat_deg", "lon_deg"),
            ("heading_deg", "site_radius_m", "geometry_source", "summary"),
        )
        candidate_id = valid_id(text(body["candidate_id"], "Candidate ID", 120))
        name = text(body["name"], "Location name", 160)
        lat, lon = float(body["lat_deg"]), float(body["lon_deg"])
        heading = float(body.get("heading_deg") or 0.0)
        if not -90 <= lat <= 90 or not -180 <= lon <= 180 or not math.isfinite(heading):
            raise ScoutError("That location has invalid coordinates.")
        radius = float(body.get("site_radius_m") or self.config.get("site_radius_m", DEFAULT_SITE_RADIUS_M))
        if not MIN_SITE_RADIUS_M <= radius <= MAX_SITE_RADIUS_M:
            raise ScoutError(
                f"Site radius must be between {MIN_SITE_RADIUS_M:g} and {MAX_SITE_RADIUS_M:g} m."
            )
        anchor = GeoAnchor(lat_deg=lat, lon_deg=lon, alt_m=None, heading_deg=heading % 360.0)
        world_id = f"{candidate_id}-{stable_digest([lat, lon, heading, radius])[:10]}"

        wanted = body.get("geometry_source") or "auto"
        if wanted not in ("auto", "open_map", "demo_proxy"):
            raise ScoutError("Unknown geometry source.")
        is_demo = candidate_id.startswith(DEMO_PREFIX)
        if wanted == "auto":
            wanted = "demo_proxy" if is_demo else "open_map"

        notes, offer_demo, source = [], False, wanted
        if wanted == "demo_proxy":
            world = planning_world.build(
                anchor,
                fixtures.planning_payload(candidate_id if is_demo else "takeone-demo-site"),
                world_id=world_id,
                site_radius_m=radius,
                place_name=name,
                source="authored_proxy",
                geodetic=False,
                notes=["Authored TakeOne demo proxy geometry. Not a survey and not open map data."],
            )
            notes.append("This planning world is authored demo geometry, not a measurement of this place.")
        elif not self.config.get("open_map_enabled", True):
            world, source = self._empty_world(anchor, world_id, radius, name), "unavailable"
            notes.append("Open map geometry is disabled in the local configuration.")
            offer_demo = True
        else:
            try:
                world = planning_world.fetch_and_build(
                    anchor,
                    world_id=world_id,
                    place_name=name,
                    site_radius_m=radius,
                    timeout_s=float(self.config.get("timeout_seconds", 20)),
                )
            except openmap.OpenMapError as error:
                world = self._empty_world(anchor, world_id, radius, name)
                source = "unavailable"
                offer_demo = True
                notes.append(
                    f"{error} No planning geometry was built for this place, so the whole site is marked "
                    "unknown. Unknown is not clear: nothing can be qualified here until geometry arrives "
                    "or an operator measures the site."
                )

        summary = affordances.site_summary(world, min_clearance_m=1.0)
        record = {
            "schema_version": 1,
            "world_id": world_id,
            "candidate_id": candidate_id,
            "name": name,
            "summary_text": text(body["summary"], "Summary", 400) if body.get("summary") else "",
            "geometry_source": source,
            "notes": notes,
            "offer_demo_proxy": offer_demo,
            "created_monotonic": time.time(),
            "planning_world": world.wire(),
            "affordances": summary,
            "visual_world": {
                "kind": "google_photorealistic_3d_tiles",
                "authority": "visualization_only",
                "metric": False,
                "centre": {"lat_deg": lat, "lon_deg": lon},
                "attribution_required": True,
                "note": (
                    "Drawn for the filmmaker. TakeOne never reads this layer as geometry and never "
                    "derives planning data from it."
                ),
            },
            "uncertainty": self._uncertainty(source, world, registered=False),
            "staging": [],
            "verdicts": [],
            "direction": None,
            "registration": None,
        }
        self.store.put(world_id, record)
        return record

    def _empty_world(self, anchor, world_id, radius, name):
        return planning_world.build(
            anchor,
            {"obstacles": [], "ways": [], "surfaces": [], "attribution": "No coverage"},
            world_id=world_id,
            site_radius_m=radius,
            place_name=name,
            source="authored_proxy",
            geodetic=False,
            notes=["No planning geometry was available for this site."],
        )

    def _uncertainty(self, source, world, *, registered):
        known = {
            "open_map": "OPEN DATA",
            "demo_proxy": "AUTHORED PROXY",
            "unavailable": "UNKNOWN",
        }[source]
        return [
            {"item": "Location selected", "state": "CONFIRMED"},
            {"item": "Coordinates", "state": "GROUNDED"},
            {"item": "Building outlines", "state": known},
            {"item": "Photorealistic appearance", "state": "GOOGLE VISUAL ONLY"},
            {"item": "Ground surface and level", "state": "UNKNOWN"},
            {"item": "Temporary furniture and people", "state": "UNKNOWN"},
            {
                "item": "Robot local origin",
                "state": "OPERATOR CONFIRMED" if registered else "OPERATOR REQUIRED",
            },
            {"item": "Actor route", "state": "PROPOSED"},
            {"item": "Shot trajectory", "state": "SIMULATED" if world else "NOT RUN"},
            {"item": "Real-world cart straightness", "state": "UNQUALIFIED"},
        ]

    # ----------------------------------------------------------- staging/sim
    def _world_record(self, body):
        world_id = valid_id(text(body["world_id"], "World ID", 160))
        record = self.store.get(world_id)
        if record is None:
            raise ScoutError("That rehearsal world is no longer cached. Select the location again.")
        return world_id, record

    def _rebuild(self, record):
        """Rebuild the typed world from its stored wire form."""
        from .contracts import GroundRegion, Obstacle, PlanningWorld, UnknownRegion, planning_evidence

        body = record["planning_world"]
        anchor = GeoAnchor.parse(body["geo_anchor"])

        def evidence_of(item):
            return planning_evidence(item["evidence"]["source"], note=item["evidence"].get("note", ""))

        obstacles = tuple(
            Obstacle(
                obstacle_id=item["obstacle_id"],
                kind=item["kind"],
                footprint_polygon_m=[tuple(point) for point in item["footprint_polygon_m"]],
                min_z_m=item["min_z_m"],
                max_z_m=item["max_z_m"],
                evidence=evidence_of(item),
                confidence=item.get("confidence", "open_data_outline"),
            )
            for item in body["static_obstacles"]
        )

        def region(item):
            return GroundRegion(
                region_id=item["region_id"],
                polygon_m=[tuple(point) for point in item["polygon_m"]],
                surface_kind=item["surface_kind"],
                evidence=evidence_of(item),
                walkable=item.get("walkable", True),
            )

        return PlanningWorld(
            world_id=body["world_id"],
            revision=body["revision"],
            geo_anchor=anchor,
            site_radius_m=body["site_radius_m"],
            ground_regions=tuple(region(item) for item in body["ground_regions"]),
            walkable_regions=tuple(region(item) for item in body["walkable_regions"]),
            static_obstacles=obstacles,
            unknown_regions=tuple(
                UnknownRegion(
                    region_id=item["region_id"],
                    polygon_m=[tuple(point) for point in item["polygon_m"]],
                    reason=item.get("reason", "no_open_map_coverage"),
                )
                for item in body["unknown_regions"]
            ),
            provenance=body.get("provenance", {}),
        )

    def staging(self, body):
        fields(body, ("world_id",), ("travel_m", "duration_s", "limit", "templates"))
        world_id, record = self._world_record(body)
        world = self._rebuild(record)
        travel = float(body.get("travel_m") or candidates.DEFAULT_TRAVEL_M)
        duration = float(body.get("duration_s") or 6.0)
        if not 0.5 <= travel <= 20 or not 1.0 <= duration <= 60:
            raise ScoutError("Ask for 0.5–20 m of travel over 1–60 seconds.")
        limit = integer(body.get("limit") or candidates.MAX_CANDIDATES, "Candidate limit", 1, 12)
        templates = body.get("templates")
        if templates is not None:
            if not isinstance(templates, list) or not all(t in candidates.BY_TEMPLATE for t in templates):
                raise ScoutError("Unknown camera movement requested.")
        produced = candidates.generate(
            world, travel_m=travel, duration_s=duration, limit=limit, templates=templates or None
        )
        record["staging"] = [candidate.wire() for candidate in produced]
        record["staging_request"] = {"travel_m": travel, "duration_s": duration, "limit": limit}
        record["verdicts"] = []
        self.store.put(world_id, record)
        return {
            "world_id": world_id,
            "staging": record["staging"],
            "note": (
                "These are proposals. Cinematic suitability is a judgement; physical feasibility is not "
                "evaluated until each one is compiled and simulated."
            ),
        }

    def simulate_world(self, body):
        fields(body, ("world_id",), ("limit", "budget_s", "subject_height_m"))
        world_id, record = self._world_record(body)
        if not record.get("staging"):
            raise ScoutError("Generate staging candidates before simulating them.")
        world = self._rebuild(record)
        request = record.get("staging_request", {})
        produced = candidates.generate(
            world,
            travel_m=request.get("travel_m", candidates.DEFAULT_TRAVEL_M),
            duration_s=request.get("duration_s", 6.0),
            limit=request.get("limit", candidates.MAX_CANDIDATES),
        )
        limit = integer(body.get("limit") or simulate.MAX_SIMULATED, "Simulation limit", 1, 12)
        budget = float(body.get("budget_s") or 120.0)
        height = float(body.get("subject_height_m") or 1.72)
        if not 0.8 <= height <= 2.2:
            raise ScoutError("Subject height must be between 0.8 and 2.2 m.")
        started = time.monotonic()
        verdicts = simulate.evaluate_all(
            produced, world, limit=limit, budget_s=min(budget, 300.0), subject_height_m=height
        )
        record["verdicts"] = [verdict.wire() for verdict in verdicts]
        record["simulated_seconds"] = round(time.monotonic() - started, 2)
        record["uncertainty"] = self._uncertainty(
            record["geometry_source"], world, registered=bool(record.get("registration"))
        )
        self.store.put(world_id, record)
        feasible = [verdict for verdict in record["verdicts"] if verdict["feasible"]]
        return {
            "world_id": world_id,
            "verdicts": record["verdicts"],
            "feasible_count": len(feasible),
            "rejected_count": len(record["verdicts"]) - len(feasible),
            "elapsed_s": record["simulated_seconds"],
            "authority": (
                "Compiled and simulated with the same rig model, IK, joint limits, cart response and "
                "lens curve Shot Studio uses. A pass is a simulated pass, not a physical qualification."
            ),
        }

    # --------------------------------------------------------------- planner
    def direct(self, body):
        fields(body, ("kind",), ("world_id", "candidates", "query", "story", "confirm", "estimate_only"))
        kind = body["kind"]
        if kind not in ("location_assessment", "location_staging"):
            raise ScoutError("Unknown direction request.")
        planner = self.planner
        if planner is None:
            raise ScoutError(self._planner_error or "The location planner is not configured.")
        story = body.get("story") if isinstance(body.get("story"), dict) else {}
        if kind == "location_assessment":
            supplied = body.get("candidates")
            if not isinstance(supplied, list) or not supplied:
                raise ScoutError("Scout some locations before asking for a cinematic read.")
            payload = digest.location_digest(supplied, query=body.get("query") or {}, story=story)
            allowed = {entry["candidate_id"] for entry in supplied}
        else:
            world_id, record = self._world_record(body)
            if not record.get("staging"):
                raise ScoutError("Generate staging candidates before asking for direction.")
            payload = digest.staging_digest(
                record["affordances"],
                record["staging"],
                location_name=record["name"],
                story=story,
                movement_catalog=[
                    {"template_id": entry["template_id"], "relation": entry["relation"]}
                    for entry in candidates.MOVEMENTS
                ],
            )
            allowed = {entry["candidate_id"] for entry in record["staging"]}
        estimate = planner.estimate(payload, kind)
        if body.get("estimate_only") or not body.get("confirm"):
            return {"estimate": estimate, "sent": False, "digest_preview": payload}
        result = planner.generate(payload, kind)
        document = result.document
        answer = {
            "sent": True,
            "estimate": estimate,
            "kind": kind,
            "provenance": result.provenance,
            "document": document,
            "authority": "cinematic_judgement_only",
        }
        if kind == "location_assessment":
            answer["ranked"] = normalise_assessments(document, allowed)
        else:
            world_id, record = self._world_record(body)
            answer["priorities"] = [
                entry for entry in document.get("staging_priorities", []) if entry["candidate_id"] in allowed
            ]
            record["direction"] = answer
            self.store.put(world_id, record)
        return answer

    # ---------------------------------------------------------- registration
    def registration(self, body):
        """The step that makes a preview into a physical setup. Operator only.

        A Google-world preview is not localisation. Nothing physical may happen
        until a person has put the cart on a mark, confirmed which way it faces
        and confirmed the actor's mark. GPS is never that answer.
        """
        fields(body, ("world_id", "origin_m", "heading_deg"), ("actor_mark_m", "confirmed_by", "note"))
        world_id, record = self._world_record(body)
        origin = body["origin_m"]
        actor_mark = body.get("actor_mark_m")
        for point, label in ((origin, "Robot origin"), (actor_mark, "Actor mark")):
            if point is None:
                continue
            if (
                not isinstance(point, list)
                or len(point) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 300 for v in point)
            ):
                raise ScoutError(f"{label} needs two finite metre coordinates.")
        heading = float(body["heading_deg"])
        if not math.isfinite(heading):
            raise ScoutError("Confirm which way the cart is facing.")
        if not body.get("confirmed_by"):
            raise ScoutError("Local registration must be confirmed by a person standing at the rig.")
        record["registration"] = {
            "origin_m": [float(v) for v in origin],
            "heading_deg": heading % 360.0,
            "actor_mark_m": [float(v) for v in actor_mark] if actor_mark else None,
            "confirmed_by": text(body["confirmed_by"], "Confirmed by", 80),
            "note": text(body["note"], "Note", 300) if body.get("note") else "",
            "method": "operator_placed_mark",
            "recorded_at": time.time(),
            "claim": (
                "The cart's scene origin and heading were set by an operator at the rig. This is the "
                "only accepted physical localisation. Satellite coordinates are not used to drive the "
                "robot and are not accurate enough to."
            ),
        }
        record["uncertainty"] = self._uncertainty(record["geometry_source"], True, registered=True)
        self.store.put(world_id, record)
        return {"world_id": world_id, "registration": record["registration"]}


def status_only(config=None):
    return LocationScoutAPI(config=config).status()
