"""Cart camera framing calibration stays resolution independent and motor free."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from takeone.config import read_json
from takeone.motion.body_calibration import measurement, median_target, save_target


class BodyCalibrationTests(unittest.TestCase):
    def test_measurement_uses_shoulder_midpoint_and_width_fractions(self):
        landmarks = [SimpleNamespace(x=0.0, y=0.0, visibility=1.0) for _ in range(33)]
        landmarks[11] = SimpleNamespace(x=0.3, y=0.4, visibility=0.9)
        landmarks[12] = SimpleNamespace(x=0.7, y=0.4, visibility=0.9)
        self.assertEqual(measurement(landmarks, 640, 360), (0.5, 0.4, 0.4))

    def test_median_target_and_atomic_save_preserve_controller_tuning(self):
        previous = {
            "center_x_fraction": 0.5,
            "center_y_fraction": 0.5,
            "shoulder_width_fraction": 0.2,
            "start_deadband_fraction": 0.03,
            "stop_deadband_fraction": 0.02,
            "pan_gain_counts_per_normalized_error": 38.4,
            "calibrated": False,
            "source": "script_defaults_scaled",
            "sample_count": 0,
            "calibrated_utc": None,
        }
        samples = [(0.45, 0.42, 0.18)] * 15 + [(0.9, 0.9, 0.7)]
        target = median_target(samples, previous)
        self.assertEqual(target["center_x_fraction"], 0.45)
        self.assertEqual(target["center_y_fraction"], 0.42)
        self.assertEqual(target["shoulder_width_fraction"], 0.18)
        self.assertTrue(target["calibrated"])
        self.assertEqual(target["pan_gain_counts_per_normalized_error"], 38.4)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tracking.json"
            path.write_text(
                '{"schema_version":1,"camera":{"body_target":{}}}', encoding="utf-8"
            )
            save_target(target, path)
            self.assertEqual(read_json(path)["camera"]["body_target"], target)


if __name__ == "__main__":
    unittest.main()
