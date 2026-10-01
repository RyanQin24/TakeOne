"""The Sol planner contract: allowlist, budget, digest shape and authority.

The model is a planner. These tests pin the two claims that make that true:
its request carries no geometry, and its response schema has no field in which
a coordinate, a joint value or a wheel command could travel.
"""

import json
import unittest

from takeone.director.provider import MODELS, PlanningError, ResponsesPlanner
from takeone.location_scout import candidates, digest, fixtures, planning_world
from takeone.location_scout.affordances import site_summary
from takeone.location_scout.contracts import GeoAnchor
from takeone.location_scout.planner import (
    RATINGS,
    LocationPlanner,
    load_config,
    location_schema,
    normalise_assessments,
    staging_schema,
)

WATERLOO = (43.466752, -80.5404672)


def demo_world(candidate="takeone-demo-site", radius=60.0):
    anchor = GeoAnchor(lat_deg=WATERLOO[0], lon_deg=WATERLOO[1], alt_m=334.0)
    return planning_world.build(
        anchor,
        fixtures.planning_payload(candidate),
        world_id=candidate,
        site_radius_m=radius,
        source="authored_proxy",
        geodetic=False,
    )


class ModelAllowlist(unittest.TestCase):
    def config(self, **overrides):
        return {**load_config(), **overrides}

    def test_sol_high_is_the_configured_location_planner(self):
        config = load_config()
        self.assertEqual(config["model"], "gpt-5.6-sol")
        self.assertEqual(config["reasoning_effort"], "high")
        planner = LocationPlanner(api_key="test-key")
        self.assertEqual(planner.status()["model"], "gpt-5.6-sol")
        self.assertEqual(planner.status()["reasoning_effort"], "high")

    def test_the_catalog_prices_match_the_published_rate(self):
        sol = MODELS["gpt-5.6-sol"]
        self.assertEqual(sol["input_microusd_per_token"], 4.0)
        self.assertEqual(sol["output_microusd_per_token"], 20.0)
        self.assertIn("openai_docs", sol["prices_source"])

    def test_the_script_planner_still_selects_luna(self):
        """World Scout's model change must not move Director script planning."""
        from takeone.config import read_json
        from takeone.paths import CONFIGS

        director = read_json(CONFIGS / "director-planning.json")
        self.assertEqual(director["model"], "gpt-5.6-luna")
        self.assertEqual(ResponsesPlanner(config=director, api_key="k").selected_model, "gpt-5.6-luna")

    def test_an_unreviewed_model_or_effort_is_refused(self):
        for overrides in (
            {"model": "gpt-5.6-terra"},
            {"model": "anything-at-all"},
            {"reasoning_effort": "ultra"},
        ):
            with self.assertRaises(ValueError, msg=str(overrides)):
                ResponsesPlanner(config=self.config(**overrides), api_key="k")

    def test_configuration_cannot_underprice_the_selected_model(self):
        with self.assertRaises(ValueError):
            ResponsesPlanner(config=self.config(input_microusd_per_token=0.2), api_key="k")
        with self.assertRaises(ValueError):
            ResponsesPlanner(config=self.config(output_microusd_per_token=1.2), api_key="k")

    def test_the_request_is_priced_before_anything_is_transmitted(self):
        planner = LocationPlanner(api_key="k")
        payload = {"question": "location_assessment", "candidates": [], "story": {}}
        estimate = planner.estimate(payload, "location_assessment")
        self.assertTrue(estimate["within_budget"])
        self.assertLessEqual(estimate["reserved_microusd"], estimate["request_budget_microusd"])
        expected = (estimate["request_bytes"] + 1000) * 4.0 + load_config()["max_output_tokens"] * 20.0
        self.assertAlmostEqual(estimate["reserved_microusd"], expected, delta=1.0)

    def test_an_oversized_payload_is_refused_before_the_network(self):
        planner = LocationPlanner(api_key="k")
        payload = {"question": "location_assessment", "filler": "x" * 40000}
        with self.assertRaises(PlanningError) as caught:
            planner.request(payload, "location_assessment")
        self.assertEqual(caught.exception.code, "input_too_large")

    def test_a_budget_that_cannot_cover_the_worst_case_is_refused(self):
        planner = LocationPlanner(config={**load_config(), "request_budget_microusd": 1000}, api_key="k")
        with self.assertRaises(PlanningError) as caught:
            planner.request({"question": "location_assessment"}, "location_assessment")
        self.assertEqual(caught.exception.code, "request_budget")

    def test_only_location_questions_are_answered_by_this_planner(self):
        planner = LocationPlanner(api_key="k")
        with self.assertRaises(PlanningError):
            planner.request({}, "creative_plan")

    def test_nothing_is_transmitted_without_a_key(self):
        planner = LocationPlanner(api_key="")
        self.assertFalse(planner.status()["available"])
        with self.assertRaises(PlanningError) as caught:
            planner.generate({"question": "location_assessment"}, "location_assessment")
        self.assertEqual(caught.exception.code, "provider_unavailable")


