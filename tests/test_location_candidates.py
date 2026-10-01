"""Staging enumeration and the rule that simulation, not scoring, decides.

These tests run the real compiler through ``previs.templates`` and need the
simulation extra, exactly like the other previs tests.
"""

import unittest

from takeone.location_scout import candidates, fixtures, planning_world, simulate
from takeone.location_scout.affordances import WorldIndex, site_summary, tracking_axes
from takeone.location_scout.api import LocationScoutAPI
from takeone.location_scout.contracts import GeoAnchor
from takeone.location_scout.store import WorldStore

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


class Affordances(unittest.TestCase):
    def test_axes_are_found_on_walkable_ground_and_ranked_by_length(self):
        axes = tracking_axes(demo_world(), min_clearance_m=1.0)
        self.assertTrue(axes)
        lengths = [axis.usable_length_m for axis in axes]
        self.assertEqual(lengths, sorted(lengths, reverse=True))
        for axis in axes:
            self.assertGreaterEqual(axis.min_clearance_m, 1.0)
            self.assertEqual(axis.kind, "tracking_axis")
            self.assertIn("nominal", axis.wire()["basis"])

    def test_enumeration_is_deterministic(self):
        first = [axis.wire() for axis in tracking_axes(demo_world())]
        second = [axis.wire() for axis in tracking_axes(demo_world())]
        self.assertEqual(first, second)

    def test_background_depth_never_claims_beyond_the_site(self):
        world = demo_world(radius=60.0)
        summary = site_summary(world)
        self.assertLessEqual(summary["best_background_depth_m"], summary["background_depth_limit_m"])

    def test_a_narrow_corridor_yields_less_room_than_an_open_plaza(self):
        narrow = site_summary(demo_world("takeone-demo-walkway"))
        open_site = site_summary(demo_world("takeone-demo-site"))
        self.assertLess(narrow["turning_room_m"], open_site["turning_room_m"])

    def test_a_point_on_known_surface_is_not_reported_unknown(self):
        world = demo_world()
        index = WorldIndex(world)
        for axis in tracking_axes(world):
            self.assertFalse(index.is_unknown(axis.start_m))


class CandidateSearch(unittest.TestCase):
    def test_the_candidate_count_is_bounded_and_deduplicated(self):
        produced = candidates.generate(demo_world(), travel_m=4.0, duration_s=6.0, limit=12)
        self.assertLessEqual(len(produced), 12)
        keys = [(c.axis_id, c.template_id, round(c.standoff_m, 1)) for c in produced]
        self.assertEqual(len(keys), len(set(keys)))

    def test_enumeration_is_deterministic(self):
        first = [c.wire() for c in candidates.generate(demo_world(), travel_m=4.0, duration_s=6.0)]
        second = [c.wire() for c in candidates.generate(demo_world(), travel_m=4.0, duration_s=6.0)]
        self.assertEqual(first, second)

    def test_a_narrow_corridor_rejects_the_staging_that_needs_side_room(self):
        produced = candidates.generate(demo_world("takeone-demo-walkway"), travel_m=4.0, duration_s=6.0)
        rejected = [c for c in produced if c.rejected_reason]
        self.assertTrue(rejected, "a 3 m corridor cannot hold every staging")
        self.assertTrue(any("cart" in c.rejected_reason.lower() for c in rejected))

    def test_the_cart_pace_policy_is_never_exceeded_by_a_proposal(self):
        produced = candidates.generate(demo_world(), travel_m=4.0, duration_s=2.0)
        for candidate in produced:
            self.assertLessEqual(candidate.pace_m_s, candidates.CART_PACE_MAX_M_S + 1e-9)
            self.assertGreaterEqual(candidate.pace_m_s, candidates.CART_PACE_MIN_M_S - 1e-9)
            self.assertTrue(candidate.pace_clipped, "4 m in 2 s must be reported as clipped")

    def test_template_settings_only_name_movements_the_rig_owns(self):
        from takeone.previs.templates import BY_ID, validate_settings

        for candidate in candidates.generate(demo_world(), travel_m=4.0, duration_s=6.0):
            settings = candidate.template_settings()
            self.assertIn(settings["template_id"], BY_ID)
            validate_settings(settings)


