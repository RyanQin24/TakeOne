"""Goal-level embodied-director contracts; no motor or serial fields."""

from dataclasses import asdict, dataclass

SUBJECT_RELATIONS = frozenset({"one_person", "pair", "group", "object"})
CAMERA_RELATIONS = frozenset({"approach", "retreat", "follow", "lead", "arc", "hold"})
FRAMINGS = frozenset({"full", "medium", "medium_close", "close", "custom"})
RECORDING_POLICIES = frozenset({"after_settle", "immediate", "manual"})
LOST_TARGET_POLICIES = frozenset({"hold", "stop"})


def _unit_pair(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} needs two normalized coordinates")
    pair = tuple(float(v) for v in value)
    if any(not 0 <= v <= 1 for v in pair):
        raise ValueError(f"{name} must stay between zero and one")
    return pair


@dataclass(frozen=True, slots=True)
class FilmingGoal:
    subject_track_ids: tuple[str, ...]
    subject_relation: str
    camera_relation: str
    framing: str
    screen_target_uv: tuple[float, float] = (0.5, 0.5)
    desired_subject_size_range: tuple[float, float] = (0.2, 0.7)
    recording_policy: str = "after_settle"
    max_duration_s: float = 10.0
    lost_target_policy: str = "hold"

    def __post_init__(self):
        ids = tuple(self.subject_track_ids)
        if not ids or any(not isinstance(value, str) or not value for value in ids):
            raise ValueError("Filming goal needs one or more transient subject track IDs")
        if len(ids) != len(set(ids)):
            raise ValueError("Subject track IDs must be unique")
        if self.subject_relation not in SUBJECT_RELATIONS:
            raise ValueError("Unknown subject relation")
        if self.camera_relation not in CAMERA_RELATIONS:
            raise ValueError("Unknown camera relation")
        if self.framing not in FRAMINGS:
            raise ValueError("Unknown framing")
        if self.recording_policy not in RECORDING_POLICIES:
            raise ValueError("Unknown recording policy")
        if self.lost_target_policy not in LOST_TARGET_POLICIES:
            raise ValueError("Unknown target-loss policy")
        object.__setattr__(self, "subject_track_ids", ids)
        object.__setattr__(self, "screen_target_uv", _unit_pair(self.screen_target_uv, "screen_target_uv"))
        size = _unit_pair(self.desired_subject_size_range, "desired_subject_size_range")
        if size[0] >= size[1]:
            raise ValueError("Subject size range must increase")
        object.__setattr__(self, "desired_subject_size_range", size)
        duration = float(self.max_duration_s)
        if not 0.25 <= duration <= 600:
            raise ValueError("max_duration_s must be 0.25 to 600 seconds")
        object.__setattr__(self, "max_duration_s", duration)

    def wire(self):
        return asdict(self)
