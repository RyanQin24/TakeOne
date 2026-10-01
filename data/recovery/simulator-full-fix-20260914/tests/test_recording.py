import math
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from takeone.recording import (
    RecordingError,
    RecordingService,
    SimulatedRecorder,
    SyntheticMediaWriter,
    ZoomRamp,
)

FFMPEG = Path(shutil.which("ffmpeg") or "ffmpeg")
FFPROBE = Path(shutil.which("ffprobe") or "ffprobe")


class Clock:
    def __init__(self):
        self.value = 1_000_000_000_000_000_000

    def __call__(self):
        return self.value

    def advance_ms(self, milliseconds):
        self.value += milliseconds * 1_000_000


class BlockingWriter:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.calls = []

    def write(self, take_id, media_root, duration_ms, scenario):
        self.calls.append(take_id)
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("test did not release finalizer")
        self.finished.set()
        return {
            "relative_path": f"{take_id}/synthetic.mp4",
            "sha256": "0" * 64,
            "size_bytes": 1,
            "duration_ms": duration_ms,
            "streams": [],
            "provenance": {"source": "blocked_test_edge"},
        }


class ProbeSimulator(SimulatedRecorder):
    def __init__(self, notified):
        super().__init__(start_delay_ms=10, delayed_start_ms=30, timeout_ms=50)
        self.notified = notified

    def request_start(self, take_id, scenario, requested_ns):
        if not self.notified or self.notified[-1][1] != "requested":
            raise AssertionError("notification must precede simulated device work")
        return super().request_start(take_id, scenario, requested_ns)


class FailingStopSimulator(SimulatedRecorder):
    def request_stop(self, take_id, scenario, requested_ns):
        raise OSError("injected device edge failure")


class BlockingStopSimulator(SimulatedRecorder):
    def __init__(self, result):
        super().__init__(start_delay_ms=10, delayed_start_ms=30, timeout_ms=50)
        self.result = result
        self.entered = threading.Event()
        self.release = threading.Event()

    def request_stop(self, take_id, scenario, requested_ns):
        self.entered.set()
        if not self.release.wait(2):
            raise RuntimeError("test did not release stop dispatch")
        if self.result == "failure":
            raise OSError("injected late stop failure")
        scenario = "disconnect" if self.result == "disconnect" else scenario
        return super().request_stop(take_id, scenario, requested_ns)


class RejectingExecutor:
    def submit(self, *args, **kwargs):
        raise RuntimeError("injected executor rejection")

    def shutdown(self, wait=True, cancel_futures=False):
        return None


class BlockingStartSimulator(SimulatedRecorder):
    def __init__(self, result):
        super().__init__(start_delay_ms=10, delayed_start_ms=30, timeout_ms=50)
        self.result = result
        self.entered = threading.Event()
        self.release = threading.Event()
        self.requests = 0

    def request_start(self, take_id, scenario, requested_ns):
        self.requests += 1
        if self.requests == 1:
            self.entered.set()
            if not self.release.wait(2):
                raise RuntimeError("test did not release start dispatch")
            if self.result == "failure":
                raise OSError("injected late start failure")
        return super().request_start(take_id, scenario, requested_ns)


class RecordingContractTests(unittest.TestCase):
    def test_zoom_ramp_interpolates_clamps_and_reports_signed_rate(self):
        ramp = ZoomRamp(1.0, 3.0, 2000)
        self.assertEqual(ramp.factor_at(0), 1.0)
        self.assertEqual(ramp.factor_at(1000), 2.0)
        self.assertEqual(ramp.factor_at(3000), 3.0)
        self.assertEqual(ZoomRamp(3.0, 1.0, 2000).wire()["rate_factor_per_s"], -1.0)

    def test_zoom_ramp_rejects_invalid_values_without_normalizing(self):
        invalid_factors = (0, -1, True, math.nan, math.inf, -math.inf, 0.999, 4.001, "2")
        for factor in invalid_factors:
            with self.subTest(factor=factor), self.assertRaises(ValueError):
                ZoomRamp(factor, 2, 500)
            with self.subTest(end_factor=factor), self.assertRaises(ValueError):
                ZoomRamp(2, factor, 500)
        for duration in (0, -1, True, 249, 10001, math.nan, math.inf, 500.0, "500"):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                ZoomRamp(1, 2, duration)
        for elapsed in (-1, True, math.nan, math.inf, "1"):
            with self.subTest(elapsed=elapsed), self.assertRaises(ValueError):
                ZoomRamp(1, 2, 500).factor_at(elapsed)

    def test_public_recording_error_rejects_unbounded_codes(self):
        with self.assertRaises(ValueError):
            RecordingError(400, "invented_code", "Unbounded errors cannot cross the service boundary.")


class RecordingServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.database = root / "recording.sqlite3"
        self.media_root = root / "media"
        self.clock = Clock()
        self.services = []

    def tearDown(self):
        for service in reversed(self.services):
            release = getattr(service.media_writer, "release", None)
            if release is not None:
                release.set()
            service.close()

    def service(self, **overrides):
        database = overrides.pop("database", self.database)
        media_root = overrides.pop("media_root", self.media_root)
        options = {
            "clock": self.clock,
            "simulator": SimulatedRecorder(start_delay_ms=10, delayed_start_ms=30, timeout_ms=50),
            "media_writer": SyntheticMediaWriter(ffmpeg=FFMPEG, ffprobe=FFPROBE, timeout_seconds=10),
        }
        options.update(overrides)
        service = RecordingService(database, media_root, **options)
        self.services.append(service)
        return service

    def acknowledge_start(self, service, take_id, delay_ms=10):
        self.clock.advance_ms(delay_ms)
        result = service.get(take_id)
        self.assertEqual(result["state"], "recording", result)
        return result

    def wait_terminal(self, service, take_id, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = service.get(take_id)
            if result["state"] in {"ready", "failed", "unknown"}:
                return result
            time.sleep(0.02)
        self.fail(f"take did not finish: {service.get(take_id)}")

    def test_start_notifies_before_device_work_and_preserves_json_snapshot(self):
        notified = []
        simulator = ProbeSimulator(notified)

        def notify(take, state):
            notified.append((take, state))

        service = self.service(simulator=simulator, notify=notify)
        context = {"source": "standalone_fixture", "nested": {"line": "Hello"}}
        started = service.start("start-1", context, ZoomRamp(1, 2, 500))
        context["nested"]["line"] = "changed"
        self.assertEqual(started["state"], "starting")
        self.assertEqual(started["source"], "simulated")
        self.assertFalse(started["real_media_verified"])
        self.assertEqual(service.get(started["take_id"])["context"]["nested"]["line"], "Hello")
        self.assertEqual(notified[0][1], "requested")
        self.assertEqual(notified[0][0]["take_id"], started["take_id"])
        self.assertEqual(started["events"][0]["request_monotonic_ns"], str(self.clock()))
        self.assertIsNone(started["events"][0]["ack_monotonic_ns"])

    def test_duplicate_start_reuses_take_and_conflicting_content_adds_no_row(self):
        service = self.service()
        context = {"source": "standalone_fixture"}
        zoom = ZoomRamp(1, 2, 500)
        first = service.start("start-1", context, zoom)
        duplicate = service.start("start-1", context, zoom)
        self.assertEqual(duplicate["take_id"], first["take_id"])
        self.assertEqual(len(service.list_takes()), 1)
        with self.assertRaises(RecordingError) as raised:
            service.start("start-1", {"source": "different"}, zoom)
        self.assertEqual((raised.exception.status, raised.exception.code), (409, "operation_conflict"))
        self.assertEqual(len(service.list_takes()), 1)

    def test_normal_take_persists_request_ack_stop_and_verified_synthetic_media(self):
        service = self.service()
        take = service.start("start-1", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        recording = self.acknowledge_start(service, take["take_id"])
        start_ack = next(event for event in recording["events"] if event["kind"] == "start_acknowledged")
        self.assertEqual(start_ack["request_monotonic_ns"], take["events"][0]["request_monotonic_ns"])
        self.assertEqual(start_ack["ack_monotonic_ns"], str(self.clock()))
        stopping = service.stop(take["take_id"], "stop-1")
        self.assertEqual(stopping["state"], "finalizing")
        result = self.wait_terminal(service, take["take_id"])
        self.assertEqual(result["state"], "ready", result)
        self.assertFalse(result["real_media_verified"])
        self.assertEqual(result["media"]["duration_ms"], 500)
        self.assertEqual(service.media_path(take["take_id"]).name, "synthetic.mp4")
        reopened = self.service().get(take["take_id"])
        self.assertEqual(reopened["state"], "ready")
        self.assertEqual(reopened["media"], result["media"])

    def test_delayed_start_waits_and_stop_before_ack_cannot_be_revived(self):
        service = self.service()
        take = service.start(
            "start-delay", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500), "delayed_start"
        )
        self.clock.advance_ms(29)
        self.assertEqual(service.get(take["take_id"])["state"], "starting")
        stopped = service.stop(take["take_id"], "stop-delay")
        self.assertEqual(stopped["state"], "failed")
        self.assertEqual(stopped["error"]["code"], "retired_before_start")
        self.clock.advance_ms(100)
        self.assertEqual(service.get(take["take_id"])["state"], "failed")

        next_take = service.start(
            "start-delay-2", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500), "delayed_start"
        )
        self.clock.advance_ms(29)
        self.assertEqual(service.get(next_take["take_id"])["state"], "starting")
        self.clock.advance_ms(1)
        self.assertEqual(service.get(next_take["take_id"])["state"], "recording")

    def test_start_timeout_blocks_new_start_until_explicit_recovery(self):
        service = self.service()
        take = service.start(
            "start-timeout", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500), "start_timeout"
        )
        self.clock.advance_ms(50)
        unknown = service.get(take["take_id"])
        self.assertEqual((unknown["state"], unknown["error"]["code"]), ("unknown", "start_timeout"))
        with self.assertRaises(RecordingError) as raised:
            service.start("start-blocked", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.assertEqual(raised.exception.code, "take_unresolved")
        recovered = service.recover(take["take_id"], "recover-1")
        self.assertEqual((recovered["state"], recovered["error"]["code"]), ("failed", "recovered"))
        self.assertEqual(service.recover(take["take_id"], "recover-1")["take_id"], take["take_id"])
        self.assertNotEqual(
            service.start("start-after-recovery", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))[
                "take_id"
            ],
            take["take_id"],
        )

    def test_disconnect_and_stop_timeout_require_recovery(self):
        for scenario, expected_code in (("disconnect", "disconnect"), ("stop_timeout", "stop_timeout")):
            with self.subTest(scenario=scenario):
                if service := (self.services[-1] if self.services else None):
                    active = [
                        take for take in service.list_takes() if take["state"] not in {"ready", "failed"}
                    ]
                    if active:
                        service.recover(active[0]["take_id"], f"cleanup-{scenario}")
                service = self.service() if not self.services else self.services[-1]
                take = service.start(
                    f"start-{scenario}",
                    {"source": "standalone_fixture"},
                    ZoomRamp(1, 2, 500),
                    scenario,
                )
                self.acknowledge_start(service, take["take_id"])
                stopping = service.stop(take["take_id"], f"stop-{scenario}")
                if scenario == "stop_timeout":
                    self.assertEqual(stopping["state"], "finalizing")
                    self.clock.advance_ms(49)
                    self.assertEqual(service.get(take["take_id"])["state"], "finalizing")
                    self.clock.advance_ms(1)
                    stopping = service.get(take["take_id"])
                self.assertEqual((stopping["state"], stopping["error"]["code"]), ("unknown", expected_code))
                service.recover(take["take_id"], f"recover-{scenario}")

    def test_simulated_stop_exception_becomes_unknown_evidence(self):
        service = self.service(
            simulator=FailingStopSimulator(start_delay_ms=10, delayed_start_ms=30, timeout_ms=50)
        )
        take = service.start("start-1", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(service, take["take_id"])
        result = service.stop(take["take_id"], "stop-1")
        self.assertEqual((result["state"], result["error"]["code"]), ("unknown", "simulator_unavailable"))

    def test_late_stop_results_cannot_revive_recovered_take(self):
        for outcome in ("disconnect", "failure"):
            with self.subTest(outcome=outcome):
                simulator = BlockingStopSimulator(outcome)
                notifications = []
                service = self.service(
                    database=self.database.with_name(f"stop-{outcome}.sqlite3"),
                    media_root=self.media_root / f"stop-{outcome}",
                    simulator=simulator,
                    notify=lambda take, state: notifications.append((take, state)),
                )
                take = service.start(
                    f"start-old-{outcome}", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500)
                )
                self.acknowledge_start(service, take["take_id"])
                completed = []
                caller = threading.Thread(
                    target=lambda: completed.append(service.stop(take["take_id"], f"stop-old-{outcome}"))
                )
                caller.start()
                self.assertTrue(simulator.entered.wait(1))
                service.recover(take["take_id"], f"recover-old-{outcome}")
                replacement = service.start(
                    f"start-new-{outcome}", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500)
                )
                notification_count = len(notifications)
                simulator.release.set()
                caller.join(2)
                self.assertFalse(caller.is_alive())
                self.assertEqual(completed[0]["state"], "failed")
                self.assertEqual(len(notifications), notification_count)
                states = {item["take_id"]: item["state"] for item in service.list_takes()}
                self.assertEqual(states, {take["take_id"]: "failed", replacement["take_id"]: "starting"})
                kinds = [event["kind"] for event in service.get(take["take_id"])["events"]]
                self.assertNotIn("recorder_disconnected", kinds)
                self.assertNotIn("stop_dispatch_failed", kinds)
                service.recover(replacement["take_id"], f"cleanup-new-{outcome}")

    def test_late_start_results_do_not_emit_state_after_take_is_retired(self):
        for outcome in ("acknowledgement", "failure"):
            with self.subTest(outcome=outcome):
                simulator = BlockingStartSimulator(outcome)
                notifications = []
                service = self.service(
                    database=self.database.with_name(f"start-{outcome}.sqlite3"),
                    media_root=self.media_root / f"start-{outcome}",
                    simulator=simulator,
                    notify=lambda take, state: notifications.append((take, state)),
                )
                completed = []
                caller = threading.Thread(
                    target=lambda: completed.append(
                        service.start(
                            f"start-old-{outcome}",
                            {"source": "standalone_fixture"},
                            ZoomRamp(1, 2, 500),
                        )
                    )
                )
                caller.start()
                self.assertTrue(simulator.entered.wait(1))
                old = service.list_takes()[0]
                service.stop(old["take_id"], f"stop-old-{outcome}")
                replacement = service.start(
                    f"start-new-{outcome}", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500)
                )
                notification_count = len(notifications)
                simulator.release.set()
                caller.join(2)
                self.assertFalse(caller.is_alive())
                self.assertEqual(completed[0]["state"], "failed")
                self.assertEqual(len(notifications), notification_count)
                kinds = [event["kind"] for event in service.get(old["take_id"])["events"]]
                self.assertNotIn("start_dispatch_failed", kinds)
                service.recover(replacement["take_id"], f"cleanup-new-{outcome}")

    def test_running_finalizer_keeps_single_admission_after_recovery(self):
        writer = BlockingWriter()
        self.addCleanup(writer.release.set)
        service = self.service(media_writer=writer)
        first = service.start("start-first", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(service, first["take_id"])
        service.stop(first["take_id"], "stop-first")
        self.assertTrue(writer.entered.wait(1))
        service.recover(first["take_id"], "recover-first")

        second = service.start("start-second", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(service, second["take_id"])
        with self.assertRaises(RecordingError) as raised:
            service.stop(second["take_id"], "stop-second")
        self.assertEqual(raised.exception.code, "finalization_busy")
        self.assertEqual(service.get(second["take_id"])["state"], "recording")
        self.assertEqual(writer.calls, [first["take_id"]])

        writer.release.set()
        self.assertTrue(writer.finished.wait(2))
        deadline = time.monotonic() + 2
        while True:
            try:
                service.stop(second["take_id"], "stop-second")
                break
            except RecordingError as error:
                if error.code != "finalization_busy" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
        result = self.wait_terminal(service, second["take_id"], timeout=2)
        self.assertEqual(result["state"], "ready")
        self.assertEqual(writer.calls, [first["take_id"], second["take_id"]])

    def test_replacement_runtime_waits_for_old_finalizer_admission(self):
        old_writer = BlockingWriter()
        new_writer = BlockingWriter()
        self.addCleanup(old_writer.release.set)
        self.addCleanup(new_writer.release.set)
        old = self.service(media_writer=old_writer)
        first = old.start("start-old", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(old, first["take_id"])
        old.stop(first["take_id"], "stop-old")
        self.assertTrue(old_writer.entered.wait(1))

        replacement = self.service(media_writer=new_writer)
        replacement.recover(first["take_id"], "recover-old")
        second = replacement.start("start-replacement", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(replacement, second["take_id"])
        with self.assertRaises(RecordingError) as raised:
            replacement.stop(second["take_id"], "stop-replacement")
        self.assertEqual(raised.exception.code, "finalization_busy")
        self.assertFalse(new_writer.entered.is_set())
        self.assertEqual(replacement.get(second["take_id"])["state"], "recording")

        close_finished = threading.Event()

        def close_old():
            old.close()
            close_finished.set()

        closer = threading.Thread(target=close_old)
        closer.start()
        self.assertFalse(close_finished.wait(0.05))
        with self.assertRaises(RecordingError) as raised:
            replacement.stop(second["take_id"], "stop-replacement")
        self.assertEqual(raised.exception.code, "finalization_busy")

        old_writer.release.set()
        self.assertTrue(old_writer.finished.wait(2))
        closer.join(2)
        self.assertFalse(closer.is_alive())
        deadline = time.monotonic() + 2
        while True:
            try:
                replacement.stop(second["take_id"], "stop-replacement")
                break
            except RecordingError as error:
                if error.code != "finalization_busy" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
        self.assertTrue(new_writer.entered.wait(1))
        new_writer.release.set()
        self.assertEqual(self.wait_terminal(replacement, second["take_id"], timeout=2)["state"], "ready")

    def test_close_releases_admission_reserved_by_blocked_stop_dispatch(self):
        simulator = BlockingStopSimulator("acknowledgement")
        new_writer = BlockingWriter()
        self.addCleanup(simulator.release.set)
        self.addCleanup(new_writer.release.set)
        old = self.service(simulator=simulator)
        first = old.start("start-old", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(old, first["take_id"])
        failures = []

        def stop_old():
            try:
                old.stop(first["take_id"], "stop-old")
            except RecordingError as error:
                failures.append(error)

        caller = threading.Thread(target=stop_old)
        caller.start()
        self.assertTrue(simulator.entered.wait(1))

        replacement = self.service(media_writer=new_writer)
        replacement.recover(first["take_id"], "recover-old")
        second = replacement.start("start-new", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(replacement, second["take_id"])
        old.close()
        self.assertEqual(replacement.stop(second["take_id"], "stop-new")["state"], "finalizing")
        self.assertTrue(new_writer.entered.wait(1))

        simulator.release.set()
        caller.join(2)
        self.assertFalse(caller.is_alive())
        self.assertEqual([error.code for error in failures], ["runtime_replaced"])
        new_writer.release.set()
        self.assertEqual(self.wait_terminal(replacement, second["take_id"], timeout=2)["state"], "ready")

    def test_replacement_during_stop_dispatch_does_not_strand_admission(self):
        simulator = BlockingStopSimulator("acknowledgement")
        new_writer = BlockingWriter()
        self.addCleanup(simulator.release.set)
        self.addCleanup(new_writer.release.set)
        old = self.service(simulator=simulator)
        first = old.start("start-old", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(old, first["take_id"])
        failures = []

        def stop_old():
            try:
                old.stop(first["take_id"], "stop-old")
            except RecordingError as error:
                failures.append(error)

        caller = threading.Thread(target=stop_old)
        caller.start()
        self.assertTrue(simulator.entered.wait(1))

        replacement = self.service(media_writer=new_writer)
        replacement.recover(first["take_id"], "recover-old")
        second = replacement.start("start-new", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(replacement, second["take_id"])
        simulator.release.set()
        caller.join(2)
        self.assertFalse(caller.is_alive())
        self.assertEqual([error.code for error in failures], ["runtime_replaced"])

        old.close()
        self.assertEqual(replacement.stop(second["take_id"], "stop-new")["state"], "finalizing")
        self.assertTrue(new_writer.entered.wait(1))
        new_writer.release.set()
        self.assertEqual(self.wait_terminal(replacement, second["take_id"], timeout=2)["state"], "ready")

    def test_finalizing_notification_failure_releases_unowned_admission(self):
        failed = False

        def notify(take, state):
            nonlocal failed
            if state == "finalizing" and not failed:
                failed = True
                raise RuntimeError("injected notification failure")

        old = self.service(notify=notify)
        first = old.start("start-old", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(old, first["take_id"])
        with self.assertRaisesRegex(RuntimeError, "injected notification failure"):
            old.stop(first["take_id"], "stop-old")

        writer = BlockingWriter()
        self.addCleanup(writer.release.set)
        replacement = self.service(media_writer=writer)
        replacement.recover(first["take_id"], "recover-old")
        second = replacement.start("start-new", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(replacement, second["take_id"])
        replacement.stop(second["take_id"], "stop-new")
        self.assertTrue(writer.entered.wait(1))
        writer.release.set()
        self.assertEqual(self.wait_terminal(replacement, second["take_id"], timeout=2)["state"], "ready")

    def test_finalizer_submit_failure_releases_unowned_admission(self):
        with patch("takeone.recording.service.ThreadPoolExecutor", return_value=RejectingExecutor()):
            old = self.service()
        first = old.start("start-old", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(old, first["take_id"])
        with self.assertRaisesRegex(RuntimeError, "injected executor rejection"):
            old.stop(first["take_id"], "stop-old")

        writer = BlockingWriter()
        self.addCleanup(writer.release.set)
        replacement = self.service(media_writer=writer)
        replacement.recover(first["take_id"], "recover-old")
        second = replacement.start("start-new", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(replacement, second["take_id"])
        replacement.stop(second["take_id"], "stop-new")
        self.assertTrue(writer.entered.wait(1))
        writer.release.set()
        self.assertEqual(self.wait_terminal(replacement, second["take_id"], timeout=2)["state"], "ready")

    def test_duplicate_stop_and_cross_operation_request_conflict_have_no_extra_event(self):
        service = self.service()
        take = service.start("start-1", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500), "stop_timeout")
        self.acknowledge_start(service, take["take_id"])
        first = service.stop(take["take_id"], "operation-1")
        duplicate = service.stop(take["take_id"], "operation-1")
        self.assertEqual(len(duplicate["events"]), len(first["events"]))
        with self.assertRaises(RecordingError) as raised:
            service.recover(take["take_id"], "operation-1")
        self.assertEqual(raised.exception.code, "operation_conflict")

    def test_restart_marks_starting_and_recording_unknown_without_reusing_deadlines(self):
        service = self.service()
        starting = service.start("start-1", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        replacement = self.service()
        restarted = replacement.get(starting["take_id"])
        self.assertEqual((restarted["state"], restarted["error"]["code"]), ("unknown", "runtime_restarted"))
        restart_event = restarted["events"][-1]
        self.assertNotEqual(restart_event["runtime_epoch"], restarted["events"][0]["runtime_epoch"])
        self.assertIsNone(restart_event["request_monotonic_ns"])
        self.assertEqual(restart_event["ack_monotonic_ns"], str(self.clock()))
        self.clock.advance_ms(100)
        self.assertEqual(replacement.get(starting["take_id"])["state"], "unknown")
        with self.assertRaises(RecordingError) as raised:
            service.get(starting["take_id"])
        self.assertEqual(raised.exception.code, "runtime_replaced")
        replacement.recover(starting["take_id"], "recover-1")

        recording = replacement.start("start-2", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(replacement, recording["take_id"])
        second_replacement = self.service()
        self.assertEqual(second_replacement.get(recording["take_id"])["state"], "unknown")

    def test_restart_during_finalization_ignores_obsolete_worker_result(self):
        writer = BlockingWriter()
        service = self.service(media_writer=writer)
        take = service.start("start-1", {"source": "standalone_fixture"}, ZoomRamp(1, 2, 500))
        self.acknowledge_start(service, take["take_id"])
        self.assertEqual(service.stop(take["take_id"], "stop-1")["state"], "finalizing")
        self.assertTrue(writer.entered.wait(2))
        replacement = self.service()
        self.assertEqual(replacement.get(take["take_id"])["state"], "unknown")
        writer.release.set()
        time.sleep(0.05)
        result = replacement.get(take["take_id"])
        self.assertEqual(result["state"], "unknown")
        self.assertIsNone(result["media"])

    def test_take_and_media_lookup_validate_exact_canonical_take_ids(self):
        service = self.service()
        for take_id in ("", "../synthetic.mp4", "not-a-uuid", True):
            with self.subTest(take_id=take_id), self.assertRaises(RecordingError) as raised:
                service.get(take_id)
            self.assertEqual(raised.exception.code, "invalid_take_id")
        with self.assertRaises(RecordingError) as raised:
            service.get("00000000-0000-0000-0000-000000000000")
        self.assertEqual((raised.exception.status, raised.exception.code), (404, "take_not_found"))


if __name__ == "__main__":
    unittest.main()
