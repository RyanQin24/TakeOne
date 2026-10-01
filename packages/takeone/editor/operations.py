"""The one writable structure in the editor: a typed, validated, append-only operation.

An operation is a *decision*, not an effect. It names what should change and why, in terms
the product can explain. `reducer.apply` is the only thing that turns it into state, and
`compile.project_graph` is the only thing that turns that state into pixels.

Parameters are validated against a declared schema before an operation exists, so an
invalid operation can never be appended, replayed or persisted.
"""

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import ClassVar

from .contracts import (
    boolean,
    choice,
    fields,
    identity,
    integer,
    mapping,
    number,
    seconds,
    slug,
    text,
    unit,
)
from .errors import ValidationError
from .state import AUDIO_KINDS, MARKER_KINDS, PHASES, TRACK_KINDS


class OperationType(StrEnum):
    IMPORT_MEDIA = "IMPORT_MEDIA"
    ANALYZE_CLIP = "ANALYZE_CLIP"
    SET_INTENT = "SET_INTENT"
    SELECT_CLIP = "SELECT_CLIP"
    REJECT_CLIP = "REJECT_CLIP"
    ADD_TRACK = "ADD_TRACK"
    ADD_CLIP = "ADD_CLIP"
    REMOVE_CLIP = "REMOVE_CLIP"
    MOVE_CLIP = "MOVE_CLIP"
    REORDER_CLIP = "REORDER_CLIP"
    SPLIT_CLIP = "SPLIT_CLIP"
    TRIM_CLIP = "TRIM_CLIP"
    APPLY_SPEED_CURVE = "APPLY_SPEED_CURVE"
    FREEZE_FRAME = "FREEZE_FRAME"
    APPLY_TRANSITION = "APPLY_TRANSITION"
    ALIGN_CUT_TO_BEAT = "ALIGN_CUT_TO_BEAT"
    ADD_MARKERS = "ADD_MARKERS"
    APPLY_COLOR_CORRECTION = "APPLY_COLOR_CORRECTION"
    MATCH_COLOR = "MATCH_COLOR"
    APPLY_CREATIVE_LOOK = "APPLY_CREATIVE_LOOK"
    ADD_EFFECT = "ADD_EFFECT"
    UPDATE_EFFECT = "UPDATE_EFFECT"
    REMOVE_EFFECT = "REMOVE_EFFECT"
    APPLY_TEMPLATE = "APPLY_TEMPLATE"
    ADD_MUSIC = "ADD_MUSIC"
    ADD_SFX = "ADD_SFX"
    SET_VOLUME = "SET_VOLUME"
    APPLY_AUDIO_DUCK = "APPLY_AUDIO_DUCK"
    SET_PHASE = "SET_PHASE"
    FINALIZE_TIMELINE = "FINALIZE_TIMELINE"


class OperationStatus(StrEnum):
    PLANNED = "PLANNED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TARGET_KINDS = ("project", "media", "track", "clip", "effect", "transition", "audio")


@dataclass(frozen=True, slots=True)
class Target:
    """A typed reference. The reducer checks that the referent exists; this checks shape."""

    kind: str
    media_id: str | None = None
    track_id: str | None = None
    clip_id: str | None = None
    instance_id: str | None = None
    transition_id: str | None = None
    event_id: str | None = None

    REQUIRED: ClassVar[dict] = {
        "project": (),
        "media": ("media_id",),
        "track": ("track_id",),
        "clip": ("clip_id",),
        "effect": ("clip_id", "instance_id"),
        "transition": ("transition_id",),
        "audio": ("event_id",),
    }

    def __post_init__(self):
        choice(self.kind, "Target kind", TARGET_KINDS)
        required = self.REQUIRED[self.kind]
        for name in required:
            value = getattr(self, name)
            if value is None:
                raise ValidationError(f"A {self.kind} target requires {name}")
            slug(value, name)
        for name in ("media_id", "track_id", "clip_id", "instance_id", "transition_id", "event_id"):
            value = getattr(self, name)
            if value is not None and name not in required:
                slug(value, name)

    def wire(self):
        document = {"kind": self.kind}
        for name in ("media_id", "track_id", "clip_id", "instance_id", "transition_id", "event_id"):
            value = getattr(self, name)
            if value is not None:
                document[name] = value
        return document

    @classmethod
    def parse(cls, value):
        data = fields(
            value,
            ("kind",),
            ("media_id", "track_id", "clip_id", "instance_id", "transition_id", "event_id"),
        )
        return cls(**data)

    @classmethod
    def project(cls):
        return cls("project")


