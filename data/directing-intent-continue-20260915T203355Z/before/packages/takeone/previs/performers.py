"""Sample explicit actor direction once, alongside the achieved rig preview.

Positions remain shot-local until sequence placement. Named object targets are
scene-local and are translated by the mark origin. New tracks require scene-local
mode, so there is no hidden legacy rotation. Rendering consumes these same samples.
"""

import copy
import math
from bisect import bisect_right

from .channels import evaluate, smooth

HEAD_RATIO = 1.59 / 1.72


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def interval(keys, fraction):
    index = max(0, bisect_right([k["at"] for k in keys], fraction) - 1)
    a = keys[index]
    if index == len(keys) - 1:
        return a, a, 0.0
    b = keys[index + 1]
    u = max(0.0, min(1.0, (fraction - a["at"]) / (b["at"] - a["at"])))
    return a, b, smooth(u) if a["ease"] == "smooth" else 0.0 if a["ease"] == "hold" else u


def target_point(key, poses, objects, origin, actor_id, height):
    if key["kind"] == "actor":
        point = list(poses[key["target_id"]]["position_m"])
        point[2] += HEAD_RATIO * height
        return point
    if key["kind"] in ("object", "point"):
        point = objects[key["target_id"]]["position_m"] if key["kind"] == "object" else key["point_m"]
        return [point[0] - origin[0], point[1] - origin[1], point[2]]
    actor = poses[actor_id]
    x, y, z = actor["position_m"]
    heading = actor["heading_rad"]
    return [x + math.cos(heading), y + math.sin(heading), z + HEAD_RATIO * height]


def look_angles(pose, target, height):
    x, y, z = pose["position_m"]
    dx, dy, dz = target[0] - x, target[1] - y, target[2] - z - HEAD_RATIO * height
    return wrap(math.atan2(dy, dx) - pose["heading_rad"]), math.atan2(dz, math.hypot(dx, dy))


def arm_target(pose, target, height):
    """Two-link staging-proxy reach; no prop attachment and no human/robot command."""
    scale = height / 1.72
    c, s = math.cos(pose["heading_rad"]), math.sin(pose["heading_rad"])
    dx, dy = target[0] - pose["position_m"][0], target[1] - pose["position_m"][1]
    x, y = (c * dx + s * dy) / scale, (-s * dx + c * dy) / scale + 0.215
    z = (target[2] - pose["position_m"][2]) / scale - 1.34
    reach = math.hypot(x, y)
    length = min(0.58 - 1e-6, max(1e-6, math.hypot(reach, z)))
    upper = -math.atan2(reach, -z) - math.acos(length / 0.58)
    elbow = math.pi - math.acos(max(-1.0, min(1.0, (2 * 0.29**2 - length**2) / (2 * 0.29**2))))
    return [math.atan2(y, x), upper, elbow]


def hand_point(pose, angles, height):
    yaw, upper, elbow = angles
    reach = -0.29 * (math.sin(upper) + math.sin(upper + elbow))
    x, y = reach * math.cos(yaw), -0.215 + reach * math.sin(yaw)
    z = 1.34 - 0.29 * (math.cos(upper) + math.cos(upper + elbow))
    scale = height / 1.72
    c, s = math.cos(pose["heading_rad"]), math.sin(pose["heading_rad"])
    return [pose["position_m"][0] + scale * (c * x - s * y),
            pose["position_m"][1] + scale * (s * x + c * y),
            pose["position_m"][2] + scale * z]


def gesture_angles(key, pose, target, height):
    rest = [0.0, 0.0, -0.1]
    desired = arm_target(pose, target, height) if key["name"] == "reach" else (
        [-0.3, -1.35, 0.65] if key["name"] == "invite" else rest)
    return [a + (b - a) * key["weight"] for a, b in zip(rest, desired)]


