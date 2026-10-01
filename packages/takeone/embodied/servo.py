"""Image-space local servo intent; deliberately above motors/joint commands."""

from dataclasses import asdict, dataclass

from takeone.perception.contracts import PerceptionState

from .contracts import FilmingGoal


@dataclass(frozen=True, slots=True)
class ServoIntent:
    subject_track_ids: tuple[str, ...]
    aim_error_uv: tuple[float, float]
    observed_subject_height: float
    size_error: float
    range_action: str
    range_strength: float
    confidence: float
    settled: bool

    def wire(self):
        return asdict(self)


def _union_box(people):
    return (
        min(person.bbox_uv[0] for person in people),
        min(person.bbox_uv[1] for person in people),
        max(person.bbox_uv[2] for person in people),
        max(person.bbox_uv[3] for person in people),
    )


class VisualServoController:
    def __init__(self, *, aim_deadband=0.04, confidence_floor=0.45):
        if not 0 < aim_deadband <= 0.25:
            raise ValueError("aim_deadband must be between zero and 0.25")
        if not 0 <= confidence_floor <= 1:
            raise ValueError("confidence_floor must be between zero and one")
        self.aim_deadband = float(aim_deadband)
        self.confidence_floor = float(confidence_floor)

    def intent(self, goal, state):
        if not isinstance(goal, FilmingGoal) or not isinstance(state, PerceptionState):
            raise ValueError("Visual servo requires typed goal and perception state")
        indexed = {person.track_id: person for person in state.people}
        selected = [indexed[track_id] for track_id in goal.subject_track_ids if track_id in indexed]
        if len(selected) != len(goal.subject_track_ids):
            raise ValueError("Selected subject is not fully visible")
        box = _union_box(selected)
        center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        aim_error = (
            center[0] - goal.screen_target_uv[0],
            center[1] - goal.screen_target_uv[1],
        )
        observed_height = box[3] - box[1]
        low, high = goal.desired_subject_size_range
        target = (low + high) / 2
        size_error = target - observed_height
        if observed_height < low:
            range_action = "approach"
            strength = min(1.0, (low - observed_height) / max(low, 1e-6))
        elif observed_height > high:
            range_action = "retreat"
            strength = min(1.0, (observed_height - high) / max(1 - high, 1e-6))
        else:
            range_action, strength = "hold", 0.0

        # An authored one-way relation does not silently reverse itself. Follow
        # may correct either direction to retain subject size.
        if goal.camera_relation == "approach" and range_action == "retreat":
            range_action, strength = "hold", 0.0
        if goal.camera_relation == "retreat" and range_action == "approach":
            range_action, strength = "hold", 0.0
        if goal.camera_relation == "hold":
            range_action, strength = "hold", 0.0

        confidence = min(person.confidence for person in selected)
        settled = (
            abs(aim_error[0]) <= self.aim_deadband
            and abs(aim_error[1]) <= self.aim_deadband
            and low <= observed_height <= high
            and confidence >= self.confidence_floor
        )
        return ServoIntent(
            tuple(goal.subject_track_ids),
            aim_error,
            observed_height,
            size_error,
            range_action,
            strength,
            confidence,
            settled,
        )
