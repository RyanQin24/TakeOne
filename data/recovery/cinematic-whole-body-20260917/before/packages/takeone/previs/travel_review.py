"""Edited-window actor/base/optical motion evidence from canonical FK samples.

This is a helper of shot_review, not a planner or video-quality model. It never
changes timing, poses, lenses or actor marks. Coarse displacement bins suppress
encoder noise; they are sampled evidence, not continuous physical qualification.
"""

import math
from bisect import bisect_right

import numpy as np
from scipy.spatial.transform import Rotation

from takeone.director.motion_contract import defaults

BIN_S = 0.4
MAX_SAMPLE_GAP_S = 0.17
ACTOR_SPEED_M_S = 0.02
CART_SPEED_M_S = 0.04
ARM_SPEED_M_S = 0.005
ARM_SPEED_RAD_S = 0.02


def trajectory(points):
    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return dict(path_m=float(steps.sum()), net_m=float(np.linalg.norm(points[-1] - points[0])),
                excursion_m=float(np.max(np.linalg.norm(points - points[0], axis=1))))


def filmed_window(shot, preview):
    setup = preview["orbit_start_s"]
    wanted = (shot["end_ms"] - shot["start_ms"]) / 1000
    available = preview["orbit_duration_s"]
    duration = min(wanted, available)
    frames = preview.get("frames", [])
    stamps = [f["time_s"] for f in frames]
    if duration <= 0 or len(stamps) < 2 or any(not math.isfinite(t) for t in stamps):
        raise ValueError("No positive retained filming window with finite timestamps.")
    if any(b <= a for a, b in zip(stamps, stamps[1:])):
        raise ValueError("Motion samples must be strictly ordered.")
    if stamps[0] > setup + 1e-8 or stamps[-1] < setup + duration - 1e-8:
        raise ValueError("Motion samples do not cover the retained window.")
    def held(t):
        i = bisect_right(stamps, t + 1e-8) - 1
        return dict(frames[i], time_s=t, sampled_time_s=stamps[i])
    retained = [held(setup)] + [f for f in frames if setup + 1e-8 < f["time_s"] < setup + duration - 1e-8] + [held(setup + duration)]
    if max(b["time_s"] - a["time_s"] for a, b in zip(retained, retained[1:])) > MAX_SAMPLE_GAP_S:
        raise ValueError("Motion evidence is undersampled; recompile at the canonical preview cadence.")
    return retained, duration, max(0.0, wanted - available)


