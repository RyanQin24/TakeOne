"""iPhone framing and lens channels, independent of motor/IK compilation.

The raw camera pose remains FK evidence. camera_view is an explicitly simulated
output orientation, not a change to the robot pose or a phone control command.
"""

import copy
import math

import numpy as np
from scipy.spatial.transform import Rotation

from takeone.motion.plan import digest

from .program import smooth

MIN_FOCAL_MM = 13.0
MAX_FOCAL_MM = 360.0  # Approximate 15x video framing, relative to the 24 mm main.
PROFILE = {
    "id": "iphone_17_pro_max",
    "name": "iPhone 17 Pro Max",
    "aspect": 16 / 9,
    "orientation": "landscape",
    "min_focal_mm": MIN_FOCAL_MM,
    "max_focal_mm": MAX_FOCAL_MM,
    "specification_url": "https://support.apple.com/en-sg/125091",
    "projection": "35 mm-equivalent pinhole with a 16:9 crop",
    "scope": "Simulated framing; capture, stabilization crop and lens switching depend on the phone app.",
}


def defaults():
    return dict(horizon="auto", zoom="preset", keyframes=[])


def validate_camera(value):
    if value is None:
        return defaults()
    if not isinstance(value, dict) or set(value) - set(defaults()):
        raise ValueError("Expected camera horizon, zoom mode and zoom points.")
    result = defaults() | copy.deepcopy(value)
    if result["horizon"] not in ("auto", "level", "phone"):
        raise ValueError("Choose automatic, level horizon or phone roll.")
    if result["zoom"] not in ("preset", "fixed", "keyframes", "dolly"):
        raise ValueError("Choose preset lens, fixed lens, zoom points or Dolly Zoom.")
    points = result["keyframes"]
    if not isinstance(points, list) or len(points) > 32:
        raise ValueError("Use at most 32 zoom points.")
    previous = -1.0
    for point in points:
        if not isinstance(point, dict) or set(point) != {"at", "focal_mm", "ease"}:
            raise ValueError("Each zoom point needs at, focal_mm and ease.")
        for name, low, high in (("at", 0, 1), ("focal_mm", MIN_FOCAL_MM, MAX_FOCAL_MM)):
            number = point[name]
            if type(number) not in (int, float) or not math.isfinite(number) or not low <= number <= high:
                raise ValueError(f"Zoom {name} must be between {low:g} and {high:g}.")
            point[name] = float(number)
        if point["at"] <= previous:
            raise ValueError("Put zoom points in increasing shot-time order.")
        previous = point["at"]
        if point["ease"] not in ("smooth", "linear", "hold"):
            raise ValueError("Choose smooth, linear or hold timing between zoom points.")
    if result["zoom"] == "keyframes" and (len(points) < 2 or points[0]["at"] != 0 or points[-1]["at"] != 1):
        raise ValueError("A zoom curve needs a starting point at 0% and an ending point at 100%.")
    return result


def zoom_at(points, fraction):
    """A point's ease controls the interval from that point to the next."""
    if fraction <= points[0]["at"]:
        return points[0]["focal_mm"]
    for a, b in zip(points, points[1:]):
        if fraction < b["at"]:
            u = (fraction - a["at"]) / (b["at"] - a["at"])
            u = smooth(u) if a["ease"] == "smooth" else 0 if a["ease"] == "hold" else u
            return a["focal_mm"] + (b["focal_mm"] - a["focal_mm"]) * u
    return points[-1]["focal_mm"]


def view_quaternion(raw_quat, horizon):
    if horizon == "phone":
        return list(raw_quat)
    rotation = Rotation.from_quat(raw_quat).as_matrix()
    forward = rotation[:, 2]
    right = np.cross(forward, [0.0, 0.0, 1.0])
    length = float(np.linalg.norm(right))
    # Straight up/down has no unique horizon. Retain the sensor's right axis
    # at this singularity instead of emitting a zero/invalid camera basis.
    right = right / length if length > 1e-7 else rotation[:, 0]
    down = np.cross(forward, right)
    return Rotation.from_matrix(np.column_stack((right, down, forward))).as_quat().tolist()


def apply_camera(preview, plan=None):
    settings = preview["settings"]
    camera = validate_camera(settings.get("camera"))
    settings["camera"] = camera
    aim = preview.get("template", {}).get("aim", "face")
    horizon = camera["horizon"]
    if horizon == "auto":
        horizon = "phone" if aim in ("roll", "handheld") else "level"
    zoom = camera["zoom"]
    if zoom == "preset":
        zoom = "preset_ramp" if aim == "zoom" else "dolly" if aim == "dolly_zoom" else "fixed"
    opening_focal = camera["keyframes"][0]["focal_mm"] if zoom == "keyframes" else settings["focal_mm"]
    start, duration = preview["orbit_start_s"], preview["orbit_duration_s"]
    filming = [frame for frame in preview["frames"] if frame["time_s"] >= start - 1e-8]
    first = filming[0]

    def depth(frame):
        forward = Rotation.from_quat(frame["camera"]["quat"]).as_matrix()[:, 2]
        return float(forward @ (np.asarray(frame["face"]) - frame["camera"]["pos"]))

    opening_depth = depth(first)
    if zoom == "dolly" and (opening_depth <= 1e-6 or any(depth(f) <= 1e-6 for f in filming)):
        raise ValueError("Dolly Zoom needs the actor in front of the camera throughout the shot.")
    for frame in preview["frames"]:
        u = min(1.0, max(0.0, (frame["time_s"] - start) / duration))
        if frame["time_s"] >= start + duration - 1e-8:
            u = 1.0
        focal = opening_focal
        if frame["time_s"] >= start - 1e-8:
            if zoom == "keyframes":
                focal = zoom_at(camera["keyframes"], u)
            elif zoom == "preset_ramp":
                change = smooth(
                    (u - settings["rise_start"]) / (settings["rise_end"] - settings["rise_start"])
                )
                focal += (settings["focal_end_mm"] - focal) * change
            elif zoom == "dolly":
                focal *= depth(frame) / opening_depth
        frame["focal_mm"] = min(MAX_FOCAL_MM, max(MIN_FOCAL_MM, focal))
        frame["camera_view"] = dict(
            pos=list(frame["camera"]["pos"]),
            quat=view_quaternion(frame["camera"]["quat"], horizon),
        )
    preview["camera_output"] = dict(
        profile=dict(PROFILE), horizon=horizon, zoom=zoom, source="simulated_camera_output"
    )
    preview["summary"].update(focal_start_mm=filming[0]["focal_mm"], focal_end_mm=filming[-1]["focal_mm"])
    preview["summary"].pop("framing_drift_percent", None)
    if zoom == "dolly":
        scale = opening_focal / opening_depth
        preview["summary"]["framing_drift_percent"] = max(
            abs(frame["focal_mm"] / depth(frame) / scale - 1) * 100 for frame in filming
        )
    if plan is not None:
        plan["settings"] = copy.deepcopy(settings)
        plan["camera_output"] = copy.deepcopy(preview["camera_output"])
        plan["camera_cues"] = [
            dict(time_s=f["time_s"], focal_mm=f["focal_mm"], source="simulated_lens_cue")
            for f in preview["frames"]
        ]
        plan["plan_id"] = digest({k: v for k, v in plan.items() if k != "plan_id"})
        preview["plan_id"] = plan["plan_id"]
    return preview