# ---------------------------------------------------------------- parameter schemas


@dataclass(frozen=True, slots=True)
class ParamSpec:
    name: str
    kind: str
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple = ()
    default: object = None

    KINDS: ClassVar[tuple] = (
        "slug",
        "text",
        "int",
        "number",
        "seconds",
        "unit",
        "bool",
        "enum",
        "mapping",
        "list",
        "curve",
        "object",
    )

    def __post_init__(self):
        if self.kind not in self.KINDS:
            raise ValidationError(f"Unknown parameter kind '{self.kind}'")

    def validate(self, value):
        name = self.name
        if self.kind == "slug":
            return slug(value, name)
        if self.kind == "text":
            return text(value, name, int(self.maximum or 240))
        if self.kind == "int":
            return integer(value, name, int(self.minimum or 0), int(self.maximum or 2**31))
        if self.kind == "number":
            return number(
                value,
                name,
                self.minimum if self.minimum is not None else -1e12,
                self.maximum if self.maximum is not None else 1e12,
            )
        if self.kind == "seconds":
            return seconds(
                value, name, self.minimum or 0.0, self.maximum if self.maximum is not None else 36000.0
            )
        if self.kind == "unit":
            return unit(value, name)
        if self.kind == "bool":
            return boolean(value, name)
        if self.kind == "enum":
            return choice(value, name, self.choices)
        if self.kind == "mapping":
            return mapping(value, name)
        if self.kind == "curve":
            from .timing.curve import SpeedCurve

            return SpeedCurve.parse(value).wire()
        if self.kind == "list":
            if not isinstance(value, list) or len(value) > 4096:
                raise ValidationError(f"{name} must be a list of at most 4096 items")
            return list(value)
        if not isinstance(value, dict):
            raise ValidationError(f"{name} must be an object")
        return dict(value)


def _spec(*specs):
    return tuple(specs)


TRIM_EDGES = ("in", "out", "both")

