"""Tracking lifetime and original-script execution with fake IO only."""

import ast
import builtins
import io
import json
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from takeone.motion.tracking import TOKEN_HEADER, TrackingService, camera_settings, source_path
from takeone.motion.tracking_worker import TrackingIO, TrackingStopped, execute


class FakeProcess:
    def __init__(self, responsive=True):
        self.lines = queue.Queue()
        self.stdout = self
        self.stdin = io.StringIO()
        self.stdin.write = self.receive
        self.commands = []
        self.code = None
        self.responsive = responsive
        self.killed = False

    def __iter__(self):
        return self

    def __next__(self):
        line = self.lines.get(timeout=5)
        if line is None:
            raise StopIteration
        return line

    def close(self):
        pass

    def receive(self, line):
        command = json.loads(line)["command"]
        self.commands.append(command)
        if command == "stop" and self.responsive:
            self.finish()
        return len(line)

    def finish(self, phase="stopped"):
        self.lines.put(
            json.dumps(dict(source="tracking_worker", terminal=True, phase=phase, cleanup_completed=True))
            + "\n"
        )
        self.code = 0
        self.lines.put(None)

    def poll(self):
        return self.code

    def wait(self):
        return self.code

    def kill(self):
        self.killed = True
        self.code = -9
        self.lines.put(None)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.launched = []
        self.responsive = True

        def launch(*args):
            self.launched.append(args)
            self.child = FakeProcess(self.responsive)
            return self.child

        self.service = TrackingService(
            launcher=launch,
            folder=self.folder.name,
            runtime=__file__,
            lease_s=1,
            stop_grace_s=0.1,
            camera_validator=lambda: None,
        )

    def tearDown(self):
        self.service.close()
        self.folder.cleanup()

    def start(self, request="a" * 32, mode="cart", arms=False):
        return self.service.start(mode, arms, request)

    def test_status_and_invalid_requests_never_launch(self):
        self.assertFalse(self.service.status()["active"])
        for mode, arms in (("invalid", False), ("cart", "false"), ("arms", False)):
            with self.assertRaises(ValueError):
                self.start(mode=mode, arms=arms)
        with self.assertRaises(PermissionError):
            self.service.authorize("invalid")
        self.assertEqual(self.launched, [])

    def test_idempotent_start_stop_logging_and_no_relaunch_on_retry(self):
        state = self.start()
        self.start()
        self.assertEqual(len(self.launched), 1)
        with self.assertRaises(ValueError):
            self.start(request="b" * 32)
        with self.assertRaises(ValueError):
            self.service.command("stop", "stale")
        self.service.command("heartbeat", state["run_id"])
        self.service.command("stop", state["run_id"])
        self.service.monitor.join(timeout=2)
        self.assertFalse(self.service.status()["active"])
        self.assertTrue(self.service.status()["cleanup_completed"])
        self.start()
        self.assertEqual(len(self.launched), 1)
        record = json.loads((Path(state["directory"]) / "run.json").read_text())
        self.assertEqual(record["phase"], "stopped")
        self.assertTrue((Path(state["directory"]) / "worker.log").is_file())

    def test_unresponsive_worker_is_killed_and_never_claimed_clean(self):
        self.responsive = False
        state = self.start()
        self.service.command("stop", state["run_id"])
        self.service.command("heartbeat", state["run_id"])
        self.service.monitor.join(timeout=2)
        self.assertTrue(self.child.killed)
        self.assertEqual(self.service.status()["phase"], "terminated")
        self.assertFalse(self.service.status()["cleanup_completed"])
        self.assertIn("unconfirmed", self.service.status()["error"])

    def test_browser_loss_and_server_close_stop_the_child(self):
        self.service.lease_s = 0.05
        self.start()
        self.service.monitor.join(timeout=2)
        self.assertIn("stop", self.child.commands)
        self.assertFalse(self.service.status()["active"])
        self.start(request="b" * 32)
        self.service.close()
        self.assertFalse(self.service.status()["active"])
        with self.assertRaises(ValueError):
            self.start(request="c" * 32)

    def test_child_crash_is_reported_and_owner_is_released(self):
        self.start()
        self.child.code = 7
        self.child.lines.put(None)
        self.service.monitor.join(timeout=2)
        self.assertEqual(self.service.status()["phase"], "failed")
        self.assertFalse(self.service.status()["active"])

    def test_stale_start_request_cannot_take_ownership_of_a_new_run(self):
        state = self.start()
        self.service.command("stop", state["run_id"])
        self.service.monitor.join(timeout=2)
        self.start(request="b" * 32)
        with self.assertRaisesRegex(ValueError, "later tracking run"):
            self.start()

    def test_blocked_control_pipe_does_not_block_stop_deadline(self):
        self.responsive = False
        self.start()
        released = threading.Event()
        entered = threading.Event()
        original_kill = self.child.kill

        def write(line):
            entered.set()
            released.wait(timeout=2)
            raise BrokenPipeError("hung child")

        def kill():
            released.set()
            original_kill()

        self.child.stdin.write = write
        self.child.kill = kill
        run_id = self.service.state["run_id"]
        self.service.command("heartbeat", run_id)
        self.assertTrue(entered.wait(timeout=1))
        self.service.command("stop", run_id)
        self.service.monitor.join(timeout=2)
        self.assertTrue(self.child.killed)
        self.assertFalse(self.service.status()["active"])


