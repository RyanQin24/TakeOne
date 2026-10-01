import importlib.util
import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from takeone import cli
from takeone.director.contracts import Command, ProductionBrief, Session
from takeone.director.planning import CreativePlanning
from takeone.director.repository import SessionRepository
from takeone.director.service import COMMAND_TTL_NS, DirectorService, OwnerReplacedError
from takeone.director.skills import sample_project
from takeone.paths import WORKSPACE
from takeone.voice.contracts import RecordingEvent, VoiceScope
from takeone.voice.provider import LiveProviderError, LiveSession
from takeone.voice.service import MUTATION_TTL_NS, VoiceService, VoiceServiceError

spec = importlib.util.spec_from_file_location("rehearsal_server", WORKSPACE / "apps/rehearsal/server.py")
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


class SelectiveBackend:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.questions = []

    def answer(self, context, question, cancellation_event):
        self.questions.append((context, question, cancellation_event))
        if question == "Delayed help":
            self.entered.set()
            self.release.wait(5)
        if question == "Backend timeout":
            raise TimeoutError("injected backend timeout")
        if question == "Invalid response":
            return {"not": "bounded text"}
        return f"Fixture suggestion: {question}"


class FakeLiveProvider:
    def __init__(self, duration_seconds=60):
        self.duration_seconds = duration_seconds
        self.created = []
        self.hung_up = []
        self.hangup_event = threading.Event()

    def status(self):
        return {
            "available": True,
            "state": "configured_unverified",
            "provider": "openai",
            "model": "gpt-live-1",
            "max_session_duration_ms": int(self.duration_seconds * 1000),
        }

    def create_session(self, offer_sdp, cancellation_event):
        self.created.append((offer_sdp, cancellation_event))
        return LiveSession("live-opaque", "v=0\r\na=answer\r\n")

    def hangup(self, session_id):
        self.hung_up.append(session_id)
        self.hangup_event.set()


class FailingHangupProvider(FakeLiveProvider):
    def hangup(self, session_id):
        from takeone.voice.provider import LiveProviderError

        self.hung_up.append(session_id)
        raise LiveProviderError("cleanup_unconfirmed", "sanitized cleanup failure")


class BlockingLiveProvider(FakeLiveProvider):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def create_session(self, offer_sdp, cancellation_event):
        self.created.append((offer_sdp, cancellation_event))
        self.entered.set()
        self.release.wait(2)
        return LiveSession("late-live", "v=0\r\na=late-answer\r\n")


class BlockingFailingHangupProvider(BlockingLiveProvider):
    def hangup(self, session_id):
        self.hung_up.append(session_id)
        raise LiveProviderError("cleanup_unconfirmed", "sanitized cleanup failure")


class UncertainLiveProvider(FakeLiveProvider):
    def create_session(self, offer_sdp, cancellation_event):
        self.created.append((offer_sdp, cancellation_event))
        raise LiveProviderError(
            "creation_uncertain",
            "sanitized uncertain creation",
            creation_uncertain=True,
        )


class FailingAfterCancellationBackend:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def answer(self, context, question, cancellation_event):
        if question == "Fail after cancellation":
            self.entered.set()
            self.release.wait(2)
            raise RuntimeError("private backend failure")
        return "Fixture suggestion: recovered"


class PausedResultFuture:
    def __init__(self, future, executor):
        self.future = future
        self.executor = executor

    def add_done_callback(self, callback):
        def complete(_future):
            callback(self)
            self.executor.callback_done.set()

        self.future.add_done_callback(complete)

    def done(self):
        return self.future.done()

    def result(self, timeout=None):
        try:
            result = self.future.result(timeout)
        except self.executor.paused_exception:
            self.executor.delivery_ready.set()
            if not self.executor.deliver.wait(2):
                raise RuntimeError("test did not release result delivery") from None
            raise
        if self.executor.paused_exception == ():
            self.executor.delivery_ready.set()
            if not self.executor.deliver.wait(2):
                raise RuntimeError("test did not release result delivery")
        return result


class PausedResultExecutor:
    def __init__(self, paused_exception):
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.paused_exception = paused_exception
        self.callback_done = threading.Event()
        self.delivery_ready = threading.Event()
        self.deliver = threading.Event()
        self.submissions = 0

    def submit(self, function):
        future = self.executor.submit(function)
        self.submissions += 1
        return PausedResultFuture(future, self) if self.submissions == 1 else future

    def shutdown(self, wait=False, cancel_futures=False):
        self.executor.shutdown(wait=wait, cancel_futures=cancel_futures)


class BlockingFirstBackend:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def answer(self, context, question, cancellation_event):
        if question == "Timeout after cancellation":
            self.entered.set()
            self.release.wait(2)
        return "Fixture suggestion: replacement answer"


class Clock:
    def __init__(self):
        self.value = 1_000_000_000_000_000_000

    def __call__(self):
        return self.value


class VoiceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.database = Path(self.folder.name) / "sessions.sqlite3"
        self.director = DirectorService(SessionRepository(self.database))
        self.backend = SelectiveBackend()
        self.live_provider = FakeLiveProvider()
        self.voice = VoiceService(
            self.director,
            offline_backend=self.backend,
            live_provider=self.live_provider,
            backend_timeout_seconds=0.25,
            recorder_ready=True,
        )
        self.server = server_module.make_server(
            0,
            self.database,
            {"ring": {"source": "voice HTTP fixture"}},
            {"previewAvailable": True},
            director_service=self.director,
            voice_service=self.voice,
        )
        self.addCleanup(self.stop_server)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

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
            content = response.read().decode()
            return response.status, json.loads(content) if content.startswith("{") else content

    def create_offline(self, **extra):
        status, created = self.request(
            "/api/voice/sessions", {"schema_version": 1, "mode": "offline", **extra}
        )
        self.assertEqual(status, 201, created)
        return created

    def envelope(self, created, snapshot=None):
        if snapshot is None:
            snapshot = created["snapshot"]
        runtime = self.request("/api/voice/runtime")[1]
        return {
            "schema_version": 1,
            "voice_session_id": created["voice_session_id"],
            "scope": snapshot["scope"],
            "generation": snapshot["generation"],
            "expires_monotonic_ns": str(int(runtime["now_monotonic_ns"]) + int(runtime["mutation_ttl_ns"])),
        }

    def test_backend_raised_timeout_releases_slot(self):
        self.check_completed_timeout("Backend timeout")

    def test_completion_before_timeout_handler_releases_slot(self):
        self.check_completed_timeout("Delayed help")

    def check_completed_timeout(self, question):
        executor = PausedResultExecutor(TimeoutError)
        self.voice._executor.shutdown()
        self.voice._executor = executor
        self.backend.release.clear()
        created = self.create_offline()
        token = created["ownership_token"]
        with ThreadPoolExecutor(max_workers=1) as callers:
            try:
                pending = callers.submit(
                    self.request,
                    "/api/voice/questions",
                    {**self.envelope(created), "request_id": str(uuid4()), "question": question},
                    token=token,
                )
                self.assertTrue(executor.delivery_ready.wait(1))
                self.backend.release.set()
                self.assertTrue(executor.callback_done.wait(1))
                executor.deliver.set()
                status, timed_out = pending.result(1)
                self.assertEqual(status, 504, timed_out)
                status, recovered = self.request(
                    "/api/voice/questions",
                    {
                        **self.envelope(created, timed_out["snapshot"]),
                        "request_id": str(uuid4()),
                        "question": "Recover after timeout",
                    },
                    token=token,
                )
                self.assertEqual(status, 200, recovered)
                self.assertEqual(executor.submissions, 2)
            finally:
                executor.deliver.set()
                self.backend.release.set()
                state = self.voice.snapshot(token)["snapshot"]
                self.request("/api/voice/disconnect", self.envelope(created, state), token=token)
        replacement = self.create_offline()
        status, recovered = self.request(
            "/api/voice/questions",
            {**self.envelope(replacement), "request_id": str(uuid4()), "question": "Replacement question"},
            token=replacement["ownership_token"],
        )
        self.assertEqual(status, 200, recovered)

    def test_rejected_nonidle_evidence_does_not_strand_logical_request(self):
        self.voice.backend_timeout_seconds = 5
        for boundary in ("fixture", "recorder"):
            for invalid in ("replayed", "wrong_scope"):
                with self.subTest(boundary=boundary, invalid=invalid):
                    executor = PausedResultExecutor(())
                    self.voice._executor.shutdown()
                    self.voice._executor = executor
                    self.backend.release.clear()
                    self.backend.entered.clear()
                    created = self.create_offline()
                    token = created["ownership_token"]
                    with ThreadPoolExecutor(max_workers=1) as callers:
                        try:
                            pending = callers.submit(
                                self.request,
                                "/api/voice/questions",
                                {
                                    **self.envelope(created),
                                    "request_id": str(uuid4()),
                                    "question": "Delayed help",
                                },
                                token=token,
                            )
                            self.assertTrue(self.backend.entered.wait(1))
                            event_scope = dict(created["snapshot"]["scope"])
                            if invalid == "wrong_scope":
                                event_scope["session_id"] = str(uuid4())
                            if boundary == "fixture":
                                status, observed = self.request(
                                    "/api/voice/fixture-recording",
                                    {
                                        **self.envelope(created),
                                        "event_scope": event_scope,
                                        "sequence": 0 if invalid == "replayed" else 1,
                                        "state": "requested",
                                    },
                                    token=token,
                                )
                                self.assertEqual(status, 200, observed)
                            else:
                                now = self.voice.clock()
                                observed = self.voice.observe_recorder(
                                    RecordingEvent(
                                        VoiceScope(**event_scope),
                                        0 if invalid == "replayed" else 1,
                                        "requested",
                                        "recorder",
                                        now,
                                        now + 5_000_000_000,
                                    )
                                )
                            self.backend.release.set()
                            self.assertTrue(executor.callback_done.wait(1))
                            executor.deliver.set()
                            status, stale = pending.result(1)
                            self.assertEqual(status, 409, stale)
                            self.assertNotIn("snapshot", stale)
                            self.assertFalse(observed["snapshot"]["recording_latch_active"])
                            self.assertIsNone(observed["snapshot"]["pending_request_id"])
                            status, recovered = self.request(
                                "/api/voice/questions",
                                {
                                    **self.envelope(created, observed["snapshot"]),
                                    "request_id": str(uuid4()),
                                    "question": "Fresh question",
                                },
                                token=token,
                            )
                            self.assertEqual(status, 200, recovered)
                        finally:
                            executor.deliver.set()
                            self.backend.release.set()
                            state = self.voice.snapshot(token)["snapshot"]
                            self.request("/api/voice/disconnect", self.envelope(created, state), token=token)

    def test_late_live_attachment_cannot_detach_replacement_transport(self):
        session = self.director.create(
            str(uuid4()),
            self.director.epoch,
            self.director.clock() + COMMAND_TTL_NS,
            ProductionBrief("Attachment race", "Practice", 12000, "9:16"),
        )["session"]
        entered, release = threading.Event(), threading.Event()
        original_refresh = self.voice._refresh_binding
        self.voice.conversation_backend = self.backend

        def create_ready():
            status, created = self.request(
                "/api/voice/sessions",
                {"schema_version": 1, "mode": "live", "director_session_id": session["session_id"]},
            )
            self.assertEqual(status, 201, created)
            now = self.voice.clock()
            ready = self.voice.observe_recorder(
                RecordingEvent(
                    VoiceScope(**created["snapshot"]["scope"]),
                    0,
                    "idle",
                    "recorder",
                    now,
                    now + 5_000_000_000,
                )
            )
            return created, ready

        old, ready = create_ready()

        def paused_refresh(*args, **kwargs):
            if self.voice._live_session_id is not None and not entered.is_set():
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("test did not release attachment")
            return original_refresh(*args, **kwargs)

        with ThreadPoolExecutor(max_workers=1) as callers:
            try:
                with patch.object(self.voice, "_refresh_binding", paused_refresh):
                    stale = callers.submit(
                        self.request,
                        "/api/voice/live-sessions",
                        {**self.envelope(old, ready["snapshot"]), "offer_sdp": "old injected offer"},
                        token=old["ownership_token"],
                    )
                    self.assertTrue(entered.wait(1))
                    status, ended = self.request(
                        "/api/voice/disconnect",
                        self.envelope(old, ready["snapshot"]),
                        token=old["ownership_token"],
                    )
                    self.assertEqual(status, 200, ended)
                    self.assertTrue(ended["cleanup_confirmed"])
                    replacement, ready = create_ready()
                    token = replacement["ownership_token"]
                    status, active = self.request(
                        "/api/voice/live-sessions",
                        {**self.envelope(replacement, ready["snapshot"]), "offer_sdp": "new injected offer"},
                        token=token,
                    )
                    self.assertEqual(status, 200, active)
                    release.set()
                    status, rejected = stale.result(1)
                    self.assertEqual(status, 409, rejected)
                    self.assertNotIn("snapshot", rejected)
                    current = self.request("/api/voice/snapshot", token=token)[1]["snapshot"]
                    self.assertEqual(current["live_transport_state"], "active")
                    self.assertEqual(current["media_directive"], "playback_permitted")
                    self.assertEqual(self.live_provider.hung_up, ["live-opaque"])
                    status, answered = self.request(
                        "/api/voice/questions",
                        {
                            **self.envelope(replacement, current),
                            "request_id": str(uuid4()),
                            "question": "Still usable",
                        },
                        token=token,
                    )
                    self.assertEqual(status, 200, answered)
            finally:
                release.set()

    def test_delayed_cleanup_returns_never_disclose_replacement_owner(self):
        for operation in ("disconnect", "interrupt", "fixture-recording", "recorder"):
            with self.subTest(operation=operation):
                old = self.create_offline()
                payload = self.envelope(old)
                if operation == "interrupt":
                    payload["reason"] = "creator_interrupt"
                elif operation == "fixture-recording":
                    payload.update(event_scope=payload["scope"], sequence=1, state="idle")
                entered = threading.Event()
                release = threading.Event()
                original_close = self.voice._finish_live_close

                def paused_close(*args, **kwargs):
                    result = original_close(*args, **kwargs)
                    if not entered.is_set():
                        entered.set()
                        if not release.wait(3):
                            raise RuntimeError("test did not release cleanup delivery")
                    return result

                with ThreadPoolExecutor(max_workers=1) as callers:
                    try:
                        with patch.object(self.voice, "_finish_live_close", paused_close):
                            if operation == "recorder":
                                now = self.voice.clock()
                                stale = callers.submit(
                                    self.voice.observe_recorder,
                                    RecordingEvent(
                                        VoiceScope(**payload["scope"]),
                                        1,
                                        "idle",
                                        "recorder",
                                        now,
                                        now + 5_000_000_000,
                                    ),
                                )
                            else:
                                stale = callers.submit(
                                    self.request,
                                    f"/api/voice/{operation}",
                                    payload,
                                    token=old["ownership_token"],
                                )
                            self.assertTrue(entered.wait(1))
                            if operation != "disconnect":
                                state = self.request("/api/voice/snapshot", token=old["ownership_token"])[1]
                                status, ended = self.request(
                                    "/api/voice/disconnect",
                                    self.envelope(old, state["snapshot"]),
                                    token=old["ownership_token"],
                                )
                                self.assertEqual(status, 200, ended)
                            replacement = self.create_offline()
                            status, answered = self.request(
                                "/api/voice/questions",
                                {
                                    **self.envelope(replacement),
                                    "request_id": str(uuid4()),
                                    "question": "Replacement owner private fixture text",
                                },
                                token=replacement["ownership_token"],
                            )
                            self.assertEqual(status, 200, answered)
                            release.set()
                            if operation == "recorder":
                                with self.assertRaises(VoiceServiceError) as raised:
                                    stale.result(1)
                                self.assertIsNone(raised.exception.snapshot)
                            else:
                                status, result = stale.result(1)
                                self.assertEqual(status, 409, result)
                                self.assertEqual(result["code"], "stale_result")
                                self.assertNotIn("snapshot", result)
                                self.assertNotIn(replacement["voice_session_id"], json.dumps(result))
                                self.assertNotIn("private fixture text", json.dumps(result))
                    finally:
                        release.set()
                        current = self.voice._voice_session_id
                        if current:
                            token = self.voice._token
                            state = self.voice.snapshot(token)["snapshot"]
                            self.voice.disconnect(
                                token,
                                current,
                                VoiceScope(**state["scope"]),
                                state["generation"],
                                self.voice.clock() + MUTATION_TTL_NS,
                            )

    def test_rejected_live_cleanup_error_omits_replacement_owner(self):
        session = self.director.create(
            str(uuid4()),
            self.director.epoch,
            self.director.clock() + COMMAND_TTL_NS,
            ProductionBrief("Offline race fixture", "Practice", 12000, "9:16"),
        )["session"]
        provider = BlockingLiveProvider()
        self.voice.live_provider = provider
        self.voice.conversation_backend = self.backend
        status, old = self.request(
            "/api/voice/sessions",
            {"schema_version": 1, "mode": "live", "director_session_id": session["session_id"]},
        )
        self.assertEqual(status, 201, old)
        now = self.voice.clock()
        ready = self.voice.observe_recorder(
            RecordingEvent(
                VoiceScope(**old["snapshot"]["scope"]),
                0,
                "idle",
                "recorder",
                now,
                now + 5_000_000_000,
            )
        )
        payload = {**self.envelope(old, ready["snapshot"]), "offer_sdp": "offline test offer"}
        entered = threading.Event()
        release = threading.Event()
        original_close = self.voice._finish_live_close

        def paused_close(session_id, **kwargs):
            result = original_close(session_id, **kwargs)
            if session_id == "late-live":
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("test did not release rejected creation cleanup")
            return result

        with ThreadPoolExecutor(max_workers=1) as callers:
            try:
                with patch.object(self.voice, "_finish_live_close", paused_close):
                    stale = callers.submit(
                        self.request, "/api/voice/live-sessions", payload, token=old["ownership_token"]
                    )
                    self.assertTrue(provider.entered.wait(1))
                    status, ended = self.request(
                        "/api/voice/disconnect",
                        self.envelope(old, ready["snapshot"]),
                        token=old["ownership_token"],
                    )
                    self.assertEqual(status, 200, ended)
                    self.assertFalse(ended["cleanup_confirmed"])
                    provider.release.set()
                    self.assertTrue(entered.wait(1))
                    replacement = self.create_offline()
                    status, answered = self.request(
                        "/api/voice/questions",
                        {
                            **self.envelope(replacement),
                            "request_id": str(uuid4()),
                            "question": "Replacement private text",
                        },
                        token=replacement["ownership_token"],
                    )
                    self.assertEqual(status, 200, answered)
                    release.set()
                    status, rejected = stale.result(1)
                    self.assertEqual(status, 409, rejected)
                    self.assertEqual(rejected["code"], "stale_result")
                    self.assertNotIn("snapshot", rejected)
                    self.assertNotIn("Replacement private text", json.dumps(rejected))
            finally:
                release.set()
                provider.release.set()

    def test_offline_loopback_conversation_cancels_delayed_reply_during_recording(self):
        before = len(self.director.repository.list_sessions())
        created = self.create_offline()
        token = created["ownership_token"]
        self.assertEqual(created["context"]["source"], "fixture")
        self.assertFalse(created["snapshot"]["quiet"])
        self.assertEqual(created["snapshot"]["media_directive"], "playback_permitted")

        status, first = self.request(
            "/api/voice/questions",
            {**self.envelope(created), "request_id": str(uuid4()), "question": "Help with my line"},
            token=token,
        )
        self.assertEqual(status, 200, first)
        self.assertEqual(first["source"], "fixture")
        self.assertEqual(first["response"], "Fixture suggestion: Help with my line")
        self.assertFalse(self.request("/api/health")[1]["hardwareConnected"])

        delayed_payload = {
            **self.envelope(created, first["snapshot"]),
            "request_id": str(uuid4()),
            "question": "Delayed help",
        }
        with ThreadPoolExecutor(max_workers=1) as pool:
            delayed = pool.submit(self.request, "/api/voice/questions", delayed_payload, token=token)
            self.assertTrue(self.backend.entered.wait(2))
            status, requested = self.request(
                "/api/voice/fixture-recording",
                {
                    **self.envelope(created, first["snapshot"]),
                    "event_scope": first["snapshot"]["scope"],
                    "sequence": 1,
                    "state": "requested",
                },
                token=token,
            )
            self.assertEqual(status, 200, requested)
            self.assertTrue(requested["snapshot"]["quiet"])
            self.assertEqual(requested["snapshot"]["quiet_reason"], "recording_requested")
            self.backend.release.set()
            late_status, late = delayed.result(2)
        self.assertEqual(late_status, 409, late)
        self.assertEqual(late["code"], "stale_result")
        current = self.request("/api/voice/snapshot", token=token)[1]["snapshot"]
        self.assertNotIn(
            "Fixture suggestion: Delayed help",
            [entry["text"] for entry in current["transcript"]],
        )

        status, stopped = self.request(
            "/api/voice/fixture-recording",
            {
                **self.envelope(created, current),
                "event_scope": first["snapshot"]["scope"],
                "sequence": 2,
                "state": "stopped",
            },
            token=token,
        )
        self.assertEqual(status, 200, stopped)
        self.assertFalse(stopped["snapshot"]["quiet"])
        status, fresh = self.request(
            "/api/voice/questions",
            {
                **self.envelope(created, stopped["snapshot"]),
                "request_id": str(uuid4()),
                "question": "Fresh help",
            },
            token=token,
        )
        self.assertEqual(status, 200, fresh)
        self.assertEqual(fresh["response"], "Fixture suggestion: Fresh help")
        self.assertEqual(len(self.director.repository.list_sessions()), before)

    def test_scope_refresh_at_generation_limit_returns_quiet_snapshot(self):
        from dataclasses import replace

        from takeone.voice.contracts import MAX_INTEGER

        scope = VoiceScope(self.director.epoch, str(uuid4()), 0, MAX_INTEGER, None, None)
        context = self.voice._fixture_context(scope.session_id)
        with patch.object(self.voice, "_read_director", return_value=(scope, context)) as read:
            created = self.create_offline(director_session_id=scope.session_id)
            token = created["ownership_token"]
            delayed_payload = {
                **self.envelope(created),
                "request_id": str(uuid4()),
                "question": "Delayed help",
            }
            with ThreadPoolExecutor(max_workers=1) as pool:
                delayed = pool.submit(
                    self.request,
                    "/api/voice/questions",
                    delayed_payload,
                    token=token,
                )
                try:
                    self.assertTrue(self.backend.entered.wait(2))
                    read.return_value = (replace(scope, revision=1), context)
                    status, result = self.request("/api/voice/snapshot", token=token)
                finally:
                    self.backend.release.set()
                delayed_status, delayed_result = delayed.result(2)

            self.assertEqual(status, 200, result)
            self.assertEqual(result["snapshot"]["generation"], MAX_INTEGER)
            self.assertTrue(result["snapshot"]["quiet"])
            self.assertTrue(result["snapshot"]["quiet_reason"].startswith("generation_exhausted"))
            self.assertTrue(self.backend.questions[0][2].is_set())
            self.assertEqual(delayed_status, 409, delayed_result)
            self.assertEqual(delayed_result["code"], "stale_result")
            reconciled_status, reconciled = self.request("/api/voice/snapshot", token=token)
            self.assertEqual(reconciled_status, 200, reconciled)
            self.assertEqual(reconciled["snapshot"]["generation"], MAX_INTEGER)
            self.assertTrue(reconciled["snapshot"]["quiet"])

    def test_fixture_delay_is_cancellable_and_rejected_outside_offline_mode(self):
        created = self.create_offline()
        token = created["ownership_token"]
        payload = {
            **self.envelope(created),
            "request_id": str(uuid4()),
            "question": "Interrupt this",
            "fixture_delay_ms": 5000,
        }
        with ThreadPoolExecutor(max_workers=1) as pool:
            question = pool.submit(self.request, "/api/voice/questions", payload, token=token)
            pending_deadline = time.monotonic() + 1
            while True:
                pending = self.request("/api/voice/snapshot", token=token)[1]["snapshot"]
                if pending["pending_request_id"] is not None:
                    break
                if time.monotonic() >= pending_deadline:
                    self.fail("delayed question did not become pending")
                time.sleep(0.005)
            status, interrupted = self.request(
                "/api/voice/interrupt",
                {**self.envelope(created), "reason": "creator_interrupt"},
                token=token,
            )
            self.assertEqual(status, 200, interrupted)
            delayed_status, delayed = question.result(2)
        self.assertEqual(delayed_status, 409, delayed)
        self.assertEqual(delayed["code"], "stale_result")
        self.assertEqual(self.backend.questions, [])

    def test_token_scope_generation_origin_and_body_limits_fail_closed(self):
        created = self.create_offline()
        token = created["ownership_token"]
        self.assertEqual(self.request("/api/voice/snapshot")[0], 401)
        self.assertEqual(self.request("/api/voice/snapshot", token="wrong-token")[1]["code"], "wrong_owner")
        self.assertEqual(
            self.request("/api/voice/snapshot", token=token, headers={"Origin": "https://untrusted.example"})[
                0
            ],
            403,
        )
        valid = {
            **self.envelope(created),
            "request_id": str(uuid4()),
            "question": "Hello",
        }
        wrong_scope = {**valid, "scope": {**valid["scope"], "revision": 999}}
        status, stale = self.request("/api/voice/questions", wrong_scope, token=token)
        self.assertEqual(status, 409)
        self.assertEqual(stale["code"], "stale_scope")
        wrong_generation = {**valid, "generation": valid["generation"] + 1}
        self.assertEqual(
            self.request("/api/voice/questions", wrong_generation, token=token)[1]["code"],
            "stale_generation",
        )
        self.assertEqual(self.request("/api/voice/questions", {**valid, "extra": True}, token=token)[0], 400)
        status, oversized = self.request("/api/voice/questions", raw=b"x" * 17000, token=token)
        self.assertEqual(status, 400)
        self.assertEqual(oversized["schema_version"], 1)
        self.assertEqual(oversized["code"], "invalid_request")

    def test_disconnect_cannot_bypass_recording_latch_with_a_new_owner(self):
        created = self.create_offline()
        token = created["ownership_token"]
        status, recording = self.request(
            "/api/voice/fixture-recording",
            {
                **self.envelope(created),
                "event_scope": created["snapshot"]["scope"],
                "sequence": 1,
                "state": "recording",
            },
            token=token,
        )
        self.assertEqual(status, 200, recording)
        status, quiet = self.request(
            "/api/voice/questions",
            {
                **self.envelope(created, recording["snapshot"]),
                "request_id": str(uuid4()),
                "question": "This must stay quiet",
            },
            token=token,
        )
        self.assertEqual(status, 409, quiet)
        self.assertEqual(quiet["code"], "recording_quiet")
        status, disconnected = self.request(
            "/api/voice/disconnect",
            self.envelope(created, recording["snapshot"]),
            token=token,
        )
        self.assertEqual(status, 200, disconnected)
        self.assertTrue(disconnected["ownership_retained"])
        status, blocked = self.request("/api/voice/sessions", {"schema_version": 1, "mode": "offline"})
        self.assertEqual(status, 409, blocked)
        self.assertEqual(blocked["code"], "recording_unresolved")
        self.assertNotIn("snapshot", blocked)

        status, stopped = self.request(
            "/api/voice/fixture-recording",
            {
                **self.envelope(created, disconnected["snapshot"]),
                "event_scope": created["snapshot"]["scope"],
                "sequence": 2,
                "state": "stopped",
            },
            token=token,
        )
        self.assertEqual(status, 200, stopped)
        self.assertEqual(
            self.request("/api/voice/sessions", {"schema_version": 1, "mode": "offline"})[0],
            201,
        )

    def test_runtime_replacement_invalidates_voice_runtime_without_exposing_owner(self):
        created = self.create_offline()
        DirectorService(SessionRepository(self.database))

        status, replaced = self.request("/api/voice/snapshot", token=created["ownership_token"])

        self.assertEqual(status, 409, replaced)
        self.assertEqual(replaced["code"], "runtime_changed")
        self.assertNotIn("ownership_token", replaced)

    def test_backend_timeout_keeps_the_only_worker_slot_until_ignored_cancellation_exits(self):
        created = self.create_offline()
        token = created["ownership_token"]
        status, timed_out = self.request(
            "/api/voice/questions",
            {
                **self.envelope(created),
                "request_id": str(uuid4()),
                "question": "Delayed help",
            },
            token=token,
        )
        self.assertEqual(status, 504, timed_out)
        self.assertEqual(timed_out["code"], "backend_timeout")
        status, occupied = self.request(
            "/api/voice/questions",
            {
                **self.envelope(created, timed_out["snapshot"]),
                "request_id": str(uuid4()),
                "question": "Must not queue",
            },
            token=token,
        )
        self.assertEqual(status, 409, occupied)
        self.assertEqual(occupied["code"], "operation_pending")
        self.backend.release.set()
        self.assertTrue(self.backend.entered.wait(1))

    def test_invalid_backend_result_is_explicit_and_does_not_strand_request_state(self):
        created = self.create_offline()
        token = created["ownership_token"]
        status, invalid = self.request(
            "/api/voice/questions",
            {
                **self.envelope(created),
                "request_id": str(uuid4()),
                "question": "Invalid response",
            },
            token=token,
        )
        self.assertEqual(status, 503, invalid)
        self.assertEqual(invalid["code"], "backend_invalid")

        status, recovered = self.request(
            "/api/voice/questions",
            {
                **self.envelope(created, invalid["snapshot"]),
                "request_id": str(uuid4()),
                "question": "Try again",
            },
            token=token,
        )
        self.assertEqual(status, 200, recovered)

    def test_director_revision_preserves_old_fixture_latch_for_exact_reconciliation(self):
        brief = ProductionBrief("Voice context", "Practice one supplied line.", 12000, "9:16")
        session = Session.parse(
            self.director.create(
                str(uuid4()), self.director.epoch, self.director.clock() + COMMAND_TTL_NS, brief
            )["session"]
        )
        created = self.create_offline(director_session_id=session.session_id)
        token = created["ownership_token"]
        old_scope = created["snapshot"]["scope"]
        status, latched = self.request(
            "/api/voice/fixture-recording",
            {
                **self.envelope(created),
                "event_scope": old_scope,
                "sequence": 1,
                "state": "recording",
            },
            token=token,
        )
        self.assertEqual(status, 200, latched)
        revised = self.director.submit(
            Command(
                str(uuid4()),
                self.director.epoch,
                self.director.clock() + COMMAND_TTL_NS,
                session.scope(),
                "revise_brief",
                ProductionBrief("Revised", "Practice one supplied line.", 12000, "9:16"),
            )
        )
        self.assertTrue(revised["ok"])
        status, refreshed = self.request("/api/voice/snapshot", token=token)
        self.assertEqual(status, 200, refreshed)
        self.assertEqual(refreshed["snapshot"]["scope"]["revision"], 1)
        self.assertEqual(refreshed["snapshot"]["quiet_reason"], "scope_changed")

        status, old_stopped = self.request(
            "/api/voice/fixture-recording",
            {
                **self.envelope(created, refreshed["snapshot"]),
                "event_scope": old_scope,
                "sequence": 2,
                "state": "stopped",
            },
            token=token,
        )
        self.assertEqual(status, 200, old_stopped)
        self.assertTrue(old_stopped["snapshot"]["quiet"])
        self.assertEqual(old_stopped["snapshot"]["quiet_reason"], "scope_changed")
        status, renewed = self.request(
            "/api/voice/fixture-recording",
            {
                **self.envelope(created, old_stopped["snapshot"]),
                "event_scope": old_stopped["snapshot"]["scope"],
                "sequence": 0,
                "state": "idle",
            },
            token=token,
        )
        self.assertEqual(status, 200, renewed)
        self.assertFalse(renewed["snapshot"]["quiet"])

    def test_offline_director_context_preserves_approved_curated_sample_provenance(self):
        sample = sample_project("product")
        session = Session.parse(
            self.director.create(
                str(uuid4()),
                self.director.epoch,
                self.director.clock() + COMMAND_TTL_NS,
                ProductionBrief.parse(sample["brief"]),
            )["session"]
        )
        planner = CreativePlanning(self.director)

        def submit(action, payload):
            nonlocal session
            body = {
                "schema_version": 1,
                "operation_id": str(uuid4()),
                "runtime_epoch": self.director.epoch,
                "expires_monotonic_ns": str(self.director.clock() + COMMAND_TTL_NS),
                "scope": asdict(session.scope()),
                "action": action,
                "payload": payload,
            }
            result = planner.submit(body, int(body["expires_monotonic_ns"]))
            session = Session.parse(result["session"])
            return result

        self.assertTrue(submit("load_sample", {"skill_id": "product"})["ok"])
        creative = self.director.repository.inspect(session.session_id)["creative"]
        self.assertTrue(submit("approve_script", {"document_digest": creative["digest"]})["ok"])
        before = self.director.repository.inspect(session.session_id)

        created = self.create_offline(director_session_id=session.session_id)

        script = created["context"]["script"]
        self.assertEqual(created["context"]["source"], "fixture_over_director_read_only")
        self.assertTrue(script["available"])
        self.assertEqual(script["provenance"]["source"], "curated_sample")
        self.assertIn("[product name]", json.dumps(script["document"]))
        self.assertEqual(self.director.repository.inspect(session.session_id), before)

    def test_live_transport_backend_and_recorder_availability_remain_distinct(self):
        brief = ProductionBrief("Live context", "Practice the approved script.", 12000, "9:16")
        session = Session.parse(
            self.director.create(
                str(uuid4()), self.director.epoch, self.director.clock() + COMMAND_TTL_NS, brief
            )["session"]
        )
        status, runtime = self.request("/api/voice/runtime")
        self.assertEqual(status, 200)
        self.assertTrue(runtime["live_transport"]["available"])
        self.assertFalse(runtime["conversation_backend"]["live_available"])
        self.assertTrue(runtime["recorder"]["ready"])

        status, created = self.request(
            "/api/voice/sessions",
            {"schema_version": 1, "mode": "live", "director_session_id": session.session_id},
        )
        self.assertEqual(status, 201, created)
        token = created["ownership_token"]
        status, delay_rejected = self.request(
            "/api/voice/questions",
            {
                **self.envelope(created),
                "request_id": str(uuid4()),
                "question": "Do not run a fixture delay",
                "fixture_delay_ms": 0,
            },
            token=token,
        )
        self.assertEqual(status, 400, delay_rejected)
        self.assertEqual(delay_rejected["code"], "fixture_delay_not_allowed")
        fixture = {
            **self.envelope(created),
            "event_scope": created["snapshot"]["scope"],
            "sequence": 0,
            "state": "idle",
        }
        status, rejected = self.request("/api/voice/fixture-recording", fixture, token=token)
        self.assertEqual(status, 409)
        self.assertEqual(rejected["code"], "fixture_not_allowed")

        scope = VoiceScope(**created["snapshot"]["scope"])
        now = self.director.clock()
        self.voice.observe_recorder(RecordingEvent(scope, 0, "idle", "recorder", now, now + 5_000_000_000))
        snapshot = self.request("/api/voice/snapshot", token=token)[1]["snapshot"]
        status, live = self.request(
            "/api/voice/live-sessions",
            {**self.envelope(created, snapshot), "offer_sdp": "v=0\r\na=offer\r\n"},
            token=token,
        )
        self.assertEqual(status, 503, live)
        self.assertEqual(live["code"], "backend_unavailable")
        self.assertEqual(self.live_provider.created, [])
        self.assertEqual(self.live_provider.hung_up, [])
        rejected = self.request("/api/voice/snapshot", token=token)[1]["snapshot"]
        self.assertEqual(rejected["live_transport_state"], "none")
        self.assertEqual(rejected["generation"], snapshot["generation"])
        self.assertIsNone(self.voice._live_cancel)
        self.assertIsNone(self.voice._live_session_id)
        self.voice.conversation_backend = self.backend
        status, live = self.request(
            "/api/voice/live-sessions",
            {**self.envelope(created, rejected), "offer_sdp": "v=0\r\na=offer\r\n"},
            token=token,
        )
        self.assertEqual(status, 200, live)
        self.assertEqual(live["transport"], {"type": "webrtc", "sdp": "v=0\r\na=answer\r\n"})
        self.assertEqual(live["playback_directive"], "suppress_until_session_started")
        status, interrupted = self.request(
            "/api/voice/interrupt",
            {**self.envelope(created, live["snapshot"]), "reason": "creator_interrupt"},
            token=token,
        )
        self.assertEqual(status, 200, interrupted)
        self.assertEqual(interrupted["media_directive"], "suppress_mic_and_playback_then_close")
        self.assertEqual(self.live_provider.hung_up, ["live-opaque"])