def review_travel(shot, settings, preview):
    authored = shot.get("motion_requirements")
    contract = defaults() | (authored or {})
    severity = "revision" if contract["priority"] in ("required", "intentionally_static") else "manual"
    result = dict(source="quantized_command_FK_and_scripted_actor", status="reviewable", issues=[],
                  requirements=authored, metrics=None, overlap_intervals_s=[],
                  timebase="edit-local seconds; source offsets retained; setup and unused source excluded",
                  thresholds=dict(bin_s=BIN_S, actor_speed_m_s=ACTOR_SPEED_M_S,
                                  cart_speed_m_s=CART_SPEED_M_S, arm_translation_speed_m_s=ARM_SPEED_M_S,
                                  arm_rotation_speed_rad_s=ARM_SPEED_RAD_S),
                  scope="Sampled motion, not video aesthetics, live following, contact dynamics or hardware qualification.")
    def issue(code, observation, evidence):
        result["issues"].append(dict(code=code, severity=severity, time_range_s=[0.0, duration],
            observation=observation, evidence=evidence,
            recommendation="Revise the declared movement, route, blocking or timing explicitly; nothing is silently frozen, relabelled or retimed."))
    duration = max(0.0, (shot["end_ms"] - shot["start_ms"]) / 1000)
    try:
        frames, duration, gap = filmed_window(shot, preview)
        stamps = np.asarray([f["time_s"] - preview["orbit_start_s"] for f in frames])
        q = np.asarray([f["q"] for f in frames], dtype=float)
        cart = np.asarray([f["axle_m"] for f in frames], dtype=float)
        camera = np.asarray([f["camera"]["pos"] for f in frames], dtype=float)
        quat = np.asarray([f["camera"]["quat"] for f in frames], dtype=float)
        actor_id = shot.get("actor_id", "")
        actors = [f.get("performers", {}).get(actor_id, f.get("actor")) for f in frames]
        actor = np.asarray([p["position_m"] if actor_id else [0, 0, 0] for p in actors], dtype=float)
        subject = np.asarray([f.get("camera_target_m", f.get("face", actor[i])) for i, f in enumerate(frames)])
        if q.shape != (len(frames), 13) or cart.shape != (len(frames), 2) or any(
                p.shape != (len(frames), 3) for p in (camera, actor, subject)) or quat.shape != (len(frames), 4):
            raise ValueError("Incomplete canonical base, actor or optical geometry.")
        if not all(np.all(np.isfinite(p)) for p in (q, cart, camera, quat, actor, subject)):
            raise ValueError("Motion evidence contains non-finite geometry.")
        optical_rotation = Rotation.from_quat(quat)
    except (ValueError, KeyError, TypeError) as error:
        issue("movement_evidence_missing", str(error), dict(source=result["source"]))
        result["status"] = "unverified"
        return result
    base_rotation = Rotation.from_euler("z", q[:, 2:3])
    base_origins = np.column_stack((q[:, :2], np.zeros(len(q))))
    relative_position = base_rotation.inv().apply(camera - base_origins)
    relative_rotation = base_rotation.inv() * optical_rotation
    arm_angles = (relative_rotation[0].inv() * relative_rotation).magnitude()
    actor_stats, cart_stats, camera_stats = trajectory(actor[:, :2]), trajectory(cart), trajectory(camera)
    arm_stats = trajectory(relative_position)
    # Camera-only displacement about the contemporaneous target: a walking actor
    # cannot manufacture a push or an orbit while the optical centre is parked.
    radial, orbital = [], []
    for i in range(len(frames) - 1):
        centre = (subject[i] + subject[i + 1]) / 2
        start, end = camera[i] - centre, camera[i + 1] - centre
        middle = (start + end) / 2
        radial.append(float(-(camera[i + 1] - camera[i]) @ middle / max(np.linalg.norm(middle), 1e-9)))
        orbital.append(math.atan2(start[0] * end[1] - start[1] * end[0], start[0] * end[0] + start[1] * end[1]))
    right = optical_rotation[0].as_matrix()[:, 0]
    bins = []
    edges = list(np.arange(0, duration, BIN_S)) + [duration]
    for begin, end in zip(edges, edges[1:]):
        if end - begin < BIN_S - 1e-8:
            continue  # A tiny tail cannot manufacture another sustained interval.
        a, b = [max(0, bisect_right(stamps, t + 1e-8) - 1) for t in (begin, end)]
        elapsed = stamps[b] - stamps[a]
        if elapsed <= 0:
            continue
        av = float(np.linalg.norm(actor[b, :2] - actor[a, :2]) / elapsed)
        cv = float(np.linalg.norm(cart[b] - cart[a]) / elapsed)
        tv = float(np.linalg.norm(relative_position[b] - relative_position[a]) / elapsed)
        rv = float((relative_rotation[a].inv() * relative_rotation[b]).magnitude() / elapsed)
        active = av >= ACTOR_SPEED_M_S and cv >= CART_SPEED_M_S and (tv >= ARM_SPEED_M_S or rv >= ARM_SPEED_RAD_S)
        bins.append(dict(start_s=float(begin), end_s=float(end), actor_m_s=av, cart_m_s=cv,
                         arm_m_s=tv, arm_rad_s=rv, simultaneous=bool(active)))
    meaningful = actor_stats["excursion_m"] >= 0.10 and cart_stats["excursion_m"] >= 0.10 and (
        arm_stats["excursion_m"] >= 0.03 or float(max(arm_angles)) >= math.radians(3))
    intervals = []
    for item in bins:
        if not item["simultaneous"] or not meaningful:
            continue
        if intervals and math.isclose(intervals[-1][1], item["start_s"], abs_tol=1e-8):
            intervals[-1][1] = item["end_s"]
        else:
            intervals.append([item["start_s"], item["end_s"]])
    longest = max((b - a for a, b in intervals), default=0.0)
    metrics = dict(actor=actor_stats, cart=cart_stats, optical=camera_stats, arm_relative=arm_stats,
                   arm_rotation_excursion_rad=float(max(arm_angles)), phone_joint_excursion_rad=np.ptp(q[:, 3:8], axis=0).tolist(),
                   cart_heading_change_rad=float(np.unwrap(q[:, 2])[-1] - q[0, 2]),
                   camera_generated_approach_m=float(sum(radial)), radial_travel_m=float(sum(abs(v) for v in radial)),
                   camera_generated_orbit_rad=float(sum(orbital)),
                   camera_lateral_right_m=float((camera[-1] - camera[0]) @ right),
                   actor_camera_distance_range_m=[float(v) for v in (min(np.linalg.norm(camera-actor,axis=1)), max(np.linalg.norm(camera-actor,axis=1)))],
                   longest_simultaneous_s=float(longest), total_simultaneous_s=float(sum(b-a for a,b in intervals)),
                   samples=len(frames), preview_hold_s=gap)
    source_in = preview.get("source_in_s", 0.0)
    result.update(metrics=metrics, activity_bins=bins, overlap_intervals_s=intervals,
                  source_interval_s=[source_in, source_in + duration],
                  source_overlap_intervals_s=[[source_in+a, source_in+b] for a,b in intervals])
    for name, stats in (("actor", actor_stats), ("cart", cart_stats), ("camera", camera_stats)):
        required = contract[name + "_travel_m"]
        if required and (stats["path_m"] + 1e-8 < required or stats["excursion_m"] < min(0.3, required / 2)):
            issue(name + "_travel_unmet", f"Required {name} travel is not realized in this edit.", dict(required_m=required, **stats))
    for key, actual in (("arm_translation_m", arm_stats["excursion_m"]),
                        ("arm_rotation_rad", float(max(arm_angles))), ("simultaneous_s", longest)):
        if actual + 1e-8 < contract[key]:
            issue(key + "_unmet", f"The retained take does not realize required {key.replace('_', ' ')}.",
                  dict(required=contract[key], achieved=actual, overlap_intervals_s=intervals))
    direction = contract["direction"]
    signed = {"approach": sum(radial), "retreat": -sum(radial),
              "right": metrics["camera_lateral_right_m"], "left": -metrics["camera_lateral_right_m"]}
    if direction in signed and signed[direction] + 1e-8 < contract["signed_progress_m"]:
        issue("camera_direction_unmet", f"Camera-generated {direction} progress is insufficient.",
              dict(required_m=contract["signed_progress_m"], achieved_m=signed[direction]))
    if direction in ("orbit_ccw", "orbit_cw"):
        angle = sum(orbital) * (1 if direction == "orbit_ccw" else -1)
        if angle + 1e-8 < contract["orbit_rad"]:
            issue("camera_orbit_unmet", "The camera does not realize the declared signed orbital sweep.",
                  dict(required_rad=contract["orbit_rad"], achieved_rad=angle))
    requested = [f.get("requested_camera_position_m") for f in frames]
    if any(p is not None for p in requested):
        if not all(p is not None for p in requested):
            issue("camera_path_evidence_missing", "Requested optical path evidence is incomplete.", {})
        else:
            error = np.linalg.norm(camera - np.asarray(requested), axis=1)
            metrics["camera_position_error_max_m"] = float(max(error))
            metrics["camera_position_error_p95_m"] = float(np.percentile(error, 95))
            if max(error) > contract["max_position_error_m"]:
                issue("camera_path_not_achieved", "The encoded arm/base trajectory misses the authored optical path.",
                      dict(maximum_m=float(max(error)), allowed_m=contract["max_position_error_m"]))
    if gap > 0.04 and authored:
        issue("movement_source_too_short", "A held preview frame cannot supply missing movement or performance.", dict(missing_s=gap))
    if contract["priority"] == "intentionally_static":
        if camera_stats["excursion_m"] > 0.005 or max((optical_rotation[0].inv()*optical_rotation).magnitude()) > math.radians(0.5):
            issue("intentional_camera_hold_not_realized", "The optical pose moves during an explicitly static camera shot.", camera_stats)
    if result["issues"]:
        result["status"] = "needs_revision" if severity == "revision" else "preference_notes"
    return result