class SubprocessTests(unittest.TestCase):
    def test_stop_reaps_real_benign_children_including_a_hung_process(self):
        # Real OS process cleanup, but neither child imports project code or IO.
        cooperative = (
            "import json,sys\n"
            "for line in sys.stdin:\n"
            " if json.loads(line)['command']=='stop':\n"
            "  print(json.dumps(dict(source='tracking_worker',terminal=True,phase='stopped',"
            "cleanup_completed=True)),flush=True)\n"
            "  break\n"
        )
        for code, expected in ((cooperative, "stopped"), ("import time; time.sleep(60)", "terminated")):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as folder:

                def launch(*args):
                    return subprocess.Popen(
                        [sys.executable, "-B", "-u", "-c", code],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                    )

                service = TrackingService(
                    launcher=launch,
                    folder=folder,
                    runtime=sys.executable,
                    stop_grace_s=0.5,
                    camera_validator=lambda: None,
                )
                try:
                    state = service.start("cart", False, "a" * 32)
                    service.command("stop", state["run_id"])
                    service.monitor.join(timeout=3)
                    self.assertFalse(service.status()["active"])
                    self.assertIsNotNone(service.process.poll())
                    self.assertEqual(service.status()["phase"], expected)
                finally:
                    service.close()


class FakeCamera:
    def __init__(self, events):
        self.events = events
        self.frames = 0

    def isOpened(self):
        return True

    def get(self, prop):
        return 1280

    def read(self):
        self.frames += 1
        return self.frames == 1, SimpleNamespace(shape=(720, 1280, 3))

    def release(self):
        self.events.append(("camera_close",))


