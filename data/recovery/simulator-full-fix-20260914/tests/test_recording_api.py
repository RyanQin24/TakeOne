"""Offline recorder exercised through the real loopback voice HTTP authority."""

import hashlib
import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from takeone.director.contracts import Command, ProductionBrief, Session
from takeone.director.repository import SessionRepository
from takeone.director.service import COMMAND_TTL_NS, DirectorService
from takeone.recording.media import SyntheticMediaWriter
from takeone.recording.service import RecordingService
from takeone.voice.service import VoiceService

from tests.test_voice_api import Clock, FakeLiveProvider, SelectiveBackend, server_module


class BlockingWriter:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def write(self, *args):
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("Test did not release the media writer")
        return SyntheticMediaWriter().write(*args)


class PausedTerminalNotification:
    """Pause after the real recorder commits terminal evidence, before voice sees it."""

    def __init__(self, notify):
        self.notify = notify
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, take, state):
        if state in {"ready", "failed"}:
            self.entered.set()
            if not self.release.wait(5):
                raise RuntimeError("Test did not release the terminal notification")
        self.notify(take, state)


class RecordingHTTPTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.database = Path(self.folder.name) / "sessions.sqlite3"
        self.clock = Clock()
        self.backend = SelectiveBackend()
        self.launch()
        self.addCleanup(self.stop_server)

    def launch(self):
        self.director = DirectorService(SessionRepository(self.database))
        self.voice = VoiceService(self.director, clock=self.clock, offline_backend=self.backend)
        self.server = server_module.make_server(
            0, self.database, {}, {}, director_service=self.director, voice_service=self.voice
        )
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop_server(self):
        self.backend.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def request(self, path, payload=None, *, token=None, headers=None, raw=None):
        data = json.dumps(payload).encode() if payload is not None else raw
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        if token is not None:
            request_headers["X-TakeOne-Voice-Token"] = token
        request = Request(self.base + path, data=data, headers=request_headers)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            data = response.read()
            body = json.loads(data) if response.headers.get_content_type() == "application/json" else data
            return response.status, body, response.headers

    def create(self, **extra):
        status, created, _ = self.request(
            "/api/voice/sessions", {"schema_version": 1, "mode": "offline", **extra}
        )
        self.assertEqual(status, 201, created)
        self.owner = created
        self.token = created["ownership_token"]
        return created

    def envelope(self, response=None):
        if response is None:
            response = self.request("/api/voice/snapshot", token=self.token)[1]
        return {
            "schema_version": 1,
            "voice_session_id": self.owner["voice_session_id"],
            "scope": response["snapshot"]["scope"],
            "generation": response["snapshot"]["generation"],
            "expires_monotonic_ns": str(self.clock() + 4_000_000_000),
        }

    def start_body(self, scenario="normal", **extra):
        return {
            **self.envelope(),
            "request_id": str(uuid4()),
            "zoom": {"start_factor": 1, "end_factor": 2, "duration_ms": 250},
            "scenario": scenario,
            **extra,
        }

    def start(self, scenario="normal"):
        status, started, _ = self.request("/api/recording/start", self.start_body(scenario), token=self.token)
        self.assertEqual(status, 200, started)
        return started

    def take(self, take_id):
        status, response, _ = self.request(f"/api/recording/takes/{take_id}", token=self.token)
        self.assertEqual(status, 200, response)
        return response

    def mutate(self, action, take_id):
        return self.request(
            f"/api/recording/{action}",
            {**self.envelope(), "request_id": str(uuid4()), "take_id": take_id},
            token=self.token,
        )

    def recording(self, scenario="normal"):
        started = self.start(scenario)
        self.clock.value += 150_000_000
        current = self.take(started["take"]["take_id"])
        self.assertEqual(current["take"]["state"], "recording")
        return current

    def settled(self, take_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            response = self.take(take_id)
            if response["take"]["state"] in {"ready", "failed"}:
                return response
            time.sleep(0.01)
        self.fail("Synthetic media did not settle within five seconds")

    def test_start_closes_voice_before_ack_without_real_readiness(self):
        before = self.create()
        self.assertFalse(before["snapshot"]["quiet"])
        started = self.start("delayed_start")
        self.assertTrue(started["snapshot"]["quiet"])
        self.assertEqual(started["take"]["state"], "starting")
        self.assertEqual(started["take"]["source"], "simulated")
        runtime = self.request("/api/voice/runtime")[1]
        self.assertFalse(runtime["recorder"]["ready"])
        self.assertFalse(runtime["recorder"]["observation_seen"])
        for state in ("idle", "stopped", "recording"):
            result = self.request(
                "/api/voice/fixture-recording",
                {
                    **self.envelope(),
                    "event_scope": started["snapshot"]["scope"],
                    "sequence": 100,
                    "state": state,
                },
                token=self.token,
            )
            self.assertEqual(result[0], 409, result[1])
            self.assertTrue(result[1]["snapshot"]["quiet"])

    def test_pending_question_is_cancelled_and_original_retry_survives_generation_change(self):
        self.create()
        body = self.start_body()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self.request,
                "/api/voice/questions",
                {**self.envelope(), "request_id": "question", "question": "Delayed help"},
                token=self.token,
            )
            self.assertTrue(self.backend.entered.wait(2))
            status, started, _ = self.request("/api/recording/start", body, token=self.token)
            self.assertEqual(status, 200, started)
            self.assertGreater(started["snapshot"]["generation"], body["generation"])
            retry = self.request("/api/recording/start", body, token=self.token)
            self.assertEqual(retry[0], 200, retry[1])
            self.assertEqual(retry[1]["take"]["take_id"], started["take"]["take_id"])
            changed = self.request(
                "/api/recording/start", {**body, "scenario": "disconnect"}, token=self.token
            )
            self.assertEqual(changed[0], 409)
            take_id = started["take"]["take_id"]
            self.assertEqual(self.mutate("stop", take_id)[0], 200)
            self.backend.release.set()
            self.assertEqual(future.result()[0], 409)
        snapshot = self.request("/api/voice/snapshot", token=self.token)[1]["snapshot"]
        self.assertFalse(snapshot["quiet"])
        self.assertFalse(any(entry["speaker"] == "director" for entry in snapshot["transcript"]))

    def test_finalization_keeps_quiet_then_serves_authenticated_verified_bytes(self):
        self.create()
        take_id = self.recording()["take"]["take_id"]
        writer = BlockingWriter()
        self.addCleanup(writer.release.set)
        self.server.recording.service.recording.media_writer = writer
        self.assertEqual(self.mutate("stop", take_id)[0], 200)
        self.assertTrue(writer.entered.wait(2))
        self.clock.value += 6_000_000_000
        current = self.take(take_id)
        self.assertEqual(current["take"]["state"], "finalizing")
        self.assertTrue(current["snapshot"]["quiet"])
        self.assertEqual(self.request(f"/api/recording/takes/{take_id}/media", token=self.token)[0], 409)
        writer.release.set()
        ready = self.settled(take_id)
        self.assertFalse(ready["snapshot"]["quiet"])
        self.assertFalse(ready["take"]["real_media_verified"])
        status, media, headers = self.request(f"/api/recording/takes/{take_id}/media", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(hashlib.sha256(media).hexdigest(), ready["take"]["media"]["sha256"])
        self.assertEqual(headers.get_content_type(), "video/mp4")
        for path in Path(self.folder.name).rglob("*"):
            if path.is_file():
                self.assertNotIn(self.token.encode(), path.read_bytes())

    def test_unknown_stop_stays_quiet_until_explicit_recovery_then_new_question_works(self):
        self.create()
        take_id = self.recording("stop_timeout")["take"]["take_id"]
        self.assertEqual(self.mutate("stop", take_id)[0], 200)
        self.clock.value += 6_000_000_000
        unknown = self.take(take_id)
        self.assertEqual(unknown["take"]["state"], "unknown")
        self.assertTrue(unknown["snapshot"]["quiet"])
        recovered = self.mutate("recover", take_id)
        self.assertEqual(recovered[0], 200, recovered[1])
        self.assertFalse(recovered[1]["snapshot"]["quiet"])
        self.assertEqual(recovered[1]["take"]["state"], "failed")
        question = self.request(
            "/api/voice/questions",
            {**self.envelope(), "request_id": "fresh-question", "question": "New help"},
            token=self.token,
        )
        self.assertEqual(question[0], 200, question[1])

    def test_strict_validation_and_local_security_have_no_start_side_effect(self):
        self.create()
        body = self.start_body()
        invalid = [
            ({**body, "file_path": "/etc/passwd"}, {}, self.token, 400),
            ({**body, "zoom": {**body["zoom"], "end_factor": 5}}, {}, self.token, 400),
            ({**body, "scenario": "live"}, {}, self.token, 400),
            ({**body, "generation": 100}, {}, self.token, 409),
            ({**body, "expires_monotonic_ns": str(self.clock() - 1)}, {}, self.token, 409),
            (body, {"Host": "evil.example"}, self.token, 403),
            (body, {"Origin": "https://evil.example"}, self.token, 403),
            (body, {}, None, 401),
            (body, {}, "wrong", 403),
        ]
        for payload, headers, token, expected in invalid:
            with self.subTest(payload=payload, headers=headers, token=bool(token)):
                result = self.request("/api/recording/start", payload, token=token, headers=headers)
                self.assertEqual(result[0], expected, result[1])
        self.assertEqual(self.request("/api/recording/takes", token=self.token)[1]["takes"], [])
        self.assertFalse(self.request("/api/voice/snapshot", token=self.token)[1]["snapshot"]["quiet"])
        self.assertEqual(self.request("/api/recording/takes")[0], 401)
        self.assertEqual(self.request("/api/recording/takes/%2e%2e%2fsecret/media", token=self.token)[0], 400)

    def test_failed_and_corrupt_synthetic_media_never_download(self):
        self.create()
        for scenario in ("save_failure", "corrupt_media"):
            with self.subTest(scenario=scenario):
                take_id = self.recording(scenario)["take"]["take_id"]
                self.assertEqual(self.mutate("stop", take_id)[0], 200)
                failed = self.settled(take_id)
                self.assertEqual(failed["take"]["state"], "failed")
                self.assertFalse(failed["snapshot"]["quiet"])
                self.assertEqual(
                    self.request(f"/api/recording/takes/{take_id}/media", token=self.token)[0], 409
                )

    def test_restart_lists_completed_media_but_requires_explicit_unfinished_recovery(self):
        self.create()
        complete_id = self.recording()["take"]["take_id"]
        self.mutate("stop", complete_id)
        self.assertEqual(self.settled(complete_id)["take"]["state"], "ready")
        unfinished_id = self.start()["take"]["take_id"]
        old_token = self.token
        self.stop_server()
        self.launch()
        created = self.create()
        self.assertTrue(created["snapshot"]["quiet"])
        self.assertEqual(self.request("/api/recording/takes", token=old_token)[0], 403)
        takes = self.request("/api/recording/takes", token=self.token)[1]
        self.assertEqual({take["take_id"] for take in takes["takes"]}, {complete_id, unfinished_id})
        self.assertTrue(takes["snapshot"]["quiet"])
        self.assertEqual(self.request(f"/api/recording/takes/{complete_id}/media", token=self.token)[0], 200)
        self.assertEqual(self.mutate("stop", unfinished_id)[0], 409)
        recovered = self.mutate("recover", unfinished_id)
        self.assertEqual(recovered[0], 200, recovered[1])
        self.assertFalse(recovered[1]["snapshot"]["quiet"])

    def test_ready_file_modified_after_validation_is_refused_and_never_public(self):
        self.create()
        take_id = self.recording()["take"]["take_id"]
        self.mutate("stop", take_id)
        ready = self.settled(take_id)
        path = self.server.recording.service.recording.media_root / ready["take"]["media"]["relative_path"]
        original = path.read_bytes()
        path.write_bytes(b"x" * len(original))
        response = self.request(f"/api/recording/takes/{take_id}/media", token=self.token)
        self.assertEqual(response[0], 409, response[1])
        self.assertEqual(response[1]["code"], "media_integrity_failed")
        self.assertEqual(self.request(f"/api/recording/takes/{take_id}/media")[0], 401)
        self.assertEqual(self.request(f"/recording/media/{take_id}/synthetic.mp4")[0], 404)

    def test_finalization_busy_keeps_stop_identity_retryable_and_new_take_quiet(self):
        self.create()
        first = self.recording()["take"]["take_id"]
        writer = BlockingWriter()
        self.addCleanup(writer.release.set)
        self.server.recording.service.recording.media_writer = writer
        self.mutate("stop", first)
        self.assertTrue(writer.entered.wait(2))
        self.assertEqual(self.mutate("recover", first)[0], 200)
        second = self.recording()["take"]["take_id"]
        body = {**self.envelope(), "request_id": "retry-busy-stop", "take_id": second}
        busy = self.request("/api/recording/stop", body, token=self.token)
        self.assertEqual(busy[0], 409, busy[1])
        self.assertEqual(busy[1]["code"], "finalization_busy")
        self.assertTrue(busy[1]["snapshot"]["quiet"])
        self.assertEqual(self.take(second)["take"]["state"], "recording")
        writer.release.set()
        # A sentinel on the sole worker runs after finalizer completion callbacks,
        # making admission release deterministic without polling mutation retries.
        recorder = self.server.recording.service.recording
        recorder._executor.submit(lambda: None).result(3)
        retry = self.request("/api/recording/stop", body, token=self.token)
        self.assertEqual(retry[0], 200, retry[1])
        self.assertEqual(self.settled(second)["take"]["state"], "ready")

    def test_late_callback_cannot_release_replacement_owner_or_take(self):
        self.create()
        old = self.recording()["take"]["take_id"]
        writer = BlockingWriter()
        self.addCleanup(writer.release.set)
        self.server.recording.service.recording.media_writer = writer
        self.mutate("stop", old)
        self.assertTrue(writer.entered.wait(2))
        recovered = self.mutate("recover", old)[1]["take"]
        old_token = self.token
        self.assertEqual(self.request("/api/voice/disconnect", self.envelope(), token=self.token)[0], 200)
        replacement = self.create()
        self.assertFalse(replacement["snapshot"]["quiet"])
        current = self.start()["take"]["take_id"]
        self.server.recording.service.observe(recovered, "stopped")
        self.assertTrue(self.take(current)["snapshot"]["quiet"])
        self.assertEqual(self.mutate("recover", old)[0], 409)
        wrong = self.request(
            "/api/recording/recover",
            {**self.envelope(), "request_id": "wrong-owner", "take_id": current},
            token=old_token,
        )
        self.assertEqual(wrong[0], 403)
        self.assertNotIn("snapshot", wrong[1])
        writer.release.set()

    def test_server_close_joins_finishing_callback_without_holding_voice_lock(self):
        self.create()
        take_id = self.recording()["take"]["take_id"]
        writer = BlockingWriter()
        self.addCleanup(writer.release.set)
        self.server.recording.service.recording.media_writer = writer
        self.mutate("stop", take_id)
        self.assertTrue(writer.entered.wait(2))
        self.server.shutdown()
        with ThreadPoolExecutor(max_workers=1) as executor:
            closed = executor.submit(self.server.server_close)
            self.assertFalse(closed.done())
            writer.release.set()
            closed.result(3)

    def test_original_director_context_and_revision_remain_unchanged(self):
        session = self.director.create(
            str(uuid4()),
            self.director.epoch,
            self.director.clock() + COMMAND_TTL_NS,
            ProductionBrief("Product", "A clear introduction", 12000, "9:16"),
        )["session"]
        before = self.director.repository.inspect(session["session_id"])
        created = self.create(director_session_id=session["session_id"])
        take_id = self.recording()["take"]["take_id"]
        self.mutate("stop", take_id)
        ready = self.settled(take_id)
        self.assertEqual(ready["take"]["context"]["director_context"], created["context"])
        self.assertEqual(self.director.repository.inspect(session["session_id"]), before)

    def test_live_owner_cannot_create_offline_take(self):
        session = self.director.create(
            str(uuid4()),
            self.director.epoch,
            self.director.clock() + COMMAND_TTL_NS,
            ProductionBrief("Product", "Practice", 12000, "9:16"),
        )["session"]
        self.voice.live_provider = FakeLiveProvider()
        status, created, _ = self.request(
            "/api/voice/sessions",
            {"schema_version": 1, "mode": "live", "director_session_id": session["session_id"]},
        )
        self.assertEqual(status, 201, created)
        self.owner, self.token = created, created["ownership_token"]
        result = self.request("/api/recording/start", self.start_body(), token=self.token)
        self.assertEqual(result[0], 409, result[1])
        self.assertEqual(result[1]["code"], "offline_required")

    def test_retry_metadata_is_taken_after_polling_changes_the_gate(self):
        self.create()
        body = self.start_body("start_timeout")
        started = self.request("/api/recording/start", body, token=self.token)[1]
        self.clock.value += 4_000_000_000
        retried = self.request("/api/recording/start", body, token=self.token)
        self.assertEqual(retried[0], 200, retried[1])
        self.assertEqual(retried[1]["take"]["take_id"], started["take"]["take_id"])
        self.assertEqual(retried[1]["take"]["state"], "unknown")
        self.assertTrue(retried[1]["snapshot"]["quiet"])

    def test_duplicate_json_and_malformed_bounds_are_rejected(self):
        self.create()
        body = self.start_body()
        for zoom in (
            {"start_factor": True, "end_factor": 2, "duration_ms": 250},
            {"start_factor": 1, "end_factor": float("nan"), "duration_ms": 250},
            {"start_factor": 1, "end_factor": 2, "duration_ms": 10001},
            {"start_factor": 1, "end_factor": 2, "duration_ms": 249},
        ):
            self.assertEqual(
                self.request("/api/recording/start", {**body, "zoom": zoom}, token=self.token)[0], 400
            )
        duplicate = json.dumps(body)[:-1] + ', "schema_version": 1}'
        self.assertEqual(
            self.request("/api/recording/start", raw=duplicate.encode(), token=self.token)[0], 400
        )
        wrong_scope = {**body, "scope": {**body["scope"], "revision": 999}}
        self.assertEqual(self.request("/api/recording/start", wrong_scope, token=self.token)[0], 409)
        self.assertEqual(
            self.request(
                "/api/recording/start", {**body, "voice_session_id": str(uuid4())}, token=self.token
            )[0],
            409,
        )
        for path in ("/api/recording/takes", "/api/recording/runtime"):
            self.assertEqual(self.request(path, headers={"Host": "evil.example"}, token=self.token)[0], 403)
            self.assertEqual(
                self.request(path, headers={"Origin": "https://evil.example"}, token=self.token)[0], 403
            )
        self.assertEqual(self.request("/api/recording/takes?path=secret", token=self.token)[0], 400)
        self.assertEqual(self.request("/api/recording/takes", token=self.token)[1]["takes"], [])

    def test_runtime_replaced_after_start_dispatch_cannot_release_the_gate(self):
        self.create()
        recorder = self.server.recording.service.recording
        original_start = recorder.simulator.request_start
        replacements = []

        def replace_after_dispatch(*args):
            self.assertTrue(self.voice.snapshot(self.token)["snapshot"]["quiet"])
            result = original_start(*args)
            replacements.append(
                RecordingService(recorder.repository.path, recorder.media_root, clock=self.clock)
            )
            return result

        try:
            with patch.object(recorder.simulator, "request_start", replace_after_dispatch):
                result = self.request("/api/recording/start", self.start_body(), token=self.token)
            self.assertEqual(result[0], 409, result[1])
            self.assertEqual(result[1]["code"], "runtime_replaced")
            self.assertTrue(self.voice.snapshot(self.token)["snapshot"]["quiet"])
        finally:
            for replacement in replacements:
                replacement.close()

    def test_director_scope_change_releases_only_original_latch_on_stop(self):
        session = Session.parse(
            self.director.create(
                str(uuid4()),
                self.director.epoch,
                self.director.clock() + COMMAND_TTL_NS,
                ProductionBrief("Product", "Practice", 12000, "9:16"),
            )["session"]
        )
        created = self.create(director_session_id=session.session_id)
        take_id = self.start("delayed_start")["take"]["take_id"]
        revised = self.director.submit(
            Command(
                str(uuid4()),
                self.director.epoch,
                self.director.clock() + COMMAND_TTL_NS,
                session.scope(),
                "revise_brief",
                ProductionBrief("Revised", "Practice", 12000, "9:16"),
            )
        )
        self.assertTrue(revised["ok"])
        stopped = self.mutate("stop", take_id)
        self.assertEqual(stopped[0], 200, stopped[1])
        self.assertEqual(stopped[1]["snapshot"]["scope"]["revision"], 1)
        self.assertTrue(stopped[1]["snapshot"]["quiet"])
        self.assertFalse(stopped[1]["snapshot"]["recording_latch_active"])
        self.assertEqual(stopped[1]["take"]["context"]["scope"], created["snapshot"]["scope"])

    def test_shutdown_rejects_late_start_instead_of_opening_a_take(self):
        self.create()
        body = self.start_body()
        self.server.recording.service.close()
        result = self.request("/api/recording/start", body, token=self.token)
        self.assertEqual(result[0], 503, result[1])
        self.assertEqual(self.server.recording.service.recording.list_takes(), [])

    def test_invalid_request_errors_are_bounded(self):
        self.create()
        body = {**self.start_body(), "x" * 2000: True}
        result = self.request("/api/recording/start", body, token=self.token)
        self.assertEqual(result[0], 400)
        self.assertLessEqual(len(result[1]["message"]), 300)

    def test_stop_and_recovery_exact_retries_survive_expiry(self):
        self.create()
        take_id = self.recording("disconnect")["take"]["take_id"]
        stop_body = {**self.envelope(), "request_id": "repeat-stop", "take_id": take_id}
        stopped = self.request("/api/recording/stop", stop_body, token=self.token)
        self.assertEqual(stopped[0], 200, stopped[1])
        self.assertEqual(stopped[1]["take"]["state"], "unknown")
        self.clock.value += 6_000_000_000
        retried = self.request("/api/recording/stop", stop_body, token=self.token)
        self.assertEqual(retried[0], 200, retried[1])
        self.assertEqual(retried[1]["take"]["events"], stopped[1]["take"]["events"])
        recovery_body = {**self.envelope(), "request_id": "repeat-recovery", "take_id": take_id}
        recovered = self.request("/api/recording/recover", recovery_body, token=self.token)
        self.assertEqual(recovered[0], 200, recovered[1])
        self.clock.value += 6_000_000_000
        retried = self.request("/api/recording/recover", recovery_body, token=self.token)
        self.assertEqual(retried[0], 200, retried[1])
        self.assertEqual(retried[1]["take"]["events"], recovered[1]["take"]["events"])

    def test_terminal_http_responses_reconcile_evidence_before_callback_delivery(self):
        self.create()
        recorder = self.server.recording.service.recording
        for scenario, expected in (
            ("normal", "ready"),
            ("save_failure", "failed"),
            ("corrupt_media", "failed"),
        ):
            for route in ("status", "list", "retry"):
                with self.subTest(scenario=scenario, route=route):
                    take_id = self.recording(scenario)["take"]["take_id"]
                    writer = BlockingWriter()
                    recorder.media_writer = writer
                    notification = PausedTerminalNotification(recorder.notify)
                    stop_body = {**self.envelope(), "request_id": str(uuid4()), "take_id": take_id}
                    with patch.object(recorder, "notify", notification):
                        try:
                            stopped = self.request("/api/recording/stop", stop_body, token=self.token)
                            self.assertEqual(stopped[0], 200, stopped[1])
                            self.assertTrue(writer.entered.wait(2))
                            writer.release.set()
                            self.assertTrue(notification.entered.wait(3))
                            # The real SQLite transaction is committed; callback
                            # delivery is deliberately still paused.
                            if route == "retry":
                                result = self.request("/api/recording/stop", stop_body, token=self.token)
                            else:
                                path = "/api/recording/takes" + (f"/{take_id}" if route == "status" else "")
                                result = self.request(path, token=self.token)
                            self.assertEqual(result[0], 200, result[1])
                            response = result[1]
                            take = response["takes"][0] if route == "list" else response["take"]
                            self.assertEqual(take["state"], expected)
                            self.assertFalse(
                                response["snapshot"]["quiet"],
                                f"Committed {expected} returned quiet before terminal callback delivery",
                            )
                        finally:
                            writer.release.set()
                            notification.release.set()
                            recorder._executor.submit(lambda: None).result(3)

    def test_status_keeps_take_and_voice_consistent_when_final_read_crosses_completion(self):
        self.create()
        take_id = self.recording()["take"]["take_id"]
        recorder = self.server.recording.service.recording
        writer = BlockingWriter()
        recorder.media_writer = writer
        notification = PausedTerminalNotification(recorder.notify)
        authority = self.voice.recording_authority

        def complete_after_snapshot(*args, **kwargs):
            response = authority(*args, **kwargs)
            if "renew_idle" in kwargs:
                writer.release.set()
                if not notification.entered.wait(3):
                    raise RuntimeError("Synthetic completion did not reach its notification")
            return response

        with patch.object(recorder, "notify", notification):
            try:
                self.assertEqual(self.mutate("stop", take_id)[0], 200)
                self.assertTrue(writer.entered.wait(2))
                with patch.object(self.voice, "recording_authority", complete_after_snapshot):
                    response = self.take(take_id)
                self.assertIn(response["take"]["state"], {"finalizing", "ready"})
                self.assertEqual(
                    response["snapshot"]["quiet"],
                    response["take"]["state"] == "finalizing",
                    "The response crossed completion after snapshotting voice metadata",
                )
            finally:
                writer.release.set()
                notification.release.set()
                recorder._executor.submit(lambda: None).result(3)

    def test_callback_cannot_open_voice_between_finalizing_read_and_response_snapshot(self):
        self.create()
        take_id = self.recording()["take"]["take_id"]
        bridge = self.server.recording.service
        recorder = bridge.recording
        writer = BlockingWriter()
        recorder.media_writer = writer
        self.assertEqual(self.mutate("stop", take_id)[0], 200)
        self.assertTrue(writer.entered.wait(2))
        boundary = Queue()
        reader_ready = threading.Event()
        continue_read = threading.Event()
        original_lock = bridge._mutations
        original_authority = self.voice.recording_authority
        original_notify = recorder.notify

        class ObservedLock:
            # The queue lets the test progress at either a blocked acquisition
            # or completed callback, without inferring scheduling from a sleep.
            def __enter__(self):
                if not original_lock.acquire(blocking=False):
                    boundary.put("callback_waiting")
                    original_lock.acquire()

            def __exit__(self, *_args):
                original_lock.release()

        def before_snapshot(*args, **kwargs):
            if "renew_idle" in kwargs:
                reader_ready.set()
                if not continue_read.wait(3):
                    raise RuntimeError("Test did not resume response assembly")
            return original_authority(*args, **kwargs)

        def delivered(take, state):
            original_notify(take, state)
            if state == "ready":
                boundary.put("callback_delivered")

        with (
            patch.object(bridge, "_mutations", ObservedLock()),
            patch.object(self.voice, "recording_authority", before_snapshot),
            patch.object(recorder, "notify", delivered),
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            try:
                future = executor.submit(self.request, f"/api/recording/takes/{take_id}", token=self.token)
                self.assertTrue(reader_ready.wait(2))
                writer.release.set()
                reached = boundary.get(timeout=3)
                continue_read.set()
                status, response, _ = future.result(3)
                self.assertEqual(status, 200, response)
                self.assertEqual(response["take"]["state"], "finalizing")
                self.assertTrue(response["snapshot"]["quiet"], reached)
            finally:
                writer.release.set()
                continue_read.set()
                recorder._executor.submit(lambda: None).result(3)
