"""Configuration completeness must not hide an observed handset mismatch."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from takeone.phone.client import CameraError
from takeone.phone.http import PhoneAPI, PhoneAPIError
from takeone.phone.service import PhoneService


class PhoneReadinessTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.camera = Mock()
        self.camera.probe.return_value = {"fingerprint": "measured", "recording": False}
        self.service = PhoneService(
            Path(folder.name) / "phone.json", client_factory=lambda *a, **k: self.camera
        )
        self.service.config.update(
            enabled=True,
            endpoint="http://127.0.0.1:4444",
            fingerprint="measured",
            calibration=[{"focal_mm": 24, "normalised": 0}, {"focal_mm": 48, "normalised": 0.1}],
        )
        self.service.config["color"].update(operator_confirmed=True, lut_name="No LUT")
        self.api = PhoneAPI(self.service)

    def probe(self):
        return self.api.post("/api/phone/probe", {}, self.service.token)

    def test_failed_reconnect_overrides_old_success_and_recovers(self):
        self.assertEqual(self.probe()["connection"]["state"], "checked")
        self.service.last_result = {"recording_confirmed": True, "stop_confirmed": True}
        self.camera.probe.side_effect = CameraError("Camera connection timed out.")
        with self.assertRaises(PhoneAPIError):
            self.probe()
        status = self.api.get("/api/phone/status")
        self.assertEqual(status["connection"]["state"], "failed")
        self.assertEqual(status["connection"]["error"], "Camera connection timed out.")
        self.assertFalse(status["readiness"]["ready"])
        self.assertEqual(status["calibration_points"], 2)
        self.assertEqual(status["observed"]["fingerprint"], "measured")
        self.camera.probe.side_effect = None
        status = self.probe()
        self.assertEqual(status["connection"]["state"], "checked")
        self.assertIsNone(status["connection"]["error"])
        self.assertTrue(status["readiness"]["ready"])

    def test_old_check_expires_without_contacting_phone(self):
        with patch("takeone.phone.service.time.monotonic", return_value=100):
            self.probe()
        with patch("takeone.phone.service.time.monotonic", return_value=161):
            self.assertEqual(self.api.get("/api/phone/status")["connection"]["state"], "stale")
        self.assertEqual(self.camera.probe.call_count, 1)

    def test_saving_look_does_not_clear_failed_connection(self):
        self.camera.probe.side_effect = CameraError("Offline")
        with self.assertRaises(PhoneAPIError):
            self.probe()
        self.service.post("color", self.service.config["color"], self.service.token)
        self.assertEqual(self.service.connection_status()["state"], "failed")

    def test_changed_address_requires_a_new_check(self):
        self.probe()
        status = self.api.post(
            "/api/phone/configure",
            {
                "endpoint": "http://127.0.0.2:4444",
                "enabled": True,
            },
            self.service.token,
        )
        self.assertEqual(status["connection"]["state"], "unchecked")
        self.assertIsNone(status["observed"])

    def test_failed_capture_overrides_old_check_and_successful_capture_recovers(self):
        self.probe()
        folder = self.service.path.parent
        for report, expected in [
            ({"start_attempted": False, "error": "Camera timed out"}, "failed"),
            ({"start_attempted": True, "recording_confirmed": True, "stop_confirmed": True}, "checked"),
        ]:
            self.service.owner = "robot"
            (folder / "phone-capture.json").write_text(json.dumps(report), encoding="utf-8")
            self.service.release(folder)
            self.assertEqual(self.service.connection_status()["state"], expected)

    def test_failed_format_verification_keeps_new_observation_for_readiness(self):
        before = {
            "fingerprint": "measured",
            "recording": False,
            "product": {},
            "zoom_description": {},
            "format": {"codec": "HEVC"},
        }
        after = {**before, "fingerprint": "changed", "format": {"codec": "unexpected"}}
        self.camera.probe.side_effect = [before, after]
        with self.assertRaises(PhoneAPIError):
            self.api.post("/api/phone/format", {"frame_rate": 60, "resolution": "1080p"}, self.service.token)
        status = self.api.get("/api/phone/status")
        self.assertFalse(status["readiness"]["ready"])
        self.assertEqual(status["observed"]["fingerprint"], "changed")

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
