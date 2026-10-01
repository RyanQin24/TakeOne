"""Local perception contracts. Track IDs are transient geometry, never identity."""

from dataclasses import asdict, dataclass


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    value = float(value)
    if value != value or abs(value) == float("inf"):
        raise ValueError(f"{name} must be finite")
    return value


def _uv_box(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("bbox_uv needs [left, top, right, bottom]")
    box = tuple(_finite(v, "bbox_uv") for v in value)
    if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        raise ValueError("bbox_uv must be ordered normalized coordinates")
    return box


@dataclass(frozen=True, slots=True)
class PersonDetection:
    bbox_uv: tuple[float, float, float, float]
    confidence: float
    def __post_init__(self):
        object.__setattr__(self, "bbox_uv", _uv_box(self.bbox_uv))
        confidence = _finite(self.confidence, "confidence")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between zero and one")
        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True, slots=True)
class TrackedPerson:
    track_id: str
    bbox_uv: tuple[float, float, float, float]
    confidence: float
    velocity_uv_s: tuple[float, float]
    last_seen_ns: int

    def __post_init__(self):
        if not isinstance(self.track_id, str) or not self.track_id:
            raise ValueError("track_id must be a non-empty string")
        object.__setattr__(self, "bbox_uv", _uv_box(self.bbox_uv))
        if type(self.last_seen_ns) is not int or self.last_seen_ns < 0:
            raise ValueError("last_seen_ns must be non-negative integer nanoseconds")
        velocity = tuple(_finite(v, "velocity_uv_s") for v in self.velocity_uv_s)
        if len(velocity) != 2:
            raise ValueError("velocity_uv_s needs two coordinates")
        object.__setattr__(self, "velocity_uv_s", velocity)


@dataclass(frozen=True, slots=True)
class VisionFrame:
    monotonic_timestamp_ns: int
    source_id: str
    width: int
    height: int
    provenance: str

    def __post_init__(self):
        if type(self.monotonic_timestamp_ns) is not int or self.monotonic_timestamp_ns < 0:
            raise ValueError("Vision frame timestamp must be non-negative nanoseconds")
        if not isinstance(self.source_id, str) or not self.source_id:
            raise ValueError("Vision source_id is required")
        if type(self.width) is not int or type(self.height) is not int or min(self.width, self.height) < 1:
            raise ValueError("Vision dimensions must be positive integers")
        if not isinstance(self.provenance, str) or not self.provenance:
            raise ValueError("Vision provenance is required")


@dataclass(frozen=True, slots=True)
class PerceptionState:
    monotonic_timestamp_ns: int
    source_frame_age_ms: int
    people: tuple[TrackedPerson, ...]
    active_subject_track_ids: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.monotonic_timestamp_ns) is not int or self.monotonic_timestamp_ns < 0:
            raise ValueError("Perception timestamp must be non-negative nanoseconds")
        if type(self.source_frame_age_ms) is not int or self.source_frame_age_ms < 0:
            raise ValueError("Frame age must be non-negative integer milliseconds")
        ids = [person.track_id for person in self.people]
        if len(ids) != len(set(ids)):
            raise ValueError("Perception track IDs must be unique")
        if any(track_id not in ids for track_id in self.active_subject_track_ids):
            raise ValueError("Active subjects must reference visible track IDs")

    def wire(self):
        return {
            "monotonic_timestamp_ns": str(self.monotonic_timestamp_ns),
            "source_frame_age_ms": self.source_frame_age_ms,
            "people": [asdict(person) for person in self.people],
            "active_subject_track_ids": list(self.active_subject_track_ids),
            "identity_scope": "transient_visual_tracks_not_person_identity",
        }
