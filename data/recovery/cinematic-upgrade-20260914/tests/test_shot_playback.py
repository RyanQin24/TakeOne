"""Playback conversion, timeline and dispatch behaviour. No serial ports are opened."""

import json
import math
import threading
import time
import unittest

from takeone.contracts import JOINTS
from takeone.motion import play
from takeone.paths import DATA

SHOT = DATA / "robot-commissioning-ready.json"


class StubArm:
    """Records the goals a dispatch loop actually sent, in order."""

    def __init__(self, role, fail_first=0):
        self.role = role
        self.joints = play.Joints(role)
        self.sent = []
        self.fail_first = fail_first

    def goal(self, counts):
        if self.fail_first > 0:
            self.fail_first -= 1
            raise ConnectionError("stub write failed")
        self.sent.append((time.perf_counter(), dict(counts)))

    def present(self):
        return dict(self.sent[-1][1])


class StubCart:
    def __init__(self):
        self.sent = []

    def set_speed(self, left, right):
        self.sent.append((time.perf_counter(), (left, right)))
        return f"{left:.2f},{right:.2f}\n"


def records():
    return {
        role: dict(sent=0, misses=0, late_skips=0, max_late_s=0.0, final_goal=None, errors=[], fault=None)
        for role in play.ROLES
    }


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.joints = {role: play.Joints(role) for role in play.ROLES}

    def test_every_shot_sample_converts_inside_its_calibration(self):
        shot = play.load_shot(SHOT)
        for role in play.ROLES:
            joints = self.joints[role]
            for sample in shot["samples"]:
                for name, value in joints.counts(sample["arms"][role]).items():
                    self.assertTrue(joints.low[name] <= value <= joints.high[name])
            self.assertEqual(sum(joints.clamped.values()), 0, f"{role}: shot needed clamping")

    def test_an_out_of_range_angle_is_clamped_to_the_calibration_endpoint(self):
        joints = self.joints["phone"]
        counts = joints.counts((10.0,) * 5)
        self.assertEqual(counts, {name: joints.high[name] for name in JOINTS})
        self.assertEqual(sum(joints.clamped.values()), 5)
        counts = joints.counts((-10.0,) * 5)
        self.assertEqual(counts, {name: joints.low[name] for name in JOINTS})

    def test_counts_match_the_installed_lerobot_degree_conversion(self):
        from takeone.calibration import ArmMapping

        mapping = ArmMapping.load("phone", require_motion=False)
        q = play.load_shot(SHOT)["samples"][0]["arms"]["phone"]
        self.assertEqual(self.joints["phone"].counts(q), mapping.to_raw(q))


