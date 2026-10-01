"""Circular cart path and pointing-first arm IK, with FK driving both previews.

This module evaluates kinematics only. It does not import a transport, run
contact dynamics, qualify hardware or produce executable motor commands.
"""

import copy
import json
import math
from functools import lru_cache

import mujoco
import numpy as np
from scipy.optimize import least_squares

from takeone.calibration import ArmMapping
from takeone.config import file_hash, provenance, rig_config
from takeone.paths import CALIBRATION
from takeone.simulation.robot import load_model, model_hash, model_path, pose_frame

from .camera import MAX_FOCAL_MM, apply_camera, validate_camera
from .catalog import DEFAULTS, capabilities
from .placement import face_actor, needs_path_solver, validate_scene
from .program import aim_direction
from .start_pose import aiming_counts, aiming_duration, initial_counts

# The light must not appear in the phone's shot. 13 mm is the widest lens the phone
# has, so clearing its cone clears every longer one; the ring fixture adds its radius.
WIDEST_CONE = 18.0 / 13.0
FIXTURE_RADIUS_M = 0.09
CLEARANCE_WEIGHT = 12.0


def fixture_clearance(point, origin, forward, focal_mm=13.0):
    """Signed sphere-to-view-cone clearance in metres, including its near plane."""
    reach = point - origin
    along = float(reach @ forward)
    off = float(np.linalg.norm(reach - along * forward))
    slope = 18.0 / focal_mm
    # Either a separating near plane or cone side puts the entire fixture out
    # of view. A light behind the lens is not an obstruction at any focal length.
    return max(-along, (off - slope * along) / math.sqrt(1 + slope * slope)) - FIXTURE_RADIUS_M