def fake_io(arms_enabled, stop=None):
    events = []
    stop = stop or threading.Event()

    class Port:
        def __init__(self, name):
            self.name, self.is_open, self.baudrate = name, False, 1000000
            events.append(("port_construct", name))

        def openPort(self):
            self.is_open = True
            events.append(("port_open", self.name))
            return True

        def setBaudRate(self, value):
            self.baudrate = value
            events.append(("port_baud", self.name, value))
            return True

        def getBaudRate(self):
            return self.baudrate

        def closePort(self):
            self.is_open = False
            events.append(("port_close", self.name))

    class Servo:
        def __init__(self, port):
            self.port = port

        def write1ByteTxRx(self, *args):
            events.append(("servo1", self.port.name, *args))
            return 0, 0

        def write2ByteTxRx(self, *args):
            events.append(("servo2", self.port.name, *args))
            return 0, 0

    class Cart:
        def __init__(self, port="COM5", **kwargs):
            self.port, self.connected = port, False

        def connect(self):
            self.connected = True
            events.append(("cart_connect",))

        def set_speed(self, left, right):
            events.append(("cart_speed", left, right))

        def stop(self):
            self.set_speed(0, 0)

        def close(self):
            self.connected = False
            events.append(("cart_close",))

    cv2 = SimpleNamespace(
        VideoCapture=lambda index: FakeCamera(events),
        waitKey=lambda delay: ord("q"),
        destroyAllWindows=lambda: events.append(("windows_close",)),
        CAP_PROP_FRAME_WIDTH=3,
        COLOR_BGR2RGB=4,
        MARKER_CROSS=0,
        FONT_HERSHEY_SIMPLEX=0,
        cvtColor=lambda frame, mode: frame,
    )
    for name in ("imshow", "drawMarker", "putText", "circle", "line", "rectangle"):
        setattr(cv2, name, lambda *args: None)
    tracker = TrackingIO(
        stop,
        arms_enabled=arms_enabled,
        sdk=SimpleNamespace(PortHandler=Port, sms_sts=Servo),
        cv2=cv2,
        motor_class=Cart,
        identity_check=lambda port: events.append(("identity", port)),
    )
    return tracker, events