def sample_actors(shot, scene, mark, frame, settings, fraction):
    """Snapshot all staged people before resolving attention; mutual looks are acyclic."""
    height = settings["subject_height_m"]
    lead = shot["actor_id"]
    poses = {lead: copy.deepcopy(frame["actor"])} if lead else {}
    for member in scene.get("cast", []):
        if member["actor_id"] == lead:
            continue
        follow = member["motion"] == "with_lead"
        base = frame["actor"] if follow else dict(
            position_m=[0, 0, 0], heading_rad=member["facing_rad"],
            phase_rad=0, gait_weight=0, walking=False)
        pose = copy.deepcopy(base)
        pose["position_m"] = [a + b for a, b in zip(base["position_m"], member["offset_m"])]
        pose.update(gaze_yaw_rad=0.0, gaze_pitch_rad=0.0)
        poses[member["actor_id"]] = pose
    tracks = {t["actor_id"]: t for t in shot.get("performers", [])}
    objects = {o["object_id"]: o for o in scene.get("objects", [])}
    origin = mark.get("position_m", [0, 0])
    for actor_id, track in tracks.items():
        pose = poses[actor_id]
        pose["heading_rad"] = evaluate(track["body_heading_rad"], fraction, pose["heading_rad"])
    for actor_id, track in tracks.items():
        pose = poses[actor_id]
        keys = track["look_at"]
        if keys:
            a, b, u = interval(keys, fraction)
            start = target_point(a, poses, objects, origin, actor_id, height)
            end = target_point(b, poses, objects, origin, actor_id, height)
            yaw_a, pitch_a = look_angles(pose, start, height)
            yaw_b, pitch_b = look_angles(pose, end, height)
            yaw = wrap(yaw_a + wrap(yaw_b - yaw_a) * u)
            pitch = pitch_a + (pitch_b - pitch_a) * u
            pose["gaze_yaw_rad"] = max(-math.pi / 2, min(math.pi / 2, yaw))
            pose["gaze_pitch_rad"] = max(-math.pi / 3, min(math.pi / 3, pitch))
            pose["attention_error_rad"] = math.hypot(wrap(yaw - pose["gaze_yaw_rad"]),
                                                    pitch - pose["gaze_pitch_rad"])
            pose["look_target_m"] = [v + (w - v) * u for v, w in zip(start, end)]
            pose["look_target"] = f"{a['kind']}:{a['target_id']}" if u < 1 else f"{b['kind']}:{b['target_id']}"
        keys = track["gestures"]
        if keys:
            a, b, u = interval(keys, fraction)
            target_a = target_point(a, poses, objects, origin, actor_id, height)
            target_b = target_point(b, poses, objects, origin, actor_id, height)
            angles_a = gesture_angles(a, pose, target_a, height)
            angles_b = gesture_angles(b, pose, target_b, height)
            angles = [v + (w - v) * u for v, w in zip(angles_a, angles_b)]
            pose["right_arm_rad"] = angles
            pose["right_hand_m"] = hand_point(pose, angles, height)
            pose["gesture"] = a["name"] if u < 0.5 else b["name"]
            if a["name"] == b["name"] == "reach":
                target = [v + (w - v) * u for v, w in zip(target_a, target_b)]
                pose["reach_error_m"] = math.dist(pose["right_hand_m"], target)
    return poses


def build_samples(shot, settings, scene, mark, preview):
    if not shot.get("performers"):
        return None
    setup = preview["orbit_start_s"]
    source_in = preview.get("source_in_s", 0.0)
    full_duration = preview.get("source_duration_s", preview["orbit_duration_s"])
    samples = []
    for frame in preview["frames"]:
        fraction = max(0.0, min(1.0, (source_in + frame["time_s"] - setup) / full_duration))
        poses = sample_actors(shot, scene, mark, frame, settings, fraction)
        frame["performers"] = poses
        samples.append(dict(time_s=frame["time_s"], actors=poses))
    return samples