SCHEMAS = {
    OperationType.IMPORT_MEDIA: _spec(
        ParamSpec("media_id", "slug"),
        ParamSpec("name", "text", maximum=200),
        ParamSpec("path", "text", maximum=1024),
        ParamSpec("sha256", "text", maximum=64),
        ParamSpec("probe", "object"),
        ParamSpec("source_space", "slug", required=False),
        ParamSpec("proxy_path", "text", required=False, maximum=1024),
        ParamSpec("thumbnail_path", "text", required=False, maximum=1024),
        ParamSpec("waveform_path", "text", required=False, maximum=1024),
    ),
    OperationType.ANALYZE_CLIP: _spec(
        ParamSpec("media_id", "slug"),
        ParamSpec("analyzer_id", "slug"),
        ParamSpec("analyzer_version", "int", minimum=1, maximum=999),
        ParamSpec("result", "object"),
    ),
    OperationType.SET_INTENT: _spec(ParamSpec("intent", "object")),
    OperationType.SELECT_CLIP: _spec(
        ParamSpec("media_id", "slug"),
        ParamSpec("score", "unit"),
        ParamSpec("signals", "mapping"),
        ParamSpec("reason", "text", required=False),
    ),
    OperationType.REJECT_CLIP: _spec(
        ParamSpec("media_id", "slug"),
        ParamSpec("score", "unit", required=False),
        ParamSpec("signals", "mapping", required=False),
        ParamSpec("reason", "text"),
    ),
    OperationType.ADD_TRACK: _spec(
        ParamSpec("track_id", "slug"),
        ParamSpec("kind", "enum", choices=TRACK_KINDS),
    ),
    OperationType.ADD_CLIP: _spec(
        ParamSpec("clip_id", "slug"),
        ParamSpec("media_id", "slug"),
        ParamSpec("timeline_start_s", "seconds"),
        ParamSpec("source_start_s", "seconds"),
        ParamSpec("source_end_s", "seconds"),
        ParamSpec("label", "text", required=False, maximum=80),
    ),
    OperationType.REMOVE_CLIP: _spec(ParamSpec("ripple", "bool", required=False)),
    OperationType.MOVE_CLIP: _spec(
        ParamSpec("timeline_start_s", "seconds"),
        ParamSpec("track_id", "slug", required=False),
    ),
    OperationType.REORDER_CLIP: _spec(ParamSpec("index", "int", minimum=0)),
    OperationType.SPLIT_CLIP: _spec(
        ParamSpec("time_s", "seconds"),
        ParamSpec("new_clip_id", "slug"),
    ),
    OperationType.TRIM_CLIP: _spec(
        ParamSpec("edge", "enum", choices=TRIM_EDGES),
        ParamSpec("source_start_s", "seconds", required=False),
        ParamSpec("source_end_s", "seconds", required=False),
        ParamSpec("ripple", "bool", required=False),
    ),
    OperationType.APPLY_SPEED_CURVE: _spec(
        ParamSpec("curve", "curve"),
        ParamSpec("interpolation", "enum", required=False, choices=("none", "blend", "mci")),
        ParamSpec("ripple", "bool", required=False),
    ),
    OperationType.FREEZE_FRAME: _spec(
        ParamSpec("time_s", "seconds"),
        ParamSpec("hold_s", "seconds", minimum=0.02, maximum=10.0),
    ),
    OperationType.APPLY_TRANSITION: _spec(
        ParamSpec("transition_id", "slug"),
        ParamSpec("effect_id", "slug"),
        ParamSpec("effect_version", "int", minimum=1, maximum=999),
        ParamSpec("from_clip_id", "slug"),
        ParamSpec("to_clip_id", "slug"),
        ParamSpec("duration_s", "seconds", minimum=0.04, maximum=5.0),
        ParamSpec("parameters", "mapping", required=False),
    ),
    OperationType.ALIGN_CUT_TO_BEAT: _spec(
        ParamSpec("clip_id", "slug"),
        ParamSpec("beat_time_s", "seconds"),
        ParamSpec("max_shift_s", "seconds", required=False, maximum=2.0),
    ),
    OperationType.ADD_MARKERS: _spec(
        ParamSpec("markers", "list"),
        ParamSpec("kind", "enum", choices=MARKER_KINDS),
    ),
    OperationType.APPLY_COLOR_CORRECTION: _spec(
        ParamSpec("exposure_stops", "number", required=False, minimum=-4.0, maximum=4.0),
        ParamSpec("temperature_k", "number", required=False, minimum=-2000.0, maximum=2000.0),
        ParamSpec("tint", "number", required=False, minimum=-1.0, maximum=1.0),
        ParamSpec("contrast", "number", required=False, minimum=0.2, maximum=3.0),
        ParamSpec("saturation", "number", required=False, minimum=0.0, maximum=3.0),
        ParamSpec("lift", "number", required=False, minimum=-0.5, maximum=0.5),
    ),
    OperationType.MATCH_COLOR: _spec(
        ParamSpec("reference_clip_id", "slug"),
        ParamSpec("exposure_stops", "number", minimum=-2.0, maximum=2.0),
        ParamSpec("temperature_k", "number", minimum=-800.0, maximum=800.0),
        ParamSpec("tint", "number", minimum=-0.5, maximum=0.5),
        ParamSpec("contrast", "number", minimum=0.75, maximum=1.25),
    ),
    OperationType.APPLY_CREATIVE_LOOK: _spec(
        ParamSpec("look_id", "slug"),
        ParamSpec("intensity", "unit"),
    ),
    OperationType.ADD_EFFECT: _spec(
        ParamSpec("instance_id", "slug"),
        ParamSpec("effect_id", "slug"),
        ParamSpec("effect_version", "int", minimum=1, maximum=999),
        ParamSpec("parameters", "mapping", required=False),
        ParamSpec("start_s", "seconds", required=False),
        ParamSpec("end_s", "seconds", required=False),
    ),
    OperationType.UPDATE_EFFECT: _spec(
        ParamSpec("parameters", "mapping", required=False),
        ParamSpec("start_s", "seconds", required=False),
        ParamSpec("end_s", "seconds", required=False),
        ParamSpec("enabled", "bool", required=False),
    ),
    OperationType.REMOVE_EFFECT: _spec(),
    OperationType.APPLY_TEMPLATE: _spec(
        ParamSpec("template_id", "slug"),
        ParamSpec("template_version", "int", minimum=1, maximum=999),
        ParamSpec("parameters", "mapping", required=False),
    ),
    OperationType.ADD_MUSIC: _spec(
        ParamSpec("event_id", "slug"),
        ParamSpec("asset_id", "slug"),
        ParamSpec("timeline_start_s", "seconds"),
        ParamSpec("duration_s", "seconds", minimum=0.01),
        ParamSpec("source_start_s", "seconds", required=False),
        ParamSpec("gain_db", "number", required=False, minimum=-60.0, maximum=12.0),
        ParamSpec("fade_in_s", "seconds", required=False, maximum=30.0),
        ParamSpec("fade_out_s", "seconds", required=False, maximum=30.0),
    ),
    OperationType.ADD_SFX: _spec(
        ParamSpec("event_id", "slug"),
        ParamSpec("asset_id", "slug"),
        ParamSpec("kind", "enum", choices=AUDIO_KINDS),
        ParamSpec("timeline_start_s", "seconds"),
        ParamSpec("duration_s", "seconds", minimum=0.01),
        ParamSpec("gain_db", "number", required=False, minimum=-60.0, maximum=12.0),
    ),
    OperationType.SET_VOLUME: _spec(ParamSpec("gain_db", "number", minimum=-60.0, maximum=12.0)),
    OperationType.APPLY_AUDIO_DUCK: _spec(ParamSpec("ducks", "bool")),
    OperationType.SET_PHASE: _spec(ParamSpec("phase", "enum", choices=PHASES)),
    OperationType.FINALIZE_TIMELINE: _spec(),
}

