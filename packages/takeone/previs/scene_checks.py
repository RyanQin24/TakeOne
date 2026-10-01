"""Nominal staging intersections; these are not hardware collision qualification."""

import math

from .diagnostics import Diagnostic


def sampled_scene_clearance(shot, settings, scene, mark, preview):
    """Screen the full rig against time-matched actor and object envelopes.

    MuJoCo geometry bounding spheres make this conservative and can flag a
    false positive. Midpoint FK is checked too; no continuous swept or dynamics
    guarantee follows from a positive sampled minimum.
    """
    import mujoco
    import numpy as np

    from takeone.config import read_json
    from takeone.paths import CONFIGS
    from takeone.simulation.robot import load_model

    from .screen_review import actor_poses, object_boxes
    from .travel_review import filmed_window

    frames, _, _ = filmed_window(shot, preview)
    model = load_model()
    data = mujoco.MjData(model)
    ids = [i for i in range(model.ngeom) if model.geom_bodyid[i] != 0 and model.geom_group[i] != 2]
    radii = model.geom_rbound[ids]
    actor_config = read_json(CONFIGS / "scene.json")["actor"]
    stature = settings["subject_height_m"] / actor_config["height_reference_m"]
    radius = actor_config["radius_at_1_72m"] * stature
    height = actor_config["height_envelope_at_1_72m"] * stature
    boxes = object_boxes(scene, mark)
    minimum, worst, count = float("inf"), None, 0

    def record(distances, other, time_s):
        nonlocal minimum, worst
        index = int(np.argmin(distances))
        if distances[index] < minimum:
            minimum = float(distances[index])
            worst = dict(
                rig_geometry=model.geom(ids[index]).name or str(ids[index]),
                target=other,
                edit_s=time_s - preview["orbit_start_s"],
            )

    for index, frame in enumerate(frames):
        samples = [(frame["q"], actor_poses(shot, scene, frame), frame["time_s"])]
        if index + 1 < len(frames):
            next_frame = frames[index + 1]
            left, right = actor_poses(shot, scene, frame), actor_poses(shot, scene, next_frame)
            midpoint = {
                key: dict(
                    pose,
                    position_m=[(a + b) / 2 for a, b in zip(pose["position_m"], right[key]["position_m"])],
                )
                for key, pose in left.items()
                if key in right
            }
            samples.append(
                (
                    (np.asarray(frame["q"]) + next_frame["q"]) / 2,
                    midpoint,
                    (frame["time_s"] + next_frame["time_s"]) / 2,
                )
            )
        for q, actors, stamp in samples:
            data.qpos[:] = q
            mujoco.mj_forward(model, data)
            count += 1
            positions = data.geom_xpos[ids]
            for actor_id, pose in actors.items():
                delta = positions - np.asarray(pose["position_m"])
                d = np.column_stack(
                    (
                        np.linalg.norm(delta[:, :2], axis=1) - radius,
                        abs(delta[:, 2] - height / 2) - height / 2,
                    )
                )
                distances = (
                    np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(np.max(d, axis=1), 0) - radii
                )
                record(distances, "actor:" + actor_id, stamp)
            for name, center, size, yaw in boxes:
                c, s = math.cos(yaw), math.sin(yaw)
                rotation = np.asarray([[c, s, 0], [-s, c, 0], [0, 0, 1]])
                local = (positions - np.asarray(center)) @ rotation.T
                d = abs(local) - np.asarray(size) / 2
                distances = (
                    np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(np.max(d, axis=1), 0) - radii
                )
                record(distances, "object:" + name, stamp)
    return dict(
        source="nominal_rig_bounding_spheres_and_time_matched_actor_object_envelopes",
        sampled_clearance_lower_bound_m=minimum if math.isfinite(minimum) else None,
        status="potential_intersection" if minimum < 0.015 else "sampled_clear",
        worst=worst,
        samples=count,
        midpoint_fk=True,
        physical_qualification=False,
        scope="All modeled rig geometry versus staged actors/objects; conservative proxy overlaps need review. "
        "Not continuous swept clearance, rig self-collision certification, cable clearance, measured human timing or dynamics.",
    )


def obstacles(scene, preview, stage, shot_id):
    found = []
    c, s = math.cos(stage["heading_rad"]), math.sin(stage["heading_rad"])
    for obj in scene.get("objects", []):
        w, d, h = obj["size_m"]
        if obj["position_m"][2] - h / 2 > 1.1:
            continue
        yaw = obj["yaw_rad"]
        cy, sy = math.cos(yaw), math.sin(yaw)
        rects = (
            [(-w * 0.44, 0, w * 0.12, d), (w * 0.44, 0, w * 0.12, d)]
            if obj["asset_id"] in ("doorway", "arch")
            else [(0, 0, w, d)]
        )
        if obj["asset_id"] == "tree":
            rects = [(0, 0, w * 0.35, d * 0.35)]
        for frame in preview["frames"]:
            x, y = frame["q"][:2]
            x, y = stage["origin_m"][0] + c * x - s * y, stage["origin_m"][1] + s * x + c * y
            dx, dy = x - obj["position_m"][0], y - obj["position_m"][1]
            x, y = cy * dx + sy * dy, -sy * dx + cy * dy
            if any(
                math.hypot(max(abs(x - rx) - rw / 2, 0), max(abs(y - ry) - rd / 2, 0)) < 0.55
                for rx, ry, rw, rd in rects
            ):
                found.append(
                    Diagnostic(
                        shot_id,
                        "scene_obstruction",
                        f"The nominal cart footprint intersects {obj['label'] or obj['object_id']}. Move the prop or revise the route.",
                        suggestion="This staging screen uses a 0.55 m cart radius; inspect arms and real clearances separately.",
                    )
                )
                break
    return found
