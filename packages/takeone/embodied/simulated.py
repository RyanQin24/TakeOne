"""Deterministic closed-loop fixture for embodied-director acceptance tests.

This is not dynamics or hardware qualification. It turns camera-level servo
intent into a simple synthetic observation so the semantic/local-control loop
can be tested without devices, serial ports, or Gemini network calls.
"""

from dataclasses import dataclass

from takeone.perception import PerceptionState, TrackedPerson

from .contracts import FilmingGoal
from .servo import ServoIntent


@dataclass(slots=True)
class SimulatedSubject:
    track_id: str
    lateral: float = 0.0
    vertical: float = 0.0
    confidence: float = 0.98


class SimulationBehaviorAdapter:
    def __init__(self, subjects, *, range_m=4.0, height_scale=0.9, clock=None):
        self.subjects = {subject.track_id: subject for subject in subjects}
        self.range_m = float(range_m)
        self.height_scale = float(height_scale)
        self.aim_uv = [0.5, 0.5]
        self.goal = None
        self.plan_id = None
        self.active = False
        self.holds = 0
        self.stops = 0
        self.updates = 0
        self.clock = clock or (lambda: 1_000_000_000)
        self.history = []

    def start(self, plan_id, goal):
        if not isinstance(goal, FilmingGoal):
            raise ValueError("Simulation adapter requires a FilmingGoal")
        if any(track_id not in self.subjects for track_id in goal.subject_track_ids):
            return False
        self.plan_id = plan_id
        self.goal = goal
        self.active = True
        self.history.append(("start", self.range_m, tuple(self.aim_uv)))
        return True

    def update(self, intent):
        if not self.active or not isinstance(intent, ServoIntent):
            return False
        # Camera-level fixture: the base owns range; the arm owns local aim.
        if intent.range_action == "approach":
            self.range_m = max(0.8, self.range_m - 0.18 * max(intent.range_strength, 0.15))
        elif intent.range_action == "retreat":
            self.range_m = min(8.0, self.range_m + 0.18 * max(intent.range_strength, 0.15))
        self.aim_uv[0] += 0.55 * intent.aim_error_uv[0]
        self.aim_uv[1] += 0.55 * intent.aim_error_uv[1]
        self.aim_uv[0] = min(0.9, max(0.1, self.aim_uv[0]))
        self.aim_uv[1] = min(0.9, max(0.1, self.aim_uv[1]))
        self.updates += 1
        self.history.append(("update", self.range_m, tuple(self.aim_uv), intent.wire()))
        return True

    def hold(self):
        self.active = False
        self.holds += 1
        self.history.append(("hold", self.range_m, tuple(self.aim_uv)))

    def stop(self):
        self.active = False
        self.stops += 1
        self.history.append(("stop", self.range_m, tuple(self.aim_uv)))

    def move_subject(self, track_id, *, lateral=None, vertical=None):
        subject = self.subjects[track_id]
        if lateral is not None:
            subject.lateral = float(lateral)
        if vertical is not None:
            subject.vertical = float(vertical)

    def observe(self, *, frame_age_ms=10):
        timestamp = int(self.clock())
        people = []
        for subject in self.subjects.values():
            # Simple pinhole-like image fixture. Subject height shrinks with range;
            # lateral/vertical scene offsets are divided by range and compensated
            # by the simulated arm aim. This is deliberately not a dynamics model.
            height = min(0.92, max(0.06, self.height_scale / max(self.range_m, 0.2)))
            width = height * 0.42
            center_x = 0.5 + subject.lateral / max(self.range_m, 0.2) - (self.aim_uv[0] - 0.5)
            center_y = 0.5 + subject.vertical / max(self.range_m, 0.2) - (self.aim_uv[1] - 0.5)
            left, right = center_x - width / 2, center_x + width / 2
            top, bottom = center_y - height / 2, center_y + height / 2
            if right <= 0 or left >= 1 or bottom <= 0 or top >= 1:
                continue
            box = (max(0.0, left), max(0.0, top), min(1.0, right), min(1.0, bottom))
            if box[2] - box[0] <= 1e-6 or box[3] - box[1] <= 1e-6:
                continue
            people.append(TrackedPerson(subject.track_id, box, subject.confidence, (0.0, 0.0), timestamp))
        return PerceptionState(timestamp, int(frame_age_ms), tuple(people))

    def snapshot(self):
        return {
            "kind": "embodied_behavior_simulation",
            "range_m": self.range_m,
            "aim_uv": list(self.aim_uv),
            "active": self.active,
            "updates": self.updates,
            "holds": self.holds,
            "stops": self.stops,
            "plan_id": self.plan_id,
            "history_length": len(self.history),
        }
