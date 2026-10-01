"""One rehearsal clock over the shots of a Director script.

The outline carries timing, placement and the exact settings for each segment; the
studio fetches each segment's frames from the endpoints that already exist. Nothing
here narrows what a shot may ask for: every check produces an advisory note, and a
script whose marks carry no coordinates rehearses exactly as it does today.
"""

import math

from takeone.motion.plan import digest
from takeone.simulation.drive import HEADING_OFFSET

from . import diagnostics
from .cache import compile_preview
from .reposition import prepare as prepare_reposition
from .templates import BY_ID, preview_geometry, route_filming_time_s

IDENTITY = dict(origin_m=[0.0, 0.0], heading_rad=0.0)
SET_LIMIT_M = 100.0
LONG_MOVE_S = 8.0


def place(stage, x, y):
    c, s = math.cos(stage["heading_rad"]), math.sin(stage["heading_rad"])
    return [stage["origin_m"][0] + x * c - y * s, stage["origin_m"][1] + x * s + y * c]


def stage_for(mark, preview):
    """Put the shot's actor on its mark, facing the direction the script asked for."""
    if not isinstance(mark, dict) or not isinstance(mark.get("position_m"), list):
        return dict(IDENTITY)
    origin = [float(mark["position_m"][0]), float(mark["position_m"][1])]
    facing = mark.get("facing_rad")
    if type(facing) not in (int, float) or not math.isfinite(facing):
        return dict(origin_m=origin, heading_rad=0.0)
    opening = next(f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"] - 1e-8)
    staged = opening["actor"]["heading_rad"]
    return dict(origin_m=origin, heading_rad=float(facing) - staged)


def axle_pose(frame, stage):
    """Axle pose in set coordinates: [x, y, drive heading]."""
    x, y = place(stage, float(frame["axle_m"][0]), float(frame["axle_m"][1]))
    return [float(x), float(y), float(frame["q"][2]) + HEADING_OFFSET + stage["heading_rad"]]


def shot_diagnostics(shot, settings, preview, stage):
    """Everything the simulator observed. All advisory: the shot already compiled."""
    shot_id = shot["shot_id"]
    summary = dict(preview["summary"])
    summary.setdefault("requested_camera_height_m", settings["height_start_m"])
    found = [
        diagnostics.timing(shot_id, preview["orbit_duration_s"], (shot["end_ms"] - shot["start_ms"]) / 1000),
        diagnostics.framing(shot_id, shot.get("framing"), preview_geometry(preview))
        if shot.get("camera_target", {}).get("kind", "actor") == "actor"
        else None,
        diagnostics.placement(shot_id, stage["origin_m"], SET_LIMIT_M),
    ]
    found.extend(diagnostics.reach(shot_id, summary))
    if settings["subject_motion"] == "walk" and BY_ID[settings["template_id"]]["route"] in (
        "lead",
        "follow",
        "side",
    ):
        if abs(settings["actor_distance_m"] - settings["distance_m"]) > 0.1:
            found.append(
                diagnostics.Diagnostic(
                    shot_id,
                    "follow_distance_mismatch",
                    f"The actor travels {settings['actor_distance_m']:.2f} m while the cart travels {settings['distance_m']:.2f} m. Following distance changes during this take.",
                    parameter="actor_distance_m",
                    suggestion="Match actor and cart distances for constant following distance, or explicitly plan the change in framing.",
                )
            )
    return [d for d in found if d]


def shot_segment(shot, stage, preview, index, start_s):
    settings = shot["settings"]
    found = shot_diagnostics(shot, settings, preview, stage)
    return dict(
        segment_id=f"shot-{index:02d}",
        kind="shot",
        index=index,
        shot_id=shot["shot_id"],
        scene_id=shot.get("scene_id", "scene-1"),
        space_id=shot.get("space_id", "scene-1"),
        transition=shot.get("transition", "reposition"),
        tracking=shot.get("tracking"),
        camera_target=shot.get("camera_target"),
        name=BY_ID[settings["template_id"]]["name"],
        template_id=settings["template_id"],
        t0_s=start_s,
        duration_s=preview["duration_s"],
        setup_s=preview["orbit_start_s"],
        filming_s=preview["orbit_duration_s"],
        planned_filming_s=route_filming_time_s(settings),
        settings=settings,
        stage=stage,
        mark_id=shot["mark_id"],
        edit=dict(start_ms=shot["start_ms"], end_ms=shot["end_ms"]),
        dialogue=shot.get("dialogue"),
        action=shot.get("action"),
        audio_intent=shot.get("audio_intent", ""),
        defaulted_parameters=shot.get("defaulted_parameters", []),
        plan_id=preview["plan_id"],
        notes=list(preview["notes"]),
        diagnostics=[d.wire() for d in found],
        advice=[d.message for d in found],
        error=None,
        assessment="needs_revision" if found else "reviewable",
        summary=dict(preview["summary"]),
        camera_output=preview.get("camera_output"),
    )


def reposition_segment(previous, stage, preview, index, start_s):
    """None when the rig already stands where the next take begins."""
    last = previous["preview"]["frames"][-1]
    request = dict(
        from_axle_m=axle_pose(last, previous["stage"]),
        to_axle_m=axle_pose(preview["frames"][0], stage),
        from_raw=last["raw_by_role"],
    )
    _, _, route, _, park_s, duration = prepare_reposition(request)
    if not duration:
        return None
    long_move = [d for d in [diagnostics.long_move(f"move-{index:02d}", duration, LONG_MOVE_S)] if d]
    return dict(
        segment_id=f"move-{index:02d}",
        kind="reposition",
        index=index,
        shot_id=None,
        name="Move to the next mark",
        t0_s=start_s,
        duration_s=duration,
        setup_s=0.0,
        filming_s=duration,
        reposition=request,
        stage=None,
        notes=[
            "Moving between marks. Both arms return to their calibrated midpoints; "
            "the next take aims from there. This travel is a kinematic estimate, not a qualified plan."
        ],
        diagnostics=[d.wire() for d in long_move],
        advice=[d.message for d in long_move],
        summary=dict(
            distance_m=math.dist(request["from_axle_m"][:2], request["to_axle_m"][:2]),
            cart_duration_s=route["cart_s"] if route else 0.0,
            arm_park_duration_s=park_s,
        ),
        error=None,
    )


def build_program(manifest):
    from .scene_checks import obstacles

    marks = {m["mark_id"]: m for m in manifest.get("marks", []) if isinstance(m, dict)}
    scenes = {s["scene_id"]: s for s in manifest.get("scenes", [])}
    segments, clock, previous, index = [], 0.0, None, 0
    shot_number = 0
    relocations = []
    for shot in manifest["shots"]:
        shot_number += 1
        if shot.get("settings") is None:
            reason = shot.get("diagnostic")
            segments.append(
                dict(
                    segment_id=f"shot-{index:02d}",
                    kind="unavailable",
                    index=index,
                    shot_id=shot["shot_id"],
                    name=shot.get("name", "Movement needs direction"),
                    t0_s=clock,
                    duration_s=0.0,
                    stage=None,
                    edit=dict(start_ms=shot["start_ms"], end_ms=shot["end_ms"]),
                    dialogue=shot.get("dialogue"),
                    action=shot.get("action"),
                    notes=[],
                    diagnostics=[reason] if reason else [],
                    advice=[],
                    error=shot.get("error", "This shot has no movement yet."),
                )
            )
            index += 1
            continue
        preview = compile_preview(shot["settings"])
        stage = stage_for(marks.get(shot["mark_id"]), preview)
        if shot.get("coordinate_mode") == "scene_local":
            stage["heading_rad"] = 0.0
        same_space = previous is not None and previous["space_id"] == shot.get("space_id", "scene-1")
        if previous is not None and not same_space:
            relocations.append(
                dict(
                    before_shot_id=shot["shot_id"],
                    scene_id=shot.get("scene_id"),
                    duration_s=None,
                    message="New location: reset the rig and actors. Relocation time is not estimated.",
                )
            )
        if same_space and shot.get("transition", "reposition") == "reposition":
            move = reposition_segment(previous, stage, preview, index, clock)
            if move:
                move.update(
                    scene_id=shot.get("scene_id", "scene-1"), space_id=shot.get("space_id", "scene-1")
                )
                segments.append(move)
                clock += move["duration_s"]
                index += 1
        segment = shot_segment(shot, stage, preview, index, clock)
        segment["shot_number"] = shot_number
        clashes = obstacles(scenes.get(shot.get("scene_id"), {}), preview, stage, shot["shot_id"])
        if clashes:
            segment["diagnostics"].extend(d.wire() for d in clashes)
            segment["advice"].extend(d.message for d in clashes)
            segment["assessment"] = "needs_revision"
        segments.append(segment)
        clock += preview["duration_s"]
        previous = dict(stage=stage, preview=preview, space_id=shot.get("space_id", "scene-1"))
        index += 1
    program = dict(
        kind="takeone_rehearsal_program",
        schema_version=1,
        title=manifest["title"],
        session_id=manifest["session_id"],
        document_digest=manifest["document_digest"],
        manifest_digest=manifest["manifest_digest"],
        coordinate_frame="set: X/Y floor, Z up. Each shot is placed on its script mark.",
        segments=segments,
        duration_s=clock,
        edit_duration_s=max((s["edit"]["end_ms"] for s in segments if s.get("edit")), default=0) / 1000,
        marks=[marks[k] for k in sorted(marks)],
        scenes=manifest.get("scenes", []),
        actors=manifest.get("actors", []),
        relocations=relocations,
        needs_revision_shot_ids=[s["shot_id"] for s in segments if s.get("assessment") == "needs_revision"],
        blocked_shot_ids=[s["shot_id"] for s in segments if s["kind"] == "unavailable"],
        timebase="seconds from the start of the rehearsal, including arm setup and moves",
    )
    return {**program, "program_digest": digest(program)}
