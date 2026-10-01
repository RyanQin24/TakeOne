"""Use Blackmagic's native millimetres without fabricating calibration points."""

import copy
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from takeone.phone.capture import PhoneTake, lens_schedule
from takeone.phone.client import BlackmagicCamera, CameraError, device_focal_range
from takeone.phone.service import PhoneService

CALIBRATION = [{"focal_mm": 24, "normalised": 0}, {"focal_mm": 48, "normalised": 1 / 14}]
OBSERVED = {
    "fingerprint": "phone",
    "focal_mm": 24,
    "normalised": 0,
    "zoom_description": {"controllable": True, "focalLength": {"min": 24, "max": 360}},
}
PLAN = {
    "plan_id": "zoom",
    "duration_s": 5,
    "camera_cues": [
        {"time_s": 0, "focal_mm": 24},
        {"time_s": 2, "focal_mm": 24},
        {"time_s": 3, "focal_mm": 180},
        {"time_s": 5, "focal_mm": 180},
    ],
}


class NativeFocalTests(unittest.TestCase):
    def test_native_range_requires_matched_identity_and_equivalent_wide_anchor(self):
        config = {"fingerprint": "phone", "calibration": CALIBRATION}
        self.assertEqual(device_focal_range(OBSERVED, config), [24, 360])
        self.assertIsNone(device_focal_range({**OBSERVED, "fingerprint": "different"}, config))
        changed = copy.deepcopy(OBSERVED)
        changed["zoom_description"]["focalLength"]["min"] = 13
        self.assertIsNone(device_focal_range(changed, config))
        self.assertIsNone(device_focal_range({**OBSERVED, "focal_mm": None}, config))

    def test_native_schedule_reaches_180_while_legacy_mapping_still_refuses_extrapolation(self):
        config = {"calibration": CALIBRATION, "device_focal_range_mm": [24, 360]}
        self.assertEqual(lens_schedule(config, PLAN), ([0, 2, 3, 5], [24, 24, 180, 180]))
        with self.assertRaisesRegex(ValueError, "outside measured"):
            lens_schedule({"calibration": CALIBRATION}, PLAN)
        with self.assertRaises(ValueError):
            lens_schedule({**config, "device_focal_range_mm": [24, 100]}, PLAN)

    def test_client_commands_and_reads_native_focal_length(self):
        camera = BlackmagicCamera("http://127.0.0.1:4444")
        with patch.object(
            camera, "request", side_effect=[None, {"focalLength": 180, "normalised": 0.464}]
        ) as request:
            self.assertEqual(camera.focal_zoom(180), 180)
        self.assertEqual(request.call_args_list[0].args, ("PUT", "/lens/zoom", {"focalLength": 180}))

    def test_capture_uses_native_controls_and_checks_readback(self):
        camera = Mock()
        camera.focal_zoom.return_value = 180
        take = PhoneTake(
            {"calibration": CALIBRATION, "device_focal_range_mm": [24, 360], "zoom_hz": 20},
            PLAN,
            "unused",
            threading.Event(),
            client=camera,
        )
        self.assertEqual(take._target_at(1), 24)
        self.assertEqual(take._target_at(2.5), 102)
        self.assertEqual(take._target_at(4), 180)
        take._zoom(180, 3)
        camera.focal_zoom.assert_called_once_with(180)
        camera.zoom.assert_not_called()
        self.assertEqual(take.report["zoom_units"], "mm")
        camera.focal_zoom.return_value = 48
        with self.assertRaisesRegex(CameraError, "readback differs"):
            take._zoom(180, 3)

    def test_capture_capabilities_do_not_change_saved_calibration(self):
        with tempfile.TemporaryDirectory() as folder:
            service = PhoneService(Path(folder) / "phone.json")
            service.config.update(
                enabled=True,
                endpoint="http://127.0.0.1:4444",
                fingerprint="phone",
                calibration=copy.deepcopy(CALIBRATION),
            )
            service.config["color"].update(operator_confirmed=True, lut_name="No LUT")
            service.observed = copy.deepcopy(OBSERVED)
            before = copy.deepcopy(service.config)
            capture = service.reserve(PLAN)
            self.assertEqual(capture["device_focal_range_mm"], [24, 360])
            self.assertEqual(service.config, before)

    def test_fast_zoom_verifies_the_180mm_endpoint_during_the_hold(self):
        from tests.test_phone_zoom_cadence import Clock

        clock = Clock()
        camera = Mock()
        camera.zoom_stream = None
        camera.focal_zoom.side_effect = lambda target: target
        take = PhoneTake(
            {"calibration": CALIBRATION, "device_focal_range_mm": [24, 360], "zoom_hz": 20},
            PLAN,
            "unused",
            threading.Event(),
            client=camera,
        )
        take.finished = clock
        with patch("takeone.phone.capture.time.perf_counter", side_effect=lambda: clock.now):
            take._run_zoom(0)
        samples = take.report["samples"]
        self.assertTrue(all(row["cue_time_s"] >= 2 for row in samples))
        self.assertTrue(any(row["requested"] == 180 and row["observed"] == 180 for row in samples))
        self.assertTrue(all(row["requested"] == 180 for row in samples if row["cue_time_s"] >= 3))


if __name__ == "__main__":
    unittest.main()
