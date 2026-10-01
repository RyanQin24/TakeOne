"""Review authored screen requirements against achieved poses and explicit proxies.

Occlusion is a center sightline test against oriented bounding boxes, not pixel
segmentation. Open furniture is decomposed where supported; proxy uncertainty is
reported. No geometry, lens, motor plan or authored intent is changed here.
"""

import math
from itertools import product

import numpy as np

from .performers import HEAD_RATIO


def corners(center, size, yaw=0):
    c, s = math.cos(yaw), math.sin(yaw)
    rotation = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    return np.array([np.asarray(center) + rotation @ (np.asarray(size) * np.asarray(sign) / 2)
                     for sign in product((-1, 1), repeat=3)])


def intersects(start, end, center, size, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    rotation = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    origin = rotation @ (np.asarray(start) - center)
    delta = rotation @ (np.asarray(end) - start)
    near, far = 0.0, 1.0
    for axis in range(3):
        half = size[axis] / 2
        if abs(delta[axis]) < 1e-10:
            if abs(origin[axis]) > half:
                return False
            continue
        a, b = sorted(((-half - origin[axis]) / delta[axis], (half - origin[axis]) / delta[axis]))
        near, far = max(near, a), min(far, b)
        if near > far:
            return False
    return far > 1e-5 and near < 1 - 1e-5


def object_boxes(scene, mark):
    origin = mark.get("position_m", [0, 0])
    boxes = []
    for obj in scene.get("objects", []):
        center = [obj["position_m"][0] - origin[0], obj["position_m"][1] - origin[1], obj["position_m"][2]]
        w, d, h = obj["size_m"]
        yaw = obj["yaw_rad"]
        parts = [(center, [w, d, h])]
        if obj["asset_id"] in ("arch", "doorway", "shelf"):
            layout = [([-w*.44, 0, 0], [w*.12, d, h]), ([w*.44, 0, 0], [w*.12, d, h]),
                      ([0, 0, h*.45], [w, d, h*.1])]
            if obj["asset_id"] == "shelf":
                layout = [([w*x, 0, 0], [w*.08, d, h]) for x in (-.46, .46)]
                layout += [([0, 0, z*h], [w, d, h*.04]) for z in (-.46, -.15, .16, .46)]
            c, s = math.cos(yaw), math.sin(yaw)
            parts = [([center[0] + c*p[0] - s*p[1], center[1] + s*p[0] + c*p[1], center[2] + p[2]], size)
                     for p, size in layout]
        for position, size in parts:
            boxes.append((obj["object_id"], position, size, yaw))
    return boxes


def actor_poses(shot, scene, frame):
    if frame.get("performers"):
        return frame["performers"]
    lead = shot.get("actor_id", "")
    poses = {lead: frame["actor"]} if lead else {}
    for member in scene.get("cast", []):
        if member["actor_id"] == lead:
            continue
        base = frame["actor"]["position_m"] if member["motion"] == "with_lead" else [0, 0, 0]
        poses[member["actor_id"]] = dict(
            position_m=[a + b for a, b in zip(base, member["offset_m"])],
            heading_rad=frame["actor"]["heading_rad"] if member["motion"] == "with_lead" else member["facing_rad"],
        )
    return poses


def actor_box(pose, height, region):
    low, high, width = (0.84, 1, 0.14) if region == "face" else (0, 1, 0.32)
    p = pose["position_m"]
    return [p[0], p[1], p[2] + (low + high) * height / 2], [width*height, .16*height, (high-low)*height]


def review_screen(shot, settings, scene, mark, preview):
    from .shot_review import projection

    contracts = (shot.get("design") or {}).get("screen_targets", [])
    if not contracts:
        return None
    setup = preview["orbit_start_s"]
    source_in = preview.get("source_in_s", 0.0)
    full = preview.get("source_duration_s", preview["orbit_duration_s"])
    duration = min(preview["orbit_duration_s"], (shot["end_ms"] - shot["start_ms"]) / 1000)
    frames = [f for f in preview["frames"] if setup - 1e-8 <= f["time_s"] <= setup + duration + 1e-8]
    boxes = object_boxes(scene, mark)
    objects = {o["object_id"]: o for o in scene.get("objects", [])}
    height = settings["subject_height_m"]
    origin = mark.get("position_m", [0, 0])
    checks, issues = [], []
    for index, contract in enumerate(contracts):
        begin, end = contract["start_at"]*full, contract["end_at"]*full
        samples, failures = [], {}
        for frame in frames:
            source_time = source_in + frame["time_s"] - setup
            if not begin - 1e-8 <= source_time <= end + 1e-8:
                continue
            poses = actor_poses(shot, scene, frame)
            kind, target = contract["kind"], contract["target_id"]
            if kind == "actor":
                center, size = actor_box(poses[target], height, contract["region"])
                yaw = poses[target]["heading_rad"]
            else:
                obj = objects[target]
                center = [obj["position_m"][0]-origin[0], obj["position_m"][1]-origin[1], obj["position_m"][2]]
                size, yaw = obj["size_m"], obj["yaw_rad"]
            points = corners(center, size, yaw)
            xy, depth = projection(frame, points)
            uv, _ = projection(frame, [center])
            center_uv = (uv[0] + 1) / 2
            size_v = float(np.ptp(xy[:, 1]) / 2)
            cropped = bool(np.min(depth) <= 0 or np.max(np.abs(xy)) > 1.03)
            camera = frame.get("camera_view", frame["camera"])["pos"]
            blockers = [name for name, p, size_b, rotation in boxes if name != target
                        and intersects(camera, center, p, size_b, rotation)]
            intruders = []
            for actor_id, pose in poses.items():
                if kind == "actor" and actor_id == target:
                    continue
                body_center, body_size = actor_box(pose, height, "body")
                if intersects(camera, center, body_center, body_size, pose["heading_rad"]):
                    blockers.append("actor:" + actor_id)
                actor_xy, actor_depth = projection(frame, corners(body_center, body_size, pose["heading_rad"]))
                in_frame = np.min(actor_depth) > 0 and all(np.min(actor_xy[:, axis]) < 1 and
                            np.max(actor_xy[:, axis]) > -1 for axis in (0, 1))
                if in_frame and actor_id not in contract["allowed_foreground_actor_ids"]:
                    intruders.append(actor_id)
            codes = []
            if cropped and not contract["allow_crop"]:
                codes.append("screen_region_cropped")
            if blockers and not contract["allow_occlusion"]:
                codes.append("screen_target_occluded")
            if size_v < contract["height_range"][0] - 1e-8:
                codes.append("screen_subject_too_small")
            if size_v > contract["height_range"][1] + 1e-8:
                codes.append("screen_subject_too_large")
            if any(abs(center_uv[i] - contract["center_uv"][i]) > contract["tolerance_uv"][i] for i in (0, 1)):
                codes.append("screen_position_mismatch")
            if intruders:
                codes.append("unwanted_actor_intrusion")
            sample = dict(edit_s=frame["time_s"]-setup, source_s=source_time,
                          center_uv=center_uv.tolist(), height_fraction=size_v,
                          cropped=cropped, blockers=blockers, intruders=intruders,
                          visible=not cropped and not blockers, codes=codes)
            samples.append(sample)
            for code in codes:
                failures.setdefault(code, []).append(sample["edit_s"])
        longest, visible_start = 0.0, None
        for sample in samples:
            if sample["visible"]:
                if visible_start is None:
                    visible_start = sample["source_s"]
                longest = max(longest, sample["source_s"] - visible_start)
            else:
                visible_start = None
        if not samples:
            failures["screen_evidence_missing"] = [0, duration]
        if longest + 1e-8 < contract["min_visible_s"]:
            failures["reveal_dwell_too_short"] = [max(0, begin-source_in), min(duration, end-source_in)]
        check = dict(contract_index=index, target_id=contract["target_id"], source_interval_s=[begin, end],
                     longest_sampled_visible_s=longest, required_visible_s=contract["min_visible_s"],
                     samples=samples, status="needs_revision" if failures else "reviewable")
        checks.append(check)
        for code, times in failures.items():
            issues.append(dict(
                code=code, severity="revision", time_range_s=[min(times), max(times)],
                observation=f"{contract['target_id']}: {code.replace('_', ' ')} in the edited phone view.",
                evidence=dict(contract_index=index, examined_samples=len(samples), affected_samples=len(times),
                              longest_sampled_visible_s=longest, source_interval_s=[begin, end]),
                recommendation="Revise blocking, viewpoint or timing, or author the intentional exception. "
                               "The review does not change the lens or claim pixel-level visibility.",
            ))
    return dict(source="achieved_optical_pose_and_oriented_proxy_boxes", checks=checks, issues=issues,
                status="needs_revision" if issues else "reviewable",
                scope="Sampled center sightlines against oriented proxy boxes; not pixel visibility, "
                      "label readability or full rig clearance.")
