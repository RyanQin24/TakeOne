"""The authored showcase must demonstrate its promised contrasts in solved motion."""

import contextlib
import io
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch


class NightDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(__file__).resolve().parents[1] / "scripts/night_demo.py"
        with patch("sys.argv", [str(script)]), contextlib.redirect_stdout(io.StringIO()):
            cls.candidate = runpy.run_path(str(script))
        cls.doc = cls.candidate["doc"]
        cls.shots = [shot for scene in cls.doc["scenes"] for shot in scene["shots"]]
        cls.program = cls.candidate["program"]

    def test_edit_has_ten_varied_beats_and_no_missing_footage(self):
        self.assertEqual(len(self.shots), 10)
        self.assertEqual(self.shots[-1]["end_ms"], 60000)
        self.assertGreater(len({s["end_ms"] - s["start_ms"] for s in self.shots}), 2)
        self.assertEqual(self.program["blocked_shot_ids"], [])
        self.assertEqual(self.program["needs_revision_shot_ids"], [])
        for segment in self.program["segments"]:
            self.assertGreaterEqual(
                segment["filming_s"], (segment["edit"]["end_ms"] - segment["edit"]["start_ms"]) / 1000
            )

    def test_three_environment_inserts_have_no_actors_or_dialogue(self):
        empty = [scene for scene in self.doc["scenes"] if not scene["cast"]]
        self.assertEqual(len(empty), 3)
        for scene in empty:
            for shot in scene["shots"]:
                self.assertEqual(shot["actor_id"], "")
                self.assertEqual(shot["movement"]["subject_motion"], "none")
                self.assertEqual(shot["camera_target"]["kind"], "object")
                self.assertEqual(shot["lines"], [])

    def test_both_characters_speak_and_reactions_have_actual_attention_tracks(self):
        self.assertEqual({s["actor_id"] for s in self.shots if s["lines"]}, {"actor-a", "actor-b"})
        self.assertTrue(self.shots[2]["performers"][0]["look_at"])
        self.assertEqual({b["actor_id"] for b in self.shots[-1]["design"]["beats"]}, {"actor-a", "actor-b"})

    def test_arm_only_shots_are_not_rigid_cart_travel(self):
        held = [
            s
            for s in self.program["segments"]
            if s["template_id"] in ("tilt_up", "tilt_down", "pan_left", "roll_left")
        ]
        self.assertEqual(len(held), 4)
        for shot in held:
            metrics = shot["shot_review"]["travel"]["metrics"]
            self.assertAlmostEqual(metrics["cart"]["path_m"], 0)
            self.assertGreater(metrics["arm_rotation_excursion_rad"], 0.05)
        self.assertEqual(self.shots[2]["movement"]["cinematography"]["camera"]["horizon"], "phone")

    def test_dolly_zoom_has_real_lens_change_and_cart_travel(self):
        shot = next(s for s in self.program["segments"] if s["template_id"] == "dolly_zoom_out")
        review = shot["shot_review"]
        self.assertGreater(review["lens_end"]["equivalent_mm"], review["lens_start"]["equivalent_mm"] + 10)
        self.assertGreater(review["travel"]["metrics"]["cart"]["path_m"], 2)

    def test_platform_reveal_has_explicit_elevation_and_independent_lift(self):
        shot = self.shots[3]
        channels = shot["movement"]["cinematography"]["channels"]
        self.assertTrue(all(k["value"][2] == 0.6 for k in channels["actor_position_m"]))
        self.assertEqual(shot["movement"]["template_id"], "boom_up")
        review = self.program["segments"][3]["shot_review"]
        self.assertAlmostEqual(review["travel"]["metrics"]["cart"]["path_m"], 0)
        self.assertGreater(review["travel"]["metrics"]["arm_relative"]["excursion_m"], 0.25)
        self.assertEqual(self.program["segments"][3]["diagnostics"], [])

    def test_stationary_lens_reveal_changes_field_of_view(self):
        review = self.program["segments"][5]["shot_review"]
        self.assertEqual(review["lens_start"]["equivalent_mm"], 48)
        self.assertEqual(review["lens_end"]["equivalent_mm"], 24)
        self.assertAlmostEqual(review["travel"]["metrics"]["cart"]["path_m"], 0)

    def test_language_director_receives_real_staged_head_samples(self):
        from takeone.director.direction_context import staged_head_targets

        scene = self.doc["scenes"][2]
        context = staged_head_targets(self.shots[3], scene, self.doc["actors"])
        self.assertTrue(context["available"])
        self.assertEqual({t["actor_id"] for t in context["targets"]}, {"actor-a", "actor-b"})
        for target in context["targets"]:
            self.assertTrue(all(abs(s["position_m"][2] - 2.191) < 0.001 for s in target["head_samples"]))

    def test_cast_scenes_have_reverse_angle_background_without_changing_shots(self):
        import copy

        document = copy.deepcopy(self.doc)
        self.candidate["dress_reverse_angles"](document)
        self.assertEqual(document, self.doc)  # Applying dressing twice is idempotent.
        for scene in document["scenes"]:
            if scene["cast"]:
                backgrounds = {o["object_id"]: o for o in scene["objects"]}
                self.assertLess(backgrounds["backdrop"]["position_m"][0], 0)
                self.assertGreater(backgrounds["reverse-backdrop"]["position_m"][0], 0)

    def test_night_redesign_with_head_context_fits_unchanged_provider_limits(self):
        from takeone.director.direction_context import staged_head_targets
        from takeone.director.provider import ResponsesPlanner

        from tests.test_provider_catalog_compaction import request_payload

        scene = self.doc["scenes"][4]
        shot = scene["shots"][0]
        payload = request_payload("cinematic")
        payload.update(
            brief=self.candidate["brief"],
            redesign_shot_id=shot["shot_id"],
            shot=shot,
            instruction="Hold the cart, frame Alex, then pan to Maya for her reply.",
            scene={k: v for k, v in scene.items() if k != "shots"},
            actors=self.doc["actors"],
            marks=self.doc["marks"],
            visual_style=self.doc["visual_style"],
            staged_head_targets=staged_head_targets(shot, scene, self.doc["actors"]),
        )
        planner = ResponsesPlanner(api_key="")
        with patch("takeone.director.provider.http.client.HTTPSConnection") as network:
            raw, reserved = planner.request(payload, "creative_plan")
            network.assert_not_called()
        self.assertLessEqual(len(raw), planner.config["max_request_bytes"])
        self.assertLessEqual(reserved, planner.config["request_budget_microusd"])