TARGET_KIND_FOR = {
    OperationType.IMPORT_MEDIA: "project",
    OperationType.ANALYZE_CLIP: "media",
    OperationType.SET_INTENT: "project",
    OperationType.SELECT_CLIP: "media",
    OperationType.REJECT_CLIP: "media",
    OperationType.ADD_TRACK: "project",
    OperationType.ADD_CLIP: "track",
    OperationType.REMOVE_CLIP: "clip",
    OperationType.MOVE_CLIP: "clip",
    OperationType.REORDER_CLIP: "clip",
    OperationType.SPLIT_CLIP: "clip",
    OperationType.TRIM_CLIP: "clip",
    OperationType.APPLY_SPEED_CURVE: "clip",
    OperationType.FREEZE_FRAME: "clip",
    OperationType.APPLY_TRANSITION: "track",
    OperationType.ALIGN_CUT_TO_BEAT: "track",
    OperationType.ADD_MARKERS: "project",
    OperationType.APPLY_COLOR_CORRECTION: "clip",
    OperationType.MATCH_COLOR: "clip",
    OperationType.APPLY_CREATIVE_LOOK: "clip",
    OperationType.ADD_EFFECT: "clip",
    OperationType.UPDATE_EFFECT: "effect",
    OperationType.REMOVE_EFFECT: "effect",
    OperationType.APPLY_TEMPLATE: "project",
    OperationType.ADD_MUSIC: "project",
    OperationType.ADD_SFX: "project",
    OperationType.SET_VOLUME: "audio",
    OperationType.APPLY_AUDIO_DUCK: "audio",
    OperationType.SET_PHASE: "project",
    OperationType.FINALIZE_TIMELINE: "project",
}

PHASE_FOR = {
    OperationType.IMPORT_MEDIA: "understand",
    OperationType.ANALYZE_CLIP: "understand",
    OperationType.SET_INTENT: "understand",
    OperationType.SELECT_CLIP: "select",
    OperationType.REJECT_CLIP: "select",
    OperationType.ADD_TRACK: "structure",
    OperationType.ADD_CLIP: "structure",
    OperationType.REMOVE_CLIP: "structure",
    OperationType.MOVE_CLIP: "structure",
    OperationType.REORDER_CLIP: "structure",
    OperationType.SPLIT_CLIP: "structure",
    OperationType.TRIM_CLIP: "rhythm",
    OperationType.APPLY_SPEED_CURVE: "rhythm",
    OperationType.FREEZE_FRAME: "rhythm",
    OperationType.APPLY_TRANSITION: "rhythm",
    OperationType.ALIGN_CUT_TO_BEAT: "rhythm",
    OperationType.ADD_MARKERS: "audio",
    OperationType.APPLY_COLOR_CORRECTION: "color",
    OperationType.MATCH_COLOR: "color",
    OperationType.APPLY_CREATIVE_LOOK: "color",
    OperationType.ADD_EFFECT: "effects",
    OperationType.UPDATE_EFFECT: "effects",
    OperationType.REMOVE_EFFECT: "effects",
    OperationType.APPLY_TEMPLATE: "effects",
    OperationType.ADD_MUSIC: "audio",
    OperationType.ADD_SFX: "audio",
    OperationType.SET_VOLUME: "audio",
    OperationType.APPLY_AUDIO_DUCK: "audio",
    OperationType.SET_PHASE: "understand",
    OperationType.FINALIZE_TIMELINE: "finalize",
}


