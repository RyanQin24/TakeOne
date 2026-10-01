"""Drawn powered-axle routes, compiled once into preview and robot commands.

The follower closes a loop around an OFFLINE prediction, not physical odometry.
It uses the existing wheel response, exact wire precision, and no lateral motion.
"""

import copy
import json
import math
from functools import lru_cache

import numpy as np

from takeone.calibration import ArmMapping
from takeone.cart.response import CartResponse
from takeone.config import provenance, rig_config
from takeone.contracts import JOINTS
from takeone.motion.plan import FRAMES, digest
from takeone.motion.studio_plan import ARM_PERIOD, CART_PERIOD, ROLES, SCHEMA
from takeone.protocol import COMMAND_CAP, MIN_COMMAND, uart_pair
from takeone.simulation.drive import cart_from_axle, integrate
from takeone.simulation.robot import load_model, model_hash, model_path, pose_frame

from .catalog import capabilities
from .choreography import camera_height, light_height, validate_choreography
from .compiler import AimingSolver
from .program import aim_direction, aim_offsets, change_progress, focal_length, subject
from .start_pose import aiming_counts, aiming_duration, initial_counts

FOOT_M = 0.3048
CONTROL_PERIOD = 0.2  # Hold each decision for 200 ms, not 20 ms motor dithering.
DEFAULTS = dict(
    mode="path",
    points_m=[[-2.0, 2.0], [2.0, 2.0]],
    speed_m_s=0.17,
    height_m=1.5,
    focal_mm=48.0,
    subject_height_m=1.72,
    choreography=None,
)


def validate_settings(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Expected drawn path settings.")
    settings = DEFAULTS | value
    if settings["mode"] != "path":
        raise ValueError("Choose drawn path mode.")
    for key, low, high in [
        ("speed_m_s", 0.14, 0.35),
        ("height_m", 0.7, 1.8),
        ("focal_mm", 13, 200),
        ("subject_height_m", 0.8, 2.2),
    ]:
        v = settings[key]
        if type(v) not in (float, int) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f"{key} must be between {low:g} and {high:g}.")
        settings[key] = float(v)
    points = settings["points_m"]
    if not isinstance(points, list) or not 2 <= len(points) <= 512:
        raise ValueError("Draw a path with 2 to 512 points.")
    cleaned = []
    for p in points:
        if (
            not isinstance(p, list)
            or len(p) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 100 for v in p)
        ):
            raise ValueError("Path points must be finite ground X/Y coordinates within 100 metres.")
        if not cleaned or math.dist(cleaned[-1], p) > 0.001:
            cleaned.append([float(v) for v in p])
    length = sum(math.dist(a, b) for a, b in zip(cleaned, cleaned[1:]))
    if not 0.15 <= length <= 65:
        raise ValueError("Draw between 0.15 and 65 metres of travel for this single take.")
    settings["points_m"] = cleaned
    settings["choreography"] = validate_choreography(settings["choreography"])
    return settings


def route_geometry(points):
    """Round hand-drawn corners with two endpoint-preserving Chaikin passes."""
    p = np.asarray(points, dtype=float)
    # Resample long segments first so corner rounding is local (about one foot).
    dense = [p[0]]
    for a, b in zip(p, p[1:]):
        n = max(1, math.ceil(np.linalg.norm(b - a) / FOOT_M))
        dense.extend(a + (b - a) * i / n for i in range(1, n + 1))
    p = np.asarray(dense)
    for _ in range(2):
        q = np.empty((2 * len(p), 2))
        q[0], q[-1] = p[0], p[-1]
        q[1:-1:2] = 0.75 * p[:-1] + 0.25 * p[1:]
        q[2:-1:2] = 0.25 * p[:-1] + 0.75 * p[1:]
        p = q
    lengths = np.linalg.norm(np.diff(p, axis=0), axis=1)
    keep = np.r_[True, lengths > 1e-8]
    p = p[keep]
    arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    return p, arc


def point_at(points, arc, distance):
    return np.array([np.interp(distance, arc, points[:, i]) for i in (0, 1)])