class VoiceAuthorityTimingTests(unittest.TestCase):
    def test_success_after_cancel_cannot_disclose_or_cancel_new_work(self):
        for replace_owner in (False, True):
            with self.subTest(replace_owner=replace_owner), tempfile.TemporaryDirectory() as folder:
                director = DirectorService(SessionRepository(Path(folder) / "director.sqlite3"))
                backend = SelectiveBackend()
                executor = PausedResultExecutor(())
                with patch("takeone.voice.service.ThreadPoolExecutor", return_value=executor):
                    service = VoiceService(director, offline_backend=backend)
                self.addCleanup(service.close)
                old = service.create("offline")

                def envelope(owner):
                    state = service.snapshot(owner["ownership_token"])["snapshot"]
                    return (
                        owner["ownership_token"],
                        owner["voice_session_id"],
                        VoiceScope(**state["scope"]),
                        state["generation"],
                        director.clock() + MUTATION_TTL_NS,
                    )

                with ThreadPoolExecutor(max_workers=2) as callers:
                    stale = callers.submit(service.question, *envelope(old), "old", "Delayed help")
                    self.assertTrue(backend.entered.wait(1))
                    if replace_owner:
                        service.disconnect(*envelope(old))
                    else:
                        service.interrupt(*envelope(old), "creator_interrupt")
                    backend.release.set()
                    self.assertTrue(executor.callback_done.wait(1))
                    self.assertTrue(executor.delivery_ready.wait(1))
                    current = service.create("offline") if replace_owner else old
                    backend.release.clear()
                    backend.entered.clear()
                    fresh = callers.submit(service.question, *envelope(current), "new", "Delayed help")
                    self.assertTrue(backend.entered.wait(1))
                    before = service.snapshot(current["ownership_token"])["snapshot"]
                    executor.deliver.set()
                    try:
                        with self.assertRaises(VoiceServiceError) as raised:
                            stale.result(1)
                        self.assertEqual(raised.exception.code, "stale_result")
                        self.assertIsNone(raised.exception.snapshot)
                        after = service.snapshot(current["ownership_token"])["snapshot"]
                        self.assertEqual(after["pending_request_id"], "new")
                        self.assertEqual(after["generation"], before["generation"])
                    finally:
                        backend.release.set()
                    self.assertEqual(fresh.result(1)["code"], "answered")

    def test_rejected_recorder_events_never_extend_authority_or_consume_sequence(self):
        with tempfile.TemporaryDirectory() as folder_name:
            folder = type("Folder", (), {"name": folder_name})()
            clock = Clock()
            _, _, service, created, scope = self.live_owner(folder, FakeLiveProvider(), clock=clock)
            self.addCleanup(service.close)
            token = created["ownership_token"]
            now = clock()
            other = VoiceScope(scope.runtime_epoch, str(uuid4()), 0, 0, None, None)
            for label, event in (
                ("future", RecordingEvent(scope, 10, "idle", "recorder", now + 1, now + 15_000_000_000)),
                ("expired", RecordingEvent(scope, 11, "idle", "recorder", now - 2, now - 1)),
                ("replayed", RecordingEvent(scope, 0, "idle", "recorder", now, now + 15_000_000_000)),
                ("wrong scope", RecordingEvent(other, 12, "idle", "recorder", now, now + 15_000_000_000)),
            ):
                with self.subTest(label=label):
                    observed = service.observe_recorder(event)["snapshot"]
                    self.assertEqual(observed["recording_authority_remaining_ms"], 5000)
            accepted = service.observe_recorder(
                RecordingEvent(scope, 1, "idle", "recorder", now, now + 6_000_000_000)
            )
            self.assertEqual(accepted["snapshot"]["recording_authority_remaining_ms"], 6000)
            clock.value += 6_000_000_000
            expired = service.snapshot(token)["snapshot"]
            self.assertTrue(expired["quiet"])
            self.assertEqual(expired["recording_authority_remaining_ms"], 0)

    @staticmethod
    def live_owner(folder, provider, *, clock=None):
        database = Path(folder.name) / f"{uuid4()}.sqlite3"
        clock = clock or time.monotonic_ns
        director = DirectorService(SessionRepository(database), clock)
        service = VoiceService(
            director,
            live_provider=provider,
            conversation_backend=SelectiveBackend(),
            recorder_ready=True,
            clock=clock,
        )
        brief = ProductionBrief("Live", "Exercise provider ownership.", 12000, "9:16")
        session = Session.parse(
            director.create(str(uuid4()), director.epoch, director.clock() + COMMAND_TTL_NS, brief)["session"]
        )
        created = service.create("live", session.session_id)
        scope = VoiceScope(**created["snapshot"]["scope"])
        now = director.clock()
        service.observe_recorder(RecordingEvent(scope, 0, "idle", "recorder", now, now + 5_000_000_000))
        return database, director, service, created, scope

    def test_replayed_fixture_sequence_cannot_renew_browser_authority(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        clock = Clock()
        director = DirectorService(SessionRepository(Path(folder.name) / "director.sqlite3"), clock)
        service = VoiceService(director, clock=clock)
        self.addCleanup(service.close)
        created = service.create("offline")
        token = created["ownership_token"]
        scope = VoiceScope(**created["snapshot"]["scope"])
        clock.value += 4_000_000_000
        expiry = clock() + MUTATION_TTL_NS
        replayed = service.fixture_recording(
            token,
            created["voice_session_id"],
            scope,
            created["snapshot"]["generation"],
            expiry,
            scope,
            0,
            "idle",
        )

        self.assertEqual(replayed["snapshot"]["recording_authority_remaining_ms"], 1000)

    def test_expired_recording_latch_blocks_owner_replacement_until_exact_stop(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        clock = Clock()
        director = DirectorService(SessionRepository(Path(folder.name) / "director.sqlite3"), clock)
        service = VoiceService(director, clock=clock)
        self.addCleanup(service.close)
        created = service.create("offline")
        token = created["ownership_token"]
        scope = VoiceScope(**created["snapshot"]["scope"])
        latched = service.fixture_recording(
            token,
            created["voice_session_id"],
            scope,
            created["snapshot"]["generation"],
            clock() + MUTATION_TTL_NS,
            scope,
            1,
            "recording",
        )
        clock.value += 5_000_000_000

        disconnected = service.disconnect(
            token,
            created["voice_session_id"],
            scope,
            latched["snapshot"]["generation"],
            clock() + MUTATION_TTL_NS,
        )

        self.assertTrue(disconnected["snapshot"]["recording_latch_active"])
        self.assertTrue(disconnected["ownership_retained"])
        with self.assertRaises(VoiceServiceError) as raised:
            service.create("offline")
        self.assertEqual(raised.exception.code, "recording_unresolved")

    def test_cancelled_backend_failure_returns_typed_error_without_touching_later_work(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        director = DirectorService(SessionRepository(Path(folder.name) / "director.sqlite3"))
        backend = FailingAfterCancellationBackend()
        service = VoiceService(director, offline_backend=backend)
        self.addCleanup(service.close)
        created = service.create("offline")
        token = created["ownership_token"]
        scope = VoiceScope(**created["snapshot"]["scope"])
        with ThreadPoolExecutor(max_workers=1) as pool:
            failing = pool.submit(
                service.question,
                token,
                created["voice_session_id"],
                scope,
                created["snapshot"]["generation"],
                director.clock() + MUTATION_TTL_NS,
                str(uuid4()),
                "Fail after cancellation",
            )
            self.assertTrue(backend.entered.wait(1))
            interrupted = service.interrupt(
                token,
                created["voice_session_id"],
                scope,
                created["snapshot"]["generation"],
                director.clock() + MUTATION_TTL_NS,
                "creator_interrupt",
            )
            backend.release.set()
            with self.assertRaises(VoiceServiceError) as raised:
                failing.result(1)
        self.assertEqual(raised.exception.code, "backend_failed")
        self.assertIsNotNone(raised.exception.snapshot)
        recovered = service.question(
            token,
            created["voice_session_id"],
            scope,
            interrupted["snapshot"]["generation"],
            director.clock() + MUTATION_TTL_NS,
            str(uuid4()),
            "Recover",
        )
        self.assertEqual(recovered["response"], "Fixture suggestion: recovered")

    def test_old_backend_failure_omits_replacement_owner_private_snapshot(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        director = DirectorService(SessionRepository(Path(folder.name) / "director.sqlite3"))
        backend = FailingAfterCancellationBackend()
        executor = PausedResultExecutor(RuntimeError)
        with patch("takeone.voice.service.ThreadPoolExecutor", return_value=executor):
            service = VoiceService(director, offline_backend=backend)
        self.addCleanup(service.close)
        old = service.create("offline")
        old_scope = VoiceScope(**old["snapshot"]["scope"])
        with ThreadPoolExecutor(max_workers=1) as pool:
            old_question = pool.submit(
                service.question,
                old["ownership_token"],
                old["voice_session_id"],
                old_scope,
                old["snapshot"]["generation"],
                director.clock() + MUTATION_TTL_NS,
                str(uuid4()),
                "Fail after cancellation",
            )
            self.assertTrue(backend.entered.wait(1))
            service.disconnect(
                old["ownership_token"],
                old["voice_session_id"],
                old_scope,
                old["snapshot"]["generation"],
                director.clock() + MUTATION_TTL_NS,
            )
            backend.release.set()
            self.assertTrue(executor.callback_done.wait(1))
            self.assertTrue(executor.delivery_ready.wait(1))

            replacement = service.create("offline")
            replacement_scope = VoiceScope(**replacement["snapshot"]["scope"])
            answered = service.question(
                replacement["ownership_token"],
                replacement["voice_session_id"],
                replacement_scope,
                replacement["snapshot"]["generation"],
                director.clock() + MUTATION_TTL_NS,
                str(uuid4()),
                "Replacement owner's private question",
            )
            executor.deliver.set()
            with self.assertRaises(VoiceServiceError) as raised:
                old_question.result(1)

        self.assertEqual(raised.exception.code, "backend_failed")
        self.assertIsNone(raised.exception.snapshot)
        current = service.snapshot(replacement["ownership_token"])["snapshot"]
        self.assertEqual(
            [entry["text"] for entry in current["transcript"]],
            ["Replacement owner's private question", "Fixture suggestion: recovered"],
        )
        self.assertEqual(current["generation"], answered["snapshot"]["generation"])

    def test_old_backend_timeout_omits_replacement_owner_private_snapshot(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        director = DirectorService(SessionRepository(Path(folder.name) / "director.sqlite3"))
        backend = BlockingFirstBackend()
        executor = PausedResultExecutor(TimeoutError)
        with patch("takeone.voice.service.ThreadPoolExecutor", return_value=executor):
            service = VoiceService(
                director,
                offline_backend=backend,
                backend_timeout_seconds=0.01,
            )
        self.addCleanup(service.close)
        old = service.create("offline")
        old_scope = VoiceScope(**old["snapshot"]["scope"])
        with ThreadPoolExecutor(max_workers=1) as pool:
            old_question = pool.submit(
                service.question,
                old["ownership_token"],
                old["voice_session_id"],
                old_scope,
                old["snapshot"]["generation"],
                director.clock() + MUTATION_TTL_NS,
                str(uuid4()),
                "Timeout after cancellation",
            )
            self.assertTrue(backend.entered.wait(1))
            self.assertTrue(executor.delivery_ready.wait(1))
            service.disconnect(
                old["ownership_token"],
                old["voice_session_id"],
                old_scope,
                old["snapshot"]["generation"],
                director.clock() + MUTATION_TTL_NS,
            )
            backend.release.set()
            self.assertTrue(executor.callback_done.wait(1))

            replacement = service.create("offline")
            replacement_scope = VoiceScope(**replacement["snapshot"]["scope"])
            answered = service.question(
                replacement["ownership_token"],
                replacement["voice_session_id"],
                replacement_scope,
                replacement["snapshot"]["generation"],
                director.clock() + MUTATION_TTL_NS,
                str(uuid4()),
                "Replacement owner's private question",
            )
            executor.deliver.set()
            with self.assertRaises(VoiceServiceError) as raised:
                old_question.result(1)

        self.assertEqual(raised.exception.code, "backend_timeout")
        self.assertIsNone(raised.exception.snapshot)
        current = service.snapshot(replacement["ownership_token"])["snapshot"]
        self.assertEqual(
            [entry["text"] for entry in current["transcript"]],
            [
                "Replacement owner's private question",
                "Fixture suggestion: replacement answer",
            ],
        )
        self.assertEqual(current["generation"], answered["snapshot"]["generation"])

    def test_live_result_is_hung_up_when_director_runtime_changes_during_https(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        provider = BlockingLiveProvider()
        database, director, service, created, scope = self.live_owner(folder, provider)
        self.addCleanup(service.close)
        snapshot = service.snapshot(created["ownership_token"])["snapshot"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            connecting = pool.submit(
                service.create_live_session,
                created["ownership_token"],
                created["voice_session_id"],
                scope,
                snapshot["generation"],
                director.clock() + MUTATION_TTL_NS,
                "v=0\r\na=offer\r\n",
            )
            self.assertTrue(provider.entered.wait(1))
            DirectorService(SessionRepository(database))
            provider.release.set()
            with self.assertRaises(OwnerReplacedError):
                connecting.result(1)
        self.assertEqual(provider.hung_up, ["late-live"])
        self.assertIsNone(service._live_session_id)
        self.assertEqual(service._live_status, "none")

    def test_runtime_change_with_failed_live_cleanup_retains_provider_identity(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        provider = BlockingFailingHangupProvider()
        database, director, service, created, scope = self.live_owner(folder, provider)
        self.addCleanup(service.close)
        snapshot = service.snapshot(created["ownership_token"])["snapshot"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            connecting = pool.submit(
                service.create_live_session,
                created["ownership_token"],
                created["voice_session_id"],
                scope,
                snapshot["generation"],
                director.clock() + MUTATION_TTL_NS,
                "v=0\r\na=offer\r\n",
            )
            self.assertTrue(provider.entered.wait(1))
            DirectorService(SessionRepository(database))
            provider.release.set()
            with self.assertRaises(OwnerReplacedError):
                connecting.result(1)
        self.assertEqual(provider.hung_up, ["late-live"])
        self.assertEqual(service._live_session_id, "late-live")
        self.assertEqual(service._live_status, "cleanup_unconfirmed")

    def test_live_result_is_hung_up_when_mutation_deadline_expires_during_https(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        clock = Clock()

        class AdvancingProvider(FakeLiveProvider):
            def create_session(self, offer_sdp, cancellation_event):
                clock.value += 2
                return super().create_session(offer_sdp, cancellation_event)

        provider = AdvancingProvider()
        _database, director, service, created, scope = self.live_owner(folder, provider, clock=clock)
        self.addCleanup(service.close)
        snapshot = service.snapshot(created["ownership_token"])["snapshot"]

        with self.assertRaises(VoiceServiceError) as raised:
            service.create_live_session(
                created["ownership_token"],
                created["voice_session_id"],
                scope,
                snapshot["generation"],
                clock() + 1,
                "v=0\r\na=offer\r\n",
            )

        self.assertEqual(raised.exception.code, "expired")
        self.assertEqual(provider.hung_up, ["live-opaque"])
        self.assertEqual(raised.exception.snapshot["live_transport_state"], "none")

    def test_unknown_live_creation_remains_unconfirmed_on_disconnect_and_interrupt(self):
        for operation in ("disconnect", "interrupt"):
            with self.subTest(operation=operation):
                folder = tempfile.TemporaryDirectory()
                self.addCleanup(folder.cleanup)
                provider = UncertainLiveProvider()
                _database, director, service, created, scope = self.live_owner(folder, provider)
                self.addCleanup(service.close)
                snapshot = service.snapshot(created["ownership_token"])["snapshot"]
                with self.assertRaises(VoiceServiceError) as raised:
                    service.create_live_session(
                        created["ownership_token"],
                        created["voice_session_id"],
                        scope,
                        snapshot["generation"],
                        director.clock() + MUTATION_TTL_NS,
                        "v=0\r\na=offer\r\n",
                    )
                self.assertEqual(raised.exception.code, "creation_uncertain")
                arguments = [
                    created["ownership_token"],
                    created["voice_session_id"],
                    scope,
                    raised.exception.snapshot["generation"],
                    director.clock() + MUTATION_TTL_NS,
                ]
                if operation == "interrupt":
                    arguments.append("creator_interrupt")
                result = getattr(service, operation)(*arguments)
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], "cleanup_unconfirmed")
                self.assertFalse(result["cleanup_confirmed"])
                self.assertEqual(result["snapshot"]["live_transport_state"], "creation_uncertain")
                if operation == "disconnect":
                    self.assertTrue(result["ownership_retained"])

    @patch("takeone.cli.subprocess.call")
    def test_simulator_cli_omits_unselected_paid_duration(self, call):
        call.return_value = 0

        self.assertEqual(cli.main(["simulator", "--voice-live-enabled"]), 0)

        command = call.call_args.args[0]
        self.assertIn("--voice-live-enabled", command)
        self.assertNotIn("--voice-live-max-duration-seconds", command)

    def test_server_duration_expires_and_hangs_up_live_session_without_browser_timer(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        director = DirectorService(SessionRepository(Path(folder.name) / "director.sqlite3"))
        provider = FakeLiveProvider(duration_seconds=0.05)
        service = VoiceService(
            director, live_provider=provider, conversation_backend=SelectiveBackend(), recorder_ready=True
        )
        self.addCleanup(service.close)
        brief = ProductionBrief("Expiry", "Test server-owned expiry.", 12000, "9:16")
        session = Session.parse(
            director.create(str(uuid4()), director.epoch, director.clock() + COMMAND_TTL_NS, brief)["session"]
        )
        created = service.create("live", session.session_id)
        token = created["ownership_token"]
        scope = VoiceScope(**created["snapshot"]["scope"])
        now = director.clock()
        service.observe_recorder(RecordingEvent(scope, 0, "idle", "recorder", now, now + 5_000_000_000))
        snapshot = service.snapshot(token)["snapshot"]
        service.create_live_session(
            token,
            created["voice_session_id"],
            scope,
            snapshot["generation"],
            director.clock() + MUTATION_TTL_NS,
            "v=0\r\na=offer\r\n",
        )

        self.assertTrue(provider.hangup_event.wait(1))
        expired = service.snapshot(token)["snapshot"]
        self.assertEqual(provider.hung_up, ["live-opaque"])
        self.assertEqual(expired["live_transport_state"], "expired")
        self.assertEqual(expired["media_directive"], "suppress_mic_and_playback")

    def test_recorder_event_alone_does_not_claim_capture_safe_integration(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        director = DirectorService(SessionRepository(Path(folder.name) / "director.sqlite3"))
        service = VoiceService(director, live_provider=FakeLiveProvider())
        self.addCleanup(service.close)
        brief = ProductionBrief("Recorder", "Keep integration status honest.", 12000, "9:16")
        session = Session.parse(
            director.create(str(uuid4()), director.epoch, director.clock() + COMMAND_TTL_NS, brief)["session"]
        )
        created = service.create("live", session.session_id)
        scope = VoiceScope(**created["snapshot"]["scope"])
        now = director.clock()
        service.observe_recorder(RecordingEvent(scope, 0, "idle", "recorder", now, now + 5_000_000_000))
        snapshot = service.snapshot(created["ownership_token"])["snapshot"]

        self.assertFalse(service.runtime()["recorder"]["ready"])
        with self.assertRaises(VoiceServiceError) as raised:
            service.create_live_session(
                created["ownership_token"],
                created["voice_session_id"],
                scope,
                snapshot["generation"],
                director.clock() + MUTATION_TTL_NS,
                "v=0\r\na=offer\r\n",
            )
        self.assertEqual(raised.exception.code, "recorder_unavailable")

    def test_failed_hangup_blocks_a_second_paid_session_until_trusted_reconciliation(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        director = DirectorService(SessionRepository(Path(folder.name) / "director.sqlite3"))
        provider = FailingHangupProvider()
        service = VoiceService(
            director, live_provider=provider, conversation_backend=SelectiveBackend(), recorder_ready=True
        )
        self.addCleanup(service.close)
        brief = ProductionBrief("Cleanup", "Test uncertain paid ownership.", 12000, "9:16")
        session = Session.parse(
            director.create(str(uuid4()), director.epoch, director.clock() + COMMAND_TTL_NS, brief)["session"]
        )
        created = service.create("live", session.session_id)
        token = created["ownership_token"]
        scope = VoiceScope(**created["snapshot"]["scope"])
        now = director.clock()
        service.observe_recorder(RecordingEvent(scope, 0, "idle", "recorder", now, now + 5_000_000_000))
        snapshot = service.snapshot(token)["snapshot"]
        connected = service.create_live_session(
            token,
            created["voice_session_id"],
            scope,
            snapshot["generation"],
            director.clock() + MUTATION_TTL_NS,
            "v=0\r\na=offer\r\n",
        )
        interrupted = service.interrupt(
            token,
            created["voice_session_id"],
            scope,
            connected["snapshot"]["generation"],
            director.clock() + MUTATION_TTL_NS,
            "creator_interrupt",
        )
        self.assertFalse(interrupted["ok"])
        self.assertFalse(interrupted["cleanup_confirmed"])

        with self.assertRaises(VoiceServiceError) as raised:
            service.create_live_session(
                token,
                created["voice_session_id"],
                scope,
                interrupted["snapshot"]["generation"],
                director.clock() + MUTATION_TTL_NS,
                "v=0\r\na=second-offer\r\n",
            )

        self.assertEqual(raised.exception.code, "cleanup_unconfirmed")
        self.assertEqual(len(provider.created), 1)
        service.reconcile_live_cleanup("live-opaque")

    def test_disconnect_during_live_creation_reports_pending_and_closes_late_success(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        director = DirectorService(SessionRepository(Path(folder.name) / "director.sqlite3"))
        provider = BlockingLiveProvider()
        service = VoiceService(
            director, live_provider=provider, conversation_backend=SelectiveBackend(), recorder_ready=True
        )
        self.addCleanup(service.close)
        brief = ProductionBrief("Late", "Cancel an in-flight provider setup.", 12000, "9:16")
        session = Session.parse(
            director.create(str(uuid4()), director.epoch, director.clock() + COMMAND_TTL_NS, brief)["session"]
        )
        created = service.create("live", session.session_id)
        token = created["ownership_token"]
        scope = VoiceScope(**created["snapshot"]["scope"])
        now = director.clock()
        service.observe_recorder(RecordingEvent(scope, 0, "idle", "recorder", now, now + 5_000_000_000))
        snapshot = service.snapshot(token)["snapshot"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            connecting = pool.submit(
                service.create_live_session,
                token,
                created["voice_session_id"],
                scope,
                snapshot["generation"],
                director.clock() + MUTATION_TTL_NS,
                "v=0\r\na=offer\r\n",
            )
            self.assertTrue(provider.entered.wait(1))
            disconnected = service.disconnect(
                token,
                created["voice_session_id"],
                scope,
                snapshot["generation"],
                director.clock() + MUTATION_TTL_NS,
            )
            self.assertFalse(disconnected["ok"])
            self.assertEqual(disconnected["code"], "cleanup_pending")
            self.assertFalse(disconnected["cleanup_confirmed"])
            provider.release.set()
            with self.assertRaises(VoiceServiceError) as raised:
                connecting.result(1)
        self.assertEqual(raised.exception.code, "stale_result")
        self.assertEqual(provider.hung_up, ["late-live"])


if __name__ == "__main__":
    unittest.main()