def validate_parameters(operation_type, parameters):
    """Validate and normalise parameters against the type's schema. Unknown keys are errors."""
    specs = SCHEMAS[operation_type]
    if not isinstance(parameters, dict):
        raise ValidationError("Operation parameters must be an object")
    known = {spec.name for spec in specs}
    unknown = parameters.keys() - known
    if unknown:
        raise ValidationError(f"Unknown parameters for {operation_type}: {sorted(unknown)}")
    result = {}
    for spec in specs:
        if spec.name not in parameters:
            if spec.required:
                raise ValidationError(f"{operation_type} requires '{spec.name}'")
            continue
        result[spec.name] = spec.validate(parameters[spec.name])
    return result


# ---------------------------------------------------------------- the operation


@dataclass(frozen=True, slots=True)
class EditOperation:
    schema_version: ClassVar[int] = 1
    operation_id: str
    type: OperationType
    target: Target
    parameters: dict = field(default_factory=dict)
    public_explanation: str = ""
    metadata: dict = field(default_factory=dict)
    sequence: int = 0
    phase: str = ""
    status: OperationStatus = OperationStatus.PLANNED
    created_utc: str = ""
    executed_utc: str | None = None

    def __post_init__(self):
        identity(self.operation_id, "Operation ID")
        if not isinstance(self.type, OperationType):
            object.__setattr__(self, "type", OperationType(self.type))
        if not isinstance(self.target, Target):
            raise ValidationError("Operation target must be typed")
        expected = TARGET_KIND_FOR[self.type]
        if self.target.kind != expected:
            raise ValidationError(f"{self.type} acts on a {expected} target, not a {self.target.kind}")
        object.__setattr__(self, "parameters", validate_parameters(self.type, self.parameters))
        object.__setattr__(self, "phase", self.phase or PHASE_FOR[self.type])
        choice(self.phase, "Operation phase", PHASES)
        if not isinstance(self.status, OperationStatus):
            object.__setattr__(self, "status", OperationStatus(self.status))
        integer(self.sequence, "Operation sequence")
        if self.public_explanation:
            text(self.public_explanation, "Explanation", 180)
        object.__setattr__(self, "metadata", mapping(self.metadata, "Operation metadata"))

    def executed(self, sequence, executed_utc):
        return replace(
            self,
            sequence=integer(sequence, "Operation sequence", 1),
            status=OperationStatus.COMPLETED,
            executed_utc=executed_utc,
        )

    def failed(self, reason):
        return replace(
            self,
            status=OperationStatus.FAILED,
            metadata={**self.metadata, "failure": text(reason, "Failure reason", 400)},
        )

    def wire(self):
        return {
            "schema_version": 1,
            "operation_id": self.operation_id,
            "sequence": self.sequence,
            "type": str(self.type),
            "phase": self.phase,
            "target": self.target.wire(),
            "parameters": dict(self.parameters),
            "status": str(self.status),
            "created_utc": self.created_utc,
            "executed_utc": self.executed_utc,
            "public_explanation": self.public_explanation,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def parse(cls, value):
        data = dict(
            fields(
                value,
                ("schema_version", "operation_id", "type", "target", "parameters"),
                (
                    "sequence",
                    "phase",
                    "status",
                    "created_utc",
                    "executed_utc",
                    "public_explanation",
                    "metadata",
                ),
            )
        )
        if data.pop("schema_version") != 1:
            raise ValidationError("Unsupported operation schema")
        data["type"] = OperationType(data["type"])
        data["target"] = Target.parse(data["target"])
        if "status" in data:
            data["status"] = OperationStatus(data["status"])
        return cls(**data)