class WorkerTests(unittest.TestCase):
    def test_original_sources_are_byte_identical_and_parse_without_execution(self):
        for mode in ("cart", "arms"):
            ast.parse(source_path(mode).read_bytes())

    def test_cart_only_never_constructs_checks_opens_or_writes_an_arm(self):
        tracker, events = fake_io(False)
        port = tracker.port("COM8")
        self.assertTrue(port.openPort())
        self.assertTrue(port.setBaudRate(1000000))
        servo = tracker.servo(port)
        servo.write1ByteTxRx(1, 40, 1)
        servo.write2ByteTxRx(1, 42, 1234)
        tracker.cleanup()
        self.assertEqual(events, [("windows_close",)])

    def test_enabled_arm_writes_pass_through_and_stop_blocks_new_goals(self):
        tracker, events = fake_io(True)
        port = tracker.port("COM9")
        self.assertEqual(port.__dict__["name"], "COM9")
        port.openPort()
        servo = tracker.servo(port)
        servo.write2ByteTxRx(1, 42, 2034)
        self.assertIn(("servo2", "COM9", 1, 42, 2034), events)
        tracker.stop.set()
        with self.assertRaises(TrackingStopped):
            servo.write2ByteTxRx(1, 42, 3000)
        tracker.cleanup()
        self.assertIn(("port_close", "COM9"), events)
        self.assertFalse(any(event[0] == "servo1" for event in events))

    def test_arm_open_does_not_reopen_port_for_existing_baud_rate(self):
        tracker, events = fake_io(True)
        port = tracker.port("COM9")
        self.assertTrue(port.openPort())
        self.assertTrue(port.setBaudRate(1000000))
        self.assertEqual([event for event in events if event[0] == "port_open"], [("port_open", "COM9")])
        self.assertFalse(any(event[0] == "port_baud" for event in events))
        self.assertTrue(port.setBaudRate(500000))
        self.assertIn(("port_baud", "COM9", 500000), events)
        tracker.cleanup()

    def test_cart_stop_sends_zero_and_closes_without_any_later_motion(self):
        tracker, events = fake_io(False)
        cart = tracker.cart()
        cart.connect()
        cart.set_speed(-0.05, -0.10)
        tracker.stop.set()
        tracker.stop_cart()
        with self.assertRaises(TrackingStopped):
            cart.set_speed(0.1, 0.1)
        tracker.cleanup()
        self.assertEqual([row for row in events if row[0] == "cart_speed"][0], ("cart_speed", -0.05, -0.10))
        self.assertTrue(all(row == ("cart_speed", 0, 0) for row in events[3:] if row[0] == "cart_speed"))
        self.assertIn(("cart_close",), events)

    def test_transient_usb_open_retries_fresh_handle_without_motor_writes(self):
        tracker, events = fake_io(True)
        original = tracker.sdk.PortHandler
        handles = []

        def factory(name):
            raw = original(name)
            raw.ser = Mock()
            if not handles:
                raw.openPort = Mock(
                    side_effect=OSError(
                        "Cannot configure port: PermissionError(13, 'device failure', None, 31)"
                    )
                )
            handles.append(raw)
            return raw

        tracker.sdk.PortHandler = factory
        with patch.object(tracker.stop, "wait", return_value=False) as wait:
            self.assertTrue(tracker.port("COM9").openPort())
        self.assertEqual(len(handles), 2)
        handles[0].ser.close.assert_called_once()
        wait.assert_called_once_with(0.5)
        self.assertEqual(len([e for e in events if e[0] == "identity"]), 2)
        self.assertFalse(any(e[0].startswith("servo") for e in events))
        tracker.cleanup()

    def test_usb_open_retry_is_bounded_and_stop_interrupts_wait(self):
        for stopped in (False, True):
            with self.subTest(stopped=stopped):
                tracker, events = fake_io(True)
                failure = OSError("Cannot configure port: PermissionError(13, 'failure', None, 31)")
                handles = []

                def factory(name):
                    raw = SimpleNamespace(is_open=False, ser=Mock(), openPort=Mock(side_effect=failure))
                    handles.append(raw)
                    return raw

                def wait(seconds):
                    if stopped:
                        tracker.stop.set()
                    return stopped

                tracker.sdk.PortHandler = factory
                with patch.object(tracker.stop, "wait", side_effect=wait):
                    with self.assertRaises(TrackingStopped if stopped else RuntimeError):
                        tracker.port("COM9").openPort()
                self.assertEqual(len(handles), 1 if stopped else 3)
                for raw in handles:
                    raw.ser.close.assert_called_once()
                self.assertFalse(any(e[0].startswith("servo") for e in events))

    def test_access_denied_does_not_retry_or_hide_port_ownership_error(self):
        tracker, _ = fake_io(True)
        raw = SimpleNamespace(
            is_open=False, ser=Mock(), openPort=Mock(side_effect=PermissionError("Access is denied"))
        )
        tracker.sdk.PortHandler = Mock(return_value=raw)
        with patch.object(tracker.stop, "wait") as wait:
            with self.assertRaisesRegex(RuntimeError, "Access is denied"):
                tracker.port("COM9").openPort()
        wait.assert_not_called()
        raw.ser.close.assert_called_once()

    def test_stop_before_initialization_constructs_no_devices(self):
        tracker, events = fake_io(True)
        tracker.stop.set()
        with self.assertRaises(TrackingStopped):
            tracker.port("COM9")
        with self.assertRaises(TrackingStopped):
            tracker.camera(2)
        self.assertEqual(events, [])

    def test_configured_camera_replaces_script_index_with_named_cart_camera(self):
        tracker, events = fake_io(False)
        calls = []
        tracker.camera_config = camera_settings(require_latency=False)
        tracker.numpy = object()
        tracker.scope = {
            "shoulder_target_px": (645, 405),
            "shoulder_size_px_target": 206,
            "int_abs_error_start": 45,
            "int_abs_error_stop": 30,
            "float_KPP": 0.03,
        }

        def make_dshow(config, **kwargs):
            calls.append((config, kwargs))
            return FakeCamera(events)

        tracker.dshow_factory = make_dshow
        camera = tracker.camera(2)
        self.assertEqual(calls[0][0]["kind"], "directshow")
        self.assertIs(calls[0][1]["numpy"], tracker.numpy)
        self.assertEqual(tracker.scope["shoulder_target_px"], (323, 203))
        self.assertEqual(tracker.scope["shoulder_size_px_target"], 103)
        self.assertEqual(tracker.scope["int_abs_error_start"], 23)
        self.assertEqual(tracker.scope["int_abs_error_stop"], 15)
        self.assertAlmostEqual(tracker.scope["float_KPP"], 0.06)
        camera.release()

    def test_cart_camera_waits_through_a_frame_gap_and_stops_cart(self):
        tracker, events = fake_io(False)
        tracker.camera_config = camera_settings()
        tracker.numpy = object()
        emitted = []
        tracker.emit = emitted.append
        cart = tracker.cart()
        cart.connect()
        cart.set_speed(0.05, 0.05)

        class GappedCamera(FakeCamera):
            def read(self):
                self.frames += 1
                return self.frames >= 2, SimpleNamespace(shape=(360, 640, 3))

        tracker.dshow_factory = lambda config, **kwargs: GappedCamera(events)
        camera = tracker.camera(2)
        ok, frame = camera.read()
        self.assertTrue(ok)
        self.assertEqual(frame.shape, (360, 640, 3))
        self.assertIn(("cart_speed", 0, 0), events)
        self.assertEqual([event["phase"] for event in emitted], ["camera_waiting", "running"])
        tracker.cleanup()

    def test_cart_camera_retries_initial_open_failure(self):
        tracker, events = fake_io(False)
        tracker.camera_config = camera_settings()
        tracker.numpy = object()
        emitted = []
        tracker.emit = emitted.append
        attempts = 0

        def open_dshow(config, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("camera temporarily unavailable")
            return FakeCamera(events)

        tracker.dshow_factory = open_dshow
        camera = tracker.camera(2)
        self.assertEqual(attempts, 2)
        self.assertEqual(emitted[0]["phase"], "camera_waiting")
        self.assertTrue(camera.read()[0])
        tracker.cleanup()

    def test_active_tracking_uses_confirmed_named_cart_camera(self):
        selected = camera_settings(require_latency=False)
        self.assertEqual(selected["kind"], "directshow")
        self.assertEqual(selected["device_label"], "Live Streamer CAM 313")
        self.assertEqual(selected["source"], "cart_camera")
        self.assertTrue(selected["operator_confirmed"])
        self.assertEqual(camera_settings(), selected)

    def test_galaxy_tracking_configuration_is_rejected(self):
        configured = {
            "camera": {
                **camera_settings(require_latency=False),
                "device_label": "Ryan's S23 FE",
                "latency_qualified": True,
            }
        }
        with (
            patch("takeone.motion.tracking.read_json", return_value=configured),
            self.assertRaisesRegex(ValueError, "Live Streamer CAM 313"),
        ):
            camera_settings()

    def test_other_directshow_camera_is_rejected(self):
        configured = {
            "camera": {
                **camera_settings(require_latency=False),
                "device_label": "Surface Camera Front",
                "latency_qualified": True,
            }
        }
        with (
            patch("takeone.motion.tracking.read_json", return_value=configured),
            self.assertRaisesRegex(ValueError, "Live Streamer CAM 313"),
        ):
            camera_settings()

    def test_original_scripts_execute_one_frame_with_fakes_in_all_three_modes(self):
        # Executes the supplied source with no real dependencies, model downloads,
        # camera, serial, or simulation. This also tests unchanged top-level setup.
        for mode, arms in (("cart", False), ("cart", True), ("arms", True)):
            with self.subTest(mode=mode, arms=arms):
                tracker, events = fake_io(arms)
                detector = SimpleNamespace(
                    detect=lambda image: SimpleNamespace(pose_landmarks=[], detections=[]), close=lambda: None
                )
                factory = SimpleNamespace(create_from_options=lambda options: detector)

                def options(**kwargs):
                    return kwargs

                mp = SimpleNamespace(
                    tasks=SimpleNamespace(
                        BaseOptions=options,
                        vision=SimpleNamespace(
                            PoseLandmarker=factory,
                            FaceDetector=factory,
                            PoseLandmarkerOptions=options,
                            FaceDetectorOptions=options,
                            RunningMode=SimpleNamespace(IMAGE=0),
                        ),
                    ),
                    Image=options,
                    ImageFormat=SimpleNamespace(SRGB=0),
                )
                original = builtins.__import__

                def imports(name, *args, **kwargs):
                    if name in ("mediapipe", "numpy"):
                        return mp if name == "mediapipe" else SimpleNamespace()
                    return original(name, *args, **kwargs)

                with (
                    patch.object(tracker, "imports", return_value=tracker.imports(imports)),
                    patch.object(Path, "mkdir"),
                    patch.object(Path, "exists", return_value=True),
                    patch("urllib.request.urlopen", side_effect=AssertionError("No download")),
                ):
                    execute(mode, tracker)
                self.assertTrue(tracker.running)
                tracker.cleanup()
                ports = [row[1] for row in events if row[0] == "port_open"]
                self.assertEqual(ports, ["COM9", "COM8"] if arms else [])
                self.assertEqual(("cart_connect",) in events, mode == "cart")
                goals = [row for row in events if row[0] == "servo2" and row[3] == 42]
                if arms:
                    self.assertIn(("servo2", "COM8", 1, 42, 2984 if mode == "cart" else 1880), goals)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        from tests.test_director_http import server_module

        self.folder = tempfile.TemporaryDirectory()
        self.child = None

        def launch(*args):
            self.child = FakeProcess()
            return self.child

        self.tracking = TrackingService(
            launcher=launch,
            folder=self.folder.name,
            runtime=__file__,
            camera_validator=lambda: None,
        )
        self.robot = Mock()
        self.robot.status.return_value = dict(active=False, phase="idle", token="robot")
        self.server = server_module.make_server(
            0,
            Path(self.folder.name) / "sessions.sqlite3",
            {},
            {},
            robot_service=self.robot,
            tracking_service=self.tracking,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.folder.cleanup()

    def request(self, path, body=None, token=True, origin=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers[TOKEN_HEADER] = self.tracking.token
        if origin:
            headers["Origin"] = origin
        req = Request(
            self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers
        )
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_start_authentication_mutual_exclusion_and_reload_deferral(self):
        body = dict(mode="cart", arms_enabled=False, request_id="a" * 32)
        self.assertEqual(self.request("/api/tracking/status")[0], 200)
        self.assertIsNone(self.child)
        self.assertEqual(self.request("/api/tracking/start", body, token=False)[0], 403)
        self.assertEqual(self.request("/api/tracking/start", body, origin="https://example.com")[0], 403)
        self.robot.status.return_value["active"] = True
        self.assertEqual(self.request("/api/tracking/start", body)[0], 409)
        self.robot.status.return_value["active"] = False
        code, state = self.request("/api/tracking/start", body)
        self.assertEqual(code, 200)
        self.assertEqual(self.request("/api/robot/start", dict(plan_id="p", request_id="b" * 32))[0], 409)
        self.robot.start.assert_not_called()
        self.assertFalse(self.server.request_reload())
        self.assertTrue(self.request("/api/robot/status")[1]["tracking_active"])
        self.assertEqual(self.request("/api/tracking/stop", dict(run_id=state["run_id"]))[0], 200)
        self.tracking.monitor.join(timeout=2)
        self.assertTrue(self.server.request_reload())

    def test_nonobject_and_unknown_options_rejected(self):
        self.assertEqual(self.request("/api/tracking/start", [1])[0], 409)
        self.assertEqual(self.request("/api/tracking/start", {"script": "arbitrary.py"})[0], 409)
        self.assertIsNone(self.child)


if __name__ == "__main__":
    unittest.main()
