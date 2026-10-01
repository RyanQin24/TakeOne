"""Story-level camera motifs compiled into existing TakeOne movement settings.

Motifs are planning vocabulary, not new hardware primitives. They expose reusable
cinematic relationships while keeping the 38 low-level movement templates as the
physical building blocks. The Director may choose a motif, then still author exact
parameters. No device I/O occurs here.
"""

from __future__ import annotations

import copy
import math

from takeone.previs.channels import ramp
from takeone.previs.templates import defaults_for, validate_settings

DEG = math.pi / 180
LIGHT_ROLES = (
    "natural",
    "key",
    "fill",
    "eye_fill",
    "edge",
    "product_glint",
    "practical_motivated",
    "background_accent",
)


def _phase(start, end, actor, cart, phone, light, note):
    return dict(at=[start, end], actor=actor, cart=cart, phone=phone, light=light, note=note)


MOTIFS = {
    "walk_angle_change": dict(
        name="Walk-and-talk lead → angle change",
        intent="Travel with the performer, then let the camera relationship change before the cut.",
        templates=["side_track", "track_lead", "track_follow"],
        duration_s=[6.0, 10.0],
        subject_motion="walk",
        light_role="eye_fill",
        phases=[
            _phase(0.0, 0.18, "walk", "hold", "hold", "track", "Performer establishes movement."),
            _phase(0.18, 0.72, "walk", "travel", "track", "track", "Robot joins and carries the move."),
            _phase(0.72, 0.90, "settle", "travel", "reframe", "side_fill", "Performer slows while camera relationship changes."),
            _phase(0.90, 1.0, "hold", "hold", "hold", "hold", "Hold a clean final composition."),
        ],
    ),
    "side_track_push": dict(
        name="Side-track → push",
        intent="Travel beside the action, then bend inward for an emphasis beat.",
        templates=["arc_push"],
        duration_s=[7.0, 12.0],
        subject_motion="walk",
        light_role="fill",
        phases=[
            _phase(0.0, 0.20, "walk", "travel", "track", "track", "Establish lateral movement."),
            _phase(0.20, 0.72, "walk", "travel", "track", "track", "Maintain readable moving relationship."),
            _phase(0.72, 0.92, "settle", "approach", "reframe", "settle", "Convert travel into emphasis."),
            _phase(0.92, 1.0, "hold", "hold", "hold", "hold", "Finish without a mechanical snap."),
        ],
    ),
    "foreground_reveal_push": dict(
        name="Foreground reveal → short push",
        intent="Clear a foreground edge, then approach the revealed subject.",
        templates=["pass_by", "arc_push"],
        duration_s=[5.0, 9.0],
        subject_motion="hold",
        light_role="practical_motivated",
        phases=[
            _phase(0.0, 0.18, "hold", "travel", "hold", "hold", "Begin partially obscured by foreground."),
            _phase(0.18, 0.62, "hold", "travel", "track", "track", "Clear foreground and discover subject."),
            _phase(0.62, 0.90, "hold", "approach", "rise", "side_fill", "Finish with a compact emphasis move."),
            _phase(0.90, 1.0, "hold", "hold", "hold", "hold", "Hold reveal."),
        ],
    ),
    "low_eye_hero_push": dict(
        name="Low-to-eye hero push",
        intent="Approach while the optical centre rises into a more direct eye-level relationship.",
        templates=["push_in"],
        duration_s=[5.0, 9.0],
        subject_motion="hold",
        light_role="key",
        phases=[
            _phase(0.0, 0.12, "hold", "hold", "low_hold", "key", "Read the lower opening relationship."),
            _phase(0.12, 0.82, "hold", "approach", "rise_track", "key", "Approach and rise together."),
            _phase(0.82, 1.0, "hold", "settle", "settle", "settle", "Arrive at eye-level emphasis."),
        ],
    ),
    "pass_by_pan_back": dict(
        name="Pass-by → pan back",
        intent="Let the base continue past the subject while the phone keeps visual attention behind the chassis heading.",
        templates=["pass_by"],
        duration_s=[6.0, 10.0],
        subject_motion="hold",
        light_role="edge",
        phases=[
            _phase(0.0, 0.24, "hold", "travel", "forward_look", "track", "Approach the crossing point."),
            _phase(0.24, 0.76, "hold", "travel", "retain_subject", "edge", "Base passes while camera relationship rotates."),
            _phase(0.76, 1.0, "hold", "travel_settle", "pan_back", "settle", "Finish looking back without reversing base travel."),
        ],
    ),
    "dialogue_attention_arc": dict(
        name="Dialogue attention arc",
        intent="Hold a conversational composition, make one modest perspective change, then settle.",
        templates=["arc_left", "arc_right"],
        duration_s=[5.0, 9.0],
        subject_motion="hold",
        light_role="fill",
        phases=[
            _phase(0.0, 0.24, "hold", "hold", "hold", "fill", "Let dialogue own the opening."),
            _phase(0.24, 0.76, "hold", "arc", "track", "fill", "Change perspective only with the attention shift."),
            _phase(0.76, 1.0, "hold", "settle", "hold", "hold", "Settle for the response."),
        ],
    ),
    "retreat_context": dict(
        name="Retreat-to-context reveal",
        intent="Retreat from a close relationship while the environment enters the frame.",
        templates=["pull_out"],
        duration_s=[5.0, 9.0],
        subject_motion="hold",
        light_role="practical_motivated",
        phases=[
            _phase(0.0, 0.16, "hold", "hold", "close_hold", "key", "Begin on the decision."),
            _phase(0.16, 0.84, "hold", "retreat", "reframe", "track", "Reveal context without abandoning the subject."),
            _phase(0.84, 1.0, "hold", "settle", "hold", "hold", "Finish with readable environment."),
        ],
    ),
    "actor_stop_camera_continue": dict(
        name="Actor stop / camera continue",
        intent="Let performer locomotion finish first, then continue the camera move for parallax and emphasis.",
        templates=["side_track", "track_lead"],
        duration_s=[6.0, 10.0],
        subject_motion="walk",
        light_role="eye_fill",
        phases=[
            _phase(0.0, 0.12, "walk", "hold", "hold", "track", "Performer initiates."),
            _phase(0.12, 0.66, "walk", "travel", "track", "track", "Actor and robot travel together."),
            _phase(0.66, 0.88, "hold", "travel", "reframe", "side_fill", "Actor stops; camera continues."),
            _phase(0.88, 1.0, "hold", "hold", "hold", "hold", "Hold the changed relationship."),
        ],
    ),
    "camera_stop_actor_continue": dict(
        name="Camera stop / actor continue",
        intent="Settle the robot first and let the performer finish through the composed frame.",
        templates=["static"],
        duration_s=[5.0, 9.0],
        subject_motion="walk",
        light_role="fill",
        phases=[
            _phase(0.0, 0.22, "walk", "hold", "track", "track", "Performer crosses into the composition."),
            _phase(0.22, 0.48, "walk", "hold", "settle", "settle", "Camera relationship stops changing."),
            _phase(0.48, 0.86, "walk", "hold", "hold", "hold", "Performer carries the frame alone."),
            _phase(0.86, 1.0, "hold", "hold", "hold", "hold", "Finish on stillness."),
        ],
    ),
    "three_beat_oner": dict(
        name="Three-beat oner · discover, follow, settle",
        intent="One compact take moves from discovery through locomotion to a held final frame.",
        templates=["side_track"],
        duration_s=[8.0, 12.0],
        subject_motion="walk",
        light_role="practical_motivated",
        phases=[
            _phase(0.0, 0.20, "walk", "hold", "reveal", "track", "Discover performer before the base commits."),
            _phase(0.20, 0.70, "walk", "travel", "track_rise", "track", "Carry the action together."),
            _phase(0.70, 0.90, "settle", "travel", "reframe", "side_fill", "Actor settles; robot finishes."),
            _phase(0.90, 1.0, "hold", "hold", "hold", "hold", "Hold the earned ending."),
        ],
    ),
    "product_parallax_light": dict(
        name="Product parallax + light sweep",
        intent="Use a short camera move and an independent light gesture to reveal form on a static object.",
        templates=["product_orbit", "product_macro"],
        duration_s=[5.0, 9.0],
        subject_motion="none",
        light_role="product_glint",
        phases=[
            _phase(0.0, 0.18, "none", "hold", "hold", "edge_start", "Establish product shape."),
            _phase(0.18, 0.78, "none", "travel", "compensate", "glint_sweep", "Create parallax and move the highlight."),
            _phase(0.78, 1.0, "none", "settle", "hold", "edge_hold", "Hold the final surface read."),
        ],
    ),
    "doorway_arrival": dict(
        name="Doorway arrival",
        intent="Let architecture reveal the performer before the robot joins their movement.",
        templates=["side_track", "track_lead"],
        duration_s=[6.0, 10.0],
        subject_motion="walk",
        light_role="practical_motivated",
        phases=[
            _phase(0.0, 0.20, "walk", "hold", "hold", "door_spill", "Actor crosses the threshold while camera waits."),
            _phase(0.20, 0.70, "walk", "travel", "track", "track", "Robot joins after the reveal."),
            _phase(0.70, 0.90, "settle", "travel", "reframe", "side_fill", "Actor stops; camera finishes."),
            _phase(0.90, 1.0, "hold", "hold", "hold", "hold", "End on a stable arrival frame."),
        ],
    ),
}


