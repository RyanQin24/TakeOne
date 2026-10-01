"""Kinematic orbit behavior, independently checked against the model and circle math."""

import math
import unittest
from unittest.mock import patch

import mujoco
import numpy as np
from takeone.calibration import ArmMapping
from takeone.config import rig_config
from takeone.contracts import JOINTS
from takeone.previs.catalog import DEFAULTS, capabilities
from takeone.previs.compiler import compile_orbit, orbit_pose, validate_settings
from takeone.previs.start_pose import initial_counts
from takeone.simulation.robot import load_model


class OrbitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preview = compile_orbit()
        cls.orbit_frames = [f for f in cls.preview["frames"] if f["phase"] == "orbit"]

    def test_circle_closes_with_no_accumulated_arm_turn(self):
        frames = self.orbit_frames
        for frame in frames:
            self.assertAlmostEqual(np.linalg.norm(frame["axle_m"]), 2.5, places=9)
            np.testing.assert_allclose(frame["q"][3:], frames[0]["q"][3:], atol=1e-12)
        start, end = np.array(frames[0]["bodies"]), np.array(frames[-1]["bodies"])
        np.testing.assert_allclose(start[:, :3], end[:, :3], atol=1e-9)
        # q and -q encode the same orientation after a complete revolution.
        np.testing.assert_allclose(abs(np.sum(start[:, 3:] * end[:, 3:], axis=1)), 1, atol=1e-9)

    def test_distance_speed_duration_and_direction(self):
        for sweep in (-math.pi, math.pi):
            result = compile_orbit(dict(radius_m=4, duration_s=10, sweep_rad=sweep, ease="linear"))
            self.assertEqual(result["frames"][-1]["time_s"], 10 + result["orbit_start_s"])
            self.assertAlmostEqual(result["summary"]["distance_m"], 4 * math.pi)
            self.assertAlmostEqual(result["summary"]["average_speed_m_s"], 4 * math.pi / 10)
            self.assertAlmostEqual(result["summary"]["peak_speed_m_s"], 4 * math.pi / 10)
            orbit = [f for f in result["frames"] if f["phase"] == "orbit"]
            self.assertEqual(
                math.copysign(1, orbit[10]["axle_m"][0]),
                -rig_config()["cart"]["drive_forward_sign"] * math.copysign(1, sweep),
            )

    def test_axle_heading_has_no_lateral_slip(self):
        cfg = rig_config()["cart"]
        for t in (0.1, 0.5, 0.9):
            q, axle, _ = orbit_pose(DEFAULTS, t, cfg["axle_offset_m"])
            _, next_axle, _ = orbit_pose(DEFAULTS, t + 1e-7, cfg["axle_offset_m"])
            velocity = (next_axle - axle) / 1e-7
            lateral = np.array([-math.sin(q[2]), math.cos(q[2])])
            self.assertLess(abs(velocity @ lateral), 1e-4)
            reconstructed = q[:2] + cfg["axle_offset_m"] * np.array([math.cos(q[2]), math.sin(q[2])])
            np.testing.assert_allclose(reconstructed, axle, atol=1e-12)

    def test_all_ten_joints_use_current_roles_and_ranges(self):
        for role, offset, roll_id in (("phone", 3, 6), ("light", 8, 5)):
            mapping = ArmMapping.load(role, require_motion=False)
            self.assertEqual(capabilities()["arms"][role][-1]["motor_id"], roll_id)
            self.assertEqual(len(JOINTS), 5)
            for frame in self.preview["frames"]:
                for q, (low, high) in zip(frame["q"][offset : offset + 5], mapping.safe_ranges_rad):
                    self.assertLessEqual(low, q)
                    self.assertLessEqual(q, high)

    def test_wheel_animation_rolls_in_the_direction_of_cart_travel(self):
        frame = self.orbit_frames[len(self.orbit_frames) // 2]
        model = load_model()
        before, after = mujoco.MjData(model), mujoco.MjData(model)
        cfg = rig_config()["cart"]
        dt = 1e-6
        before.qpos[:] = frame["q"]
        after.qpos[:] = frame["q"]
        after.qpos[:3] = orbit_pose(DEFAULTS, 0.5 + dt / DEFAULTS["duration_s"], cfg["axle_offset_m"])[0]
        mujoco.mj_forward(model, before)
        mujoco.mj_forward(model, after)
        for side, speed in zip(("left", "right"), frame["drive"]["wheelSpeeds"]):
            body = model.body("drive_" + side).id
            translation = (after.xpos[body] - before.xpos[body]) / dt
            axis = before.xmat[body].reshape(3, 3) @ [frame["drive"]["wheelAxisSign"], 0, 0]
            radius = cfg["wheel_diameter_m"] / 2
            rotation = np.cross(axis * speed / radius, [0, 0, -radius])
            np.testing.assert_allclose(translation + rotation, 0, atol=1e-6)

    def test_camera_and_light_are_the_achieved_fk_sites(self):
        model = load_model()
        data = mujoco.MjData(model)
        for frame in self.orbit_frames[::60]:
            data.qpos[:] = frame["q"]
            mujoco.mj_forward(model, data)
            for name, prefix in (("camera", "cam"), ("light", "light")):
                site = model.site(prefix + "_optical").id
                np.testing.assert_allclose(data.site_xpos[site], frame[name]["pos"], atol=1e-12)
                direction = np.array(frame["face"]) - data.site_xpos[site]
                direction /= np.linalg.norm(direction)
                self.assertGreater(data.site_xmat[site].reshape(3, 3)[:, 2] @ direction, 0.9999)

    def test_calibration_start_and_aiming_keep_the_cart_still(self):
        frames = self.preview["frames"]
        for role, offset in (("phone", 3), ("light", 8)):
            mapping = ArmMapping.load(role, require_motion=False)
            expected = initial_counts(mapping)
            self.assertEqual(frames[0]["raw_by_role"][role], expected)
            np.testing.assert_allclose(frames[0]["q"][offset : offset + 5], mapping.from_raw(expected))
        setup = [f for f in frames if f["time_s"] < self.preview["orbit_start_s"]]
        self.assertGreater(len(setup), 1)
        for frame in setup:
            self.assertEqual(frame["q"][:3], frames[0]["q"][:3])
            self.assertEqual(frame["drive"]["wheelSpeeds"], [0, 0])
        self.assertEqual(self.orbit_frames[0]["time_s"], self.preview["orbit_start_s"])
        self.assertNotEqual(frames[0]["q"][3:], self.orbit_frames[0]["q"][3:])

    def test_powered_wheels_lead_and_both_mounts_face_the_corrected_side(self):
        model = load_model()
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        for side, sign in (("left", 1), ("right", -1)):
            powered = data.xpos[model.body("drive_" + side).id]
            caster = data.xpos[model.body("caster_" + side).id]
            np.testing.assert_allclose(powered[:2], [0.27, sign * 0.29], atol=1e-9)
            np.testing.assert_allclose(caster[:2], [-0.32, sign * 0.2262], atol=1e-9)
        rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
        for role in ("cam", "light"):
            np.testing.assert_allclose(
                data.xmat[model.body(role + "_base").id].reshape(3, 3), rotation, atol=1e-9
            )
        before, after = self.orbit_frames[0], self.orbit_frames[1]
        self.assertAlmostEqual(before["q"][2], math.pi)
        self.assertGreater(self.preview["settings"]["sweep_rad"], 0)
        heading = np.array([math.cos(before["q"][2]), math.sin(before["q"][2])])
        self.assertGreater((np.array(after["axle_m"]) - before["axle_m"]) @ heading, 0)
        bx, by = before["axle_m"]
        ax, ay = after["axle_m"]
        self.assertGreater(bx * ay - by * ax, 0)

    def test_kinematic_compilation_never_steps_dynamics(self):
        with patch("mujoco.mj_step", side_effect=AssertionError("No dynamic simulation")):
            result = compile_orbit(dict(radius_m=1.5, height_m=1.4, sweep_rad=-math.pi / 2))
        self.assertLess(result["summary"]["max_aim_error_deg"], 1)
        self.assertEqual(result["kind"], "takeone_orbit_previs")

    def test_invalid_or_nonfinite_settings_are_rejected(self):
        for body in (
            [],
            "orbit",
            {"radius_m": float("nan")},
            {"duration_s": 0},
            {"sweep_rad": 0},
            {"height_m": True},
            {"radius_m": 0.1},
            {"unknown": 2},
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                validate_settings(body)


if __name__ == "__main__":
    unittest.main()