def predict_route(settings, response=None):
    """Plan forward-only wheel commands, then integrate those exact commands.

    Pure-pursuit curvature is 2*y/L^2 in the powered-axle frame. Sequential
    projection prevents jumps across a self-intersection. End detection chooses
    the closest reachable forward endpoint; it is not an arm-error gate.
    """
    cfg = rig_config()["cart"]
    response = response or CartResponse.load(cfg["minimum_speed_m_s"])
    p, arc = route_geometry(settings["points_m"])
    choices = []
    for side in range(2):
        wheel = [(0.0, 0.0)]
        for n in range(round(MIN_COMMAND * 100), round(COMMAND_CAP * 100) + 1):
            c = n / 100
            try:
                v = (
                    response.speeds_for((c, c))[side]
                    if response.wheels is None
                    else response.wheels[side].interpolate(c)
                )
                wheel.append((c, v))
            except ValueError:
                continue
        if len(wheel) < 2:
            raise ValueError("The wheel response needs at least one forward command for each wheel.")
        choices.append(wheel)
    pairs = [
        (np.array([lc, rc]), np.array([lv, rv]))
        for lc, lv in choices[0]
        for rc, rv in choices[1]
        if lv + rv > 0
    ]
    heading = math.atan2(*(p[1] - p[0])[::-1])
    axle = np.r_[p[0], heading]
    distances = np.zeros(2)
    rows, poses, travel = [], [axle.tolist()], [distances.tolist()]
    progress, previous, end_distance = 0.0, np.zeros(2), math.inf
    lookahead = max(0.45, settings["speed_m_s"] * 2)
    max_steps = round(570 / CONTROL_PERIOD)
    endpoint_reached = False
    for step in range(max_steps):
        low = max(0, np.searchsorted(arc, progress) - 1)
        high = min(len(p) - 1, np.searchsorted(arc, progress + lookahead * 2) + 1)
        a, delta = p[low:high], p[low + 1 : high + 1] - p[low:high]
        u = np.clip(np.sum((axle[:2] - a) * delta, axis=1) / np.sum(delta * delta, axis=1), 0, 1)
        projections = a + u[:, None] * delta
        ix = int(np.argmin(np.linalg.norm(projections - axle[:2], axis=1)))
        progress = max(progress, float(arc[low + ix] + u[ix] * (arc[low + ix + 1] - arc[low + ix])))
        remaining = float(np.linalg.norm(p[-1] - axle[:2]))
        if progress >= arc[-1] - lookahead and (remaining < 0.025 or remaining > end_distance + 0.001):
            endpoint_reached = True
            break
        if progress >= arc[-1] - lookahead:
            end_distance = remaining
        target = point_at(p, arc, min(arc[-1], progress + lookahead)) - axle[:2]
        lateral = -math.sin(axle[2]) * target[0] + math.cos(axle[2]) * target[1]
        curvature = 2 * lateral / max(float(target @ target), 0.02)
        curvature = float(np.clip(curvature, -2 / cfg["track_width_m"], 2 / cfg["track_width_m"]))
        # Lower cruise demand into bends; coarse motor deadband still applies.
        speed = settings["speed_m_s"] / max(1.0, 1 + abs(curvature) * 0.35)
        yaw = speed * curvature

        def score(pair):
            commands, velocities = pair
            linear = float(sum(velocities)) / 2
            omega = float(velocities[1] - velocities[0]) / cfg["track_width_m"]
            # Prefer a sustained wire value when two choices predict similar motion.
            return (
                (linear - speed) ** 2
                + 0.25 * (omega - yaw) ** 2
                + 0.002 * float(np.sum((commands - previous) ** 2))
            )

        allowed = [
            (c, v)
            for c, v in pairs
            if all(
                abs(x - old) <= 0.010001 or (min(x, old) == 0 and max(x, old) <= MIN_COMMAND + 1e-9)
                for x, old in zip(c, previous)
            )
        ]
        # Sparse measured tables may not contain a .01 neighbour; choose their
        # documented command instead of inventing an unmeasured speed.
        commands, speeds = min(allowed or pairs, key=score)
        previous = commands
        for _ in range(round(CONTROL_PERIOD / CART_PERIOD)):
            rows.append(dict(commands=commands.tolist(), wire=uart_pair(*commands)))
            axle = integrate(axle, *(speeds * CART_PERIOD), cfg["track_width_m"])
            distances += speeds * CART_PERIOD
            poses.append(axle.tolist())
            travel.append(distances.tolist())
    if not endpoint_reached:
        raise ValueError(
            "This route loops too tightly for forward travel. Widen that turn or split the route."
        )
    return dict(
        rows=rows,
        poses=poses,
        wheel_travel=travel,
        reference=p.tolist(),
        distance_m=float(arc[-1]),
        endpoint_error_m=float(np.linalg.norm(axle[:2] - p[-1])),
        response_mode=response.mode,
    )