BOUNDS = {
    "radius_m": (0.8, 30),
    "duration_s": (1, 180),
    "sweep_rad": (-2 * math.tau, 2 * math.tau),
    "bearing_rad": (-math.tau, math.tau),
    "height_m": (0.7, 1.8),
    "focal_mm": (13, MAX_FOCAL_MM),
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
    settings["camera"] = validate_camera(settings["camera"])
    settings["scene"] = validate_scene(settings["scene"])
    return settings


def orbit_pose(settings, fraction, axle_offset):
    u = max(0.0, min(1.0, fraction))
    progress = u * u * (3 - 2 * u) if settings["ease"] == "smooth" else u
    a = settings["bearing_rad"] + settings["sweep_rad"] * progress
    r = settings["radius_m"]
    # Turn the complete cart 180 degrees at its existing starting mark.
    # Positive sweep is counterclockwise with the powered front wheels leading.
    facing = -rig_config()["cart"]["drive_forward_sign"]
    axle = facing * np.array([r * math.sin(a), -r * math.cos(a)])
    # The powered axle, not the cart's origin, follows the tangent without slip.
    heading = a + math.pi
    cart = axle - axle_offset * np.array([math.cos(heading), math.sin(heading)])
    return np.r_[cart, heading], axle, progress


class AimingSolver:
    def __init__(self, model):
        self.model, self.data = model, mujoco.MjData(model)
        self.lower = model.jnt_range[3:, 0] + 1e-6
        self.upper = model.jnt_range[3:, 1] - 1e-6

    def optical(self, q, role):
        """That arm's optical point for this exact pose, cart included."""
        self.data.qpos[:] = q
        mujoco.mj_forward(self.model, self.data)
        name = ("cam" if role == "phone" else "light") + "_optical"
        return self.data.site_xpos[self.model.site(name).id].copy()

    def camera_clearance(self, q):
        """Lens origin and actual optical direction, including a pan or tilt."""
        origin = self.optical(q, "phone")
        forward = self.data.site_xmat[self.model.site("cam_optical").id].reshape(3, 3)[:, 2].copy()
        return origin, forward

    def solve(
        self,
        q,
        role,
        target,
        height,
        *,
        warm=False,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        clear=None,
        clear_forward=None,
        desired_position=None,
    ):
        """Five joints against four constraints leaves a family of solutions. `clear` is the
        camera's optical point: it picks the member of that family that stays out of shot."""
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
            direction = aim_direction(position, target, yaw, pitch)
            right = np.cross(direction, [0, 0, 1])
            right /= max(1e-8, np.linalg.norm(right))
            right = right * math.cos(roll) + np.cross(direction, right) * math.sin(roll)
            clearance = []
            if clear is not None:
                axis = target - clear if clear_forward is None else clear_forward
                length = float(np.linalg.norm(axis))
                if length > 1e-6:
                    forward = axis / length
                    clearance = [CLEARANCE_WEIGHT * max(0.0, -fixture_clearance(position, clear, forward))]
            return np.r_[
                12 * (rotation[:, 2] - direction),
                2 * (rotation[:, 0] - right),
                2 * (position[2] - height) if desired_position is None else 50 * (position - desired_position),
                # Prefer a continuous phone posture along the free IK direction.
                # Too little weight lets tilt/lift keyframes reconfigure faster
                # than the existing motor trajectory can follow.
                (0.03 if role == "phone" else 0.003) * (joints - seed),
                clearance,
            ]

        seeds = [
            seed,
            np.clip([0, -0.7, 1.1, 0.3, 0], low, high),
            np.clip([0, 0.7, -1.1, -0.3, 0], low, high),
        ]
        if warm:
            seeds = [seed]
        elif role == "phone":
            # The same landscape pose can sit on either side of the wrist's
            # encoder wrap. Try both starts instead of settling at an endpoint.
            seeds += [
                np.clip([*posture[:4], angle], low, high)
                for posture in seeds[1:]
                for angle in (-math.pi / 2, math.pi / 2)
            ]
        solutions = [
            least_squares(
                residual,
                s,
                bounds=(low, high),
                max_nfev=40 if warm else 160,
                ftol=1e-6 if warm else 1e-9,
                xtol=1e-6 if warm else 1e-9,
                gtol=1e-9,
            )
            for s in seeds
        ]
        best = min(solutions, key=lambda s: np.linalg.norm(residual(s.x)))
        q[sl] = best.x
        return q


def compile_orbit(value=None):
    settings = validate_settings({} if value is None else value)
    if needs_path_solver(settings["scene"]):
        return compile_placed_orbit(settings)["preview"]
    motion = {k: v for k, v in settings.items() if k != "camera"} | {"focal_mm": 24.0}
    preview = copy.deepcopy(
        _compile_orbit(json.dumps(motion, sort_keys=True), json.dumps(provenance(), sort_keys=True))
    )
    preview["settings"] = settings
    for frame in preview["frames"]:
        frame["actor"] = dict(
            position_m=[0.0, 0.0, 0.0], heading_rad=0.0, phase_rad=0.0, gait_weight=0.0, walking=False
        )
    face_actor(preview["frames"], preview["orbit_start_s"], settings["scene"])
    return apply_camera(preview)


def compile_placed_orbit(settings):
    """A placed orbit uses the same per-sample arm and wheel planner as drawn paths."""
    from .path import compile_scene
    from .templates import defaults_for, path_settings

    speed = settings["radius_m"] * abs(settings["sweep_rad"]) / settings["duration_s"]
    expanded = defaults_for("arc_right" if settings["sweep_rad"] < 0 else "arc_left") | dict(
        radius_m=settings["radius_m"],
        sweep_rad=abs(settings["sweep_rad"]),
        bearing_rad=settings["bearing_rad"],
        height_start_m=settings["height_m"],
        height_end_m=settings["height_m"],
        speed_m_s=min(0.35, max(0.14, speed)),
        subject_height_m=settings["subject_height_m"],
        scene=settings["scene"],
    )
    result = compile_scene(path_settings(expanded))
    preview, plan = result["preview"], result["plan"]
    preview.update(kind="takeone_orbit_previs", settings=settings)
    preview["notes"].append(
        "Placed orbit: timing follows the wheel commands; both arms track the actor at their independent mark."
    )
    apply_camera(preview, plan)
    return result


@lru_cache(maxsize=3)
def _compile_orbit(settings_json, provenance_json):
    settings = json.loads(settings_json)
    model, cart_cfg = load_model(), rig_config()["cart"]
    solver = AimingSolver(model)
    q = np.r_[np.zeros(3), (solver.lower + solver.upper) / 2]
    q[:3] = orbit_pose(settings, 0, cart_cfg["axle_offset_m"])[0]
    face = np.array([0, 0, settings["subject_height_m"] * 0.925])
    q = solver.solve(q, "phone", face, settings["height_m"])
    clear, forward = solver.camera_clearance(q)
    q = solver.solve(q, "light", face, 1.6, clear=clear, clear_forward=forward)
    mappings = {r: ArmMapping.load(r, require_motion=False) for r in ("phone", "light")}
    starts = {r: initial_counts(mapping) for r, mapping in mappings.items()}
    targets = {r: mapping.encode(q[3 + i * 5 : 8 + i * 5]) for i, (r, mapping) in enumerate(mappings.items())}
    for i, (role, mapping) in enumerate(mappings.items()):
        q[3 + i * 5 : 8 + i * 5] = mapping.from_raw(targets[role])
    setup_s = aiming_duration(starts, targets)
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
            settings["radius_m"] * delta - delta * cart_cfg["track_width_m"] / 2,
            settings["radius_m"] * delta + delta * cart_cfg["track_width_m"] / 2,
        ]
        omega = settings["sweep_rad"] / settings["duration_s"]
        if settings["ease"] == "smooth":
            omega *= 6 * fraction * (1 - fraction)
        linear = settings["radius_m"] * omega
        # Align the passive casters with their pivot velocities. Hold this
        # direction at the eased endpoints instead of snapping back when stopped.
        turn_sign = math.copysign(1, settings["sweep_rad"])
        caster_yaw = [
            math.atan2(
                turn_sign
                * cart_cfg["drive_forward_sign"]
                * (cart_cfg["caster_offset_m"] - cart_cfg["axle_offset_m"]),
                settings["radius_m"] * turn_sign - turn_sign * y,
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
        frame = pose_frame(model, solver.data, q, setup_s + fraction * settings["duration_s"], drive)
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
            raw_by_role=targets,
            phase="orbit",
        )
        frames.append(frame)
    # Each take starts on the configured integer starting goals, then aims
    # while the cart stays still. These same raw goals feed the physical player.
    setup = []
    for i in range(round(setup_s / 0.04)):
        stamp = i * 0.04
        raw = aiming_counts(starts, targets, stamp / setup_s)
        q[:3] = frames[0]["q"][:3]
        for j, (role, mapping) in enumerate(mappings.items()):
            q[3 + j * 5 : 8 + j * 5] = mapping.from_raw(raw[role])
        frame = pose_frame(
            model,
            solver.data,
            q,
            stamp,
            dict(frames[0]["drive"], wheelAngles=[0.0, 0.0], wheelSpeeds=[0.0, 0.0]),
        )
        frame.update(
            face=face.tolist(),
            axle_m=frames[0]["axle_m"],
            raw_by_role=raw,
            phase="calibrated_start" if i == 0 else "aiming",
            focal_mm=settings["focal_mm"],
            subject_distance_m=float(np.linalg.norm(face - np.array(frame["camera"]["pos"]))),
            aim_error_deg=None,
        )
        setup.append(frame)
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
        "duration_s": setup_s + settings["duration_s"],
        "orbit_start_s": setup_s,
        "orbit_duration_s": settings["duration_s"],
        "initial_raw": starts,
        "aiming_raw": targets,
        "frames": setup + frames,
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
