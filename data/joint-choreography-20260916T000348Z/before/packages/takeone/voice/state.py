"""Local recording gate and conversational cancellation state."""

import time

from .contracts import MAX_INTEGER, RecordingEvent, VoiceScope

MAX_TRANSCRIPT_ENTRIES = 32
MAX_TRANSCRIPT_BYTES = 32 * 1_024
MAX_FRAGMENT_BYTES = 16 * 1_024
MAX_REQUEST_IDENTITIES = 1_024
MAX_OBSERVED_SCOPES = 256
TRANSCRIPT_SPEAKERS = frozenset({"creator", "director", "system"})
TRANSCRIPT_SOURCES = frozenset({"fixture", "live", "system"})


def _bounded_label(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f"{name} must contain 1 to 200 characters")


class VoiceState:
    def __init__(self, scope: VoiceScope, *, mode: str, clock=time.monotonic_ns):
        if not isinstance(scope, VoiceScope):
            raise ValueError("Voice state requires a typed scope")
        if mode not in ("offline", "live"):
            raise ValueError("Voice mode must be offline or live")
        self._scope = scope
        self._mode = mode
        self._clock = clock
        self._generation = scope.cancellation_generation
        self._quiet = True
        self._quiet_reason = "recording_state_unknown"
        self._pending_request_id = None
        self._transcript = []
        self._transcript_bytes = 0
        self._scope_sequences = {}
        self._recording_latch_scope = None
        self._recording_latch_sequence = None
        self._observation_expires_ns = None
        self._used_request_ids = set()
        self._retired_reason = None

    def _invalidate_pending(self):
        if self._pending_request_id is not None:
            self._pending_request_id = None
            if self._generation == MAX_INTEGER:
                self._retire("generation_exhausted")
            else:
                self._generation += 1

    def recording_authority_remaining_ms(self):
        self._refresh_authority()
        if self._observation_expires_ns is None:
            return 0
        return max(0, (self._observation_expires_ns - self._clock()) // 1_000_000)

    def _close_gate(self, reason):
        self._quiet = True
        self._quiet_reason = reason
        self._invalidate_pending()

    def _fresh(self, event):
        now = self._clock()
        return event.observed_monotonic_ns <= now < event.expires_monotonic_ns

    def _refresh_authority(self):
        if self._retired_reason is not None:
            return
        if self._observation_expires_ns is not None and self._clock() >= self._observation_expires_ns:
            self._observation_expires_ns = None
            self._close_gate("recording_observation_expired")

    def _retired_quiet_reason(self):
        if self._recording_latch_scope is not None:
            return f"{self._retired_reason}_latch_pending"
        return self._retired_reason

    def _retire(self, reason):
        if self._retired_reason is None:
            self._retired_reason = reason
            self._observation_expires_ns = None
        self._close_gate(self._retired_quiet_reason())

    def _observe_retired_latch(self, event):
        if (
            self._recording_latch_scope is None
            or event.scope != self._recording_latch_scope
            or event.sequence <= self._recording_latch_sequence
            or (self._mode == "live" and event.source == "fixture" and event.state in ("idle", "stopped"))
        ):
            return self.snapshot()
        self._recording_latch_sequence = event.sequence
        if event.state == "stopped":
            if event.scope in self._scope_sequences:
                self._scope_sequences[event.scope] = event.sequence
            self._recording_latch_scope = None
            self._recording_latch_sequence = None
        self._quiet = True
        self._quiet_reason = self._retired_quiet_reason()
        return self.snapshot()

    def observe_recording(self, event: RecordingEvent) -> dict:
        if not isinstance(event, RecordingEvent):
            raise ValueError("A typed recording event is required")
        if not self._fresh(event):
            return self.snapshot()
        if self._retired_reason is not None:
            return self._observe_retired_latch(event)

        if self._recording_latch_scope is not None:
            if (
                event.scope != self._recording_latch_scope
                or event.sequence <= self._recording_latch_sequence
                or (self._mode == "live" and event.source == "fixture" and event.state in ("idle", "stopped"))
            ):
                return self.snapshot()
            self._recording_latch_sequence = event.sequence
            self._observation_expires_ns = event.expires_monotonic_ns
            if event.state == "stopped":
                self._scope_sequences[event.scope] = event.sequence
                self._recording_latch_scope = None
                self._recording_latch_sequence = None
                if event.scope == self._scope:
                    self._quiet = False
                    self._quiet_reason = None
            else:
                self._close_gate(f"recording_{event.state}")
            return self.snapshot()

        if event.scope != self._scope:
            return self.snapshot()
        if self._mode == "live" and event.source == "fixture" and event.state in ("idle", "stopped"):
            return self.snapshot()
        previous_sequence = self._scope_sequences.get(event.scope, -1)
        if event.sequence <= previous_sequence:
            return self.snapshot()
        if event.scope not in self._scope_sequences and len(self._scope_sequences) >= MAX_OBSERVED_SCOPES:
            if event.state not in ("idle", "stopped"):
                self._recording_latch_scope = event.scope
                self._recording_latch_sequence = event.sequence
            self._retire("scope_history_exhausted")
            return self.snapshot()
        self._scope_sequences[event.scope] = event.sequence

        if event.state in ("idle", "stopped"):
            self._observation_expires_ns = event.expires_monotonic_ns
            self._quiet = False
            self._quiet_reason = None
        else:
            self._recording_latch_scope = event.scope
            self._recording_latch_sequence = event.sequence
            self._observation_expires_ns = event.expires_monotonic_ns
            self._close_gate(f"recording_{event.state}")
        return self.snapshot()

    def set_scope(self, scope: VoiceScope) -> dict:
        if not isinstance(scope, VoiceScope):
            raise ValueError("A typed voice scope is required")
        if scope == self._scope:
            return self.snapshot()
        if self._retired_reason is not None:
            raise RuntimeError("Voice state history is exhausted; create a fresh voice session")
        self._invalidate_pending()
        if self._retired_reason is not None:
            return self.snapshot()
        self._generation = max(self._generation, scope.cancellation_generation)
        self._scope = scope
        self._observation_expires_ns = None
        self._quiet = True
        self._quiet_reason = "scope_changed"
        return self.snapshot()

    def interrupt(self, reason: str) -> dict:
        _bounded_label(reason, "Interrupt reason")
        self._refresh_authority()
        self._invalidate_pending()
        return self.snapshot()

    @staticmethod
    def _fragment_bytes(text, *, allow_empty):
        if not isinstance(text, str) or (not allow_empty and not text):
            raise ValueError("Transcript text must be a string")
        size = len(text.encode("utf-8"))
        if size > MAX_FRAGMENT_BYTES:
            raise ValueError("Transcript fragment exceeds the 16 KiB limit")
        return size

    def _append_entry(self, speaker, text, start_ms, end_ms, source, size):
        self._transcript.append(
            {
                "speaker": speaker,
                "text": text,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "source": source,
            }
        )
        self._transcript_bytes += size
        while len(self._transcript) > MAX_TRANSCRIPT_ENTRIES or self._transcript_bytes > MAX_TRANSCRIPT_BYTES:
            removed = self._transcript.pop(0)
            self._transcript_bytes -= len(removed["text"].encode("utf-8"))

    def append_transcript(self, speaker: str, delta: str, start_ms: int, end_ms: int) -> None:
        if not isinstance(speaker, str) or speaker not in TRANSCRIPT_SPEAKERS:
            raise ValueError("Transcript speaker must be creator, director or system")
        if (
            type(start_ms) is not int
            or type(end_ms) is not int
            or start_ms < 0
            or end_ms < start_ms
            or end_ms > MAX_INTEGER
        ):
            raise ValueError("Transcript interval must be finite non-negative integer milliseconds")
        size = self._fragment_bytes(delta, allow_empty=True)
        if not delta:
            return
        source = "system" if speaker == "system" else ("fixture" if self._mode == "offline" else "live")
        self._append_entry(speaker, delta, start_ms, end_ms, source, size)

    def begin(self, request_id: str) -> int:
        _bounded_label(request_id, "Request ID")
        self._refresh_authority()
        if self._pending_request_id is not None:
            raise RuntimeError("Only one conversation request may be active")
        if request_id in self._used_request_ids:
            raise ValueError("Request ID has already been used")
        if self._retired_reason is not None:
            raise RuntimeError("Voice state history is exhausted; create a fresh voice session")
        if self._quiet:
            raise RuntimeError("Conversation is quiet while recording state is uncertain")
        if len(self._used_request_ids) >= MAX_REQUEST_IDENTITIES:
            self._retire("request_history_exhausted")
            raise RuntimeError("Voice request history is exhausted; create a fresh voice session")
        self._used_request_ids.add(request_id)
        self._pending_request_id = request_id
        return self._generation

    def complete(self, request_id: str, generation: int, text: str, *, source: str) -> bool:
        self._refresh_authority()
        if (
            self._quiet
            or request_id != self._pending_request_id
            or type(generation) is not int
            or generation != self._generation
        ):
            return False
        size = self._fragment_bytes(text, allow_empty=False)
        expected_source = "fixture" if self._mode == "offline" else "live"
        if (
            not isinstance(source, str)
            or source not in TRANSCRIPT_SOURCES
            or source not in (expected_source, "system")
        ):
            raise ValueError("Transcript source must be fixture, live or system")
        speaker = "system" if source == "system" else "director"
        self._append_entry(speaker, text, None, None, source, size)
        self._pending_request_id = None
        return True

    def snapshot(self) -> dict:
        self._refresh_authority()
        return {
            "scope": self._scope.wire(),
            "mode": self._mode,
            "generation": self._generation,
            "quiet": self._quiet,
            "quiet_reason": self._quiet_reason,
            "recording_latch_active": self._recording_latch_scope is not None,
            "pending_request_id": self._pending_request_id,
            "transcript": [entry.copy() for entry in self._transcript],
            "transcript_bytes": self._transcript_bytes,
        }
