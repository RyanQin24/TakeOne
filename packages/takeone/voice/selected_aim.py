"""Local selected-person image-space objective. No depth or actuator guesses."""

import math

from takeone.embodied import FilmingGoal, VisualServoController
from takeone.perception import PerceptionState


def selected_person_aim(state, selected_track_id, *, now_ns, source_role):
    """Requires an observation from the phone's own optical view, not the cart webcam.

    Perception/selection must be supplied by the local vision owner, never model arguments.
    A controller with measured camera calibration/Jacobian is still required to actuate.
    """
    if source_role != "phone":
        raise ValueError("Phone aiming requires its optical view or a separately calibrated transform")
    if not isinstance(state, PerceptionState) or type(now_ns) is not int:
        raise ValueError("Typed perception and a local monotonic time are required")
    age_ms = (now_ns - state.monotonic_timestamp_ns) / 1e6 + state.source_frame_age_ms
    if now_ns < state.monotonic_timestamp_ns or not 0 <= age_ms <= 250:
        raise ValueError("Selected-person observation is stale or from a future clock")
    if not selected_track_id or selected_track_id not in state.active_subject_track_ids:
        raise ValueError("Select a visible person locally before asking the arm to face them")
    person = next((p for p in state.people if p.track_id == selected_track_id), None)
    if person is None or not 0 <= (now_ns - person.last_seen_ns) / 1e6 <= 250:
        raise ValueError("Selected person is lost; do not switch to another person")
    if not math.isfinite(person.confidence) or not 0.7 <= person.confidence <= 1:
        raise ValueError("Selected-person confidence is insufficient")
    goal = FilmingGoal(
        subject_track_ids=(selected_track_id,),
        subject_relation="one_person",
        camera_relation="hold",
        framing="medium",
        recording_policy="manual",
    )
    result = VisualServoController().intent(goal, state)
    return dict(
        code="image_aim_objective_only",
        selected_track_id=selected_track_id,
        aim_error_uv=list(result.aim_error_uv),
        observed_age_ms=age_ms,
        cart_action="hold",
        depth_m=None,
        executable=False,
        hardware_commands_sent=False,
        message="Center this selected person using local calibrated feedback. "
        "Image error is not a motor command or a measured 3D target.",
    )
