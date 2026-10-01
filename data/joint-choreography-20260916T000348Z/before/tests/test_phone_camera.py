"""Phone output orientation, reusable zoom channels and motor-cache isolation."""

import copy
import math
import unittest
from unittest import mock

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from takeone.motion.studio_plan import prepare, validate
from takeone.previs.camera import PROFILE, apply_camera, validate_camera, view_quaternion, zoom_at
from takeone.previs.compiler import compile_orbit
from takeone.previs.path import compile_path
from takeone.previs.templates import PRESETS, compile_template, validate_settings
from takeone.simulation.robot import load_model


def point(at, focal, ease="smooth"):
    return dict(at=at, focal_mm=focal, ease=ease)


class CameraMathTests(unittest.TestCase):
    def test_level_output_keeps_forward_and_position_independent_of_sensor_roll(self):
        for yaw, pitch, roll in ((0, 0, 90), (45, 20, -135), (-120, -50, 180)):
            rotation = Rotation.from_euler("zyx", [yaw, pitch, roll], degrees=True)
            raw = rotation.as_quat()
            result = Rotation.from_quat(view_quaternion(raw, "level")).as_matrix()
            np.testing.assert_allclose(result[:, 2], rotation.as_matrix()[:, 2], atol=1e-12)
            self.assertGreaterEqual(-result[2, 1], 0)
            self.assertAlmostEqual(result[2, 0], 0)
            np.testing.assert_allclose(view_quaternion(raw, "phone"), raw)

    def test_vertical_aim_has_a_finite_orthonormal_output(self):
        for degrees in (0, 180):
            raw = Rotation.from_euler("x", degrees, degrees=True).as_quat()
            result = Rotation.from_quat(view_quaternion(raw, "level")).as_matrix()
            self.assertTrue(np.isfinite(result).all())
            np.testing.assert_allclose(result.T @ result, np.eye(3), atol=1e-12)
            self.assertAlmostEqual(np.linalg.det(result), 1)

    def test_zoom_in_hold_zoom_out_and_cut_boundaries(self):
        points = [point(0, 24), point(0.3, 100), point(0.6, 100), point(1, 24)]
        self.assertEqual(zoom_at(points, -1), 24)
        self.assertAlmostEqual(zoom_at(points, 0.15), 62)
        self.assertEqual(zoom_at(points, 0.5), 100)
        self.assertEqual(zoom_at(points, 1), 24)
        cuts = [point(0, 24, "hold"), point(0.5, 100, "linear"), point(1, 200)]
        self.assertEqual(zoom_at(cuts, 0.499999), 24)
        self.assertEqual(zoom_at(cuts, 0.5), 100)
        self.assertEqual(zoom_at(cuts, 0.75), 150)

    def test_rejects_ambiguous_or_nonfinite_lens_scripts(self):
        bad = [
            {"zoom": "unknown"},
            {"horizon": "upside"},
            {"hardware_ready": True},
            {"zoom": "keyframes", "keyframes": []},
            {"zoom": "keyframes", "keyframes": [point(0, 24), point(0.5, 100)]},
            {"keyframes": [point(0, 24), point(0, 100)]},
            {"keyframes": [point(0, float("nan"))]},
            {"keyframes": [point(0, 361)]},
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_camera(value)

    def test_every_template_accepts_the_same_camera_script(self):
        camera = dict(horizon="level", zoom="keyframes", keyframes=[point(0, 24), point(1, 360)])
        for preset in PRESETS:
            self.assertEqual(
                validate_settings({"template_id": preset["id"], "camera": camera})["camera"], camera
            )
        self.assertEqual(PROFILE["name"], "iPhone 17 Pro Max")
        self.assertEqual(PROFILE["orientation"], "landscape")

    def test_landscape_optical_width_follows_the_handsets_long_edge_in_every_model(self):
        for variant in ("ring", "panel", "tube"):
            with self.subTest(variant=variant):
                model = load_model(variant)
                data = mujoco.MjData(model)
                mujoco.mj_forward(model, data)
                handset, site = model.geom("cam_payload").id, model.site("cam_optical").id
                body_rotation = data.geom_xmat[handset].reshape(3, 3)
                optical_rotation = data.site_xmat[site].reshape(3, 3)
                long_edge = body_rotation[:, int(np.argmax(model.geom_size[handset]))]
                self.assertAlmostEqual(abs(long_edge @ optical_rotation[:, 0]), 1)
                np.testing.assert_allclose(optical_rotation[:, 2], -body_rotation[:, 2], atol=1e-12)
                np.testing.assert_allclose(model.site_pos[site], [0.025, 0.05, -0.06], atol=1e-12)

    def test_dolly_zoom_uses_optical_depth_and_reports_lens_limit(self):
        # Optical +Z faces world +X. Off-axis displacement must not affect f/z.
        quat = Rotation.from_euler("y", 90, degrees=True).as_quat().tolist()
        frames = [
            dict(time_s=t, camera=dict(pos=pos, quat=quat), face=[10, 3, 1], focal_mm=50)
            for t, pos in ((0, [0, 0, 1]), (1, [0, 0, 1]), (2, [5, 0, 1]), (3, [8, 0, 1]))
        ]
        preview = dict(
            settings=dict(focal_mm=50, camera=dict(zoom="dolly")),
            frames=frames,
            orbit_start_s=1,
            orbit_duration_s=2,
            summary={},
        )
        raw = copy.deepcopy([f["camera"] for f in frames])
        apply_camera(preview)
        np.testing.assert_allclose([f["focal_mm"] for f in frames], [50, 50, 25, 13])
        self.assertGreater(preview["summary"]["framing_drift_percent"], 0)
        self.assertEqual([f["camera"] for f in frames], raw)


class CameraIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = {"template_id": "static", "duration_s": 2}
        cls.original = compile_template(cls.base)

    def test_lens_edit_reuses_ik_and_preserves_every_motor_command(self):
        options = dict(
            zoom="keyframes", keyframes=[point(0, 24), point(0.3, 100), point(0.6, 100), point(1, 24)]
        )
        with mock.patch(
            "takeone.previs.path.AimingSolver.solve", side_effect=AssertionError("Unexpected IK")
        ):
            result = compile_template(self.base | {"focal_mm": 24, "camera": options})
        self.assertEqual(result["plan"]["samples"], self.original["plan"]["samples"])
        self.assertEqual(result["plan"]["cart_schedule"], self.original["plan"]["cart_schedule"])
        self.assertNotEqual(result["plan"]["plan_id"], self.original["plan"]["plan_id"])
        self.assertEqual(validate(result["plan"])["plan_id"], result["preview"]["plan_id"])
        self.assertEqual(result["plan"]["camera_cues"][-1]["focal_mm"], 24)
        for frame in result["preview"]["frames"]:
            if frame["time_s"] < result["preview"]["orbit_start_s"]:
                self.assertEqual(frame["focal_mm"], 24)
        saved = compile_template(copy.deepcopy(result["plan"]["settings"]))
        self.assertEqual(saved["plan"]["plan_id"], result["plan"]["plan_id"])

    def test_calibrated_start_has_upright_output_without_changing_raw_pose(self):
        preview = self.original["preview"]
        first = preview["frames"][0]
        self.assertEqual(preview["camera_output"]["horizon"], "level")
        self.assertEqual(first["raw_by_role"], preview["initial_raw"])
        output = Rotation.from_quat(first["camera_view"]["quat"]).as_matrix()
        self.assertGreater(-output[2, 1], 0.99)
        result = compile_template(self.base | {"camera": {"horizon": "phone"}})
        for f in result["preview"]["frames"]:
            self.assertEqual(f["camera_view"], f["camera"])

    def test_intentional_roll_survives_auto_output_mode(self):
        preview = compile_template({"template_id": "roll_left", "duration_s": 2})["preview"]
        self.assertEqual(preview["camera_output"]["horizon"], "phone")
        self.assertTrue(all(f["camera_view"] == f["camera"] for f in preview["frames"]))

    def test_custom_path_and_orbit_share_the_lens_script(self):
        camera = dict(zoom="keyframes", keyframes=[point(0, 24), point(1, 48)])
        path = compile_path(dict(points_m=[[-0.3, 2.5], [0.3, 2.5]], camera=camera))
        orbit_settings = dict(duration_s=2, sweep_rad=math.pi / 12, camera=camera)
        orbit = compile_orbit(orbit_settings)
        for preview in (path["preview"], orbit):
            self.assertEqual(preview["frames"][0]["focal_mm"], 24)
            self.assertEqual(preview["frames"][-1]["focal_mm"], 48)
            self.assertEqual(preview["camera_output"]["horizon"], "level")
            model = load_model()
            data = mujoco.MjData(model)
            opening = next(f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"])
            data.qpos[:] = opening["q"]
            mujoco.mj_forward(model, data)
            handset = model.geom("cam_payload").id
            long_edge = data.geom_xmat[handset].reshape(3, 3)[:, int(np.argmax(model.geom_size[handset]))]
            self.assertLess(abs(long_edge[2]), math.sin(math.radians(2)))
        plan = prepare(orbit_settings)
        self.assertAlmostEqual(plan["camera_cues"][-1]["time_s"], plan["duration_s"])
        self.assertEqual(plan["camera_cues"][-1]["focal_mm"], 48)


if __name__ == "__main__":
    unittest.main()