def catalog():
    """Compact planning vocabulary exposed to Director/voice without motor details."""
    return {
        "principle": "Choose a story relationship first; resolve it into existing templates and channels.",
        "light_roles": list(LIGHT_ROLES),
        "motifs": [
            {
                "id": motif_id,
                "name": value["name"],
                "intent": value["intent"],
                "templates": list(value["templates"]),
                "duration_s": list(value["duration_s"]),
                "subject_motion": value["subject_motion"],
                "light_role": value["light_role"],
                "phases": copy.deepcopy(value["phases"]),
            }
            for motif_id, value in MOTIFS.items()
        ],
    }


def _bounded(value, low, high):
    return min(high, max(low, float(value)))


def _short_breath():
    return dict(pre_hold_s=0.10, post_hold_s=0.20, entry_s=0.25, exit_s=0.25)


def _base_settings(template_id, duration_s, radius_m, focal_mm, speed_m_s):
    settings = copy.deepcopy(defaults_for(template_id))
    settings.update(
        radius_m=_bounded(radius_m, 1.6, 4.0),
        focal_mm=_bounded(focal_mm, 20.0, 85.0),
        speed_m_s=_bounded(speed_m_s, 0.14, 0.24),
    )
    route = template_id
    if route in {"static"}:
        settings["duration_s"] = duration_s
    elif route in {"push_in", "pull_out", "track_follow", "track_lead", "side_track", "truck_left", "truck_right"}:
        settings["distance_m"] = _bounded(settings["speed_m_s"] * duration_s * 0.88, 0.35, 1.5)
    elif route in {"arc_left", "arc_right", "product_orbit"}:
        arc = settings["speed_m_s"] * duration_s * 0.88 / settings["radius_m"]
        settings["sweep_rad"] = _bounded(arc, 15 * DEG, 35 * DEG)
    elif route == "pass_by":
        settings["distance_m"] = _bounded(settings["speed_m_s"] * max(2.0, duration_s - 0.8), 0.45, 1.25)
        settings["breath"] = _short_breath()
    elif route == "arc_push":
        settings["radius_m"] = _bounded(radius_m, 1.6, 2.4)
        settings["sweep_rad"] = 15 * DEG
        settings["distance_m"] = _bounded(0.08 * duration_s - 0.36, 0.20, 0.50)
        settings["breath"] = _short_breath()
    elif route == "product_macro":
        settings["distance_m"] = _bounded(settings["speed_m_s"] * max(2.0, duration_s - 0.8), 0.45, 1.0)
        settings["breath"] = _short_breath()
    return settings


