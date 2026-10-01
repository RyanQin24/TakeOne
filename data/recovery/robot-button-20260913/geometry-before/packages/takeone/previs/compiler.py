"""Circular cart path and pointing-first arm IK, with FK driving both previews.

This module evaluates kinematics only. It does not import a transport, run
contact dynamics, qualify hardware or produce executable motor commands.
"""

import math

import mujoco
import numpy as np
from scipy.optimize import least_squares

from takeone.config import file_hash, rig_config
from takeone.paths import CALIBRATION
from takeone.simulation.robot import load_model, model_hash, model_path, pose_frame

from .catalog import DEFAULTS, capabilities

BOUNDS = {
    "radius_m": (0.8, 30),
    "duration_s": (1, 180),
    "sweep_rad": (-2 * math.tau, 2 * math.tau),
    "bearing_rad": (-math.tau, math.tau),
    "height_m": (0.7, 1.8),
    "focal_mm": (13, 200),
    "subject_height_m": (0.8, 2.2),
}


def validate_settings(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Invalid orbit settings.")
    settings = {**DEFAULTS, **value}
    for name, (low, high) in BOUNDS.items():
        v = settings[name]
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f"{name} must be between {low:g} and {high:g}.")
        settings[name] = float(v)
    if abs(settings["sweep_rad"]) < math.radians(1):
        raise ValueError("Choose a sweep of at least one degree.")
    if settings["ease"] not in ("smooth", "linear"):
        raise ValueError("Choose smooth or linear motion.")
    return settings


def orbit_pose(settings, fraction, axle_offset):
    u = max(0.0, min(1.0, fraction))
    progress = u * u * (3 - 2 * u) if settings["ease"] == "smooth" else u
    a = settings["bearing_rad"] + settings["sweep_rad"] * progress
    r = settings["radius_m"]
    axle = np.array([r * math.sin(a), -r * math.cos(a)])
    # The powered axle, not the cart's origin, follows the tangent without slip.
    cart = axle - axle_offset * np.array([math.cos(a), math.sin(a)])
    return np.r_[cart, a], axle, progress


class AimingSolver:
    def __init__(self, model):
        self.model, self.data = model, mujoco.MjData(model)
        self.lower = model.jnt_range[3:, 0] + 1e-6
        self.upper = model.jnt_range[3:, 1] - 1e-6

    def solve(self, q, role, target, height):
        offset, prefix = (3, "cam") if role == "phone" else (8, "light")
        sl = slice(offset, offset + 5)
        low, high = self.lower[offset - 3 : offset + 2], self.upper[offset - 3 : offset + 2]
        seed = np.clip(q[sl], low, high)
        site = self.model.site(prefix + "_optical").id

        def residual(joints):
            self.data.qpos[:] = q
            self.data.qpos[sl] = joints
            mujoco.mj_forward(self.model, self.data)
            position = self.data.site_xpos[site]
            rotation = self.data.site_xmat[site].reshape(3, 3)
            direction = target - position
            direction /= max(1e-8, np.linalg.norm(direction))
            right = np.cross(direction, [0, 0, 1])
            right /= max(1e-8, np.linalg.norm(right))
            return np.r_[
                12 * (rotation[:, 2] - direction),
                2 * (rotation[:, 0] - right),
                2 * (position[2] - height),
                0.003 * (joints - seed),
            ]

        seeds = [
            seed,
            np.clip([0, -0.7, 1.1, 0.3, 0], low, high),
            np.clip([0, 0.7, -1.1, -0.3, 0], low, high),
        ]
        solutions = [
            least_squares(residual, s, bounds=(low, high), max_nfev=160, ftol=1e-9, xtol=1e-9, gtol=1e-9)
            for s in seeds
        ]
        best = min(solutions, key=lambda s: np.linalg.norm(residual(s.x)))
        q[sl] = best.x
        return q


