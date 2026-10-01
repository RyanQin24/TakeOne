"""Robot button contracts and fault paths with isolated fake devices only."""

import copy
import io
import json
import math
import queue
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from takeone.calibration import ArmMapping
from takeone.motion import play
from takeone.motion.plan import digest
from takeone.motion.studio import TOKEN_HEADER, RobotPlayback
from takeone.motion.studio_plan import prepare, validate
from takeone.motion.studio_worker import BrowserControl, device_ownership

from tests.test_director_http import server_module


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = prepare({})

    def test_retimes_to_wire_cap_preserving_nominal_circle(self):
        plan = self.plan
        self.assertGreater(plan["duration_s"], 20)
        self.assertLessEqual(plan["summary"]["max_command"], 0.15)
        for actual, requested in zip(
            plan["summary"]["wheel_travel_m"], plan["summary"]["requested_wheel_travel_m"]
        ):
            self.assertLess(abs(actual - requested), 0.003)
        self.assertLess(abs(plan["summary"]["predicted_sweep_rad"] - math.tau), 0.01)
        self.assertTrue(all(v >= 0 for row in plan["cart_schedule"] for v in row["commands"]))
        self.assertEqual(plan["cart_schedule"][-1]["commands"], [0, 0])
        self.assertFalse(plan["summary"]["physical_path_verified"])

    def test_phone_and_light_use_their_own_calibration_without_clamping(self):
        for role, wrist in (("phone", 6), ("light", 5)):
            mapping = ArmMapping.load(role, require_motion=False)
            self.assertEqual(mapping.raw_calibration["wrist_roll"]["id"], wrist)
            for sample in (self.plan["samples"][0], self.plan["samples"][-1]):
                self.assertEqual(tuple(sample["arms"][role]), mapping.from_raw(sample["raw_by_role"][role]))
            self.assertEqual(self.plan["samples"][0]["raw_by_role"][role], self.plan["initial_raw"][role])
            self.assertEqual(self.plan["samples"][-1]["raw_by_role"][role], self.plan["raw_goals"][role])

    def test_aiming_is_on_the_shared_clock_before_the_cart_moves(self):
        plan = self.plan
        self.assertAlmostEqual(plan["duration_s"], plan["orbit_start_s"] + plan["orbit_duration_s"])
        for row in plan["cart_schedule"]:
            if row["time_s"] < plan["orbit_start_s"]:
                self.assertEqual(row["commands"], [0, 0])
        for sample in plan["samples"]:
            if sample["time_s"] >= plan["orbit_start_s"]:
                self.assertEqual(sample["raw_by_role"], plan["raw_goals"])

    def test_reverse_orbit_produces_reverse_commands(self):
        plan = prepare({"sweep_rad": -math.pi, "duration_s": 40})
        self.assertTrue(all(v <= 0 for row in plan["cart_schedule"] for v in row["commands"]))
        self.assertAlmostEqual(plan["summary"]["predicted_sweep_rad"], -math.pi, delta=0.01)

    def test_stale_and_rehashed_malformed_commands_rejected(self):
        changed = copy.deepcopy(self.plan)
        changed["settings"]["radius_m"] = 8
        with self.assertRaises(ValueError):
            validate(changed)
        changed = copy.deepcopy(self.plan)
        changed["cart_schedule"][0]["commands"] = [0.9, 0.9]
        changed["plan_id"] = digest({k: v for k, v in changed.items() if k != "plan_id"})
        with self.assertRaises(ValueError):
            validate(changed)


class Lines:
    def __init__(self):
        self.queue = queue.Queue()

    def __iter__(self):
        return self

    def __next__(self):
        value = self.queue.get(timeout=5)
        if value is None:
            raise StopIteration
        return value

    def close(self):
        pass


