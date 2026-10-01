"""Owned in-memory voice sessions over read-only Director context."""

import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from copy import deepcopy
from dataclasses import dataclass
from uuid import uuid4

from takeone.director.service import COMMAND_TTL_NS

from .contracts import MAX_INTEGER, RecordingEvent, VoiceScope
from .provider import LiveProvider, LiveProviderError
from .state import MAX_FRAGMENT_BYTES, VoiceState

MUTATION_TTL_NS = COMMAND_TTL_NS
FIXTURE_EVIDENCE_TTL_NS = 5_000_000_000
FIXTURE_POLL_INTERVAL_MS = 2_000
MAX_QUESTION_BYTES = 4_096
MAX_FIXTURE_DELAY_MS = 5_000
DEFAULT_BACKEND_TIMEOUT_SECONDS = 6.0


class VoiceServiceError(RuntimeError):
    def __init__(self, status, code, message, *, snapshot=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.snapshot = snapshot


class FixtureBackend:
    """A visible local suggestion, never an AI or production-state mutation."""

    def answer(self, context, question, cancellation_event):
        if cancellation_event.is_set():
            return None
        if context["script"]["available"]:
            return "Fixture suggestion: Use a short pause, then deliver the selected line naturally."
        return "Fixture suggestion: Draft one short line, then try it again with a deliberate pause."


@dataclass(slots=True)
class _PendingQuestion:
    request_id: str
    generation: int
    cancellation: threading.Event
    future: object | None = None
    accepting: bool = True


class VoiceService:
    def __init__(
        self,
        director,
        *,
        offline_backend=None,
        conversation_backend=None,
        live_provider=None,
        backend_timeout_seconds=DEFAULT_BACKEND_TIMEOUT_SECONDS,
        recorder_ready=False,
        clock=time.monotonic_ns,
    ):
        if (
            isinstance(backend_timeout_seconds, bool)
            or not isinstance(backend_timeout_seconds, (int, float))
            or not 0 < backend_timeout_seconds <= 60
        ):
            raise ValueError("Backend timeout must be finite and positive")
        if type(recorder_ready) is not bool:
            raise ValueError("Recorder readiness must be explicitly true or false")
        self.director = director
        self.repository = director.repository
        self.offline_backend = offline_backend if offline_backend is not None else FixtureBackend()
        self.conversation_backend = conversation_backend
        self.live_provider = (
            live_provider
            if live_provider is not None
            else LiveProvider(
                {
                    "schema_version": 1,
                    "enabled": False,
                    "model": "gpt-live-1",
                    "timeout_seconds": 10,
                    "max_session_duration_seconds": None,
                }
            )
        )
        self.backend_timeout_seconds = float(backend_timeout_seconds)
        self.clock = clock
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="takeone-voice")
        self._voice_session_id = None
        self._token = None
        self._state = None
        self._context = None
        self._director_session_id = None
        self._connected = False
        self._pending = None
        self._snapshot_sequence = 0
        self._recorder_ready = recorder_ready
        self._recorder_seen = False
        self._live_status = "none"
        self._live_session_id = None
        self._live_cancel = None
        self._live_timer = None
        self._fixture_capture = None
        self._fixture_sequence = 0
        self._fixture_recovery_id = None

    def _verify_director_owner(self):
        with self.repository.connect() as connection:
            connection.execute("BEGIN")
            self.director._owner(connection)

    def _read_director(self, session_id):
        with self.repository.connect() as connection:
            connection.execute("BEGIN")
            self.director._owner(connection)
            session = self.repository.get(connection, session_id)
            creative = self.repository.creative(connection, session)
        scope = VoiceScope(
            self.director.epoch,
            session.session_id,
            session.revision,
            session.cancellation_generation,
            session.shot.plan_id if session.shot else None,
            session.take_id,
        )
        approved = bool(creative and creative["approved"])
        script = {
            "available": approved,
            "reason": "accepted" if approved else "not_approved" if creative else "unavailable",
            "document": creative["document"] if approved else None,
            "digest": creative["digest"] if approved else None,
            "provenance": creative["provenance"] if creative else None,
            "timing_source": creative["timing_source"] if creative else None,
        }
        return scope, {
            "source": "director_read_only",
            "director_session_id": session.session_id,
            "brief": session.brief.__dict__
            if hasattr(session.brief, "__dict__")
            else {
                "title": session.brief.title,
                "objective": session.brief.objective,
                "duration_ms": session.brief.duration_ms,
                "aspect_ratio": session.brief.aspect_ratio,
            },
            "script": script,
        }

    def _fixture_context(self, session_id):
        return {
            "source": "fixture",
            "director_session_id": session_id,
            "brief": {
                "title": "Offline voice rehearsal",
                "objective": "Exercise conversational coaching without production changes.",
                "duration_ms": 12000,
                "aspect_ratio": "9:16",
            },
            "script": {
                "available": True,
                "reason": "fixture",
                "document": {
                    "label": "Offline fixture script",
                    "lines": ["Introduce the product in one clear sentence."],
                },
                "digest": None,
                "provenance": {"source": "fixture"},
                "timing_source": "fixture",
            },
        }

    def runtime(self):
        self._verify_director_owner()
        provider = self.live_provider.status()
        with self._lock:
            return {
                "schema_version": 1,
                "ok": True,
                "mode": "voice_conversation",
                "now_monotonic_ns": str(self.clock()),
                "clock_domain": "server_monotonic",
                "mutation_ttl_ns": str(MUTATION_TTL_NS),
                "offline_available": True,
                "live_transport": provider,
                "conversation_backend": {
                    "offline_source": "fixture",
                    "live_available": self.conversation_backend is not None,
                },
                "recorder": {
                    "ready": self._recorder_ready,
                    "source": "configured_integration" if self._recorder_ready else None,
                    "observation_seen": self._recorder_seen,
                },
                "fixture": {
                    "recording_evidence_ttl_ms": FIXTURE_EVIDENCE_TTL_NS // 1_000_000,
                    "poll_interval_ms": FIXTURE_POLL_INTERVAL_MS,
                    "max_delay_ms": MAX_FIXTURE_DELAY_MS,
                },
                "active_owner": self._voice_session_id is not None,
                "live_cleanup_state": self._live_status,
            }

    def _raw_state_snapshot_locked(self):
        return self._state.snapshot() if self._state is not None else None

    def _snapshot_locked(self):
        self._snapshot_sequence += 1
        now = self.clock()
        state = self._raw_state_snapshot_locked()
        return {
            **state,
            "snapshot_sequence": self._snapshot_sequence,
            "generated_monotonic_ns": str(now),
            "clock_domain": "server_monotonic",
            "recording_authority_remaining_ms": self._state.recording_authority_remaining_ms(),
            "connected": self._connected,
            "live_transport_state": self._live_status,
            "media_directive": "suppress_mic_and_playback"
            if not self._connected
            or state["quiet"]
            or (state["mode"] == "live" and self._live_status != "active")
            else "playback_permitted",
        }

    def _response_locked(self, code, *, source=None, **extra):
        result = {
            "schema_version": 1,
            "ok": True,
            "code": code,
            "voice_session_id": self._voice_session_id,
            "mode": self._state.snapshot()["mode"],
            "context": self._context,
            "snapshot": self._snapshot_locked(),
            **extra,
        }
        if source is not None:
            result["source"] = source
        return result

    def _raise_locked(self, status, code, message, *, include_snapshot=True):
        snapshot = self._snapshot_locked() if include_snapshot and self._state is not None else None
        raise VoiceServiceError(status, code, message, snapshot=snapshot)

    @staticmethod
    def _has_recording_latch(snapshot):
        return snapshot["recording_latch_active"]

    @staticmethod
    def _history_exhausted(snapshot):
        reason = snapshot["quiet_reason"]
        return bool(
            reason
            and reason.startswith(
                ("request_history_exhausted", "scope_history_exhausted", "generation_exhausted")
            )
        )

    def create(self, mode, director_session_id=None):
        if mode not in ("offline", "live"):
            raise ValueError("Voice mode must be offline or live")
        if director_session_id is None:
            self._verify_director_owner()
            if mode == "live":
                raise VoiceServiceError(
                    400, "director_context_required", "Live mode requires a current Director session."
                )
            scope = VoiceScope(self.director.epoch, str(uuid4()), 0, 0, None, None)
            context = self._fixture_context(None)
        else:
            scope, context = self._read_director(director_session_id)
            if mode == "offline":
                context = {**context, "source": "fixture_over_director_read_only"}
        if mode == "live" and not self.live_provider.status()["available"]:
            raise VoiceServiceError(503, "live_unavailable", "Live transport is not configured.")

        with self._lock:
            if self._voice_session_id is not None:
                old = self._raw_state_snapshot_locked()
                if self._connected:
                    self._raise_locked(
                        409,
                        "owner_active",
                        "Another tab owns the active voice session.",
                        include_snapshot=False,
                    )
                if self._live_status not in ("none", "expired"):
                    self._raise_locked(
                        409,
                        "cleanup_unconfirmed",
                        "Live cleanup must be reconciled before creating another voice session.",
                        include_snapshot=False,
                    )
                if self._pending is not None:
                    self._raise_locked(
                        409,
                        "operation_pending",
                        "Previous backend work has not exited.",
                        include_snapshot=False,
                    )
                if self._has_recording_latch(old):
                    self._raise_locked(
                        409,
                        "recording_unresolved",
                        "The prior recording lifecycle must be reconciled by its owner.",
                        include_snapshot=False,
                    )
            self._voice_session_id = str(uuid4())
            self._token = secrets.token_urlsafe(32)
            self._state = VoiceState(scope, mode=mode, clock=self.clock)
            self._context = context
            self._director_session_id = director_session_id
            self._connected = True
            self._pending = None
            self._snapshot_sequence = 0
            self._fixture_capture = None
            self._fixture_sequence = 0
            if mode == "offline":
                now = self.clock()
                expires = now + FIXTURE_EVIDENCE_TTL_NS
                self._state.observe_recording(RecordingEvent(scope, 0, "idle", "fixture", now, expires))
                if self._fixture_recovery_id is not None:
                    self._fixture_event_locked(scope, "unknown")
                    self._fixture_capture = (self._voice_session_id, self._fixture_recovery_id, scope)
            response = self._response_locked("created", source="fixture" if mode == "offline" else "live")
            response["ownership_token"] = self._token
            return response

    def _owner_locked(self, token):
        if token is None:
            self._raise_locked(
                401, "ownership_required", "Voice ownership token is required.", include_snapshot=False
            )
        if not secrets.compare_digest(token, self._token or ""):
            self._raise_locked(
                403, "wrong_owner", "This tab does not own the voice session.", include_snapshot=False
            )

    def _detach_live_locked(self):
        if self._live_cancel is not None:
            self._live_cancel.set()
        if self._live_timer is not None:
            self._live_timer.cancel()
            self._live_timer = None
        session_id = self._live_session_id
        if session_id is not None and self._live_status not in ("closing", "expired_closing"):
            self._live_status = "closing"
            return session_id
        return None

    def _finish_live_close(self, session_id, *, final_status="none", creation_owner=None):
        if session_id is None:
            return True

        def current():
            return self._live_session_id == session_id and (
                creation_owner is None or self._owns_live_creation_locked(*creation_owner)
            )

        with self._lock:
            if not current():
                return True
        try:
            self.live_provider.hangup(session_id)
        except LiveProviderError:
            with self._lock:
                if current():
                    self._live_status = "cleanup_unconfirmed"
            return False
        with self._lock:
            if current():
                self._live_session_id = None
                self._live_status = final_status
        return True

    def _cleanup_outcome_locked(self, provider_cleanup_succeeded):
        if self._live_status in ("creating", "closing", "expired_closing"):
            return "pending", False
        if self._live_status in ("creation_uncertain", "cleanup_unconfirmed"):
            return "unconfirmed", False
        return "confirmed", provider_cleanup_succeeded

    def _cancel_pending_locked(self, reason):
        pending = self._pending
        if pending is not None:
            pending.accepting = False
            pending.cancellation.set()
        self._state.interrupt(reason)
        if pending is not None and pending.future.done():
            self._pending_done(pending)

    def _refresh_binding(self, expected_voice_session_id=None):
        with self._lock:
            if self._state is None:
                return
            if expected_voice_session_id is not None and expected_voice_session_id != self._voice_session_id:
                return
            voice_session_id = self._voice_session_id
            director_session_id = self._director_session_id
        if director_session_id is None:
            self._verify_director_owner()
            return
        scope, context = self._read_director(director_session_id)
        close_id = None
        with self._lock:
            if voice_session_id != self._voice_session_id:
                return
            current = self._state.snapshot()
            if scope != VoiceScope(**current["scope"]) and not self._history_exhausted(current):
                self._cancel_pending_locked("director_scope_changed")
                current = self._state.snapshot()
                if not self._history_exhausted(current):
                    self._state.set_scope(scope)
                    self._context = context
                close_id = self._detach_live_locked()
        self._finish_live_close(close_id)
        with self._lock:
            if voice_session_id != self._voice_session_id:
                return
            quiet_close_id = (
                self._detach_live_locked()
                if self._state.snapshot()["quiet"] and self._live_status == "active"
                else None
            )
        self._finish_live_close(quiet_close_id)

    def _validate_locked(self, token, voice_session_id, scope, generation, expiry):
        self._owner_locked(token)
        if voice_session_id != self._voice_session_id:
            self._raise_locked(409, "stale_voice_session", "The voice session changed. Refresh first.")
        now = self.clock()
        if expiry <= now:
            self._raise_locked(409, "expired", "This voice request expired. Refresh and try again.")
        if expiry > now + MUTATION_TTL_NS:
            self._raise_locked(400, "invalid_deadline", "Voice request deadline exceeds the allowed window.")
        current = self._raw_state_snapshot_locked()
        if scope != VoiceScope(**current["scope"]):
            self._raise_locked(409, "stale_scope", "The Director scope changed. Refresh first.")
        if generation != current["generation"]:
            self._raise_locked(409, "stale_generation", "The conversation generation changed. Refresh first.")
        return current

    def snapshot(self, token):
        self._refresh_binding()
        with self._lock:
            self._owner_locked(token)
            return self._response_locked("snapshot")

    def live_authority(self, token, envelope=None):
        """Validate ownership (and optionally the scoped envelope) for browser-direct
        live-transport routes: token minting and tool dispatch.

        Unlike the recorder path this accepts either voice mode — the live socket
        is a conversation transport, while the session mode continues to govern
        recorder evidence rules.
        """
        self._refresh_binding()
        with self._lock:
            self._owner_locked(token)
            if envelope is not None:
                self._validate_locked(token, *envelope)
            result = deepcopy(self._response_locked("live_authorized"))
            result["director_session_id"] = self._director_session_id
            return result

    def recording_authority(self, token, envelope=None, *, capture_id=None, renew_idle=False):
        """Validate offline ownership and optionally reserve its fixture gate atomically.

        No recorder work runs under this lock. The returned context contains no
        ownership token or transcript and may be persisted by the offline recorder.
        """
        self._refresh_binding()
        with self._lock:
            self._owner_locked(token)
            current = (
                self._validate_locked(token, *envelope)
                if envelope is not None
                else self._raw_state_snapshot_locked()
            )
            if current["mode"] != "offline":
                self._raise_locked(409, "offline_required", "Recording rehearsal requires an offline owner.")
            if capture_id is not None:
                if self._fixture_capture is not None:
                    if self._fixture_capture[1] != capture_id:
                        self._raise_locked(409, "recording_unresolved", "A capture owns the fixture gate.")
                else:
                    if current["recording_latch_active"]:
                        self._raise_locked(409, "recording_unresolved", "Reconcile the prior fixture first.")
                    if not self._connected:
                        self._raise_locked(409, "disconnected", "Create a connected offline session first.")
                    scope = VoiceScope(**current["scope"])
                    self._fixture_event_locked(scope, "requested")
                    self._fixture_capture = (self._voice_session_id, capture_id, scope)
                    self._cancel_pending_locked("recording_requested")
            elif renew_idle and self._fixture_capture is None and not current["recording_latch_active"]:
                self._fixture_event_locked(VoiceScope(**current["scope"]), "idle")
            return deepcopy(self._response_locked("recording_authorized", source="fixture"))

    def require_fixture_recovery(self, capture_id):
        """Carry persisted simulator uncertainty into explicit offline creation.

        Called by the local recorder integration at startup, never as physical
        recorder evidence. No token, database operation or device is involved.
        """
        if not isinstance(capture_id, str) or not capture_id or len(capture_id) > 240:
            raise ValueError("Fixture recovery identity must be a bounded label")
        with self._lock:
            self._fixture_recovery_id = capture_id
            if self._state is not None and self._state.snapshot()["mode"] == "offline":
                scope = VoiceScope(**self._state.snapshot()["scope"])
                self._fixture_event_locked(scope, "unknown")
                self._fixture_capture = (self._voice_session_id, capture_id, scope)
                self._cancel_pending_locked("recording_recovery_required")

    def _fixture_event_locked(self, scope, state):
        if self._fixture_sequence >= MAX_INTEGER:
            self._raise_locked(409, "fixture_history_exhausted", "Create a fresh offline voice session.")
        self._fixture_sequence += 1
        now = self.clock()
        self._state.observe_recording(
            RecordingEvent(
                scope, self._fixture_sequence, state, "fixture", now, now + FIXTURE_EVIDENCE_TTL_NS
            )
        )

    def finish_fixture_capture(self, voice_session_id, capture_id):
        """Release only the originating fixture latch on confirmed simulator cleanup."""
        with self._lock:
            capture = self._fixture_capture
            if capture is None or capture[:2] != (voice_session_id, capture_id):
                return False
            if voice_session_id != self._voice_session_id:
                return False
            self._fixture_event_locked(capture[2], "stopped")
            self._fixture_capture = None
            if self._fixture_recovery_id == capture_id:
                self._fixture_recovery_id = None
            return True

    def _pending_done(self, pending):
        with self._lock:
            if self._pending is pending and not pending.accepting:
                self._pending = None

    def _request_snapshot_locked(self, token, voice_session_id):
        if (
            voice_session_id != self._voice_session_id
            or not isinstance(token, str)
            or not isinstance(self._token, str)
            or not secrets.compare_digest(token, self._token)
        ):
            return None
        return self._snapshot_locked()

    def question(
        self,
        token,
        voice_session_id,
        scope,
        generation,
        expiry,
        request_id,
        question,
        fixture_delay_ms=None,
    ):
        self._refresh_binding()
        begin_failure = None
        close_id = None
        with self._lock:
            current = self._validate_locked(token, voice_session_id, scope, generation, expiry)
            if not self._connected:
                self._raise_locked(409, "disconnected", "Reconnect with a fresh voice session.")
            mode = current["mode"]
            if mode == "live" and fixture_delay_ms is not None:
                self._raise_locked(400, "fixture_delay_not_allowed", "Fixture delay is offline-only.")
            if current["quiet"]:
                code = (
                    "fresh_session_required"
                    if current["quiet_reason"]
                    in ("request_history_exhausted", "scope_history_exhausted", "generation_exhausted")
                    else "recording_quiet"
                )
                self._raise_locked(
                    409,
                    code,
                    "Conversation is quiet until recording state is freshly reconciled.",
                )
            backend = self.offline_backend if mode == "offline" else self.conversation_backend
            if backend is None:
                self._raise_locked(
                    503,
                    "backend_unavailable",
                    "The conversation backend is not integrated. No substitute planner was run.",
                )
            if self._pending is not None:
                self._raise_locked(409, "operation_pending", "One conversation request is already active.")
            try:
                request_generation = self._state.begin(request_id)
            except RuntimeError:
                latest = self._raw_state_snapshot_locked()
                code = (
                    "fresh_session_required"
                    if latest["quiet_reason"]
                    in ("request_history_exhausted", "scope_history_exhausted", "generation_exhausted")
                    else "recording_quiet"
                )
                close_id = self._detach_live_locked()
                begin_failure = VoiceServiceError(
                    409,
                    code,
                    "Conversation state changed before this request could begin.",
                    snapshot=self._snapshot_locked(),
                )
            if begin_failure is None:
                self._state.append_transcript("creator", question, 0, 0)
                pending = _PendingQuestion(request_id, request_generation, threading.Event())

                def work():
                    if fixture_delay_ms and pending.cancellation.wait(fixture_delay_ms / 1000):
                        return None
                    if pending.cancellation.is_set():
                        return None
                    return backend.answer(self._context, question, pending.cancellation)

                pending.future = self._executor.submit(work)
                pending.future.add_done_callback(lambda _future: self._pending_done(pending))
                self._pending = pending
        if begin_failure is not None:
            self._finish_live_close(close_id)
            raise begin_failure
        timeout = min(self.backend_timeout_seconds, max(0.001, (expiry - self.clock()) / 1_000_000_000))
        try:
            response = pending.future.result(timeout=timeout)
        except FutureTimeout:
            with self._lock:
                if self._pending is pending:
                    self._cancel_pending_locked("backend_timeout")
                snapshot = self._request_snapshot_locked(token, voice_session_id)
            raise VoiceServiceError(
                504,
                "backend_timeout",
                "Conversation work timed out. No retry was made.",
                snapshot=snapshot,
            ) from None
        except Exception:
            with self._lock:
                if self._pending is pending:
                    self._pending = None
                    pending.accepting = False
                    self._state.interrupt("backend_failed")
                snapshot = self._request_snapshot_locked(token, voice_session_id)
            raise VoiceServiceError(
                503,
                "backend_failed",
                "The conversation backend failed without applying a result.",
                snapshot=snapshot,
            ) from None

        with self._lock:
            self._require_pending_locked(token, voice_session_id, pending)
        self._refresh_binding(expected_voice_session_id=voice_session_id)
        with self._lock:
            self._require_pending_locked(token, voice_session_id, pending)
            self._pending = None
            valid_response = (
                isinstance(response, str)
                and bool(response)
                and len(response.encode("utf-8")) <= MAX_FRAGMENT_BYTES
            )
            if pending.accepting and not valid_response:
                pending.accepting = False
                self._state.interrupt("backend_invalid")
                self._raise_locked(
                    503,
                    "backend_invalid",
                    "The conversation backend returned invalid bounded text.",
                )
            accepted = (
                pending.accepting
                and self.clock() < expiry
                and self._state.complete(
                    request_id,
                    request_generation,
                    response,
                    source="fixture" if mode == "offline" else "live",
                )
            )
            pending.accepting = False
            if not accepted:
                self._state.interrupt("stale_result")
                self._raise_locked(409, "stale_result", "The late conversation result was discarded.")
            return self._response_locked(
                "answered",
                source="fixture" if mode == "offline" else "live",
                response=response,
            )

    def _require_pending_locked(self, token, voice_session_id, pending):
        if (
            self._pending is not pending
            or voice_session_id != self._voice_session_id
            or not secrets.compare_digest(token, self._token or "")
        ):
            raise VoiceServiceError(409, "stale_result", "The late conversation result was discarded.")

    def _require_return_owner_locked(self, token, voice_session_id):
        if voice_session_id != self._voice_session_id or not secrets.compare_digest(token, self._token or ""):
            raise VoiceServiceError(409, "stale_result", "The voice operation owner changed.")

    def interrupt(self, token, voice_session_id, scope, generation, expiry, reason):
        self._refresh_binding()
        with self._lock:
            self._validate_locked(token, voice_session_id, scope, generation, expiry)
            self._cancel_pending_locked(reason)
            close_id = self._detach_live_locked()
        cleanup = self._finish_live_close(close_id)
        with self._lock:
            self._require_return_owner_locked(token, voice_session_id)
            cleanup_state, cleanup_confirmed = self._cleanup_outcome_locked(cleanup)
            return self._response_locked(
                "cleanup_pending"
                if cleanup_state == "pending"
                else "interrupted"
                if cleanup_confirmed
                else "cleanup_unconfirmed",
                ok=cleanup_confirmed,
                media_directive="suppress_mic_and_playback_then_close",
                cleanup_confirmed=cleanup_confirmed,
            )

    def fixture_recording(
        self,
        token,
        voice_session_id,
        scope,
        generation,
        expiry,
        event_scope,
        sequence,
        state,
    ):
        self._refresh_binding()
        now = self.clock()
        event_expiry = now + FIXTURE_EVIDENCE_TTL_NS
        event = RecordingEvent(event_scope, sequence, state, "fixture", now, event_expiry)
        with self._lock:
            current = self._validate_locked(token, voice_session_id, scope, generation, expiry)
            if current["mode"] != "offline":
                self._raise_locked(409, "fixture_not_allowed", "Fixture recording events are offline-only.")
            if self._fixture_capture is not None:
                self._raise_locked(409, "capture_owns_gate", "Use recording stop or recovery for this take.")
            self._fixture_sequence = max(self._fixture_sequence, sequence)
            if state not in ("idle", "stopped"):
                self._cancel_pending_locked("recording_observation")
            self._state.observe_recording(event)
            close_id = self._detach_live_locked()
        self._finish_live_close(close_id)
        with self._lock:
            self._require_return_owner_locked(token, voice_session_id)
            return self._response_locked("recording_observed", source="fixture")

    def observe_recorder(self, event):
        if not isinstance(event, RecordingEvent) or event.source != "recorder":
            raise ValueError("Trusted recorder hook requires recorder evidence")
        self._refresh_binding()
        with self._lock:
            if self._state is None:
                raise RuntimeError("No voice owner is available for recorder evidence")
            token, voice_session_id = self._token, self._voice_session_id
            self._fixture_sequence = max(self._fixture_sequence, event.sequence)
            if event.state not in ("idle", "stopped"):
                self._cancel_pending_locked("recording_observation")
            self._state.observe_recording(event)
            after = self._raw_state_snapshot_locked()
            self._recorder_seen = True
            close_id = (
                self._detach_live_locked()
                if event.state not in ("idle", "stopped") or after["quiet"]
                else None
            )
        self._finish_live_close(close_id)
        with self._lock:
            self._require_return_owner_locked(token, voice_session_id)
            return self._response_locked("recording_observed", source="recorder")

    def _expire_live(self, voice_session_id, provider_session_id):
        with self._lock:
            if (
                self._voice_session_id != voice_session_id
                or self._live_session_id != provider_session_id
                or self._live_status != "active"
            ):
                return
            self._state.interrupt("live_session_expired")
            self._live_status = "expired_closing"
            self._live_timer = None
        self._finish_live_close(provider_session_id, final_status="expired")

    def _owns_live_creation_locked(self, token, voice_session_id, cancellation):
        return (
            voice_session_id == self._voice_session_id
            and secrets.compare_digest(token, self._token or "")
            and self._live_cancel is cancellation
        )

    def _require_live_creation_locked(
        self, token, voice_session_id, cancellation, *, provider_session_id=None
    ):
        if not self._owns_live_creation_locked(token, voice_session_id, cancellation) or (
            provider_session_id is not None and provider_session_id != self._live_session_id
        ):
            raise VoiceServiceError(409, "stale_result", "The Live creation owner changed.")

    def create_live_session(self, token, voice_session_id, scope, generation, expiry, offer_sdp):
        self._refresh_binding()
        with self._lock:
            current = self._validate_locked(token, voice_session_id, scope, generation, expiry)
            if current["mode"] != "live":
                self._raise_locked(409, "live_mode_required", "WebRTC setup requires live mode.")
            if current["quiet"]:
                self._raise_locked(
                    409,
                    "recorder_unavailable",
                    "Fresh trusted recorder evidence is required before live audio.",
                )
            if not self._recorder_ready:
                self._raise_locked(
                    409,
                    "recorder_unavailable",
                    "The real recorder audio-gate integration is not verified.",
                )
            if self.conversation_backend is None:
                self._raise_locked(503, "backend_unavailable", "The conversation backend is not integrated.")
            if not self.live_provider.status()["available"]:
                self._raise_locked(503, "live_unavailable", "Live transport is not configured.")
            if self._live_status in ("cleanup_unconfirmed", "creation_uncertain"):
                self._raise_locked(
                    409,
                    "cleanup_unconfirmed",
                    "Previous paid-session ownership requires trusted reconciliation.",
                )
            if self._live_status not in ("none", "expired"):
                self._raise_locked(
                    409,
                    "live_session_exists",
                    "A Live session exists or requires cleanup reconciliation.",
                )
            cancellation = threading.Event()
            self._live_cancel = cancellation
            self._live_status = "creating"
        creation_owner = (token, voice_session_id, cancellation)
        try:
            live = self.live_provider.create_session(offer_sdp, cancellation)
        except LiveProviderError as error:
            with self._lock:
                self._require_live_creation_locked(*creation_owner)
                self._live_cancel = None
                if error.creation_uncertain:
                    self._live_status = "creation_uncertain"
                    self._live_session_id = error.provider_session_id
                else:
                    self._live_status = "none"
                snapshot = self._snapshot_locked()
            raise VoiceServiceError(503, error.code, str(error), snapshot=snapshot) from None

        with self._lock:
            self._require_live_creation_locked(*creation_owner)
            self._live_session_id = live.session_id
        attached = False
        try:
            self._refresh_binding(expected_voice_session_id=voice_session_id)
            with self._lock:
                self._require_live_creation_locked(*creation_owner, provider_session_id=live.session_id)
                current = self._raw_state_snapshot_locked()
                if self.clock() >= expiry:
                    rejection = (
                        409,
                        "expired",
                        "The Live session result arrived after the mutation deadline.",
                    )
                elif (
                    cancellation.is_set()
                    or not self._connected
                    or scope != VoiceScope(**current["scope"])
                    or generation != current["generation"]
                    or current["quiet"]
                ):
                    rejection = (
                        409,
                        "stale_result",
                        "The late Live session was not attached to stale voice state.",
                    )
                else:
                    rejection = None

                if rejection is not None:
                    close_id = (
                        None
                        if self._live_status in ("creation_uncertain", "cleanup_unconfirmed")
                        else self._detach_live_locked()
                    )
                else:
                    duration_ms = self.live_provider.status()["max_session_duration_ms"]
                    if duration_ms is None:
                        raise RuntimeError("Live provider became unavailable without a duration")
                    self._live_status = "active"
                    timer = threading.Timer(
                        duration_ms / 1000,
                        self._expire_live,
                        args=(voice_session_id, live.session_id),
                    )
                    timer.daemon = True
                    self._live_timer = timer
                    timer.start()
                    response = self._response_locked(
                        "live_connected",
                        source="live",
                        transport={"type": "webrtc", "sdp": live.answer_sdp},
                        playback_directive="suppress_until_session_started",
                        max_session_duration_ms=duration_ms,
                    )
                    self._live_cancel = None
                    attached = True
                    return response

            cleanup = self._finish_live_close(close_id, creation_owner=creation_owner)
            with self._lock:
                self._require_live_creation_locked(*creation_owner)
                _cleanup_state, cleanup_confirmed = self._cleanup_outcome_locked(cleanup)
                if not cleanup_confirmed:
                    self._raise_locked(
                        503,
                        "cleanup_unconfirmed",
                        "The rejected Live session could not be confirmed closed.",
                    )
                self._raise_locked(*rejection)
        except BaseException:
            if not attached:
                with self._lock:
                    close_id = (
                        self._detach_live_locked()
                        if self._owns_live_creation_locked(*creation_owner)
                        and self._live_session_id == live.session_id
                        and self._live_status not in ("creation_uncertain", "cleanup_unconfirmed")
                        else None
                    )
                self._finish_live_close(close_id, creation_owner=creation_owner)
            raise

    def disconnect(self, token, voice_session_id, scope, generation, expiry):
        self._refresh_binding()
        with self._lock:
            self._validate_locked(token, voice_session_id, scope, generation, expiry)
            self._connected = False
            self._cancel_pending_locked("disconnect")
            close_id = self._detach_live_locked()
        cleanup = self._finish_live_close(close_id)
        with self._lock:
            self._require_return_owner_locked(token, voice_session_id)
            cleanup_state, cleanup_confirmed = self._cleanup_outcome_locked(cleanup)
            return self._response_locked(
                "cleanup_pending"
                if cleanup_state == "pending"
                else "disconnected"
                if cleanup_confirmed
                else "cleanup_unconfirmed",
                ok=cleanup_confirmed,
                media_directive="suppress_mic_and_playback_then_close",
                cleanup_confirmed=cleanup_confirmed,
                ownership_retained=self._has_recording_latch(self._raw_state_snapshot_locked())
                or not cleanup_confirmed,
            )

    def reconcile_live_cleanup(self, provider_session_id=None):
        """Trusted operator hook after external confirmation; never exposed over HTTP."""
        with self._lock:
            if self._live_status not in ("cleanup_unconfirmed", "creation_uncertain"):
                raise RuntimeError("No uncertain Live cleanup is pending")
            if self._live_session_id is not None and provider_session_id != self._live_session_id:
                raise ValueError("Provider session identity does not match")
            self._live_session_id = None
            self._live_status = "none"

    def close(self):
        with self._lock:
            if self._state is not None:
                self._connected = False
                self._cancel_pending_locked("server_shutdown")
            close_id = self._detach_live_locked()
        self._finish_live_close(close_id)
        self._executor.shutdown(wait=False, cancel_futures=True)