def compile_path(value):
    settings = validate_settings(value)
    return compile_scene(settings)


def compile_scene(settings):
    """Compile validated path settings or an internally expanded named program."""
    # Preview and Prepare consume the same deterministic result. A source change
    # changes provenance and cannot reuse an older robot artifact.
    return copy.deepcopy(
        _compile(json.dumps(settings, sort_keys=True), json.dumps(provenance(), sort_keys=True))
    )


@lru_cache(maxsize=6)
def _compile(settings_json, provenance_json):
    settings = json.loads(settings_json)
    program = settings.get("program")
    # Cart travel is independent of lens choice and arm-height choreography.
    # Keep a small separate cache so changing the reveal reuses wheel prediction.
    route = (
        stationary_route(settings)
        if len(settings["points_m"]) == 1
        else _route(
            json.dumps({k: settings[k] for k in ("points_m", "speed_m_s")}, sort_keys=True), provenance_json
        )
    )
    cfg, model = rig_config()["cart"], load_model()
    response = CartResponse.load(cfg["minimum_speed_m_s"])
    solver = AimingSolver(model)
    mappings = {r: ArmMapping.load(r, require_motion=False) for r in ROLES}
    starts = {r: initial_counts(m) for r, m in mappings.items()}
    q = np.r_[np.zeros(3), (solver.lower + solver.upper) / 2]
    count = len(route["rows"]) // 2
    travel_s = count * ARM_PERIOD
    # Sample animated aim/subjects more finely; playback itself never solves IK.
    animated = program and (
        program["aim"] in ("pan", "tilt", "roll", "handheld", "high") or program["subject_motion"] == "walk"
    )
    step = 5 if animated else 20
    key_indices = sorted(set([*range(0, count + 1, step), count]))
    goals = []
    previous_targets = {}
    for k, i in enumerate(key_indices):
        q[:3] = cart_from_axle(route["poses"][i * 2])
        fraction = i / max(1, count)
        _, face = subject(program, fraction, settings["subject_height_m"])
        offsets = aim_offsets(program, fraction, travel_s)
        for role, height in [
            ("phone", camera_height(settings["choreography"], fraction, settings["height_m"])),
            (
                "light",
                light_height(settings["choreography"], fraction)
                if program is None
                else program["light_height_start_m"]
                + change_progress(program, fraction)
                * (program["light_height_end_m"] - program["light_height_start_m"]),
            ),
        ]:
            angles = offsets if role == "phone" else (0.0, 0.0, 0.0)
            target = (
                np.array([0.0, 0.0, settings["subject_height_m"] * 0.925])
                if role == "phone" and program and program["aim"] == "locked"
                else face
            )
            target_key = (*q[:3], *target, height, *angles)
            if previous_targets.get(role) != target_key:
                solver.solve(
                    q, role, target, height, warm=k != 0, yaw=angles[0], pitch=angles[1], roll=angles[2]
                )
                previous_targets[role] = target_key
        goals.append({r: m.encode(q[3 + j * 5 : 8 + j * 5]) for j, (r, m) in enumerate(mappings.items())})
    setup = aiming_duration(starts, goals[0])
    setup_count = round(setup / ARM_PERIOD)
    duration = (setup_count + count) * ARM_PERIOD
    if duration > 600:
        raise ValueError("Shorten this route to fit a ten-minute take including arm setup.")
    schedule = [dict(commands=[0.0, 0.0], wire=uart_pair(0, 0)) for _ in range(setup_count * 2)] + route[
        "rows"
    ]
    schedule = [dict(row, time_s=i * CART_PERIOD) for i, row in enumerate(schedule)]
    schedule.append(dict(time_s=duration, commands=[0.0, 0.0], wire=uart_pair(0, 0)))
    frames, samples, errors = [], [], []
    opening_depth = None
    key = 0
    previous_raw = goals[0]
    for i in range(setup_count + count + 1):
        index = max(0, i - setup_count)
        if i < setup_count:
            raw = aiming_counts(starts, goals[0], i / setup_count)
        else:
            while key + 1 < len(key_indices) - 1 and index > key_indices[key + 1]:
                key += 1
            mix = (index - key_indices[key]) / max(1, key_indices[key + 1] - key_indices[key])
            # Linear key interpolation, then bounded per-tick travel. This is a
            # trajectory rate, never a measured arm-error stop condition.
            max_delta = max(1, math.floor(25 / (360 / 4095) * ARM_PERIOD))
            raw = {
                r: {
                    n: int(
                        np.clip(
                            round(goals[key][r][n] + mix * (goals[key + 1][r][n] - goals[key][r][n])),
                            previous_raw[r][n] - max_delta,
                            previous_raw[r][n] + max_delta,
                        )
                    )
                    for n in JOINTS
                }
                for r in ROLES
            }
            previous_raw = raw
        stamp = i * ARM_PERIOD
        arms = {r: m.from_raw(raw[r]) for r, m in mappings.items()}
        samples.append(dict(time_s=stamp, raw_by_role=raw, arms=arms))
        if i % 2 and i != setup_count + count and i != setup_count:
            continue
        axle = route["poses"][index * 2]
        q[:3] = cart_from_axle(axle)
        for j, role in enumerate(ROLES):
            q[3 + j * 5 : 8 + j * 5] = arms[role]
        row = min(i * 2, len(schedule) - 1)
        velocities = response.speeds_for(schedule[row]["commands"])
        v, omega = sum(velocities) / 2, (velocities[1] - velocities[0]) / cfg["track_width_m"]
        caster = [
            math.atan2(omega * (cfg["caster_offset_m"] - cfg["axle_offset_m"]), v - omega * y)
            if v or omega
            else 0.0
            for y in (cfg["caster_track_width_m"] / 2, -cfg["caster_track_width_m"] / 2)
        ]
        drive = dict(
            wheelAngles=[d / (cfg["wheel_diameter_m"] / 2) for d in route["wheel_travel"][index * 2]],
            wheelAxisSign=-cfg["drive_forward_sign"],
            wheelSpeeds=list(velocities),
            casterYaw=caster,
        )
        frame = pose_frame(model, solver.data, q, stamp, drive)
        fraction = index / max(1, count)
        actor, face = subject(program, fraction, settings["subject_height_m"])
        offsets = aim_offsets(program, fraction, travel_s)
        position = np.array(frame["camera"]["pos"])
        direction = face - position
        distance = float(np.linalg.norm(direction))
        forward = solver.data.site_xmat[model.site("cam_optical").id].reshape(3, 3)[:, 2]
        target = (
            np.array([0.0, 0.0, settings["subject_height_m"] * 0.925])
            if program and program["aim"] == "locked"
            else face
        )
        error = math.degrees(
            math.acos(float(np.clip(forward @ aim_direction(position, target, *offsets[:2]), -1, 1)))
        )
        depth = float(forward @ direction)
        if i == setup_count:
            opening_depth = depth
        focal = (
            settings["focal_mm"]
            if i < setup_count
            else focal_length(program, fraction, depth, opening_depth or depth, settings["focal_mm"])
        )
        if i >= setup_count:
            errors.append(error)
        frame.update(
            axle_m=axle[:2],
            face=face.tolist(),
            raw_by_role=raw,
            focal_mm=focal,
            actor=actor,
            optical_depth_m=depth,
            requested_aim_rad=list(offsets),
            phase="calibrated_start" if i == 0 else "aiming" if i < setup_count else "path",
            aim_error_deg=error if i >= setup_count else None,
            subject_distance_m=distance,
            requested_camera_height_m=camera_height(
                settings["choreography"], index / max(1, count), settings["height_m"]
            ),
            camera_pitch_deg=math.degrees(math.atan2(forward[2], math.hypot(forward[0], forward[1]))),
        )
        frames.append(frame)
    travel_s = count * ARM_PERIOD
    actual_distance = sum(route["wheel_travel"][-1]) / 2
    response = CartResponse.load(cfg["minimum_speed_m_s"])
    peak = max(sum(response.speeds_for(r["commands"])) / 2 for r in route["rows"])
    summary = dict(
        requested_duration_s=travel_s,
        duration_s=duration,
        orbit_duration_s=travel_s,
        setup_duration_s=setup,
        retimed=False,
        distance_m=actual_distance,
        requested_distance_m=route["distance_m"],
        endpoint_error_m=route["endpoint_error_m"],
        max_command=max(max(r["commands"]) for r in schedule),
        wheel_travel_m=route["wheel_travel"][-1],
        response_mode=route["response_mode"],
        physical_path_verified=False,
        average_speed_m_s=actual_distance / travel_s,
        peak_speed_m_s=peak,
        max_aim_error_deg=max(errors),
        camera_height_m=frames[-1]["camera"]["pos"][2],
        subject_distance_m=frames[-1]["subject_distance_m"],
        within_joint_ranges=True,
        scope="Drawn cart route and both arms. Recording and lenses remain manual.",
    )
    height_error = 0.0
    if settings["choreography"]:
        filming = [f for f in frames if f["time_s"] >= setup]
        height_error = max(abs(f["camera"]["pos"][2] - f["requested_camera_height_m"]) for f in filming)
        summary.update(
            camera_height_start_m=filming[0]["camera"]["pos"][2],
            camera_height_end_m=filming[-1]["camera"]["pos"][2],
            camera_pitch_start_deg=filming[0]["camera_pitch_deg"],
            camera_pitch_end_deg=filming[-1]["camera_pitch_deg"],
            focal_start_mm=filming[0]["focal_mm"],
            focal_end_mm=filming[-1]["focal_mm"],
        )
        if program and program["aim"] == "dolly_zoom":
            scale = filming[0]["focal_mm"] / max(filming[0]["optical_depth_m"], 1e-8)
            summary["framing_drift_percent"] = max(
                abs((f["focal_mm"] / max(f["optical_depth_m"], 1e-8)) / scale - 1) * 100 for f in filming
            )
    body = dict(
        schema=SCHEMA,
        frames=FRAMES,
        provenance=json.loads(provenance_json),
        settings=settings,
        roles=list(ROLES),
        joint_order=list(JOINTS),
        arm_period_s=ARM_PERIOD,
        duration_s=duration,
        orbit_start_s=setup,
        orbit_duration_s=travel_s,
        initial_raw=starts,
        samples=samples,
        cart_schedule=schedule,
        raw_goals=samples[-1]["raw_by_role"],
        summary=summary,
    )
    plan = body | {"plan_id": digest(body)}
    notes = [
        "Red is your route; amber is the path predicted from the exact motor commands. "
        "Real travel is timed and has no position feedback, so wheel slip or unequal motors can cause drift."
    ]
    if max(errors) > 3:
        notes.append(
            f"The phone reaches a maximum aiming offset of {max(errors):.1f}°. This does not block playback."
        )
    if height_error > 0.03:
        notes.append(
            f"Maximum requested-to-achieved camera height difference: {height_error:.2f} m. Preview shows the achieved arm pose."
        )
    preview = dict(
        kind="takeone_path_previs",
        schema_version=1,
        settings=settings,
        duration_s=duration,
        orbit_start_s=setup,
        orbit_duration_s=travel_s,
        initial_raw=starts,
        aiming_raw=goals[0],
        frames=frames,
        notes=notes,
        summary=summary,
        capabilities=capabilities(),
        model_hash=model_hash(model_path(), cfg["track_width_m"]),
        frame="world_z_up",
        grid_spacing_m=FOOT_M,
        timebase="seconds from calibrated arm start; identical prepared robot clock",
        plan_id=plan["plan_id"],
        requested_path_m=settings["points_m"],
    )
    return dict(plan=plan, preview=preview)


def stationary_route(settings):
    program = settings["program"]
    count = math.ceil(program["duration_s"] / ARM_PERIOD) * 2
    pose = [*settings["points_m"][0], program["bearing_rad"] + math.pi]
    return dict(
        rows=[dict(commands=[0.0, 0.0], wire=uart_pair(0, 0)) for _ in range(count)],
        poses=[pose[:] for _ in range(count + 1)],
        wheel_travel=[[0.0, 0.0] for _ in range(count + 1)],
        reference=settings["points_m"],
        distance_m=0.0,
        endpoint_error_m=0.0,
        response_mode="stationary",
    )


@lru_cache(maxsize=8)
def _route(geometry_json, provenance_json):
    return predict_route(json.loads(geometry_json))
