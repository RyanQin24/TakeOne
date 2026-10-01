"""Story-to-shot regressions with real compiled arm/camera geometry, no hardware."""

import copy
import json
import math
import unittest
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation
from takeone.director.contracts import ProductionBrief
from takeone.director.creative import digest, plan_schema, validate, validate_plan
from takeone.director.scenes import tracking_intent, tracking_status
from takeone.director.studio import rehearsal_manifest
from takeone.previs.cache import compile_preview
from takeone.previs.scene_checks import obstacles
from takeone.previs.sequence import build_program, stage_for
from takeone.previs.templates import defaults_for, preview_geometry


class SceneAwareDirectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = json.loads((Path(__file__).parent / "fixtures/director_arrival.json").read_text())
        cls.document = cls.project["document"]
        cls.detail = dict(
            creative=dict(document=cls.document, context=cls.project["context"], digest=digest(cls.document)),
            session=dict(brief=cls.project["brief"], session_id="offline-test", revision=1),
        )
        cls.manifest = rehearsal_manifest(cls.detail, digest(cls.document))
        cls.program = build_program(cls.manifest)

    def test_five_scene_story_survives_strict_schema_and_compilation(self):
        # This saved fixture predates independent cinematic channels. It must
        # remain accepted; new provider proposals use the current strict schema.
        validate(self.document, plan_schema(require_movement=False))
        self.assertEqual(len(self.program["scenes"]), 5)
        self.assertEqual([s["shot_number"] for s in self.program["segments"]], [1, 2, 3, 4, 5])
        self.assertEqual(
            [s["edit"] for s in self.program["segments"]],
            [
                dict(start_ms=0, end_ms=5000),
                dict(start_ms=5000, end_ms=10000),
                dict(start_ms=10000, end_ms=18000),
                dict(start_ms=18000, end_ms=24000),
                dict(start_ms=24000, end_ms=30000),
            ],
        )
        self.assertEqual(self.program["edit_duration_s"], 30)
        self.assertFalse(self.program["needs_revision_shot_ids"])
        self.assertFalse(self.program["blocked_shot_ids"])

    def test_location_change_does_not_invent_a_cart_route(self):
        self.assertEqual({s["kind"] for s in self.program["segments"]}, {"shot"})
        self.assertEqual(len(self.program["relocations"]), 4)
        self.assertTrue(all(r["duration_s"] is None for r in self.program["relocations"]))

    def test_walking_direction_is_independent_of_camera_bearing(self):
        preview = dict(
            orbit_start_s=0, frames=[dict(time_s=0, actor=dict(heading_rad=0), camera=dict(pos=[0, -2, 1.5]))]
        )
        stage = stage_for(dict(position_m=[2, 3], facing_rad=math.pi / 2), preview)
        self.assertAlmostEqual(stage["heading_rad"], math.pi / 2)
        side = self.program["segments"][2]
        self.assertEqual(side["stage"]["heading_rad"], 0)
        self.assertAlmostEqual(side["settings"]["actor_heading_rad"], math.pi / 2)

    def test_sign_reveal_aims_at_the_sign_and_finishes_within_one_degree(self):
        settings = self.manifest["shots"][1]["settings"]
        preview = compile_preview(settings)
        end = preview["frames"][-1]
        np.testing.assert_allclose(end["camera_target_m"], [0, 2, 2.4])
        self.assertGreater(np.linalg.norm(np.asarray(end["camera_target_m"]) - end["face"]), 1)
        forward = Rotation.from_quat(end["camera"]["quat"]).as_matrix()[:, 2]
        direction = np.asarray(end["camera_target_m"]) - end["camera"]["pos"]
        direction /= np.linalg.norm(direction)
        self.assertGreater(float(forward @ direction), math.cos(math.radians(1)))

    def test_follow_modes_have_identity_and_truthful_live_status(self):
        for index in (2, 3):
            shot = self.manifest["shots"][index]
            self.assertEqual(shot["tracking"]["cart"], "follow_actor")
            self.assertEqual(shot["tracking"]["phone"], "follow_head")
            self.assertEqual(shot["tracking"]["actor_id"], "alex")
            self.assertFalse(shot["tracking"]["live_available"])
            self.assertEqual(shot["tracking"]["on_loss"], "stop_and_hold")
            self.assertEqual(shot["settings"]["actor_distance_m"], shot["settings"]["distance_m"])
        self.assertEqual(self.manifest["shots"][1]["tracking"]["requested_controllers"], [])

    def test_old_tracking_shots_get_follow_intent_without_parsing_prose(self):
        self.assertEqual(
            tracking_intent(dict(movement=dict(template_id="side_track", subject_motion="walk")))["cart"],
            "follow_actor",
        )
        self.assertEqual(
            tracking_intent(dict(movement=dict(template_id="tilt_up", subject_motion="hold")))["phone"],
            "planned",
        )

    def test_follow_explanation_cannot_select_a_controller(self):
        status = tracking_status(
            dict(cart="planned", phone="planned", on_loss="stop_and_hold", reason="follow_actor"), "alex"
        )
        self.assertEqual(status["requested_controllers"], [])
        self.assertEqual(status["hooks"], {})

    def test_unknown_target_and_cross_scene_marks_are_rejected(self):
        for mutate in (
            lambda d: d["scenes"][1]["shots"][0]["camera_target"].update(target_id="missing-sign"),
            lambda d: d["scenes"][1]["shots"][0].update(mark_id="M1"),
            lambda d: d["scenes"][1]["shots"][0]["tracking"].update(phone="follow_head"),
        ):
            document = copy.deepcopy(self.document)
            mutate(document)
            with self.assertRaises(ValueError):
                validate_plan(document, ProductionBrief.parse(self.project["brief"]), self.project["context"])

    def test_silence_never_becomes_a_spoken_instruction(self):
        self.assertTrue(all(s["dialogue"] is None for s in self.manifest["shots"]))
        self.assertTrue(all(s["audio_intent"] for s in self.manifest["shots"]))

    def test_wide_framing_fits_head_and_feet_instead_of_centring_on_the_face(self):
        for index in (0, 3):
            preview = compile_preview(self.manifest["shots"][index]["settings"])
            frame = next(f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"])
            rotation = Rotation.from_quat(frame["camera_view"]["quat"]).as_matrix()
            for z in (0.0, 1.72):
                coordinates = rotation.T @ (np.array([0.0, 0.0, z]) - frame["camera"]["pos"])
                vertical = coordinates[1] / coordinates[2] * frame["focal_mm"] / (20.25 / 2)
                self.assertLess(abs(vertical), 1)

    def test_placeholder_follow_dispatch_calls_only_requested_controllers(self):
        from unittest.mock import patch

        from takeone.director.following import start_following

        request = self.manifest["shots"][2]["tracking"]
        pending = start_following(request)
        self.assertFalse(pending["active"])
        self.assertEqual({r["state"] for r in pending["controllers"]}, {"implementation_pending"})
        with (
            patch("takeone.director.following.start_cart_follow") as cart,
            patch("takeone.director.following.start_head_follow") as head,
        ):
            cart.return_value = head.return_value = {"active": False}
            start_following(request | {"cart": "planned"})
            cart.assert_not_called()
            head.assert_called_once_with(
                actor_id="alex", on_loss="stop_and_hold", aim_offset_m=request["aim_offset_m"]
            )

    def test_actual_dolly_zoom_frame_height_uses_compensated_lens(self):
        settings = defaults_for("dolly_zoom_out") | dict(height_start_m=1.5, height_end_m=1.5, distance_m=0.6)
        geometry = preview_geometry(compile_preview(settings))
        self.assertAlmostEqual(*geometry["frame_height_m"], places=6)

    def test_nominal_obstacle_screen_keeps_the_doorway_open(self):
        door = dict(
            object_id="door",
            asset_id="doorway",
            label="Door",
            position_m=[0, 0, 1.5],
            size_m=[3, 0.2, 3],
            yaw_rad=0,
        )
        stage = dict(origin_m=[0, 0], heading_rad=0)
        self.assertEqual(obstacles(dict(objects=[door]), dict(frames=[dict(q=[0, 0, 0])]), stage, "s"), [])
        self.assertTrue(obstacles(dict(objects=[door]), dict(frames=[dict(q=[1.3, 0, 0])]), stage, "s"))


if __name__ == "__main__":
    unittest.main()
