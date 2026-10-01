"""Cinematic motifs resolve to existing, deterministic TakeOne motion. No device I/O."""

import json
import unittest

from takeone.director.cinematic_motifs import MOTIFS, catalog, resolve
from takeone.previs.templates import BY_ID, compile_template, validate_settings
from takeone.previs.travel_review import review_travel


class CinematicMotifTests(unittest.TestCase):
    def test_catalog_is_story_level_and_keeps_existing_physical_templates(self):
        data = catalog()
        self.assertGreaterEqual(len(data["motifs"]), 10)
        self.assertEqual(len({m["id"] for m in data["motifs"]}), len(data["motifs"]))
        for motif in data["motifs"]:
            with self.subTest(motif=motif["id"]):
                self.assertTrue(set(motif["templates"]) <= set(BY_ID))
                self.assertGreaterEqual(len(motif["phases"]), 3)
                self.assertEqual(motif["phases"][0]["at"][0], 0)
                self.assertEqual(motif["phases"][-1]["at"][1], 1)

    def test_every_motif_resolves_deterministically_and_compiles_short(self):
        for motif_id, metadata in MOTIFS.items():
            with self.subTest(motif=motif_id):
                duration = sum(metadata["duration_s"]) / 2
                first = resolve(motif_id, duration)
                second = resolve(motif_id, duration)
                self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
                self.assertEqual(validate_settings(first["settings"]), first["settings"])
                preview = compile_template(first["settings"])["preview"]
                self.assertLessEqual(preview["orbit_duration_s"], 13.0)
                self.assertGreaterEqual(preview["orbit_duration_s"], 4.0)
                self.assertLess(preview["summary"]["max_aim_error_deg"], 3.0)

    def test_actor_cart_phone_motifs_create_meaningful_independent_motion(self):
        for motif_id, duration in (("walk_angle_change", 8), ("three_beat_oner", 10)):
            with self.subTest(motif=motif_id):
                resolved = resolve(motif_id, duration)
                preview = compile_template(resolved["settings"])["preview"]
                shot = {
                    "start_ms": 0,
                    "end_ms": round(preview["orbit_duration_s"] * 1000),
                    "actor_id": "lead",
                }
                review = review_travel(shot, resolved["settings"], preview)
                metrics = review["metrics"]
                self.assertGreater(metrics["actor"]["path_m"], 0.7)
                self.assertGreater(metrics["cart"]["path_m"], 0.7)
                self.assertGreater(metrics["arm_relative"]["excursion_m"], 0.05)
                self.assertGreater(metrics["light_relative"]["excursion_m"], 0.03)
                self.assertGreater(metrics["longest_simultaneous_s"], 1.0)

    def test_sequential_motif_proves_actor_can_stop_before_robot(self):
        resolved = resolve("actor_stop_camera_continue", 8)
        preview = compile_template(resolved["settings"])["preview"]
        shot = {"start_ms": 0, "end_ms": round(preview["orbit_duration_s"] * 1000), "actor_id": "lead"}
        review = review_travel(shot, resolved["settings"], preview)
        self.assertTrue(any("actor" in p["active"] for p in review["coordination_phases"]))
        self.assertTrue(
            any(
                "actor" not in p["active"] and "cart" in p["active"] and "phone" in p["active"]
                for p in review["coordination_phases"]
            )
        )

    def test_light_position_channel_is_an_emitter_path_not_a_servo_command(self):
        from takeone.previs.channels import ramp
        from takeone.previs.templates import defaults_for

        settings = defaults_for("static")
        settings["duration_s"] = 8
        settings["channels"] = {
            "light_position_m": ramp([-0.22275, -2.44745, 1.6003], [-0.17, -2.44745, 1.60], 0.1, 0.9)
        }
        preview = compile_template(settings)["preview"]
        filmed = [f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"]]
        self.assertIn("requested_light_position_m", filmed[0])
        self.assertLess(max(f["light_position_error_m"] for f in filmed), 0.03)
        self.assertNotEqual(filmed[0]["light"]["pos"], filmed[-1]["light"]["pos"])

    def test_legacy_motion_contract_without_light_fields_still_validates(self):
        from takeone.director.creative import plan_schema, validate
        from takeone.director.motion_contract import defaults

        current = defaults()
        legacy = {k: v for k, v in current.items() if not k.startswith("light_")}
        schema = plan_schema(require_movement=False)["properties"]["scenes"]["items"]["properties"]["shots"][
            "items"
        ]["properties"]["motion_requirements"]
        validate(legacy, schema, "motion_requirements")
        strict = plan_schema(require_movement=True)["properties"]["scenes"]["items"]["properties"]["shots"][
            "items"
        ]["properties"]["motion_requirements"]
        self.assertIn("light_role", strict["required"])

    def test_product_motif_moves_light_independently_of_a_static_subject(self):
        resolved = resolve("product_parallax_light", 7)
        preview = compile_template(resolved["settings"])["preview"]
        shot = {"start_ms": 0, "end_ms": 6800, "actor_id": ""}
        review = review_travel(shot, resolved["settings"], preview)
        self.assertEqual(review["metrics"]["actor"]["path_m"], 0)
        self.assertGreater(review["metrics"]["cart"]["path_m"], 0.5)
        self.assertGreater(review["metrics"]["light_relative"]["excursion_m"], 0.10)


if __name__ == "__main__":
    unittest.main()