class FakeProcess:
    """No child process or device. Exercises the exact broker IO interface."""

    def __init__(self):
        self.stdout = Lines()
        self.stdin = io.StringIO()
        self.original_write = self.stdin.write
        self.stdin.write = self.write
        self.commands = []
        self.done = False

    def write(self, value):
        self.commands.append(json.loads(value)["command"])
        if self.commands[-1] == "stop" and not self.done:
            self.done = True
            self.stdout.queue.put(
                json.dumps(dict(source="studio_worker", terminal=True, phase="stopped")) + "\n"
            )
            self.stdout.queue.put(None)
        return self.original_write(value)

    def wait(self):
        return 0


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = prepare({"sweep_rad": math.pi / 2})

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.launched = []

        def launch(path, folder):
            self.launched.append((path, folder))
            self.child = FakeProcess()
            return self.child

        self.service = RobotPlayback(launcher=launch, folder=self.folder.name, runtime=Path(__file__))
        self.server = server_module.make_server(
            0, Path(self.folder.name) / "sessions.sqlite3", {}, {}, robot_service=self.service
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.service.close()
        if self.service.reader:
            self.service.reader.join(timeout=3)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.folder.cleanup()

    def request(self, path, data=None, token=True, origin=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers[TOKEN_HEADER] = self.service.token
        if origin:
            headers["Origin"] = origin
        request = Request(
            self.base + path, data=None if data is None else json.dumps(data).encode(), headers=headers
        )
        try:
            response = urlopen(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def prepare(self):
        with patch("takeone.motion.studio.prepare", return_value=self.plan):
            status, result = self.request("/api/robot/prepare", {"settings": {}})
        self.assertEqual(status, 200)
        return result

    def test_get_and_prepare_never_launch_devices(self):
        self.assertEqual(self.request("/api/robot/status")[1]["phase"], "idle")
        self.assertFalse(self.prepare()["ports_opened"])
        self.assertEqual(self.launched, [])

    def test_preview_waits_for_another_tab_and_returns_its_requested_movement(self):
        def preview(settings):
            return {"preview": {"settings": settings}}

        with patch("takeone.previs.templates.compile_template", side_effect=preview):
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.server.compile_lock.acquire()
                try:
                    future = pool.submit(self.request, "/api/previs/templates", {"template_id": "whip_pan"})
                    with self.assertRaises(TimeoutError):
                        future.result(timeout=0.15)
                finally:
                    self.server.compile_lock.release()
                status, result = future.result(timeout=5)
        self.assertEqual(status, 200)
        self.assertEqual(result["settings"]["template_id"], "whip_pan")
        self.assertEqual(self.launched, [])

    def test_local_origin_token_and_prepared_plan_required(self):
        body = dict(plan_id="forged", request_id="a" * 32)
        self.assertEqual(self.request("/api/robot/start", body, token=False)[0], 403)
        self.assertEqual(self.request("/api/robot/start", body, origin="https://example.com")[0], 403)
        self.assertEqual(self.request("/api/robot/status", origin="https://example.com")[0], 403)
        self.assertEqual(self.request("/api/robot/start", body)[0], 409)
        self.assertEqual(self.launched, [])

    def test_single_owner_idempotent_start_heartbeat_stop_and_no_auto_restart(self):
        prepared = self.prepare()
        body = dict(plan_id=prepared["plan_id"], request_id="b" * 32)
        code, state = self.request("/api/robot/start", body)
        self.assertEqual(code, 200)
        self.assertTrue(state["active"])
        self.assertEqual(self.request("/api/robot/start", body)[0], 200)
        self.assertEqual(self.request("/api/robot/start", dict(body, request_id="c" * 32))[0], 409)
        self.assertEqual(len(self.launched), 1)
        run = {"run_id": state["run_id"]}
        self.request("/api/robot/heartbeat", run)
        self.assertIn("heartbeat", self.child.commands)
        self.request("/api/robot/stop", run)
        self.service.reader.join(timeout=3)
        self.assertFalse(self.service.status()["active"])
        self.assertEqual(self.service.status()["phase"], "stopped")
        self.request("/api/robot/start", body)
        self.assertEqual(len(self.launched), 1)


class ControlTests(unittest.TestCase):
    def test_a_second_studio_worker_cannot_own_the_devices(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("takeone.motion.studio_worker.DATA", Path(folder)),
        ):
            with device_ownership():
                with self.assertRaises(OSError):
                    with device_ownership():
                        self.fail("A second owner acquired the device lock")
            with device_ownership():
                pass

    def test_browser_lease_stop_eof_and_no_rearming(self):
        now = [1.0]
        stop = threading.Event()
        control = BrowserControl(stop, lambda: now[0])
        now[0] = 5
        control.receive('{"command":"heartbeat"}')
        now[0] = 9
        self.assertFalse(control.expired())
        now[0] = 11
        self.assertTrue(control.expired())
        control.receive('{"command":"heartbeat"}')
        self.assertTrue(stop.is_set())
        control.receive("")
        self.assertIn("closed", control.reason)

    def test_cart_skips_late_commands_and_persistent_failure_stops_arms(self):
        stop = threading.Event()

        class Cart:
            def set_speed(self, left, right):
                if left != 0:
                    raise IOError("disconnected")
                return "0.00,0.00\n"

        record = dict(sent=0, misses=0, moving_writes=0, stop_writes=0, max_gap_s=0, errors=[])
        with patch.object(play, "STOP_WINDOW_S", 0.01):
            play.drive_cart(
                Cart(), [0, 1], [(0.04, 0.04), (0, 0)], 0, 1, 0.005, time.perf_counter(), stop, record
            )
        self.assertTrue(stop.is_set())
        self.assertEqual(record["misses"], 3)
        self.assertGreater(record["stop_writes"], 0)

    def test_stop_before_activation_opens_no_buses_and_never_releases(self):
        plan = prepare({"duration_s": 2, "sweep_rad": math.pi / 18})
        stop = threading.Event()
        stop.set()
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(play, "identify_port"),
            patch.object(play, "Arm") as arm,
            patch.object(play, "MotorUART") as cart,
        ):
            report = play._play(plan, "windows", 25, Path(folder), {}, stop_event=stop, interactive=False)
            self.assertFalse(report["completed"])
            arm.assert_not_called()
            cart.assert_not_called()

    def test_complete_playback_with_fake_devices_retains_arms_and_synchronizes_cart(self):
        plan = prepare({"duration_s": 1, "sweep_rad": math.pi / 90})
        opened = {}
        events = []

        class Arm:
            def __init__(self, role, device, joints):
                self.role = role
                self.active = False
                self.raw = dict(plan["initial_raw"][role])
                self.sent = []
                self.released = False
                self.closed = False
                opened[role] = self

            def open(self):
                return self.raw

            def activate(self, raw):
                self.active = True

            def goal(self, raw):
                self.raw = dict(raw)
                self.sent.append(dict(raw))

            def present(self):
                # Deliberately report an arm that did not track its goals.
                # Position error is an observation, never a playback gate.
                return plan["initial_raw"][self.role]

            def release(self):
                self.released = True
                return []

            def close(self):
                self.closed = True

        class Cart:
            def __init__(self, *args, **kwargs):
                self.sent = []
                opened["cart"] = self

            def connect(self):
                pass

            def set_speed(self, left, right):
                self.sent.append((time.perf_counter(), (left, right)))

            def stop(self):
                self.set_speed(0, 0)

            def close(self):
                pass

        stop = threading.Event()
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(play, "identify_port"),
            patch.object(play, "Arm", Arm),
            patch.object(play, "MotorUART", Cart),
        ):
            report = play._play(
                plan, "windows", 25, Path(folder), {}, stop_event=stop, emit=events.append, interactive=False
            )
        self.assertTrue(report["completed"])
        self.assertTrue(any(e["phase"] == "positioning" for e in events))
        self.assertTrue(any(e["phase"] == "aiming" for e in events))
        self.assertTrue(any(e["phase"] == "running" for e in events))
        self.assertTrue(any(pair != (0, 0) for _, pair in opened["cart"].sent))
        self.assertEqual(opened["cart"].sent[-1][1], (0, 0))
        for role in ("phone", "light"):
            self.assertEqual(opened[role].sent[0], plan["initial_raw"][role])
            self.assertEqual(opened[role].sent[-1], plan["raw_goals"][role])
            self.assertFalse(opened[role].released)
            self.assertTrue(opened[role].closed)
            self.assertGreater(report["arms"][role]["final_error_deg"], 1)


if __name__ == "__main__":
    unittest.main()
