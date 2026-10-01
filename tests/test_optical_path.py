"""Canonical optical path, pose parity, bounded placement and edit contracts."""

import copy
import unittest
from unittest.mock import patch

import mujoco
import numpy as np
from takeone.director.creative import validate
from takeone.director.motion_contract import defaults, schema, validate_links
from takeone.previs.channels import ramp, validate_channels
from takeone.previs.optical_candidates import candidates
from takeone.previs.templates import compile_template, defaults_for
from takeone.simulation.robot import load_model


class OpticalPathTests(unittest.TestCase):
    def test_fixed_frame_optical_path_is_achieved_by_real_arm_fk(self):
        settings = copy.deepcopy(defaults_for("boom_up")) | dict(
            duration_s=10, radius_m=2.5, height_start_m=1.51, height_end_m=1.58, focal_mm=35
        )
        reference = compile_template(settings)["preview"]
        frames = [f for f in reference["frames"] if f["time_s"] >= reference["orbit_start_s"] - 1e-8]
        settings["channels"] = dict(
            camera_position_m=[
                dict(at=t, value=frames[round(t * (len(frames) - 1))]["camera"]["pos"], ease="linear")
                for t in (0, 0.5, 1)
            ]
        )
        original = copy.deepcopy(settings)
        result = compile_template(settings)
        self.assertEqual(settings, original)
        self.assertLess(result["preview"]["summary"]["max_camera_position_error_m"], 0.01)
        self.assertLess(result["preview"]["summary"]["max_aim_error_deg"], 1)
        model = load_model()
        data = mujoco.MjData(model)
        site = model.site("cam_optical").id
        for frame in result["preview"]["frames"][::9]:
            data.qpos[:] = frame["q"]
            mujoco.mj_forward(model, data)
            np.testing.assert_allclose(frame["camera"]["pos"], data.site_xpos[site], atol=1e-12)
        plan = result["plan"]
        self.assertTrue(all(all(0 <= v <= 0.15 for v in row["commands"]) for row in plan["cart_schedule"]))
        self.assertTrue(all(f["focal_mm"] == 35 for f in result["preview"]["frames"]))

    def test_unreachable_optical_path_stays_visible_as_failure(self):
        settings = copy.deepcopy(defaults_for("static")) | dict(duration_s=1)
        settings["channels"] = dict(camera_position_m=ramp([20, 20, 1.5], [20.1, 20, 1.5]))
        result = compile_template(settings)["preview"]
        self.assertGreater(result["summary"]["max_camera_position_error_m"], 10)
        self.assertFalse(np.allclose(result["frames"][-1]["camera"]["pos"], [20.1, 20, 1.5]))

    def test_optical_height_conflicts_and_teleports_are_rejected(self):
        for value in (
            dict(camera_position_m=ramp([0, 0, 1.5], [0, 0, 1.6]), camera_height_m=ramp(1.5, 1.6)),
            dict(camera_position_m=ramp([0, 0, 4], [0, 0, 4])),
            dict(
                camera_position_m=[
                    dict(at=0, value=[0, 0, 1.5], ease="hold"),
                    dict(at=1, value=[1, 0, 1.5], ease="smooth"),
                ]
            ),
        ):
            with self.assertRaises(ValueError):
                validate_channels(value)

    def test_candidates_preserve_actor_lens_timing_and_absolute_target(self):
        settings = copy.deepcopy(defaults_for("side_track"))
        settings["channels"] = dict(
            camera_position_m=ramp([0, -2, 1.5], [1, -2, 1.5]), actor_position_m=ramp([0, 0, 0], [1, 0, 0])
        )
        original = copy.deepcopy(settings)

        def compile_candidate(candidate):
            return dict(
                plan_id="test",
                orbit_duration_s=10,
                summary=dict(max_camera_position_error_m=0.02, max_aim_error_deg=0.5),
            )

        with patch(
            "takeone.previs.optical_candidates.compile_preview", side_effect=compile_candidate
        ) as compile_call:
            result = candidates(dict(settings=settings, offsets_m=[[0, 0], [0.08, 0], [-0.08, 0]]))
        self.assertFalse(result["applied"])
        for call in compile_call.call_args_list:
            c = call.args[0]
            self.assertEqual(c["channels"], settings["channels"])
            self.assertEqual(c["focal_mm"], settings["focal_mm"])
            self.assertEqual(c["speed_m_s"], settings["speed_m_s"])
        self.assertEqual(original, settings)

    def test_candidate_search_is_bounded(self):
        settings = copy.deepcopy(defaults_for("static"))
        settings["channels"] = dict(camera_position_m=ramp([0, -2, 1.5], [0, -2, 1.6]))
        for offsets in ([[0, 0]] * 6, [[0.4, 0]], [[True, 0]], [[float("nan"), 0]]):
            with self.assertRaises(ValueError):
                candidates(dict(settings=settings, offsets_m=offsets))

    def test_required_empty_and_ambiguous_direction_are_rejected(self):
        for value in (
            defaults() | dict(priority="required"),
            defaults() | dict(signed_progress_m=0.5),
            defaults() | dict(orbit_rad=0.5),
        ):
            validate(value, schema())
            with self.assertRaises(ValueError):
                validate_links(
                    dict(
                        scenes=[
                            dict(
                                shots=[dict(actor_id="a", start_ms=0, end_ms=6000, motion_requirements=value)]
                            )
                        ]
                    )
                )

    def test_motion_contract_is_saved_and_reaches_the_existing_review(self):
        from takeone.previs.sequence import build_program

        from tests.test_shot_design import manifest, story

        f = story()
        s = f["document"]["scenes"][0]["shots"][0]
        s["motion_requirements"] = defaults() | dict(priority="required", cart_travel_m=0.5)
        m = manifest(f)
        p = build_program(m)
        report = p["segments"][0]["shot_review"]["travel"]
        self.assertEqual(report["status"], "needs_revision")
        self.assertIn("cart_travel_unmet", {x["code"] for x in report["issues"]})

    def test_dynamic_actor_crossing_is_not_hidden_by_clear_endpoints(self):
        from takeone.previs.scene_checks import sampled_scene_clearance

        from tests.test_travel_review import fixture

        shot, settings, preview = fixture(actor=False, cart=False, arm=False, duration=2)
        settings["subject_height_m"] = 1.72
        for f in preview["frames"]:
            u = max(0, f["time_s"] - 2) / 2
            f["actor"]["position_m"] = [-2 + 4 * u, -2.3, 0]
        result = sampled_scene_clearance(
            shot, settings, dict(objects=[], cast=[]), dict(position_m=[0, 0]), preview
        )
        self.assertEqual(result["status"], "potential_intersection")
        self.assertTrue(result["midpoint_fk"])
        self.assertLess(result["worst"]["edit_s"], 2)
        self.assertGreater(result["worst"]["edit_s"], 0)


if __name__ == "__main__":
    unittest.main()
