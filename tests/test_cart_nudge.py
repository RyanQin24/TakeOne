"""Cart commissioning tests use injected devices/processes only. No physical IO."""

import copy
import io
import json
import queue
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from takeone.cart.nudge import NudgeService
from takeone.cart.nudge_plan import prepare_nudge, validate_nudge
from takeone.cart.nudge_worker import NudgeControl, run_plan
from takeone.cart.runtime import CartRunner
from takeone.protocol import uart_pair

from tests.support.devices import VirtualClock


class TestTransport:
    simulated = True

    def __init__(self, clock, polarity=-1):
        self.clock, self.polarity = clock, polarity
        self.connected = False
        self.connects = 0
        self.sent = []

    def connect(self):
        self.connects += 1
        self.connected = True

    def set_speed(self, left, right):
        wire = uart_pair(self.polarity * left or 0.0, self.polarity * right or 0.0)
        self.sent.append((self.clock.now(), wire))
        return wire

    def close(self):
        self.connected = False


class PlanTests(unittest.TestCase):
    def test_exact_plan_wire_and_no_distance_claim(self):
        plan = prepare_nudge("forward")
        document = plan.to_dict()
        self.assertEqual(plan.duration_s, 0.5)
        self.assertEqual(plan.command_at(0), (0.04, 0.04))
        self.assertEqual(plan.command_at(0.5), (0.0, 0.0))
        self.assertEqual(document["transmitted_wire"], "-0.04,-0.04\n")
        self.assertIsNone(document["predicted_distance_m"])
        self.assertFalse(document["arms_commanded"])
        self.assertEqual(validate_nudge(document).plan_id, plan.plan_id)

    def test_changed_duration_polarity_and_provenance_rejected(self):
        document = prepare_nudge("forward").to_dict()
        for field, value in (("duration_s", 1.0), ("wire_polarity", 1), ("provenance", {})):
            changed = copy.deepcopy(document)
            changed[field] = value
            with self.assertRaises(ValueError):
                validate_nudge(changed)

    def test_other_directions_do_not_silently_flip_configuration(self):
        for direction in ("backward", "left", "right", None):
            with self.assertRaises(ValueError):
                prepare_nudge(direction)


class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = prepare_nudge("forward")

    def setUp(self):
        self.clock = VirtualClock()
        self.control = NudgeControl(self.clock.now)
        self.transport = TestTransport(self.clock)

    def factory(self, transport, timing, **kw):
        return CartRunner(transport, timing, self.clock.now, self.clock.sleep, **kw)

    def test_no_execute_means_no_connection(self):
        with self.assertRaises(InterruptedError):
            run_plan(self.plan, self.transport, self.control, runner_factory=self.factory)
        self.assertEqual(self.transport.connects, 0)
        self.assertEqual(self.transport.sent, [])

    def test_finite_schedule_applies_polarity_once_and_shutdown_zeros(self):
        self.control.receive('{"command":"execute"}')
        report = run_plan(self.plan, self.transport, self.control, runner_factory=self.factory)
        motion = [(stamp, wire) for stamp, wire in self.transport.sent if wire != "0.00,0.00\n"]
        self.assertEqual(len(motion), 25)
        self.assertEqual({wire for _, wire in motion}, {"-0.04,-0.04\n"})
        zero_after = next(
            stamp for stamp, wire in self.transport.sent if stamp > motion[-1][0] and wire == "0.00,0.00\n"
        )
        self.assertAlmostEqual(zero_after - motion[0][0], 0.5)
        self.assertFalse(report["physical_stop_confirmed"])
        self.assertFalse(self.transport.connected)
        moving_event = next(e for e in report["events"] if e.get("requested_wire") == "0.04,0.04\n")
        self.assertEqual(moving_event["wire"], "-0.04,-0.04\n")

    def test_expiry_and_eof_latch_no_resume(self):
        self.control.receive('{"command":"execute"}')
        self.clock.sleep(0.76)
        self.assertTrue(self.control.cancelled())
        self.control.receive('{"command":"heartbeat"}')
        self.assertTrue(self.control.cancelled())
        self.control = NudgeControl(self.clock.now)
        self.control.receive("")
        self.control.receive('{"command":"execute"}')
        self.assertFalse(self.control.execute.is_set())

    def test_stop_mid_run_sends_only_zero_after_cancel(self):
        self.control.receive('{"command":"execute"}')
        original = self.transport.set_speed

        def send(left, right):
            result = original(left, right)
            if left:
                self.control.receive('{"command":"stop"}')
            return result

        self.transport.set_speed = send
        with self.assertRaises(InterruptedError):
            run_plan(self.plan, self.transport, self.control, runner_factory=self.factory)
        self.assertEqual(sum(wire != "0.00,0.00\n" for _, wire in self.transport.sent), 1)
        self.assertEqual(self.transport.sent[-1][1], "0.00,0.00\n")

    def test_wrong_wire_is_a_fault(self):
        self.transport.polarity = 1
        self.control.receive('{"command":"execute"}')
        original = self.transport.set_speed
        self.transport.set_speed = lambda left, right: "0.05,0.05\n" if left else original(left, right)
        with self.assertRaisesRegex(RuntimeError, "different motor packet"):
            run_plan(self.plan, self.transport, self.control, runner_factory=self.factory)