class SimulationIsTheAuthority(unittest.TestCase):
    def test_a_feasible_candidate_carries_achieved_numbers_not_requested_ones(self):
        world = demo_world()
        produced = candidates.generate(world, travel_m=4.0, duration_s=6.0, limit=4)
        verdicts = simulate.evaluate_all(produced, world, limit=3, budget_s=180)
        passing = [verdict for verdict in verdicts if verdict.feasible]
        self.assertTrue(passing, "the open demo site must hold at least one shot")
        achieved = passing[0].achieved
        self.assertTrue(achieved["within_joint_ranges"])
        self.assertFalse(achieved["lens_clamped"])
        self.assertGreater(achieved["shot_duration_s"], 0)
        self.assertNotEqual(achieved["cart_travel_m"], achieved["requested_travel_m"])
        self.assertFalse(achieved["physical_path_verified"], "simulation is never physical proof")
        self.assertIn("registration", passing[0].wire()["physical_status"])

    def test_a_high_score_can_never_rescue_a_hard_constraint(self):
        world = demo_world()
        candidate = candidates.generate(world, travel_m=4.0, duration_s=6.0, limit=1)[0]
        verdict = simulate.evaluate(candidate, world)
        self.assertTrue(verdict.feasible)
        verdict.failures.append("invented failure")
        self.assertFalse(verdict.feasible)
        self.assertEqual(verdict.total, 0.0)
        self.assertEqual(verdict.wire()["physical_feasibility"], "rejected")

    def test_a_candidate_the_world_rejected_is_never_compiled_but_is_kept(self):
        world = demo_world("takeone-demo-walkway")
        produced = candidates.generate(world, travel_m=4.0, duration_s=6.0)
        rejected = next(c for c in produced if c.rejected_reason)
        verdict = simulate.evaluate(rejected, world)
        self.assertFalse(verdict.compiled)
        self.assertFalse(verdict.feasible)
        self.assertEqual(verdict.failures[0], rejected.rejected_reason)

    def test_the_simulation_budget_marks_the_rest_not_simulated_rather_than_failed(self):
        world = demo_world()
        produced = candidates.generate(world, travel_m=4.0, duration_s=6.0, limit=8)
        verdicts = simulate.evaluate_all(produced, world, limit=1, budget_s=180)
        skipped = [verdict for verdict in verdicts if verdict.skipped]
        self.assertTrue(skipped)
        self.assertEqual(skipped[0].wire()["physical_feasibility"], "not_simulated")

    def test_the_achieved_cart_path_is_screened_against_the_metre_world(self):
        world = demo_world()
        candidate = candidates.generate(world, travel_m=4.0, duration_s=6.0, limit=1)[0]
        verdict = simulate.evaluate(candidate, world)
        screen = verdict.achieved["cart_path_screen"]
        self.assertIn("min_clearance_m", screen)
        self.assertIn("required_m", screen)
        self.assertTrue(screen["clear"])
        self.assertGreater(verdict.achieved["frame_count"], 10)


class ScoutAPIFlow(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.api = LocationScoutAPI(store=WorldStore(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def scouted(self):
        search = self.api.post("/api/location-scout/search", {"query": "43.466752, -80.5404672"})
        first = search["candidates"][0]
        return self.api.post(
            "/api/location-scout/select",
            {
                "candidate_id": first["candidate_id"],
                "name": first["name"],
                "lat_deg": first["lat_deg"],
                "lon_deg": first["lon_deg"],
                "site_radius_m": 60,
            },
        )

    def test_the_offline_flow_reaches_a_simulated_shot(self):
        record = self.scouted()
        self.assertEqual(record["geometry_source"], "demo_proxy")
        self.assertTrue(record["planning_world"]["unknown_regions"])
        self.assertEqual(record["visual_world"]["authority"], "visualization_only")
        self.assertFalse(record["visual_world"]["metric"])
        staging = self.api.post("/api/location-scout/staging", {"world_id": record["world_id"]})
        self.assertTrue(staging["staging"])
        result = self.api.post("/api/location-scout/simulate", {"world_id": record["world_id"], "limit": 2})
        self.assertGreaterEqual(result["feasible_count"], 1)
        self.assertIn("simulated pass", result["authority"])

    def test_uncertainty_always_states_what_is_unknown(self):
        record = self.scouted()
        items = {entry["item"]: entry["state"] for entry in record["uncertainty"]}
        self.assertEqual(items["Robot local origin"], "OPERATOR REQUIRED")
        self.assertEqual(items["Photorealistic appearance"], "GOOGLE VISUAL ONLY")
        self.assertEqual(items["Real-world cart straightness"], "UNQUALIFIED")
        self.assertEqual(items["Ground surface and level"], "UNKNOWN")

    def test_registration_needs_a_person_and_then_changes_the_record(self):
        record = self.scouted()
        with self.assertRaises(Exception):
            self.api.post(
                "/api/location-scout/registration",
                {"world_id": record["world_id"], "origin_m": [0, 0], "heading_deg": 0},
            )
        answer = self.api.post(
            "/api/location-scout/registration",
            {
                "world_id": record["world_id"],
                "origin_m": [0.0, -2.6],
                "heading_deg": 12.0,
                "confirmed_by": "Operator",
            },
        )
        self.assertEqual(answer["registration"]["method"], "operator_placed_mark")
        self.assertIn("not used to drive the robot", answer["registration"]["claim"])
        stored = self.api.get(f"/api/location-scout/worlds/{record['world_id']}")
        items = {entry["item"]: entry["state"] for entry in stored["uncertainty"]}
        self.assertEqual(items["Robot local origin"], "OPERATOR CONFIRMED")

    def test_unknown_world_ids_and_bad_bodies_are_refused(self):
        for body in (
            {"world_id": "../../etc/passwd"},
            {"world_id": "not-a-real-world"},
        ):
            with self.assertRaises(Exception):
                self.api.post("/api/location-scout/staging", body)
        with self.assertRaises(Exception):
            self.api.post("/api/location-scout/search", {"query": "https://maps.app.goo.gl/x"})

    def test_a_site_with_no_planning_geometry_stays_unknown(self):
        record = self.api.post(
            "/api/location-scout/select",
            {
                "candidate_id": "real-place",
                "name": "Somewhere real",
                "lat_deg": 43.47,
                "lon_deg": -80.54,
                "site_radius_m": 50,
                "geometry_source": "open_map",
            },
        )
        if record["geometry_source"] == "unavailable":
            self.assertEqual(len(record["planning_world"]["walkable_regions"]), 0)
            self.assertTrue(record["planning_world"]["unknown_regions"])
            self.assertTrue(record["offer_demo_proxy"])
            self.assertIn("Unknown is not clear", " ".join(record["notes"]))
            staging = self.api.post("/api/location-scout/staging", {"world_id": record["world_id"]})
            self.assertEqual(staging["staging"], [])


if __name__ == "__main__":
    unittest.main()
