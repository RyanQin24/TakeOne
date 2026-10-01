"""Immutable identities and recording observations for voice state."""

from dataclasses import dataclass
from uuid import UUID

MAX_INTEGER = 2**63 - 1
RECORDING_STATES = frozenset(
    {"idle", "requested", "starting", "recording", "finalizing", "stopped", "unknown"}
)
RECORDING_SOURCES = frozenset({"fixture", "recorder"})


def _integer(value, name):
    if type(value) is not int or not 0 <= value <= MAX_INTEGER:
        raise ValueError(f"{name} must be a non-negative integer")


def _uuid(value, name):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a canonical UUID")
    try:
        canonical = str(UUID(value))
    except ValueError:
        canonical = None
    if canonical != value:
        raise ValueError(f"{name} must be a canonical UUID")


def _plan_id(value):
    if value is not None and (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("Plan ID must be a lowercase SHA-256 digest or null")


@dataclass(frozen=True, slots=True)
class VoiceScope:
    runtime_epoch: str
    session_id: str
    revision: int
    cancellation_generation: int
    plan_id: str | None
    take_id: str | None

    def __post_init__(self):
        _uuid(self.runtime_epoch, "Runtime epoch")
        _uuid(self.session_id, "Session ID")
        _integer(self.revision, "Revision")
        _integer(self.cancellation_generation, "Cancellation generation")
        _plan_id(self.plan_id)
        if self.take_id is not None:
            _uuid(self.take_id, "Take ID")

    def wire(self):
        return {
            "runtime_epoch": self.runtime_epoch,
            "session_id": self.session_id,
            "revision": self.revision,
            "cancellation_generation": self.cancellation_generation,
            "plan_id": self.plan_id,
            "take_id": self.take_id,
        }


@dataclass(frozen=True, slots=True)
class RecordingEvent:
    scope: VoiceScope
    sequence: int
    state: str
    source: str
    observed_monotonic_ns: int
    expires_monotonic_ns: int

    def __post_init__(self):
        if not isinstance(self.scope, VoiceScope):
            raise ValueError("Recording event requires a typed voice scope")
        _integer(self.sequence, "Recording sequence")
        if not isinstance(self.state, str) or self.state not in RECORDING_STATES:
            raise ValueError("Unknown recording state")
        if not isinstance(self.source, str) or self.source not in RECORDING_SOURCES:
            raise ValueError("Unknown recording source")
        _integer(self.observed_monotonic_ns, "Recording observation time")
        _integer(self.expires_monotonic_ns, "Recording expiry")
        if self.expires_monotonic_ns <= self.observed_monotonic_ns:
            raise ValueError("Recording expiry must follow its observation time")

    def wire(self):
        return {
            "scope": self.scope.wire(),
            "sequence": self.sequence,
            "state": self.state,
            "source": self.source,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "expires_monotonic_ns": self.expires_monotonic_ns,
        }
