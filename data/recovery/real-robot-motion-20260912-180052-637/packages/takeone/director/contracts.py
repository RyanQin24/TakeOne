"""Strict, immutable session contracts; no model, camera or hardware imports."""

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from uuid import UUID


def integer(value, name, minimum=0, maximum=2**63 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def text(value, name, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must contain 1–{maximum} characters")
    return value


def identity(value, name="ID"):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a UUID")
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise ValueError(f"{name} must be a canonical UUID") from None
    return value


def fields(value, required, optional=()):
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    missing, extra = set(required) - value.keys(), value.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f"Invalid fields; missing: {sorted(missing)}, unknown: {sorted(extra)}")
    return value


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Mode(StrEnum):
    PLANNING = "planning"
    DEMONSTRATION = "demonstration"


class Phase(StrEnum):
    BRIEF = "brief"
    PLANNING = "planning"
    PREVIEW = "preview"
    SCRIPT = "script"
    REHEARSAL = "rehearsal"
    READY = "ready"
    STARTING_RECORDING = "starting_recording"
    RECORDING = "recording"
    FINALIZING = "finalizing"
    REVIEW = "review"
    ACCEPTED = "accepted"
    EDITING = "editing"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAULT = "fault"


@dataclass(frozen=True, slots=True)
class ProductionBrief:
    title: str
    objective: str
    duration_ms: int
    aspect_ratio: str

    def __post_init__(self):
        text(self.title, "Title", 120)
        text(self.objective, "Video idea")
        integer(self.duration_ms, "Duration in milliseconds", 1000, 300000)
        if self.aspect_ratio not in ("9:16", "16:9", "1:1"):
            raise ValueError("Choose 9:16, 16:9 or 1:1")

    @classmethod
    def parse(cls, value):
        return cls(**fields(value, ("title", "objective", "duration_ms", "aspect_ratio")))


@dataclass(frozen=True, slots=True)
class Beat:
    beat_id: str
    start_ms: int
    end_ms: int
    instruction: str

    def __post_init__(self):
        identity(self.beat_id, "Beat ID")
        integer(self.start_ms, "Beat start")
        integer(self.end_ms, "Beat end", self.start_ms + 1, 300000)
        text(self.instruction, "Beat instruction", 2000)

    @classmethod
    def parse(cls, value):
        return cls(**fields(value, ("beat_id", "start_ms", "end_ms", "instruction")))


@dataclass(frozen=True, slots=True)
class ShotReference:
    scene_id: str
    shot_id: str
    revision: int
    plan_id: str
    duration_ms: int
    source: str
    beats: tuple[Beat, ...]

    def __post_init__(self):
        identity(self.scene_id, "Scene ID")
        identity(self.shot_id, "Shot ID")
        integer(self.revision, "Shot revision")
        if (
            not isinstance(self.plan_id, str)
            or len(self.plan_id) != 64
            or any(c not in "0123456789abcdef" for c in self.plan_id)
        ):
            raise ValueError("Plan ID must be a SHA-256 digest")
        integer(self.duration_ms, "Shot duration", 1, 300000)
        if self.source not in ("simulated", "fixture"):
            raise ValueError("A preview reference cannot claim measured execution")
        if not isinstance(self.beats, tuple) or len(self.beats) > 256:
            raise ValueError("Beats must be a bounded immutable tuple")
        seen = set()
        for beat in self.beats:
            if not isinstance(beat, Beat) or beat.end_ms > self.duration_ms or beat.beat_id in seen:
                raise ValueError("Invalid, duplicate or out-of-shot beat")
            seen.add(beat.beat_id)

    @classmethod
    def parse(cls, value):
        data = fields(
            value, ("scene_id", "shot_id", "revision", "plan_id", "duration_ms", "source", "beats")
        ).copy()
        if not isinstance(data["beats"], list):
            raise ValueError("Beats must be a list")
        data["beats"] = tuple(Beat.parse(item) for item in data["beats"])
        return cls(**data)


@dataclass(frozen=True, slots=True)
class Evidence:
    source: str
    source_id: str
    sequence: int
    captured_monotonic_ns: int
    runtime_epoch: str
    frame: str

    def __post_init__(self):
        if self.source not in ("observed", "simulated", "fixture"):
            raise ValueError("Unknown evidence source")
        text(self.source_id, "Evidence source", 200)
        integer(self.sequence, "Evidence sequence")
        integer(self.captured_monotonic_ns, "Evidence capture time")
        identity(self.runtime_epoch, "Evidence clock epoch")
        if self.frame not in ("world", "cart", "optical", "screen", "session"):
            raise ValueError("Evidence must name its coordinate frame")


@dataclass(frozen=True, slots=True)
class Scope:
    session_id: str
    expected_revision: int
    cancellation_generation: int
    take_id: str | None
    plan_id: str | None

    def __post_init__(self):
        identity(self.session_id, "Session ID")
        integer(self.expected_revision, "Expected revision")
        integer(self.cancellation_generation, "Cancellation generation")
        if self.take_id is not None:
            identity(self.take_id, "Take ID")
        if self.plan_id is not None:
            if not isinstance(self.plan_id, str) or len(self.plan_id) != 64:
                raise ValueError("Invalid scoped plan ID")

    @classmethod
    def parse(cls, value):
        return cls(
            **fields(
                value, ("session_id", "expected_revision", "cancellation_generation", "take_id", "plan_id")
            )
        )


@dataclass(frozen=True, slots=True)
class Command:
    operation_id: str
    runtime_epoch: str
    expires_monotonic_ns: int
    scope: Scope
    action: str
    brief: ProductionBrief | None = None

    def __post_init__(self):
        identity(self.operation_id, "Operation ID")
        identity(self.runtime_epoch, "Runtime epoch")
        integer(self.expires_monotonic_ns, "Command expiry")
        if not isinstance(self.scope, Scope):
            raise ValueError("Command scope is required")
        if self.action not in (
            "revise_brief",
            "cancel",
            "request_plan",
            "request_rehearsal",
            "mark_ready",
            "request_record",
            "request_cut",
            "request_review",
            "accept_take",
            "prepare_edit",
        ):
            raise ValueError("Unknown Director action")
        if (self.action == "revise_brief") != isinstance(self.brief, ProductionBrief):
            raise ValueError("Only revise_brief takes a complete brief")

    @classmethod
    def parse(cls, value):
        data = fields(
            value,
            ("schema_version", "operation_id", "runtime_epoch", "expires_monotonic_ns", "scope", "action"),
            ("brief",),
        ).copy()
        if type(data.pop("schema_version")) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported command schema")
        data["scope"] = Scope.parse(data["scope"])
        if "brief" in data:
            data["brief"] = ProductionBrief.parse(data["brief"])
        return cls(**data)


@dataclass(frozen=True, slots=True)
class Session:
    session_id: str
    revision: int
    cancellation_generation: int
    mode: Mode
    phase: Phase
    brief: ProductionBrief
    shot: ShotReference | None
    take_id: str | None
    reviewed_take_id: str | None
    created_utc: str
    updated_utc: str

    def __post_init__(self):
        identity(self.session_id, "Session ID")
        integer(self.revision, "Session revision")
        integer(self.cancellation_generation, "Cancellation generation")
        if not isinstance(self.mode, Mode) or not isinstance(self.phase, Phase):
            raise ValueError("Typed session mode and phase required")
        if not isinstance(self.brief, ProductionBrief):
            raise ValueError("Typed production brief required")
        if self.shot is not None and not isinstance(self.shot, ShotReference):
            raise ValueError("Typed shot reference required")
        for value in (self.take_id, self.reviewed_take_id):
            if value is not None:
                identity(value, "Take ID")

    def scope(self):
        return Scope(
            self.session_id,
            self.revision,
            self.cancellation_generation,
            self.take_id,
            self.shot.plan_id if self.shot else None,
        )

    def wire(self):
        document = asdict(self)
        if document["shot"] is not None:
            document["shot"]["beats"] = list(document["shot"]["beats"])
        return {"schema_version": 1, **document}

    @classmethod
    def parse(cls, value):
        data = fields(
            value,
            (
                "schema_version",
                "session_id",
                "revision",
                "cancellation_generation",
                "mode",
                "phase",
                "brief",
                "shot",
                "take_id",
                "reviewed_take_id",
                "created_utc",
                "updated_utc",
            ),
        ).copy()
        if type(data.pop("schema_version")) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported session schema")
        data["mode"], data["phase"] = Mode(data["mode"]), Phase(data["phase"])
        data["brief"] = ProductionBrief.parse(data["brief"])
        data["shot"] = ShotReference.parse(data["shot"]) if data["shot"] is not None else None
        return cls(**data)
