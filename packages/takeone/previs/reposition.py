"""Cart move and arm park between two takes. Kinematic preview, never a qualified plan.

The displayed turn/drive/turn is an idealized timing diagram. When reverse is
disabled its wheel reversal is unavailable, so its time is only a lower bound,
never an executable cart route. Both arms return to their configured integer
starting goals, with calibrated integer midpoints as the fallback.
"""

import math

import mujoco
import numpy as np

from takeone.calibration import ArmMapping
from takeone.config import rig_config
from takeone.contracts import JOINTS
from takeone.motion.studio_plan import ARM_PERIOD, ROLES
from takeone.simulation.drive import cart_from_axle
from takeone.simulation.robot import load_model, model_hash, model_path, pose_frame

from .start_pose import aiming_duration, initial_counts
from .templates import FIELDS

# Repositioning is dead time, so it uses the same ceiling any dolly or truck shot may already command.
SPEED_M_S = FIELDS["speed_m_s"]["max"]
ANGLE_TOLERANCE_RAD = math.radians(1.0)
DISTANCE_TOLERANCE_M = 0.02


def wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def plan(from_axle, to_axle):
    """Turn, drive, turn. Returns the leg list and total seconds, or None when already there."""
    dx, dy = to_axle[0] - from_axle[0], to_axle[1] - from_axle[1]
    distance = math.hypot(dx, dy)
    track = rig_config()["cart"]["track_width_m"]
    spin_rate = 2 * SPEED_M_S / track  # rad/s with the wheels turning opposite ways
    if distance <= DISTANCE_TOLERANCE_M:
        turn = wrap(to_axle[2] - from_axle[2])
        if abs(turn) <= ANGLE_TOLERANCE_RAD:
            return None
        legs = [("turn", turn)]
    else:
        bearing = math.atan2(dy, dx)
        legs = [
            ("turn", wrap(bearing - from_axle[2])),
            ("drive", distance),
            ("turn", wrap(to_axle[2] - bearing)),
        ]
    seconds = sum(
        abs(amount) / (spin_rate if kind == "turn" else SPEED_M_S) for kind, amount in legs if amount
    )
    return dict(
        legs=legs,
        cart_s=seconds,
        spin_rate=spin_rate,
        track_width_m=track,
        timing_is_lower_bound=True,
        executable=False,
    )


def axle_at(from_axle, legs, spin_rate, track_width_m, elapsed):
    """Axle pose and per-wheel travel/velocity after `elapsed` seconds of the plan."""
    x, y, heading = from_axle
    left = right = 0.0
    speeds = [0.0, 0.0]
    for kind, amount in legs:
        if not amount:
            continue
        rate = spin_rate if kind == "turn" else SPEED_M_S
        duration = abs(amount) / rate
        share = min(elapsed, duration)
        sign = math.copysign(1, amount)
        if kind == "turn":
            heading += sign * rate * share
            left -= sign * rate * track_width_m / 2 * share
            right += sign * rate * track_width_m / 2 * share
            if share < duration:
                speeds = [-sign * SPEED_M_S, sign * SPEED_M_S]
        else:
            x += math.cos(heading) * rate * share
            y += math.sin(heading) * rate * share
            left += rate * share
            right += rate * share
            if share < duration:
                speeds = [SPEED_M_S, SPEED_M_S]
        elapsed -= share
        if elapsed <= 0:
            return [x, y, heading], [left, right], speeds
    return [x, y, heading], [left, right], [0.0, 0.0]


def validate(value):
    keys = ("from_axle_m", "to_axle_m", "from_raw")
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("A reposition needs a starting pose, a target pose and the arm positions.")
    poses = []
    for key in ("from_axle_m", "to_axle_m"):
        pose = value[key]
        if not isinstance(pose, list) or len(pose) != 3:
            raise ValueError(f"{key} must be [x, y, heading].")
        for number in pose:
            if type(number) not in (int, float) or not math.isfinite(number):
                raise ValueError(f"{key} must contain finite numbers.")
        poses.append([float(n) for n in pose])
    mappings = {r: ArmMapping.load(r, require_motion=False) for r in ROLES}
    raw = {}
    for role, mapping in mappings.items():
        counts = value["from_raw"].get(role) if isinstance(value["from_raw"], dict) else None
        if not isinstance(counts, dict) or set(counts) != set(JOINTS):
            raise ValueError("Arm positions need every named joint for both arms.")
        limits = mapping.raw_calibration
        raw[role] = {
            n: int(np.clip(int(counts[n]), limits[n]["range_min"], limits[n]["range_max"])) for n in JOINTS
        }
    return dict(from_axle_m=poses[0], to_axle_m=poses[1], from_raw=raw), mappings