class ApproachTests(unittest.TestCase):
    def setUp(self):
        self.start = dict.fromkeys(JOINTS, 2000)

    def test_approach_ends_on_the_target_and_never_exceeds_the_requested_rate(self):
        period, rate = 0.04, 25.0
        target = dict(self.start, elbow_flex=3000)
        frames = play.approach_frames(self.start, target, period, rate)
        self.assertEqual(frames[-1], target)
        steps = [abs(b["elbow_flex"] - a["elbow_flex"]) for a, b in zip(frames, frames[1:])]
        # Goals are whole encoder counts, and one count per period is 2.2 deg/s at
        # this rate, so a count-level path cannot be held tighter than that.
        quantization = 360 / 4095 / period
        self.assertLessEqual(max(steps) * 360 / 4095 / period, rate + quantization)

    def test_approach_starts_and_ends_slowly(self):
        target = dict(self.start, shoulder_lift=2800)
        frames = play.approach_frames(self.start, target, 0.04, 25.0)
        steps = [abs(b["shoulder_lift"] - a["shoulder_lift"]) for a, b in zip(frames, frames[1:])]
        self.assertLess(steps[0], max(steps) / 4)
        self.assertLess(steps[-1], max(steps) / 4)

    def test_an_arm_already_at_the_target_needs_no_approach(self):
        self.assertEqual(play.approach_frames(self.start, dict(self.start), 0.04, 25.0), [])

    def test_timeline_ends_on_the_shot_and_both_arms_share_one_length(self):
        shot = play.load_shot(SHOT)
        joints = {role: play.Joints(role) for role in play.ROLES}
        counts = {r: [joints[r].counts(s["arms"][r]) for s in shot["samples"]] for r in play.ROLES}
        starts = {r: dict(counts[r][0], elbow_flex=counts[r][0]["elbow_flex"] + 400) for r in play.ROLES}
        frames, lead_s, period = play.build_timeline(shot, counts, starts, 25.0)
        self.assertEqual(len(frames["phone"]), len(frames["light"]))
        self.assertGreater(lead_s, 0)
        for role in play.ROLES:
            self.assertEqual(frames[role][-1], counts[role][-1])
            # The shot itself starts exactly at the lead boundary.
            self.assertEqual(frames[role][round(lead_s / period)], counts[role][0])


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.frames = {role: [dict.fromkeys(JOINTS, 2000 + i) for i in range(10)] for role in play.ROLES}

    def test_both_arms_receive_every_setpoint_in_order(self):
        arms = {role: StubArm(role) for role in play.ROLES}
        result = records()
        play.stream_arms(arms, self.frames, 0.01, time.perf_counter(), threading.Event(), result)
        for role in play.ROLES:
            self.assertEqual([c for _, c in arms[role].sent], self.frames[role])
            self.assertEqual(result[role]["sent"], 10)
            self.assertEqual(result[role]["misses"], 0)

    def test_a_dropped_packet_is_logged_and_the_trajectory_continues(self):
        arms = {role: StubArm(role, fail_first=2) for role in play.ROLES}
        result = records()
        play.stream_arms(arms, self.frames, 0.01, time.perf_counter(), threading.Event(), result)
        for role in play.ROLES:
            self.assertEqual(result[role]["misses"], 2)
            self.assertEqual(result[role]["sent"], 8)
            self.assertIsNone(result[role]["fault"], "a lost datagram must not fault the run")
            self.assertEqual(arms[role].sent[-1][1], self.frames[role][-1])

    def test_a_persistently_dead_bus_faults_and_stops_the_run(self):
        arms = {role: StubArm(role, fail_first=10_000) for role in play.ROLES}
        frames = {role: [dict.fromkeys(JOINTS, 2000)] * (play.MISS_LIMIT + 5) for role in play.ROLES}
        stop = threading.Event()
        result = records()
        play.stream_arms(arms, frames, 0.001, time.perf_counter(), stop, result)
        self.assertTrue(stop.is_set())
        self.assertTrue(any(result[role]["fault"] for role in play.ROLES))

    def test_a_late_start_skips_superseded_setpoints_instead_of_bursting(self):
        arms = {role: StubArm(role) for role in play.ROLES}
        result = records()
        # An epoch four ticks in the past is a host stall the loop must absorb.
        play.stream_arms(arms, self.frames, 0.01, time.perf_counter() - 0.04, threading.Event(), result)
        for role in play.ROLES:
            self.assertGreaterEqual(result[role]["late_skips"], 3)
            self.assertLess(result[role]["sent"], 10)
            self.assertEqual(arms[role].sent[-1][1], self.frames[role][-1])

    def test_an_operator_stop_ends_dispatch_and_freezes_on_the_last_goal(self):
        arms = {role: StubArm(role) for role in play.ROLES}
        frames = {role: [dict.fromkeys(JOINTS, 2000 + i) for i in range(200)] for role in play.ROLES}
        stop = threading.Event()
        result = records()
        threading.Timer(0.05, stop.set).start()
        play.stream_arms(arms, frames, 0.01, time.perf_counter(), stop, result)
        for role in play.ROLES:
            self.assertLess(result[role]["sent"], 200)
            self.assertEqual(result[role]["final_goal"], arms[role].sent[-1][1])


class CartTests(unittest.TestCase):
    def setUp(self):
        self.times = [0.0, 0.1, 0.2]
        self.commands = [(0.0, 0.0), (0.04, 0.05), (0.0, 0.0)]

    def run_cart(self, lead_s=0.0, duration_s=0.3):
        cart = StubCart()
        record = dict(sent=0, misses=0, moving_writes=0, stop_writes=0, max_gap_s=0.0, errors=[])
        play.drive_cart(
            cart,
            self.times,
            self.commands,
            lead_s,
            duration_s,
            0.005,
            time.perf_counter(),
            threading.Event(),
            record,
        )
        return cart, record

    def test_the_active_command_is_resent_far_inside_the_firmware_watchdog(self):
        cart, record = self.run_cart()
        gaps = [b - a for (a, _), (b, _) in zip(cart.sent, cart.sent[1:])]
        watchdog = 0.060
        self.assertLess(max(gaps), watchdog, f"max gap {max(gaps):.3f}s reaches the watchdog")
        self.assertGreater(record["moving_writes"], 10)

    def test_the_schedule_is_followed_and_the_run_always_ends_stopped(self):
        cart, record = self.run_cart()
        for stamp, pair in cart.sent:
            self.assertIn(pair, self.commands)
        self.assertEqual(cart.sent[-1][1], (0.0, 0.0))
        self.assertGreater(record["stop_writes"], 0)

    def test_the_cart_stays_stopped_through_the_arm_approach(self):
        cart, _ = self.run_cart(lead_s=0.2, duration_s=0.3)
        start = cart.sent[0][0]
        during = [pair for stamp, pair in cart.sent if stamp - start < 0.15]
        self.assertTrue(all(pair == (0.0, 0.0) for pair in during))


class ShotContractTests(unittest.TestCase):
    def test_a_shot_missing_its_final_stop_is_refused(self):
        import tempfile
        from pathlib import Path

        document = json.loads(SHOT.read_text(encoding="utf-8-sig"))
        document["cart_schedule"][-1]["commands"] = [0.04, 0.04]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shot.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ValueError):
                play.load_shot(path)

    def test_the_saved_shot_loads_and_reports_its_own_identity(self):
        shot = play.load_shot(SHOT)
        self.assertEqual(shot["schema"], "takeone.robot-plan.v2")
        self.assertTrue(math.isfinite(float(shot["duration_s"])))
        self.assertEqual(len(shot["samples"]), 326)


if __name__ == "__main__":
    unittest.main()
