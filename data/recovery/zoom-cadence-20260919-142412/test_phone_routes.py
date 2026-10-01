"""The phone routes: explicit, loopback-only, and unable to move anything.

`PhoneService` existed with seven actions and no door. These tests pin the door:
what it accepts, what it refuses, what it never leaks, and the fact that no path
through it reaches the motion code.
"""

import ast
import inspect
import json
import tempfile
import unittest
from pathlib import Path

from takeone.phone import http as phone_http
from takeone.phone.http import BODY_LIMITS, PhoneAPI, PhoneAPIError
from takeone.phone.service import PhoneService, defaults

SERVER = Path(__file__).resolve().parents[1] / "apps" / "rehearsal" / "server.py"


class FakeCamera:
    """A device that is never contacted unless a test says so."""

    contacted = 0
    frame_rate = 24

    def __init__(self, address, timeout_s, *, cert_sha256=""):
        self.address = address
        self.timeout_s = timeout_s
        self.cert_sha256 = cert_sha256
        self.record_resolution = {"width": 3840, "height": 2160}
        self.sensor_resolution = {"width": 3840, "height": 2160}

    def probe(self):
        FakeCamera.contacted += 1
        return {
            "product": "Blackmagic Camera",
            "format": {
                "frameRate": str(FakeCamera.frame_rate),
                "offSpeedEnabled": False,
                "recordResolution": self.record_resolution,
                "sensorResolution": self.sensor_resolution,
                "codec": "HEVC (H.265):High",
            },
            "zoom_description": {"controllable": True},
            "normalised": 0.0,
            "recording": False,
            "fingerprint": f"device-fingerprint-{FakeCamera.frame_rate}",
            "controllable": True,
        }

    def set_recording_format(self, value, resolution):
        FakeCamera.contacted += 1
        FakeCamera.frame_rate = value
        size = {"1080p": {"width": 1920, "height": 1080}, "4k": {"width": 3840, "height": 2160}}[resolution]
        self.record_resolution = size
        self.sensor_resolution = size
        return {"frameRate": str(value), "offSpeedEnabled": False, "recordResolution": size, "sensorResolution": size}


def service(folder):
    path = Path(folder) / "iphone-camera.json"
    path.write_text(json.dumps(defaults(), indent=2), encoding="utf-8")
    return PhoneService(path, client_factory=FakeCamera)


class PhoneRouteTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.service = service(self.folder.name)
        self.api = PhoneAPI(self.service)
        FakeCamera.contacted = 0
        FakeCamera.frame_rate = 24

    # ── shape ───────────────────────────────────────────────────────────────

    def test_status_is_honest_on_a_fresh_config(self):
        status = self.api.get("/api/phone/status")
        self.assertFalse(status["enabled"])
        self.assertFalse(status["paired"])
        self.assertFalse(status["hardware_verified"])
        self.assertEqual(
            status["readiness"],
            {"enabled": False, "ready": False, "reason": "iPhone capture is disabled."},
        )
        self.assertEqual(status["calibration_points"], 0)
        self.assertEqual(status["zoom_mapping"], "estimated_between_operator_measured_points")
        self.assertFalse(status["optical_framing_verified"])
        self.assertFalse(status["color"]["baked_pixels_verified"])
        self.assertEqual(FakeCamera.contacted, 0, "status must never contact the device")

    def test_existing_config_without_certificate_pin_still_loads(self):
        path = Path(self.folder.name) / "old-iphone-camera.json"
        config = defaults()
        del config["tls_cert_sha256"]
        path.write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(PhoneService(path, client_factory=FakeCamera).config["tls_cert_sha256"], "")

    def test_unknown_endpoints_are_refused(self):
        for path in ("/api/phone/", "/api/phone/anything", "/api/phone/statuses"):
            with self.assertRaises(PhoneAPIError) as caught:
                self.api.get(path)
            self.assertEqual(caught.exception.status, 404)
        with self.assertRaises(PhoneAPIError) as caught:
            self.api.post("/api/phone/arm", {}, self.service.token)
        self.assertEqual(caught.exception.status, 404)

    # ── authority ───────────────────────────────────────────────────────────

    def test_every_action_needs_the_token(self):
        for path in sorted(BODY_LIMITS):
            with self.assertRaises(PhoneAPIError) as caught:
                self.api.post(path, {}, "not-the-token")
            self.assertEqual(caught.exception.status, 403, path)
            self.assertEqual(caught.exception.code, "phone_authority_required", path)
        self.assertEqual(FakeCamera.contacted, 0)

    def test_a_bad_address_produces_the_clients_own_refusal(self):
        with self.assertRaises(PhoneAPIError) as caught:
            self.api.post(
                "/api/phone/configure",
                {"endpoint": "http://camera.local:8080", "enabled": True},
                self.service.token,
            )
        self.assertEqual(caught.exception.status, 400)
        # The client's wording, not a vaguer restatement of it.
        self.assertIn("private-network IP", str(caught.exception))

    def test_probe_is_the_only_action_that_reaches_the_device(self):
        self.api.post(
            "/api/phone/configure",
            {"endpoint": "http://192.168.1.44:8080", "enabled": True},
            self.service.token,
        )
        self.assertEqual(FakeCamera.contacted, 0)
        result = self.api.post("/api/phone/probe", {}, self.service.token)
        self.assertEqual(FakeCamera.contacted, 1)
        self.assertTrue(result["paired"] is False or result["fingerprint"] == "")
        self.assertEqual(result["observed"]["product"], "Blackmagic Camera")

    def test_frame_rate_change_is_explicit_verified_and_preserves_stable_lens_calibration(self):
        self.service.config.update(
            enabled=True,
            endpoint="http://192.168.1.44:8080",
            fingerprint="device-fingerprint-24",
            calibration=[
                {"focal_mm": 24.0, "normalised": 0.0},
                {"focal_mm": 48.0, "normalised": 0.0714285714},
            ],
        )
        result = self.api.post(
            "/api/phone/format", {"frame_rate": 60, "resolution": "1080p"}, self.service.token
        )
        self.assertEqual(result["observed"]["format"]["frameRate"], "60")
        self.assertEqual(result["observed"]["format"]["recordResolution"], {"width": 1920, "height": 1080})
        self.assertEqual(result["fingerprint"], "device-fingerprint-60")
        self.assertEqual(result["calibration_points"], 2)

    def test_taking_a_take_is_refused_until_the_lens_is_calibrated(self):
        self.api.post(
            "/api/phone/configure",
            {"endpoint": "http://192.168.1.44:8080", "enabled": True},
            self.service.token,
        )
        with self.assertRaises(PhoneAPIError) as caught:
            self.api.post("/api/phone/test-record", {"seconds": 2}, self.service.token)
        self.assertIn(caught.exception.status, (400, 409))

    # ── separation ──────────────────────────────────────────────────────────

    def test_no_phone_route_can_reach_the_motion_path(self):
        """Judged on code, not on prose: identifiers and imports only."""
        tree = ast.parse(inspect.getsource(phone_http))
        identifiers = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
            elif isinstance(node, ast.alias):
                identifiers.update(node.name.split("."))
            elif isinstance(node, ast.ImportFrom) and node.module:
                identifiers.update(node.module.split("."))
        for forbidden in (
            "behavior_manager",
            "robot",
            "studio",
            "cart",
            "serial",
            "actuator",
            "motion",
            "direct",
        ):
            self.assertNotIn(forbidden, identifiers, f"a phone route must not reach {forbidden}")

    def test_no_phone_action_is_exposed_as_a_voice_tool(self):
        from takeone.voice import tools as voice_tools

        source = inspect.getsource(voice_tools)
        self.assertNotIn("/api/phone", source)
        self.assertNotIn("PhoneService", source)
        self.assertNotIn("phone_recorder", source)

    # ── transport limits ────────────────────────────────────────────────────

    def test_body_limits_cover_every_action_and_match_the_validator(self):
        self.assertEqual(
            sorted(BODY_LIMITS),
            [
                "/api/phone/calibrate",
                "/api/phone/color",
                "/api/phone/configure",
                "/api/phone/format",
                "/api/phone/lut",
                "/api/phone/probe",
                "/api/phone/test-record",
                "/api/phone/zoom",
            ],
        )
        # The cube validator accepts 4 MiB, so the transport must too; a smaller
        # limit would reject a valid LUT at the wrong layer.
        self.assertGreaterEqual(BODY_LIMITS["/api/phone/lut"], 4 * 1024 * 1024)
        self.assertEqual(BODY_LIMITS["/api/phone/color"], 16 * 1024)

    def test_the_server_registers_the_routes_with_their_limits_and_rejects_queries(self):
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn("PHONE_BODY_LIMITS", source)
        self.assertIn("Phone routes do not accept query parameters", source)
        self.assertIn("PhoneAPI(phone_service)", source)
        self.assertIn("PhoneService()", source)
        self.assertIn('path.startswith("/api/phone/")', source)


if __name__ == "__main__":
    unittest.main()
