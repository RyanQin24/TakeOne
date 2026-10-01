"""The illustrative pass must stay straight, face forward, and never execute."""

import unittest

import numpy as np
from scipy.spatial.transform import Rotation
from takeone.motion.studio_plan import prepare, validate
from takeone.previs.templates import catalog, compile_template, defaults_for, validate_settings


class OvertakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = defaults_for("accelerate_pass")
        cls.result = compile_template(cls.settings)
        cls.preview = cls.result["preview"]
        cls.frames = [f for f in cls.preview["frames"] if f["time_s"] >= cls.preview["orbit_start_s"] - 1e-8]

    def test_catalog_and_simulation_speed_do_not_raise_hardware_limit(self):
        self.assertIn("accelerate_pass", [p["id"] for p in catalog()["templates"]])
        self.assertEqual(validate_settings(self.settings)["speed_m_s"], 1)
        with self.assertRaises(ValueError):
            validate_settings(defaults_for("track_follow") | dict(speed_m_s=1))

    def test_five_seconds_accelerate_cruise_and_stop(self):
        self.assertEqual(self.preview["orbit_duration_s"], 5)
        self.assertAlmostEqual(self.preview["summary"]["distance_m"], 4)
        self.assertEqual(self.preview["summary"]["peak_speed_m_s"], 1)
        positions = np.array([f["axle_m"] for f in self.frames])
        times = np.array([f["time_s"] for f in self.frames])
        speeds = np.diff(positions[:, 0]) / np.diff(times)
        self.assertLess(speeds[0], 0.1)
        self.assertGreater(max(speeds), 0.99)
        self.assertLess(speeds[-1], 0.1)
        self.assertLess(np.ptp(positions[:, 1]), 1e-10)

    def test_passes_walking_person_with_camera_remaining_forward(self):
        first, last = self.frames[0], self.frames[-1]
        self.assertLess(first["axle_m"][0], first["actor"]["position_m"][0])
        self.assertGreater(last["axle_m"][0], last["actor"]["position_m"][0])
        self.assertGreater(last["actor"]["position_m"][0], first["actor"]["position_m"][0])
        for frame in self.frames:
            forward = Rotation.from_quat(frame["camera"]["quat"]).as_matrix()[:, 2]
            self.assertGreater(forward[0], 0.999)
            self.assertAlmostEqual(abs(frame["axle_m"][1] - frame["actor"]["position_m"][1]), 1.25)
            self.assertEqual(frame["focal_mm"], 24)

    def test_real_robot_preparation_and_artifact_rejected(self):
        self.assertTrue(self.preview["simulation_only"])
        self.assertEqual(self.result["plan"]["cart_schedule"], [])
        with self.assertRaisesRegex(ValueError, "simulator-only"):
            prepare(self.settings)
        with self.assertRaises(ValueError):
            validate(self.result["plan"])


if __name__ == "__main__":
    unittest.main()
