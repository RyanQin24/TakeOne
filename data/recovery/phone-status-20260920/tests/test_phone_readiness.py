"""Configuration completeness must not hide an observed handset mismatch."""

import tempfile
import unittest
from pathlib import Path

from takeone.phone.service import PhoneService


class PhoneReadinessTests(unittest.TestCase):
    def test_observed_mismatch_is_reported_without_contacting_or_relabelling_phone(self):
        with tempfile.TemporaryDirectory() as folder:
            service = PhoneService(Path(folder) / "phone.json")
            service.config.update(
                enabled=True,
                endpoint="http://127.0.0.1:4444",
                fingerprint="measured",
                calibration=[
                    {"focal_mm": 24, "normalised": 0},
                    {"focal_mm": 48, "normalised": 0.1},
                ],
            )
            service.config["color"].update(operator_confirmed=True, lut_name="No LUT")
            self.assertTrue(service.readiness()["ready"])
            service.observed = {"fingerprint": "changed"}
            self.assertFalse(service.readiness()["ready"])
            self.assertIn("changed since calibration", service.readiness()["reason"])
            self.assertEqual(service.config["fingerprint"], "measured")
            service.observed = {"fingerprint": "measured"}
            self.assertTrue(service.readiness()["ready"])
            self.assertFalse(service.status()["hardware_verified"])


if __name__ == "__main__":
    unittest.main()
