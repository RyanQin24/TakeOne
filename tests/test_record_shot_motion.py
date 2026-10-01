"""Selected-shot motor and camera timelines. All device IO remains mocked."""

import copy
import math
import unittest
from unittest.mock import patch

from takeone.motion.play import Arm
from takeone.motion.record_shot import prepare_shot
from takeone.motion.studio_plan import prepare, validate
from takeone.phone.capture import lens_schedule


class RecordShotMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = prepare(dict(mode="template", template_id="tilt_up", duration_s=6))

    def test_selected_shot_retains_the_reviewed_motor_goals(self):
        source = self.source
        with patch("takeone.motion.record_shot.prepare", return_value=source):
            plan = prepare_shot(
                source["settings"],
                dict(plan_id=source["plan_id"], start_s=0, duration_s=source["duration_s"]),
            )
        self.assertEqual(plan["samples"], source["samples"])
        self.assertEqual(plan["cart_schedule"], source["cart_schedule"])
        self.assertEqual(validate(plan), plan)

    def test_one_cropped_shot_stops_at_its_own_end(self):
        source = self.source
        start = source["orbit_start_s"] + 1.0
        with patch("takeone.motion.record_shot.prepare", return_value=source):
            plan = prepare_shot(
                source["settings"], dict(plan_id=source["plan_id"], start_s=start, duration_s=2)
            )
        self.assertAlmostEqual(plan["duration_s"], source["orbit_start_s"] + 2)
        expected = source["samples"][round((start + 2) / 0.04)]["raw_by_role"]
        self.assertEqual(plan["raw_goals"], expected)
        self.assertEqual(plan["cart_schedule"][-1]["commands"], [0, 0])
        self.assertTrue(
            all(
                row["commands"] == [0, 0]
                for row in plan["cart_schedule"]
                if row["time_s"] < plan["orbit_start_s"]
            )
        )
        self.assertEqual(plan["camera_cues"][-1]["time_s"], plan["duration_s"])

    def test_phone_accepts_rounded_full_and_cropped_shot_boundaries(self):
        source = copy.deepcopy(self.source)
        # A changing lens also verifies that removing a duplicate endpoint
        # preserves the selected shot's final lens target.
        for cue in source["camera_cues"]:
            cue["focal_mm"] = 24 + 24 * cue["time_s"] / source["duration_s"]
        config = {
            "calibration": [
                {"focal_mm": 24, "normalised": 0},
                {"focal_mm": 48, "normalised": 1},
            ]
        }
        windows = [(0, source["duration_s"]), (source["orbit_start_s"] + 1, 2)]
        with patch("takeone.motion.record_shot.prepare", return_value=source):
            for start, duration in windows:
                for requested in (
                    math.nextafter(duration, -math.inf),
                    duration,
                    math.nextafter(duration, math.inf),
                ):
                    with self.subTest(start=start, duration=requested):
                        plan = prepare_shot(
                            source["settings"],
                            dict(
                                plan_id=source["plan_id"],
                                start_s=start,
                                duration_s=requested,
                            ),
                        )
                        times, targets = lens_schedule(config, plan)
                        self.assertEqual(times[0], 0)
                        self.assertEqual(times[-1], plan["duration_s"])
                        self.assertTrue(all(a < b for a, b in zip(times, times[1:])))
                        self.assertAlmostEqual(targets[0], start / source["duration_s"])
                        self.assertAlmostEqual(targets[-1], (start + duration) / source["duration_s"])

    def test_stale_or_outside_shots_do_not_compile(self):
        source = self.source
        with patch("takeone.motion.record_shot.prepare", return_value=source):
            for window in [
                dict(plan_id="wrong", start_s=0, duration_s=2),
                dict(plan_id=source["plan_id"], start_s=0, duration_s=1000),
            ]:
                with self.assertRaises(ValueError):
                    prepare_shot(source["settings"], window)

    def test_connection_error_keeps_the_windows_cause(self):
        class Bus:
            port = "COM9"

            def connect(self):
                try:
                    raise PermissionError("Access is denied")
                except PermissionError as error:
                    raise ConnectionError("Find port") from error

        arm = object.__new__(Arm)
        arm.role, arm.bus = "phone", Bus()
        with self.assertRaisesRegex(ConnectionError, "phone arm on COM9: Access is denied"):
            arm.open()
