"""Zoom must follow the shot clock despite REST latency, without faking readback."""

import threading
import unittest
from unittest.mock import patch

from takeone.phone.capture import PhoneTake
from takeone.phone.client import CameraError


class Clock:
    def __init__(self):
        self.now = 0.0

    def wait(self, seconds):
        self.now += seconds
        return False

    def is_set(self):
        return False


class Camera:
    def __init__(self, clock, delay=0.035):
        self.clock, self.delay = clock, delay
        self.commands = []
        self.bad_readback = False

    def set_zoom(self, target):
        self.commands.append((self.clock.now, target))
        self.clock.now += self.delay

    def zoom(self, target):
        self.set_zoom(target)
        self.clock.now += self.delay
        return target + 0.1 if self.bad_readback else target

    def recording(self):
        return False


def take(clock, camera, cues=None):
    config = {
        "calibration": [
            {"focal_mm": 24.0, "normalised": 0.0},
            {"focal_mm": 48.0, "normalised": 1 / 14},
        ],
        "zoom_hz": 20,
    }
    plan = {
        "plan_id": "cadence-test",
        "duration_s": 1.0,
        "camera_cues": cues
        or [
            {"time_s": 0.0, "focal_mm": 24.0},
            {"time_s": 1.0, "focal_mm": 48.0},
        ],
    }
    result = PhoneTake(config, plan, "unused", threading.Event(), client=camera)
    result.finished = clock
    return result


class ZoomCadenceTests(unittest.TestCase):
    def test_sparse_cues_interpolate_instead_of_holding_then_jumping(self):
        clock = Clock()
        subject = take(clock, Camera(clock))
        self.assertAlmostEqual(subject._target_at(0.5), 1 / 28)
        self.assertEqual(subject._target_at(-1), 0)
        self.assertAlmostEqual(subject._target_at(9), 1 / 14)

    def test_authored_hold_is_retained(self):
        clock = Clock()
        subject = take(
            clock,
            Camera(clock),
            [
                {"time_s": 0.0, "focal_mm": 24.0},
                {"time_s": 0.6, "focal_mm": 24.0},
                {"time_s": 1.0, "focal_mm": 48.0},
            ],
        )
        self.assertEqual(subject._target_at(0.5), 0.0)
        self.assertAlmostEqual(subject._target_at(0.8), 1 / 28)

    def test_zoom_out_is_continuous_and_reaches_its_wide_endpoint(self):
        clock = Clock()
        camera = Camera(clock)
        subject = take(
            clock,
            camera,
            [
                {"time_s": 0.0, "focal_mm": 48.0},
                {"time_s": 1.0, "focal_mm": 24.0},
            ],
        )
        with patch("takeone.phone.capture.time.perf_counter", side_effect=lambda: clock.now):
            subject._run(0)
        values = [target for _, target in camera.commands]
        self.assertGreater(len(values), 10)
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertEqual(subject.report["samples"][-1]["observed"], 0.0)

    def test_network_time_is_part_of_period_and_endpoint_is_verified(self):
        clock = Clock()
        camera = Camera(clock)
        subject = take(clock, camera)
        with patch("takeone.phone.capture.time.perf_counter", side_effect=lambda: clock.now):
            subject._run(0)
        # Old scheduler sent one endpoint for these two cues. Even with dense
        # cues, PUT+GET+sleep restricted it to ~8 Hz for this fake link.
        self.assertGreaterEqual(len(camera.commands), 18)
        self.assertAlmostEqual(camera.commands[1][0] - camera.commands[0][0], 0.05)
        samples = subject.report["samples"]
        self.assertEqual(samples[-1]["cue_time_s"], 1.0)
        self.assertAlmostEqual(samples[-1]["observed"], 1 / 14)
        self.assertTrue(any(s["observed"] is None for s in samples))
        self.assertGreaterEqual(subject.report["zoom_readbacks"], 2)
        self.assertFalse(subject.report["optical_smoothness_verified"])

    def test_late_requests_skip_backlog_and_never_replay_old_targets(self):
        clock = Clock()
        camera = Camera(clock, delay=0.22)
        subject = take(clock, camera)
        with patch("takeone.phone.capture.time.perf_counter", side_effect=lambda: clock.now):
            subject._run(0)
        for stamp, target in camera.commands:
            self.assertAlmostEqual(target, min(stamp, 1.0) / 14)
        self.assertAlmostEqual(camera.commands[-1][1], 1 / 14)
        self.assertLess(len(camera.commands), 7)

    def test_readback_mismatch_still_stops_playback(self):
        clock = Clock()
        camera = Camera(clock)
        camera.bad_readback = True
        subject = take(clock, camera)
        with patch("takeone.phone.capture.time.perf_counter", side_effect=lambda: clock.now):
            subject._run(0)
        self.assertTrue(subject.stop.is_set())
        self.assertIn("readback differs", subject.report["error"])

    def test_recording_monitor_still_stops_playback(self):
        clock = Clock()
        subject = take(clock, Camera(clock))
        subject._health()
        self.assertTrue(subject.stop.is_set())
        self.assertIn("stopped recording", subject.report["error"])

    def test_request_failure_is_not_reported_as_an_acknowledgement(self):
        clock = Clock()
        camera = Camera(clock)
        subject = take(clock, camera)
        with patch.object(camera, "set_zoom", side_effect=CameraError("timeout")):
            with patch("takeone.phone.capture.time.perf_counter", side_effect=lambda: clock.now):
                subject._run(0)
        self.assertTrue(subject.stop.is_set())
        self.assertEqual(subject.report["zoom_commands"], 0)


if __name__ == "__main__":
    unittest.main()
