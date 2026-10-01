"""Offline recording ownership and fixture-only voice gate coordination."""

import hashlib
import json
import threading

from takeone.voice.service import VoiceServiceError

from .contracts import RecordingError
from .service import UNRESOLVED_STATES, RecordingService

MAX_OPERATION_HISTORY = 1024


class RecordingVoiceBridge:
    def __init__(self, voice, directory):
        self.voice = voice
        self._mutations = threading.RLock()
        self._accepted = {}
        self._captures = {}
        self._starting_capture = None
        self._starting_take_id = None
        self._closed = False
        self.recording = RecordingService(
            directory / "takes.sqlite3", directory / "media", clock=voice.clock, notify=self.observe
        )
        self._restarted = {
            take["take_id"] for take in self.recording.list_takes() if take["state"] in UNRESOLVED_STATES
        }
        for take_id in self._restarted:
            self.voice.require_fixture_recovery("restart:" + take_id)

    def observe(self, take, state):
        # Serialize callback release with HTTP response assembly. The lock order
        # is bridge then voice; shutdown joins workers after releasing both.
        with self._mutations:
            if state == "requested" and self._starting_capture is not None:
                self._starting_take_id = take["take_id"]
                self._captures[take["take_id"]] = self._starting_capture
            if state in {"stopped", "ready", "failed"} and take["state"] in {"ready", "failed"}:
                confirmed = any(
                    event["kind"] in {"stop_acknowledged", "start_retired", "recovery_retired"}
                    for event in take["events"]
                )
                if confirmed:
                    capture = self._captures.get(take["take_id"])
                    if capture is not None:
                        self.voice.finish_fixture_capture(*capture)

    def _reconcile(self, token):
        owner = self.voice.recording_authority(token)
        takes = self.recording.list_takes()
        for take in takes:
            self.observe(take, take["state"])
            if take["state"] in UNRESOLVED_STATES:
                take_id = take["take_id"]
                capture = self._captures.get(take_id)
                if capture is None and take_id in self._restarted:
                    capture = (owner["voice_session_id"], "restart:" + take_id)
                    self.voice.recording_authority(token, capture_id=capture[1])
                    self._captures[take_id] = capture
                if capture is not None and capture[0] == owner["voice_session_id"]:
                    self.recording.get(take_id)
        return owner

    def read(self, token, take_id=None):
        with self._mutations:
            self._require_open()
            self._reconcile(token)
            takes = self.recording.list_takes()
            take = self.recording.get(take_id) if take_id is not None else None
            # A terminal SQLite transaction can be visible before its worker's
            # callback. Reconcile the exact evidence being returned, then take
            # the voice snapshot without any later recorder read.
            for observed in takes:
                self.observe(observed, observed["state"])
            if take is not None:
                self.observe(take, take["state"])
            active = any(take["state"] in UNRESOLVED_STATES for take in takes)
            owner = self.voice.recording_authority(token, renew_idle=not active)
            if take is not None:
                return {**owner, "code": "take_status", "take": take}
            return {**owner, "code": "takes", "takes": takes}

    def mutate(
        self,
        kind,
        token,
        envelope,
        request_id,
        *,
        zoom=None,
        scenario=None,
        take_id=None,
        plan_id=None,
        source="simulated",
        behavior_context=None,
        shot=None,
    ):
        with self._mutations:
            self._require_open()
            owner = self.voice.recording_authority(token)
            identity = {
                "kind": kind,
                "voice_session_id": envelope[0],
                "scope": envelope[1].wire(),
                "generation": envelope[2],
                "expires_monotonic_ns": envelope[3],
                "zoom": zoom.wire() if zoom is not None else None,
                "scenario": scenario,
                "take_id": take_id,
            }
            if shot is not None and plan_id is None:
                plan_id = shot["plan_id"]
            if plan_id is not None:
                # Only added when present so pre-plan request fingerprints replay unchanged.
                identity["plan_id"] = plan_id
            if shot is not None:
                # Part of the request identity: two starts that film different
                # lens timelines are different requests, not a replay of one.
                identity["shot"] = shot
            if source != "simulated":
                identity["source"] = source
            if behavior_context is not None:
                identity["behavior_context"] = behavior_context
            fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            accepted = self._accepted.get(request_id)
            if accepted is not None:
                if accepted[:2] != (owner["voice_session_id"], fingerprint):
                    raise RecordingError(
                        409, "operation_conflict", "This request ID was already used differently."
                    )
                take = self.recording.get(accepted[2])
                self.observe(take, take["state"])
                return {**self.voice.recording_authority(token), "code": "retried", "take": take}
            self.voice.recording_authority(token, envelope)
            if kind == "start" and len(self._accepted) >= MAX_OPERATION_HISTORY - 2:
                raise VoiceServiceError(
                    409, "recording_history_exhausted", "Restart the local rehearsal runtime."
                )
            if kind == "start":
                self._reconcile(token)
                if any(take["state"] in UNRESOLVED_STATES for take in self.recording.list_takes()):
                    raise RecordingError(409, "take_unresolved", "Stop or recover the unresolved take first.")
                capture_id = "start:" + request_id
                owner = self.voice.recording_authority(token, envelope, capture_id=capture_id)
                context = {
                    "voice_session_id": owner["voice_session_id"],
                    "scope": owner["snapshot"]["scope"],
                    "director_context": owner["context"],
                    "recording_runtime_epoch": self.recording.epoch,
                }
                if behavior_context is not None:
                    context.update(behavior_context)
                if shot is not None:
                    # The reviewed lens timeline travels with the take so the
                    # phone recorder can drive the lens instead of leaving it
                    # wherever the operator last set it.
                    context["shot"] = shot
                # The requested notification precedes simulator dispatch. Register
                # the provisional identity there so even immediate completion binds.
                self._starting_capture = (owner["voice_session_id"], capture_id)
                self._starting_take_id = None
                try:
                    take = self.recording.start(
                        request_id, context, zoom, scenario, plan_id=plan_id, source=source
                    )
                except Exception:
                    # The requested notification is synchronous and precedes
                    # dispatch. A runtime/storage failure after it is uncertainty,
                    # never stopped evidence, even when it is a RecordingError.
                    if self._starting_take_id is None:
                        self.voice.finish_fixture_capture(owner["voice_session_id"], capture_id)
                    raise
                finally:
                    self._starting_capture = None
                    self._starting_take_id = None
                self._captures[take["take_id"]] = (owner["voice_session_id"], capture_id)
            else:
                self._reconcile(token)
                take = self.recording.get(take_id)
                same_owner = take["context"].get("voice_session_id") == owner["voice_session_id"]
                if not same_owner and not (kind == "recover" and take_id in self._restarted):
                    raise VoiceServiceError(
                        409, "take_owner_mismatch", "This take belongs to another voice owner."
                    )
                take = getattr(self.recording, kind)(take_id, request_id)
            self._accepted[request_id] = (owner["voice_session_id"], fingerprint, take["take_id"])
            self.observe(take, take["state"])
            return {**self.voice.recording_authority(token), "code": kind + "_accepted", "take": take}

    def review(self, token, envelope, take_id):
        """Score a ready take against its plan and persist the verdict.

        Deterministic for a given media/plan/prompt version (the verdict cache is
        content-addressed), so replays are naturally idempotent.
        """
        from takeone.review.verdict import review_take

        with self._mutations:
            self._require_open()
            self.voice.recording_authority(token, envelope)
            take = self.recording.get(take_id)
            media_path = self.recording.media_root / take_id / "synthetic.mp4"
            try:
                verdict = review_take(take, media_path)
            except ValueError as error:
                raise RecordingError(409, "review_unavailable", str(error)) from None
            repository = self.recording.repository
            with repository.transaction() as connection:
                repository.owner(connection, self.recording.epoch)
                repository.record_verdict(
                    connection,
                    take_id,
                    verdict["prompt_version"],
                    verdict["score"],
                    verdict["signals"],
                    verdict["reason"],
                    verdict["model"],
                    verdict["created_ns"],
                )
                verdicts = repository.verdicts(connection, take_id)
            return {
                **self.voice.recording_authority(token),
                "code": "take_reviewed",
                "verdict": verdict,
                "verdicts": verdicts,
            }

    def _require_open(self):
        if self._closed:
            raise VoiceServiceError(503, "recording_unavailable", "The offline recording runtime is closed.")

    def close(self):
        with self._mutations:
            if self._closed:
                return
            self._closed = True
        # Finalizers may notify voice. Never join workers under either lock.
        self.recording.close()
