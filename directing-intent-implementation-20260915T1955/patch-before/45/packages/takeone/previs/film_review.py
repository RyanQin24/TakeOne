"""Edited-window boundary evidence, separate from full-source rehearsal checks."""

import copy
import math

from .screen_review import actor_poses


def edit_boundaries(shot, settings, scene, stage, preview):
    setup = preview["orbit_start_s"]
    duration = (shot["end_ms"] - shot["start_ms"]) / 1000
    available = preview["orbit_duration_s"]
    source_in = preview.get("source_in_s", 0.0)
    filmed = [f for f in preview["frames"] if f["time_s"] >= setup - 1e-8]
    evidence = []
    for local_time in (0.0, min(duration, available)):
        frame = next((f for f in reversed(filmed) if f["time_s"] <= setup + local_time + 1e-8), filmed[0])
        actors = copy.deepcopy(actor_poses(shot, scene, frame))
        c, s = math.cos(stage["heading_rad"]), math.sin(stage["heading_rad"])
        for pose in actors.values():
            x, y, z = pose["position_m"]
            pose["position_m"] = [stage["origin_m"][0]+c*x-s*y, stage["origin_m"][1]+s*x+c*y, z]
            pose["heading_rad"] += stage["heading_rad"]
        evidence.append(dict(edit_local_s=local_time, source_s=source_in+local_time,
            sampled_source_s=source_in+frame["time_s"]-setup, actors=actors,
            raw_optical_pose=copy.deepcopy(frame["camera"]),
            simulated_output_pose=copy.deepcopy(frame.get("camera_view", frame["camera"])),
            focal_mm=frame["focal_mm"]))
        from scipy.spatial.transform import Rotation

        for key in ("raw_optical_pose", "simulated_output_pose"):
            pose = evidence[-1][key]
            x, y, z = pose["pos"]
            pose["pos"] = [stage["origin_m"][0]+c*x-s*y, stage["origin_m"][1]+s*x+c*y, z]
            pose["quat"] = (Rotation.from_euler("z", stage["heading_rad"]) * Rotation.from_quat(pose["quat"])).as_quat().tolist()
    return dict(
        opening=evidence[0], ending=evidence[1], source_window_s=[source_in, source_in+min(duration, available)],
        preview_hold_s=max(0, duration-available), coordinate_frame="scene-local XYZ metres, Z up",
        viewpoint="Simulated processed phone output; raw achieved optical orientation retained separately.",
        boundary_sampling="Preceding actual FK/performer sample; unused source tails and setup are excluded.",
    )


def axis_side(boundary, actor_ids):
    if len(actor_ids) != 2:
        return None
    a, b = [boundary["actors"][key]["position_m"] for key in actor_ids]
    camera = boundary["raw_optical_pose"]["pos"]
    value = (b[0]-a[0])*(camera[1]-a[1]) - (b[1]-a[1])*(camera[0]-a[0])
    return 0 if abs(value) < 1e-6 else 1 if value > 0 else -1


def review_cuts(segments, scenes):
    locations = {s["scene_id"]: s for s in scenes}
    shots = [s for s in segments if s.get("edit_evidence")]
    cuts = []
    for previous, current in zip(shots, shots[1:]):
        left, right = previous["edit_evidence"]["ending"], current["edit_evidence"]["opening"]
        same_space = previous["space_id"] == current["space_id"]
        common = sorted(set(left["actors"]) & set(right["actors"]))
        a = {o["object_id"]: o for o in locations[previous["scene_id"]].get("objects", [])}
        b = {o["object_id"]: o for o in locations[current["scene_id"]].get("objects", [])}
        changed = sorted(key for key in a.keys() | b.keys() if a.get(key) != b.get(key)) if same_space else []
        sides = [axis_side(boundary, common) for boundary in (left, right)] if same_space else [None, None]
        cuts.append(dict(
            before_shot_id=current["shot_id"], after_shot_id=previous["shot_id"], same_space=same_space,
            cut_edit_s=current["edit"]["start_ms"]/1000, actor_ids_on_both_sides=common,
            actor_position_change_m={key: math.dist(left["actors"][key]["position_m"], right["actors"][key]["position_m"])
                                     for key in common} if same_space else {},
            object_staging_changes=changed,
            attention_before={key: left["actors"][key].get("look_target", "unspecified") for key in common},
            attention_after={key: right["actors"][key].get("look_target", "unspecified") for key in common},
            camera_side_of_actor_axis=sides,
            axis_crossing_observed=bool(sides[0] and sides[1] and sides[0] != sides[1]),
            authored_continuity=(current.get("shot_card") or {}).get("continuity", ""),
            interpretation="Review continuity intent; a deliberate cut or axis crossing is not automatically an error.",
        ))
    return dict(source="authored_staging_and_sampled_edited_boundaries", cuts=cuts,
                scope="Identity uses persistent actor IDs/appearance. Object state is fixed staging only; "
                      "no ownership or transfer is simulated. Axis evidence is available only for two common actors. "
                      "This is not recorded-footage, identity-recognition or cinematic-quality evidence.")