class RequestShape(unittest.TestCase):
    def body(self, kind="location_staging"):
        world = demo_world()
        summary = site_summary(world)
        staging = [c.wire() for c in candidates.generate(world, travel_m=4.0, duration_s=6.0)]
        payload = digest.staging_digest(
            summary, staging, location_name="demo", story={"logline": "a student arrives"}
        )
        raw, _ = LocationPlanner(api_key="k").request(payload, kind)
        return json.loads(raw), payload

    def test_the_request_is_strict_json_schema_with_no_tools(self):
        body, _ = self.body()
        self.assertEqual(body["model"], "gpt-5.6-sol")
        self.assertEqual(body["reasoning"], {"effort": "high"})
        self.assertIs(body["store"], False)
        self.assertNotIn("tools", body)
        fmt = body["text"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertIs(fmt["strict"], True)
        self.assertIs(fmt["schema"]["additionalProperties"], False)

    def test_no_geometry_reaches_the_model(self):
        """The digest carries counts and lengths. Never rings, meshes or tiles."""
        body, payload = self.body()
        text = body["input"]
        for forbidden in (
            "polygon_m",
            "footprint_polygon_m",
            "start_m",
            "end_m",
            "vertices",
            "lat_deg",
            "lon_deg",
            "google_photorealistic_tiles",
            "tile",
        ):
            self.assertNotIn(forbidden, text, f"{forbidden} must not be sent to the planner")

        def coordinate_pairs(value):
            """Any list of two numbers anywhere in the payload is a position."""
            if isinstance(value, dict):
                return sum(coordinate_pairs(item) for item in value.values())
            if isinstance(value, list):
                numeric = [item for item in value if isinstance(item, (int, float))]
                found = 1 if len(value) == 2 and len(numeric) == 2 else 0
                return found + sum(coordinate_pairs(item) for item in value)
            return 0

        # lens_range_mm is the rig's own two-ended focal range, not a position.
        rig_only = {key: value for key, value in payload.items() if key != "rig"}
        self.assertEqual(coordinate_pairs(rig_only), 0, "no position may reach the planner")
        world = payload["world"]
        self.assertIsInstance(world["known_obstacles"], int)
        self.assertTrue(all("polygon_m" not in axis for axis in world["candidate_axes"]))

    def test_the_request_stays_inside_its_byte_bound(self):
        body, _ = self.body()
        self.assertLess(len(json.dumps(body)), load_config()["max_request_bytes"])

    def test_the_response_schema_has_no_field_that_could_carry_a_command(self):
        """Sol may rank and explain. Every leaf is prose, an enum or a rank."""
        banned = {
            "position",
            "joint",
            "servo",
            "pwm",
            "wheel",
            "counts",
            "velocity",
            "coordinate",
            "metres",
            "meters",
            "radians",
            "seconds",
            "focal",
            "speed",
            "angle",
            "heading",
            "duration",
            "command",
        }

        def leaves(schema, name="root"):
            kind = schema.get("type")
            if kind == "object":
                for key, child in schema["properties"].items():
                    yield from leaves(child, key)
            elif kind == "array":
                yield from leaves(schema["items"], name)
            else:
                yield name, schema

        for schema in (location_schema(), staging_schema()):
            for name, leaf in leaves(schema):
                words = set(name.split("_"))
                self.assertFalse(words & banned, f"{name} could carry a physical command")
                if leaf["type"] == "integer":
                    # The one number the model may return is an ordering rank,
                    # bounded to the number of candidates it was given.
                    self.assertEqual(name, "rank")
                    self.assertLessEqual(leaf["maximum"], 12)
                else:
                    self.assertEqual(leaf["type"], "string")
                    if "enum" in leaf:
                        self.assertEqual(leaf["enum"], RATINGS)
                    else:
                        self.assertLessEqual(leaf["maxLength"], 600)

    def test_the_instructions_forbid_physical_claims(self):
        body, _ = self.body()
        instructions = body["instructions"].lower()
        self.assertIn("not a robot controller", instructions)
        self.assertIn("never claim", instructions)
        self.assertIn("unknown ground is unknown", instructions)


class Normalisation(unittest.TestCase):
    def entry(self, candidate_id, rating):
        keys = (
            "story_fit",
            "visual_character",
            "background_depth",
            "leading_lines",
            "reveal_potential",
            "tracking_shot_potential",
            "wide_shot_potential",
            "actor_route_quality",
        )
        return {"candidate_id": candidate_id, "why": "because", **{key: rating for key in keys}}

    def test_code_ranks_and_the_model_only_judges(self):
        document = {
            "location_assessments": [self.entry("b", "fair"), self.entry("a", "excellent")],
            "why_this_location": "",
            "cinematic_intent": "",
        }
        ranked = normalise_assessments(document, {"a", "b"})
        self.assertEqual([entry["candidate_id"] for entry in ranked], ["a", "b"])
        self.assertGreater(ranked[0]["cinematic_suitability"], ranked[1]["cinematic_suitability"])

    def test_feasibility_is_never_claimed_before_simulation(self):
        document = {
            "location_assessments": [self.entry("a", "excellent")],
            "why_this_location": "",
            "cinematic_intent": "",
        }
        ranked = normalise_assessments(document, {"a"})
        self.assertEqual(ranked[0]["physical_feasibility"], "not_yet_evaluated")
        self.assertEqual(ranked[0]["cinematic_band"], "high")

    def test_a_location_the_model_invented_is_dropped(self):
        document = {
            "location_assessments": [self.entry("ghost", "excellent"), self.entry("a", "good")],
            "why_this_location": "",
            "cinematic_intent": "",
        }
        ranked = normalise_assessments(document, {"a"})
        self.assertEqual([entry["candidate_id"] for entry in ranked], ["a"])


if __name__ == "__main__":
    unittest.main()