def prepare(value):
    """Validated settings and timing, without solving any frames."""
    settings, mappings = validate(value)
    route = plan(settings["from_axle_m"], settings["to_axle_m"])
    targets = {r: initial_counts(m) for r, m in mappings.items()}
    park_s = aiming_duration(settings["from_raw"], targets)
    duration = math.ceil(max(park_s, route["cart_s"] if route else 0.0) / ARM_PERIOD) * ARM_PERIOD
    return settings, mappings, route, targets, park_s, duration


def compile_reposition(value):
    """Frames in set coordinates, in the same schema the studio already renders."""
    settings, mappings, route, targets, park_s, duration = prepare(value)
    cfg = rig_config()["cart"]
    model = load_model()
    data = mujoco.MjData(model)
    q = np.zeros(model.nq)
    frames = []
    for i in range(round(duration / ARM_PERIOD) + 1):
        stamp = i * ARM_PERIOD
        axle, travel, speeds = (
            axle_at(settings["from_axle_m"], route["legs"], route["spin_rate"], route["track_width_m"], stamp)
            if route
            else (list(settings["from_axle_m"]), [0.0, 0.0], [0.0, 0.0])
        )
        raw = {
            r: {
                n: round(
                    settings["from_raw"][r][n]
                    + (targets[r][n] - settings["from_raw"][r][n])
                    * (1 - math.cos(math.pi * min(1.0, stamp / park_s)))
                    / 2
                )
                for n in JOINTS
            }
            for r in ROLES
        }
        q[:3] = cart_from_axle(axle)
        for j, role in enumerate(ROLES):
            q[3 + j * 5 : 8 + j * 5] = mappings[role].from_raw(raw[role])
        v, omega = sum(speeds) / 2, (speeds[1] - speeds[0]) / cfg["track_width_m"]
        drive = dict(
            wheelAngles=[d / (cfg["wheel_diameter_m"] / 2) for d in travel],
            wheelAxisSign=-cfg["drive_forward_sign"],
            wheelSpeeds=list(speeds),
            casterYaw=[
                math.atan2(omega * (cfg["caster_offset_m"] - cfg["axle_offset_m"]), v - omega * y)
                if v or omega
                else 0.0
                for y in (cfg["caster_track_width_m"] / 2, -cfg["caster_track_width_m"] / 2)
            ],
        )
        frame = pose_frame(model, data, q, stamp, drive)
        camera = np.array(frame["camera"]["pos"])
        face = [axle[0], axle[1], 0.0]
        frame.update(
            face=face,
            axle_m=axle[:2],
            aim_error_deg=None,
            focal_mm=24.0,
            subject_distance_m=float(np.linalg.norm(camera - np.array(face))),
            optical_depth_m=0.0,
            camera_pitch_deg=0.0,
            camera_view=dict(pos=list(frame["camera"]["pos"]), quat=list(frame["camera"]["quat"])),
            requested_camera_height_m=float(camera[2]),
            requested_aim_rad=[0.0, 0.0, 0.0],
            raw_by_role=raw,
            actor=None,
            phase="reposition",
        )
        frames.append(frame)
    return dict(
        kind="takeone_reposition_previs",
        schema_version=1,
        settings=settings,
        frames=frames,
        duration_s=duration,
        orbit_start_s=0.0,
        orbit_duration_s=max(duration, ARM_PERIOD),
        initial_raw=settings["from_raw"],
        aiming_raw=targets,
        notes=[
            "Minimum reposition time only. The turn-in-place diagram requires reverse, which is unavailable on this cart. A forward-only route or manual reset takes additional unestimated time. Both arms park at their configured starting pose."
        ],
        timing_is_lower_bound=True,
        executable=False,
        summary=dict(
            distance_m=math.dist(settings["from_axle_m"][:2], settings["to_axle_m"][:2]),
            duration_s=duration,
            cart_duration_s=route["cart_s"] if route else 0.0,
            arm_park_duration_s=park_s,
            speed_m_s=SPEED_M_S,
            physical_path_verified=False,
            timing_is_lower_bound=True,
        ),
        model_hash=model_hash(model_path(), cfg["track_width_m"]),
        frame="world_z_up",
        timebase="seconds from the start of this reposition",
    )
