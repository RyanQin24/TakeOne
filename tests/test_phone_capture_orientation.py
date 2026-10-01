"""Robot playback must not record a portrait clip for a landscape plan."""

import tempfile
import threading
import unittest
from pathlib import Path

from takeone.phone.capture import PhoneTake
from takeone.phone.client import CameraError


class PortraitCamera:
    def __init__(self):
        self.commands = []

    def probe(self):
        return {
            "recording": False,
            "fingerprint": "same-phone",
            "format": {"recordResolution": {"width": 1214, "height": 2160}},
        }

    def request(self, *args):
        self.commands.append(args)


class FlakyCamera:
    def __init__(self):
        self.probes = 0

    def probe(self):
        self.probes += 1
        if self.probes == 1:
            raise CameraError("temporary camera timeout")
        return {"recording": False}


class PhoneOrientationTests(unittest.TestCase):
    def test_camera_preflight_retries_one_transient_timeout_before_recording(self):
        config = {
            "calibration": [
                {"focal_mm": 24, "normalised": 0.0},
                {"focal_mm": 48, "normalised": 0.0714285714},
            ],
            "zoom_hz": 10,
            "fingerprint": "same-phone",
        }
        plan = {
            "plan_id": "shot-1",
            "duration_s": 1,
            "camera_cues": [
                {"time_s": 0, "focal_mm": 24},
                {"time_s": 1, "focal_mm": 24},
            ],
        }
        camera = FlakyCamera()
        with tempfile.TemporaryDirectory() as folder:
            take = PhoneTake(config, plan, Path(folder), threading.Event(), client=camera)
            self.assertEqual(take._probe(), {"recording": False})
            self.assertEqual(camera.probes, 2)
            self.assertEqual(take.report["probe_attempts"], 2)

    def test_portrait_format_blocks_landscape_robot_plan_before_record(self):
        config = {
            "calibration": [
                {"focal_mm": 24, "normalised": 0.0},
                {"focal_mm": 48, "normalised": 0.0714285714},
            ],
            "zoom_hz": 10,
            "fingerprint": "same-phone",
        }
        plan = {
            "schema": "takeone.studio-motion.v1",
            "plan_id": "shot-1",
            "duration_s": 1,
            "camera_cues": [
                {"time_s": 0, "focal_mm": 24},
                {"time_s": 1, "focal_mm": 24},
            ],
        }
        camera = PortraitCamera()
        with tempfile.TemporaryDirectory() as folder:
            take = PhoneTake(config, plan, Path(folder), threading.Event(), client=camera)
            with self.assertRaisesRegex(CameraError, "landscape"):
                take.__enter__()
            self.assertFalse(take.report["start_attempted"])
            self.assertEqual(camera.commands, [])


if __name__ == "__main__":
    unittest.main()