class Output:
    def __init__(self):
        self.queue = queue.Queue()

    def __iter__(self):
        while (line := self.queue.get(timeout=3)) is not None:
            yield line

    def emit(self, **event):
        self.queue.put(json.dumps(dict(source="nudge_worker", **event)) + "\n")

    def close(self):
        pass


class Process:
    def __init__(self):
        self.stdout = Output()
        self.stdin = io.StringIO()
        self.stdout.emit(phase="ready_for_execute")

    def finish(self):
        self.stdout.emit(phase="commands_completed", terminal=True)
        self.stdout.queue.put(None)

    def wait(self):
        return 0


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = VirtualClock()
        self.launches = []
        self.process = Process()

        def launch(path, plan_id):
            self.launches.append((path, plan_id))
            return self.process

        self.service = NudgeService(
            lambda: None,
            launcher=launch,
            clock=self.clock.now,
            folder=Path(self.temp.name),
            runtime=sys.executable,
        )

    def tearDown(self):
        self.service.close()
        if self.launches:
            self.process.finish()
            for _ in range(100):
                if not self.service.status("owner")["active"]:
                    break
                time.sleep(0.005)

    def proposal(self):
        return self.service.prepare("owner", "forward")["review"]

    def start(self, review, **extra):
        args = dict(
            owner="owner",
            review_id=review["review_id"],
            plan_id=review["plan_id"],
            request_id="request-1234567890",
            operator_ready=True,
        )
        return self.service.start(**(args | extra))

    def test_prepare_and_unconfirmed_or_wrong_owner_never_launch(self):
        review = self.proposal()
        self.assertEqual(self.launches, [])
        with self.assertRaises(PermissionError):
            self.start(review, operator_ready=False)
        with self.assertRaises(ValueError):
            self.start(review, owner="other")
        self.assertEqual(self.launches, [])

    def test_expired_replaced_and_revoked_reviews(self):
        review = self.proposal()
        self.clock.sleep(91)
        with self.assertRaises(ValueError):
            self.start(review)
        review = self.proposal()
        self.proposal()
        with self.assertRaises(ValueError):
            self.start(review)
        review = self.proposal()
        self.service.stop("owner")
        with self.assertRaises(ValueError):
            self.start(review)
        self.assertEqual(self.launches, [])

    def test_busy_and_changed_source_block_start(self):
        review = self.proposal()
        with patch.object(self.service, "check_idle", side_effect=ValueError("busy")):
            with self.assertRaises(ValueError):
                self.start(review)
        with patch("takeone.cart.nudge.validate_nudge", side_effect=ValueError("stale")):
            with self.assertRaises(ValueError):
                self.start(review)
        self.assertEqual(self.launches, [])

    def test_one_approval_launches_once_and_waits_for_owned_browser_heartbeat(self):
        review = self.proposal()
        state = self.start(review)
        self.start(review)
        self.assertEqual(len(self.launches), 1)
        for _ in range(100):
            if self.service.status("owner")["phase"] == "ready_for_execute":
                break
            time.sleep(0.005)
        self.assertEqual(self.process.stdin.getvalue(), "")
        with self.assertRaises(PermissionError):
            self.service.heartbeat("other", state["run_id"])
        self.service.heartbeat("owner", state["run_id"])
        self.assertIn('"execute"', self.process.stdin.getvalue())
        self.service.stop("owner")
        self.assertIn('"stop"', self.process.stdin.getvalue())

    def test_distance_and_wrong_direction_invalidate_review(self):
        self.proposal()
        with self.assertRaises(ValueError):
            self.service.prepare("owner", "forward", 0.1)
        self.assertIsNone(self.service.status("owner")["pending"])
        with self.assertRaises(ValueError):
            self.service.prepare("owner", "backward")
        self.assertEqual(self.launches, [])


if __name__ == "__main__":
    unittest.main()
