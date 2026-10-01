"""Local owner for long-running embodied filming behaviors.

Gemini may create/adjust goals, but this manager owns target freshness, arming,
serialization and stop/hold decisions. It emits no low-level motor commands.
"""

import secrets
import time
from dataclasses import dataclass
from uuid import uuid4

from takeone.perception.contracts import PerceptionState

from .contracts import FilmingGoal
from .servo import VisualServoController

RELATION_TEMPLATE = {
    "approach": "push_in",
    "retreat": "pull_out",
    "follow": "side_track",
    "lead": "side_track",
    "arc": "arc_left",
    "hold": "static",
}
ACTIVE_STATES = frozenset({"APPROACHING", "FOLLOWING", "REFRAMING", "SETTLING", "RECORDING"})


class BehaviorError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class Behavior:
    behavior_id: str
    goal: FilmingGoal
    plan_id: str
    state: str
    revision: int
    started_ns: int | None = None
    take_id: str | None = None
    termination_reason: str | None = None


class BehaviorManager:
    def __init__(
        self,
        *,
        compiler=None,
        actuator=None,
        recorder=None,
        servo=None,
        clock=time.monotonic_ns,
        max_perception_age_ms=250,
        settle_samples=3,
        confidence_floor=0.45,
        low_confidence_grace_ms=500,
    ):
        self._compiler = compiler
        self._actuator = actuator
        self._recorder = recorder
        self._servo = servo or VisualServoController()
        self._clock = clock
        self._max_perception_age_ms = int(max_perception_age_ms)
        if not 0 <= confidence_floor <= 1:
            raise ValueError("confidence_floor must be between zero and one")
        if type(low_confidence_grace_ms) is not int or not 0 <= low_confidence_grace_ms <= 5_000:
            raise ValueError("low_confidence_grace_ms must be 0 to 5000")
        self._confidence_floor = float(confidence_floor)
        self._low_confidence_grace_ns = low_confidence_grace_ms * 1_000_000
        self._low_confidence_since_ns = None
        self._perception = None
        self._behavior = None
        self._selected_subject_track_ids = ()
        self._selection_reason = None
        if type(settle_samples) is not int or not 1 <= settle_samples <= 120:
            raise ValueError("settle_samples must be 1 to 120")
        self._settle_samples = settle_samples
        self._settle_streak = 0
        self._latest_servo = None
        self._arm_token = None
        self._arm_expires_ns = 0

    def update_perception(self, state):
        if not isinstance(state, PerceptionState):
            raise ValueError("BehaviorManager requires typed PerceptionState")
        self._perception = state
        behavior = self._behavior
        if behavior is None or behavior.state not in ACTIVE_STATES:
            return self.snapshot()
        if state.source_frame_age_ms > self._max_perception_age_ms:
            self._latest_servo = None
            self.hold(reason="stale_perception")
            return self.snapshot()
        visible = {person.track_id for person in state.people}
        missing = [track_id for track_id in behavior.goal.subject_track_ids if track_id not in visible]
        if missing:
            self._latest_servo = None
            self._low_confidence_since_ns = None
            reason = "target_lost:" + ",".join(missing)
            if behavior.goal.lost_target_policy == "stop":
                self.stop(reason=reason)
            else:
                self.hold(reason=reason)
            return self.snapshot()
        selected = [
            person for person in state.people if person.track_id in behavior.goal.subject_track_ids
        ]
        confidence = min(person.confidence for person in selected)
        if confidence < self._confidence_floor:
            if self._low_confidence_since_ns is None:
                self._low_confidence_since_ns = state.monotonic_timestamp_ns
            elif (
                state.monotonic_timestamp_ns - self._low_confidence_since_ns
                >= self._low_confidence_grace_ns
            ):
                self._latest_servo = None
                reason = "target_confidence_low"
                if behavior.goal.lost_target_policy == "stop":
                    self.stop(reason=reason)
                else:
                    self.hold(reason=reason)
                return self.snapshot()
        else:
            self._low_confidence_since_ns = None
        intent = self._servo.intent(behavior.goal, state)
        self._latest_servo = intent
        if self._actuator is not None and hasattr(self._actuator, "update"):
            if self._actuator.update(intent) is False:
                self.hold(reason="controller_update_rejected")
                return self.snapshot()
        if intent.settled:
            self._settle_streak += 1
            if behavior.state in {"APPROACHING", "REFRAMING", "SETTLING"}:
                behavior.state = "SETTLING"
            if (
                behavior.take_id is None
                and behavior.goal.recording_policy == "after_settle"
                and self._settle_streak >= self._settle_samples
            ):
                self._start_recording(behavior)
        else:
            self._settle_streak = 0
            if behavior.state == "SETTLING":
                behavior.state = (
                    "FOLLOWING" if behavior.goal.camera_relation in ("follow", "lead") else "APPROACHING"
                )
        return self.snapshot()

    def select_subject(self, track_ids, semantic_reason):
        if not isinstance(track_ids, (list, tuple)) or not track_ids:
            raise ValueError("select_subject needs one or more transient track IDs")
        ids = tuple(track_ids)
        if len(ids) != len(set(ids)) or any(not isinstance(value, str) or not value for value in ids):
            raise ValueError("Selected track IDs must be unique non-empty strings")
        if not isinstance(semantic_reason, str) or not semantic_reason.strip() or len(semantic_reason) > 300:
            raise ValueError("semantic_reason must contain 1 to 300 characters")
        state = self._perception
        if state is None or state.source_frame_age_ms > self._max_perception_age_ms:
            raise BehaviorError("stale_perception", "Refresh visual grounding before selecting a subject.")
        visible = {person.track_id for person in state.people}
        if any(track_id not in visible for track_id in ids):
            raise BehaviorError("target_missing", "Selected subject track is not currently visible.")
        self._selected_subject_track_ids = ids
        self._selection_reason = semantic_reason.strip()
        return self.snapshot()

    def arm(self, *, lease_ms, operator_confirmed):
        if operator_confirmed is not True:
            raise BehaviorError("operator_confirmation_required", "Live Director arming needs operator confirmation.")
        if self._actuator is None:
            raise BehaviorError(
                "motion_adapter_unavailable",
                "No supervised physical behavior adapter is connected.",
            )
        if type(lease_ms) is not int or not 1_000 <= lease_ms <= 120_000:
            raise ValueError("Arming lease must be 1000 to 120000 milliseconds")
        self._arm_token = secrets.token_urlsafe(24)
        self._arm_expires_ns = self._clock() + lease_ms * 1_000_000
        return {"arm_token": self._arm_token, "expires_monotonic_ns": str(self._arm_expires_ns)}

    def disarm(self, reason="operator_disarmed"):
        # Revoke authority before touching behavior state so an expired lease can
        # never recurse through snapshot()->_armed()->disarm().
        self._arm_token = None
        self._arm_expires_ns = 0
        if self._behavior and self._behavior.state in ACTIVE_STATES:
            self.hold(reason=reason)

    def _armed(self):
        if self._arm_token is None:
            return False
        if self._clock() >= self._arm_expires_ns:
            self.disarm("arming_lease_expired")
            return False
        return True

    def _require_fresh_subjects(self, goal):
        state = self._perception
        if state is None:
            raise BehaviorError("perception_required", "Inspect the current scene before preparing motion.")
        if state.source_frame_age_ms > self._max_perception_age_ms:
            raise BehaviorError("stale_perception", "The visual state is too old to prepare motion.")
        visible = {person.track_id for person in state.people}
        missing = [track_id for track_id in goal.subject_track_ids if track_id not in visible]
        if missing:
            raise BehaviorError("target_missing", "Selected subject track is not currently visible.")

    def _compile(self, goal):
        template_id = RELATION_TEMPLATE[goal.camera_relation]
        subject_motion = "walk" if goal.camera_relation in ("follow", "lead") else "hold"
        settings = {"mode": "template", "template_id": template_id, "subject_motion": subject_motion}
        if self._compiler is None:
            from takeone.previs.cache import compile_preview

            preview = compile_preview(settings)
        else:
            preview = self._compiler(settings)
        plan_id = preview.get("plan_id")
        if not isinstance(plan_id, str) or not plan_id:
            raise BehaviorError("plan_unavailable", "The local planner returned no plan identity.")
        return preview

    def prepare(self, goal):
        if not isinstance(goal, FilmingGoal):
            raise ValueError("prepare requires a FilmingGoal")
        if self._behavior is not None and self._behavior.state in ACTIVE_STATES:
            raise BehaviorError(
                "behavior_active",
                "Hold or stop the active filming behavior before preparing a replacement.",
            )
        self._require_fresh_subjects(goal)
        if self._perception is not None and len(self._perception.people) > 1:
            selected = set(self._selected_subject_track_ids)
            requested = set(goal.subject_track_ids)
            if not selected:
                raise BehaviorError(
                    "subject_selection_required",
                    "Multiple people are visible; bind the intended transient track IDs first.",
                )
            if requested != selected:
                raise BehaviorError(
                    "subject_selection_mismatch",
                    "The filming goal does not match the currently selected subject tracks.",
                )
        preview = self._compile(goal)
        behavior = Behavior(str(uuid4()), goal, preview["plan_id"], "HOLDING", 1)
        self._behavior = behavior
        self._latest_servo = None
        self._settle_streak = 0
        self._low_confidence_since_ns = None
        return {
            "behavior_id": behavior.behavior_id,
            "plan_id": behavior.plan_id,
            "state": behavior.state,
            "physical_motion": False,
            "template_id": RELATION_TEMPLATE[goal.camera_relation],
        }

    def adjust(self, behavior_id, *, screen_target_uv=None, desired_subject_size_range=None):
        behavior = self._behavior
        if behavior is None or behavior.behavior_id != behavior_id:
            raise BehaviorError("unknown_behavior", "Adjust the current behavior by its behavior_id.")
        changes = behavior.goal.wire()
        if screen_target_uv is not None:
            changes["screen_target_uv"] = tuple(screen_target_uv)
        if desired_subject_size_range is not None:
            changes["desired_subject_size_range"] = tuple(desired_subject_size_range)
        adjusted = FilmingGoal(**changes)
        if adjusted.subject_track_ids != behavior.goal.subject_track_ids:
            raise BehaviorError("subject_change_requires_prepare", "Changing subjects requires a new prepared behavior.")
        if adjusted.camera_relation != behavior.goal.camera_relation:
            raise BehaviorError("motion_change_requires_prepare", "Changing camera relation requires a new prepared behavior.")
        behavior.goal = adjusted
        behavior.revision += 1
        self._settle_streak = 0
        return self.snapshot()

    def start(self, behavior_id):
        behavior = self._behavior
        if behavior is None or behavior.behavior_id != behavior_id:
            raise BehaviorError("unknown_behavior", "Prepare this behavior before starting it.")
        if not self._armed():
            raise BehaviorError("live_director_disarmed", "Live Director motion is disarmed; simulation remains available.")
        if self._actuator is None:
            raise BehaviorError("motion_adapter_unavailable", "No supervised physical behavior adapter is connected.")
        if behavior.goal.recording_policy != "manual" and self._recorder is None:
            raise BehaviorError("recorder_unavailable", "This behavior requires a recording adapter before motion can start.")
        self._require_fresh_subjects(behavior.goal)
        accepted = self._actuator.start(behavior.plan_id, behavior.goal)
        if not accepted:
            raise BehaviorError("motion_rejected", "The local motion adapter rejected this behavior.")
        if behavior.goal.camera_relation in ("follow", "lead"):
            behavior.state = "FOLLOWING"
        elif behavior.goal.camera_relation == "hold":
            behavior.state = "REFRAMING"
        else:
            behavior.state = "APPROACHING"
        behavior.started_ns = self._clock()
        behavior.revision += 1
        self._settle_streak = 0
        self._low_confidence_since_ns = None
        if behavior.goal.recording_policy == "immediate":
            self._start_recording(behavior)
        return self.snapshot()

    def _start_recording(self, behavior):
        if self._recorder is None:
            raise BehaviorError("recorder_unavailable", "No behavior recording adapter is connected.")
        take_id = self._recorder.start(behavior.plan_id, behavior.goal, behavior.behavior_id)
        if not isinstance(take_id, str) or not take_id:
            raise BehaviorError("recording_rejected", "The recording adapter did not return a take identity.")
        behavior.take_id = take_id
        behavior.state = "RECORDING"
        behavior.revision += 1

    def _stop_recording(self, behavior, reason):
        if behavior.take_id is None:
            return
        if self._recorder is not None:
            self._recorder.stop(behavior.take_id, reason)
        behavior.take_id = None

    def hold(self, reason="hold_requested"):
        behavior = self._behavior
        if behavior is None:
            return self.snapshot()
        if self._actuator is not None and behavior.state in ACTIVE_STATES:
            self._actuator.hold()
        self._stop_recording(behavior, reason)
        self._settle_streak = 0
        self._low_confidence_since_ns = None
        behavior.state = "HOLDING"
        behavior.termination_reason = reason
        behavior.revision += 1
        return self.snapshot()

    def stop(self, reason="stop_requested"):
        behavior = self._behavior
        if behavior is None:
            return self.snapshot()
        if self._actuator is not None and behavior.state in ACTIVE_STATES:
            self._actuator.stop()
        self._stop_recording(behavior, reason)
        self._settle_streak = 0
        self._low_confidence_since_ns = None
        behavior.state = "STOPPING"
        behavior.termination_reason = reason
        behavior.revision += 1
        return self.snapshot()

    def snapshot(self):
        behavior = self._behavior
        return {
            "armed": self._armed(),
            "actuator_available": self._actuator is not None,
            "arm_expires_monotonic_ns": str(self._arm_expires_ns) if self._arm_token else None,
            "servo": self._latest_servo.wire() if self._latest_servo is not None else None,
            "settle_streak": self._settle_streak,
            "selected_subject_track_ids": list(self._selected_subject_track_ids),
            "selection_reason": self._selection_reason,
            "behavior": None
            if behavior is None
            else {
                "behavior_id": behavior.behavior_id,
                "plan_id": behavior.plan_id,
                "state": behavior.state,
                "revision": behavior.revision,
                "take_id": behavior.take_id,
                "goal": behavior.goal.wire(),
                "termination_reason": behavior.termination_reason,
            },
        }