def compile_orbit(value=None):
    settings = validate_settings({} if value is None else value)
    model, cart_cfg = load_model(), rig_config()["cart"]
    solver = AimingSolver(model)
    q = np.r_[np.zeros(3), (solver.lower + solver.upper) / 2]
    q[:3] = orbit_pose(settings, 0, cart_cfg["axle_offset_m"])[0]
    face = np.array([0, 0, settings["subject_height_m"] * 0.925])
    q = solver.solve(q, "phone", face, settings["height_m"])
    q = solver.solve(q, "light", face, 1.6)
    frames, aim_errors = [], []
    count = min(
        1200,
        max(60, math.ceil(settings["duration_s"] * 12), math.ceil(abs(math.degrees(settings["sweep_rad"])))),
    )
    # Circular motion around a static face is rigidly symmetric. One bounded
    # solution stays aimed for the whole orbit; it does not accumulate wrist turns.
    for i in range(count + 1):
        fraction = i / count
        q[:3], axle, progress = orbit_pose(settings, fraction, cart_cfg["axle_offset_m"])
        delta = settings["sweep_rad"] * progress
        wheel_distances = [
            -settings["radius_m"] * delta - delta * cart_cfg["track_width_m"] / 2,
            -settings["radius_m"] * delta + delta * cart_cfg["track_width_m"] / 2,
        ]
        omega = settings["sweep_rad"] / settings["duration_s"]
        if settings["ease"] == "smooth":
            omega *= 6 * fraction * (1 - fraction)
        linear = -settings["radius_m"] * omega
        # Align the passive casters with their pivot velocities. Hold this
        # direction at the eased endpoints instead of snapping back when stopped.
        turn_sign = math.copysign(1, settings["sweep_rad"])
        caster_yaw = [
            math.atan2(
                turn_sign
                * cart_cfg["drive_forward_sign"]
                * (cart_cfg["caster_offset_m"] - cart_cfg["axle_offset_m"]),
                -settings["radius_m"] * turn_sign - turn_sign * y,
            )
            for y in (cart_cfg["caster_track_width_m"] / 2, -cart_cfg["caster_track_width_m"] / 2)
        ]
        drive = dict(
            wheelAngles=[d / (cart_cfg["wheel_diameter_m"] / 2) for d in wheel_distances],
            wheelAxisSign=-cart_cfg["drive_forward_sign"],
            wheelSpeeds=[
                linear - omega * cart_cfg["track_width_m"] / 2,
                linear + omega * cart_cfg["track_width_m"] / 2,
            ],
            casterYaw=caster_yaw,
        )
        frame = pose_frame(model, solver.data, q, fraction * settings["duration_s"], drive)
        direction = face - np.array(frame["camera"]["pos"])
        distance = float(np.linalg.norm(direction))
        direction /= max(1e-8, distance)
        forward = solver.data.site_xmat[model.site("cam_optical").id].reshape(3, 3)[:, 2]
        aim = math.degrees(math.acos(float(np.clip(forward @ direction, -1, 1))))
        aim_errors.append(aim)
        frame.update(
            face=face.tolist(),
            axle_m=axle.tolist(),
            aim_error_deg=aim,
            focal_mm=settings["focal_mm"],
            subject_distance_m=distance,
        )
        frames.append(frame)
    distance = settings["radius_m"] * abs(settings["sweep_rad"])
    height = frames[0]["camera"]["pos"][2]
    notes = []
    if max(aim_errors) > 3:
        notes.append(
            "At this setting the arm reaches its aiming range. Try another camera height or a larger radius."
        )
    if abs(height - settings["height_m"]) > 0.03:
        notes.append(
            f"The arm reaches a camera height of {height:.2f} m for the requested {settings['height_m']:.2f} m."
        )
    return {
        "kind": "takeone_orbit_previs",
        "schema_version": 1,
        "settings": settings,
        "duration_s": settings["duration_s"],
        "frames": frames,
        "notes": notes,
        "summary": {
            "distance_m": distance,
            "average_speed_m_s": distance / settings["duration_s"],
            "peak_speed_m_s": distance
            / settings["duration_s"]
            * (1.5 if settings["ease"] == "smooth" else 1),
            "max_aim_error_deg": max(aim_errors),
            "camera_height_m": height,
            "subject_distance_m": frames[0]["subject_distance_m"],
            "within_joint_ranges": True,
        },
        "capabilities": capabilities(),
        "model_hash": model_hash(model_path(), cart_cfg["track_width_m"]),
        "calibration_hashes": {r: file_hash(CALIBRATION / f"derived/{r}.json") for r in ("phone", "light")},
        "frame": "world_z_up",
        "timebase": "seconds from the start of this simulated shot",
    }
