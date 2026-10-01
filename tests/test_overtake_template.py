"""The real pass uses the same capped motor clock in preview and playback."""

import unittest

import numpy as np
from scipy.spatial.transform import Rotation
from takeone.cart.response import CartResponse
from takeone.config import rig_config
from takeone.motion.studio_plan import prepare, validate
from takeone.previs.templates import catalog, compile_template, defaults_for, validate_settings
from takeone.protocol import COMMAND_CAP, MIN_COMMAND
from takeone.simulation.drive import integrate


class OvertakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = defaults_for("accelerate_pass")
        cls.result = compile_template(cls.settings)
        cls.preview = cls.result["preview"]
        cls.frames = [f for f in cls.preview["frames"] if f["time_s"] >= cls.preview["orbit_start_s"] - 1e-8]

    def test_catalog_and_pace_respect_existing_hardware_limit(self):
        self.assertIn("accelerate_pass", [p["id"] for p in catalog()["templates"]])
        self.assertEqual(validate_settings(self.settings)["speed_m_s"], 0.5)
        with self.assertRaises(ValueError):
            validate_settings(defaults_for("track_follow") | dict(speed_m_s=1))

    def test_five_seconds_accelerate_cruise_and_stop(self):
        self.assertEqual(self.preview["orbit_duration_s"], 5)
        self.assertGreater(self.preview["summary"]["distance_m"], 1)
        self.assertLessEqual(self.preview["summary"]["peak_speed_m_s"], 0.5)
        positions = np.array([f["axle_m"] for f in self.frames])
        times = np.array([f["time_s"] for f in self.frames])
        speeds = np.diff(positions[:, 0]) / np.diff(times)
        self.assertLess(speeds[0], 0.1)
        self.assertGreater(max(speeds), 0.45)
        self.assertLess(speeds[-1], 0.1)
        self.assertLess(np.ptp(positions[:, 1]), 1e-10)

    def test_passes_person_with_camera_remaining_forward(self):
        first, last = self.frames[0], self.frames[-1]
        self.assertLess(first["axle_m"][0], first["actor"]["position_m"][0])
        self.assertGreater(last["axle_m"][0], last["actor"]["position_m"][0])
        self.assertEqual(last["actor"]["position_m"][0], first["actor"]["position_m"][0])
        for frame in self.frames:
            forward = Rotation.from_quat(frame["camera"]["quat"]).as_matrix()[:, 2]
            self.assertGreater(forward[0], 0.999)
            self.assertAlmostEqual(abs(frame["axle_m"][1] - frame["actor"]["position_m"][1]), 1.25)
            self.assertEqual(frame["focal_mm"], 24)

    def test_real_robot_preparation_and_motor_prediction_agree(self):
        plan = prepare(self.settings)
        self.assertEqual(validate(plan)["plan_id"], self.result["plan"]["plan_id"])
        self.assertFalse(self.preview.get("simulation_only", False))
        cfg = rig_config()["cart"]
        response = CartResponse.load(cfg["minimum_speed_m_s"])
        first = self.preview["frames"][0]
        axle = np.array([*first["axle_m"], first["q"][2]])
        poses = [axle.copy()]
        for row in plan["cart_schedule"][:-1]:
            left, right = response.speeds_for(row["commands"])
            axle = integrate(axle, left * 0.02, right * 0.02, cfg["track_width_m"])
            poses.append(axle.copy())
            self.assertLessEqual(max(row["commands"]), COMMAND_CAP)
        for frame in self.preview["frames"]:
            np.testing.assert_allclose(frame["axle_m"], poses[round(frame["time_s"] / 0.02)][:2])
        self.assertEqual(plan["cart_schedule"][-1]["commands"], [0, 0])

    def test_acceleration_and_braking_respect_command_slew(self):
        plan = self.result["plan"]
        rows = [r for r in plan["cart_schedule"] if r["time_s"] >= plan["orbit_start_s"] - 1e-8]
        changes = [(a, b) for a, b in zip(rows, rows[1:]) if a["commands"] != b["commands"]]
        previous_time = -1
        for a, b in changes:
            for old, new in zip(a["commands"], b["commands"]):
                self.assertTrue(abs(new - old) <= 0.010001 or {new, old} == {0, MIN_COMMAND})
            self.assertGreaterEqual(b["time_s"] - previous_time, 0.2 - 1e-8)
            previous_time = b["time_s"]
        self.assertEqual(rows[0]["commands"], [0, 0])
        self.assertEqual(rows[-2]["commands"], [0, 0])

    def test_old_one_metre_per_second_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            prepare(self.settings | dict(speed_m_s=1))


if __name__ == "__main__":
    unittest.main()