def resolve(
    motif_id,
    duration_s,
    *,
    radius_m=2.3,
    focal_mm=35.0,
    speed_m_s=0.14,
    direction="right",
    preferred_template=None,
):
    """Resolve one motif into validated low-level settings plus an explicit phase plan.

    This is a deterministic planning helper, not an execution plan. The caller may
    override its exact settings or ask the canonical compiler to reject them.
    """
    if motif_id not in MOTIFS:
        raise ValueError("Choose a cinematic motif from the catalog.")
    motif = MOTIFS[motif_id]
    low, high = motif["duration_s"]
    if not low <= duration_s <= high:
        raise ValueError(f"{motif['name']} expects {low:g}–{high:g} seconds of filmed motion.")
    candidates = motif["templates"]
    if preferred_template is not None:
        if preferred_template not in candidates:
            raise ValueError("Preferred template is not compatible with this motif.")
        template_id = preferred_template
    elif direction == "left" and "arc_right" in candidates:
        template_id = "arc_right"
    else:
        template_id = candidates[0]
    settings = _base_settings(template_id, duration_s, radius_m, focal_mm, speed_m_s)
    settings["subject_motion"] = motif["subject_motion"]
    channels = settings["channels"]

    travel = settings.get("distance_m", settings["speed_m_s"] * duration_s * 0.8)
    if motif_id in {"walk_angle_change", "doorway_arrival", "three_beat_oner", "actor_stop_camera_continue"}:
        settings["actor_distance_m"] = travel
        settings["height_start_m"], settings["height_end_m"] = 1.50, 1.54
        channels["actor_position_m"] = ramp([0, 0, 0], [travel, 0, 0], 0.08, 0.72 if motif_id == "actor_stop_camera_continue" else 0.88)
        channels["camera_height_m"] = ramp(1.50, 1.54, 0.18, 0.84)
        channels["actor_heading_rad"] = ramp(0.0, 0.18, 0.70, 0.94)
        channels["gaze_yaw_rad"] = ramp(0.0, -0.18, 0.70, 0.94)
        channels["light_height_m"] = ramp(1.58, 1.53, 0.18, 0.86)
    elif motif_id == "side_track_push":
        settings["actor_distance_m"] = travel * 0.82
        settings["height_start_m"], settings["height_end_m"] = 1.49, 1.54
        channels["actor_position_m"] = ramp([0, 0, 0], [travel * 0.82, 0, 0], 0.05, 0.78)
        channels["camera_height_m"] = ramp(1.49, 1.54, 0.20, 0.88)
        channels["light_height_m"] = ramp(1.58, 1.52, 0.18, 0.86)
    elif motif_id == "foreground_reveal_push":
        settings["height_start_m"], settings["height_end_m"] = 1.48, 1.52
        channels["camera_height_m"] = ramp(1.48, 1.52, 0.40, 0.88)
        channels["light_height_m"] = ramp(1.56, 1.61, 0.35, 0.84)
    elif motif_id == "low_eye_hero_push":
        channels["camera_height_m"] = ramp(1.42, 1.57, 0.12, 0.86)
        channels["light_height_m"] = ramp(1.54, 1.62, 0.18, 0.88)
    elif motif_id == "pass_by_pan_back":
        channels["pan_rad"] = ramp(0.0, -12 * DEG if direction != "left" else 12 * DEG, 0.38, 0.94)
        channels["light_height_m"] = ramp(1.58, 1.53, 0.20, 0.84)
    elif motif_id == "dialogue_attention_arc":
        channels["camera_height_m"] = ramp(1.51, 1.56, 0.30, 0.78)
        channels["light_height_m"] = ramp(1.60, 1.54, 0.28, 0.82)
    elif motif_id == "retreat_context":
        channels["camera_height_m"] = ramp(1.57, 1.49, 0.18, 0.86)
        channels["light_height_m"] = ramp(1.56, 1.62, 0.18, 0.86)
    elif motif_id == "camera_stop_actor_continue":
        channels["actor_position_m"] = ramp([0, 0, 0], [0.8, 0, 0], 0.08, 0.84)
        settings["actor_distance_m"] = 0.8
    elif motif_id == "product_parallax_light":
        settings["subject_motion"] = "none"
        settings["camera_target"] = dict(kind="point", position_m=[0.0, 0.0, 1.4])
        channels["light_target_m"] = ramp([0, -0.22, 1.36], [0, 0.22, 1.44], 0.18, 0.82)
        channels["light_height_m"] = ramp(1.48, 1.62, 0.15, 0.86)
    settings = validate_settings(settings)
    return dict(
        motif_id=motif_id,
        name=motif["name"],
        intent=motif["intent"],
        template_id=template_id,
        light_role=motif["light_role"],
        phases=copy.deepcopy(motif["phases"]),
        settings=settings,
    )
