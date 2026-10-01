"""Offline differential-drive prediction. No serial port or hardware imports.

Measured: wheel size, minimum command, one approximate straight-line speed.
Assumed: track width, linear command/speed map, symmetry, no slip, response times.
The UART formatting exactly mirrors the user's clamp + two-decimal protocol.
"""

import math

import numpy as np

from takeone.cart.response import CartResponse
from takeone.config import rig_config
from takeone.protocol import COMMAND_CAP, MIN_COMMAND, uart_pair

_cart = rig_config()["cart"]
WHEEL_RADIUS = _cart["wheel_diameter_m"] / 2
WHEEL_WIDTH = _cart["wheel_width_m"]
AXLE_OFFSET = _cart["axle_offset_m"]
FORWARD_SIGN = _cart["drive_forward_sign"]
DIRECTION_SIGN = -1 if _cart["reverse_enabled"] else 1
HEADING_OFFSET = math.pi if FORWARD_SIGN == -1 else 0.0
CASTER_OFFSET = _cart["caster_offset_m"]
CASTER_TRACK = _cart["caster_track_width_m"]
CASTER_RADIUS = _cart["caster_radius_m"]
CASTER_WIDTH = _cart["caster_width_m"]
CASTER_TRAIL = _cart["caster_trail_m"]


def body_velocity(left, right, track):
    return (left + right) / 2, (right - left) / track


def wheel_velocity(linear, yaw_rate, track):
    return linear - yaw_rate * track / 2, linear + yaw_rate * track / 2


def integrate(axle, left_distance, right_distance, track):
    """Exact SE(2) integration of a constant wheel-speed segment; axle midpoint."""
    x, y, heading = map(float, axle)
    distance = (left_distance + right_distance) / 2
    angle = (right_distance - left_distance) / track
    # sinc remains accurate at zero curvature and permits signed reverse travel.
    chord = distance * float(np.sinc(angle / (2 * math.pi)))
    return np.array(
        [
            x + chord * math.cos(heading + angle / 2),
            y + chord * math.sin(heading + angle / 2),
            heading + angle,
        ]
    )


def cart_from_axle(axle):
    """Axle pose uses drive heading; upper-cart pose retains its original axes."""
    cart_yaw = axle[2] - HEADING_OFFSET
    return np.array(
        [
            axle[0] - AXLE_OFFSET * math.cos(cart_yaw),
            axle[1] - AXLE_OFFSET * math.sin(cart_yaw),
            cart_yaw,
        ]
    )


def response(initial, target, dt, tau):
    """Exact first-order velocity and displacement for an optional assumed lag."""
    if tau == 0:
        return target, target * dt
    factor = -math.expm1(-dt / tau)
    return initial + (target - initial) * factor, target * dt + (initial - target) * tau * factor


def segment(axle, speeds, distances, target, dt, track, response_time, brake_time):
    result = [response(s, t, dt, brake_time if t == 0 else response_time) for s, t in zip(speeds, target)]
    new_speed = np.array([r[0] for r in result])
    delta = np.array([r[1] for r in result])
    return integrate(axle, *delta, track), new_speed, distances + delta


def reference(cfg, time):
    u = min(1, max(0, time / cfg["duration"]))
    if cfg["driveProfile"] == "arms":
        # A straight dolly at the measured minimum speed: the arms take the pan.
        # Equal commands avoid the coarse .01 differential that makes turns abrupt.
        distance = cfg["minimumSpeed"] * cfg["duration"]
        # Place the upper-cart path explicitly, then derive the powered axle.
        # Changing the wheel end must not silently recenter the filming path.
        cart_yaw = -math.pi / 2
        cart_y = cfg["dollyOffset"] + FORWARD_SIGN * DIRECTION_SIGN * distance * (0.5 - u)
        axle = np.array(
            [
                -cfg["radius"] + AXLE_OFFSET * math.cos(cart_yaw),
                cart_y + AXLE_OFFSET * math.sin(cart_yaw),
                cart_yaw + HEADING_OFFSET,
            ]
        )
        speed = DIRECTION_SIGN * cfg["minimumSpeed"]
        return axle, (speed, speed)
    smooth = cfg["driveProfile"] == "smooth"
    progress = 10 * u**3 - 15 * u**4 + 6 * u**5 if smooth else u
    rate = 30 * u * u * (1 - u) ** 2 if smooth else 1.0
    angle = math.radians(cfg["orbit"])
    theta = FORWARD_SIGN * DIRECTION_SIGN * (-angle / 2 + angle * progress)
    axle = np.array(
        [
            -cfg["radius"] * math.cos(theta),
            -cfg["radius"] * math.sin(theta),
            theta - math.pi / 2 + HEADING_OFFSET,
        ]
    )
    yaw_rate = FORWARD_SIGN * DIRECTION_SIGN * angle * rate / cfg["duration"]
    linear = DIRECTION_SIGN * cfg["radius"] * angle * rate / cfg["duration"]
    return axle, wheel_velocity(linear, yaw_rate, cfg["trackWidth"])


def simulate(cfg, dt=0.02):
    motor_response = CartResponse.load(cfg["minimumSpeed"])
    count = math.ceil(cfg["duration"] / dt)
    dt = cfg["duration"] / count
    axle = reference(cfg, 0)[0]
    speeds = np.zeros(2)
    distances = np.zeros(2)
    records = []
    for i in range(count):
        time = i * dt
        desired = np.array(reference(cfg, time + dt / 2)[1])
        raw = np.array(motor_response.commands_for(desired))
        wire = uart_pair(*raw)
        commands = np.array([float(v) for v in wire.strip().split(",")])
        target = np.array(motor_response.speeds_for(commands))
        records.append(
            dict(
                time=time,
                axle=axle.copy(),
                speeds=speeds.copy(),
                distances=distances.copy(),
                desired=desired,
                raw=raw,
                commands=commands,
                target=target,
                wire=wire,
            )
        )
        axle, speeds, distances = segment(
            axle, speeds, distances, target, dt, cfg["trackWidth"], cfg["responseTime"], cfg["brakeTime"]
        )
    return dict(
        records=records,
        dt=dt,
        cfg=cfg,
        final=(axle, speeds, distances),
        response=motor_response.describe(),
        source="settings_reference",
    )


def simulate_constant_schedule(cfg, initial_cart, desired_speeds, dt=0.02):
    """Integrate a finite, two-decimal schedule for a coordinated mobile plan.

    Error feedback distributes adjacent representable moving commands over time.
    Every transmitted value remains at or above the configured moving minimum;
    the resulting packet sequence, rather than the continuous average, is the
    authoritative path.
    """
    initial_cart = np.asarray(initial_cart, dtype=float)
    desired_speeds = np.asarray(desired_speeds, dtype=float)
    if (
        initial_cart.shape != (3,)
        or desired_speeds.shape != (2,)
        or not np.isfinite(np.r_[initial_cart, desired_speeds]).all()
    ):
        raise ValueError("Coordinated cart staging and wheel speeds must be finite")
    if np.any(desired_speeds < cfg["minimumSpeed"] - 1e-12):
        raise ValueError("Coordinated forward wheel speeds cannot enter the unmeasured deadband")
    motor_response = CartResponse.load(cfg["minimumSpeed"])
    desired_commands = np.asarray(motor_response.commands_for(desired_speeds))
    if np.any(abs(desired_commands) > COMMAND_CAP + 1e-12):
        raise ValueError("Coordinated wheel schedule exceeds the command cap")
    count = math.ceil(cfg["duration"] / dt)
    dt = cfg["duration"] / count
    cart_yaw = initial_cart[2]
    axle = np.array(
        [
            initial_cart[0] + AXLE_OFFSET * math.cos(cart_yaw),
            initial_cart[1] + AXLE_OFFSET * math.sin(cart_yaw),
            cart_yaw + HEADING_OFFSET,
        ]
    )
    speeds = np.zeros(2)
    distances = np.zeros(2)
    quantization_error = np.zeros(2)
    records = []
    for i in range(count):
        time = i * dt
        adjusted = desired_commands + quantization_error
        commands = np.round(adjusted, 2)
        commands = np.where(
            (commands != 0) & (abs(commands) < MIN_COMMAND), np.sign(commands) * MIN_COMMAND, commands
        )
        commands = np.clip(commands, -COMMAND_CAP, COMMAND_CAP)
        wire = uart_pair(*commands)
        commands = np.array([float(value) for value in wire.strip().split(",")])
        quantization_error = adjusted - commands
        target = np.asarray(motor_response.speeds_for(commands))
        records.append(
            dict(
                time=time,
                axle=axle.copy(),
                speeds=speeds.copy(),
                distances=distances.copy(),
                desired=desired_speeds.copy(),
                raw=desired_commands.copy(),
                commands=commands,
                target=target,
                wire=wire,
            )
        )
        axle, speeds, distances = segment(
            axle, speeds, distances, target, dt, cfg["trackWidth"], cfg["responseTime"], cfg["brakeTime"]
        )
    return dict(
        records=records,
        dt=dt,
        cfg=cfg,
        final=(axle, speeds, distances),
        response=motor_response.describe(),
        source="coordinated_quantized_constant_wheel_schedule",
        desired_average_speeds=desired_speeds.tolist(),
        desired_average_commands=desired_commands.tolist(),
        initial_cart=initial_cart.tolist(),
    )


def simulate_wire_schedule(cfg, initial_cart, schedule):
    """Reintegrate an already reviewed two-decimal packet sequence."""
    initial_cart = np.asarray(initial_cart, dtype=float)
    if initial_cart.shape != (3,) or not np.isfinite(initial_cart).all() or not schedule:
        raise ValueError("A finite initial cart pose and nonempty packet schedule are required")
    count = len(schedule)
    dt = cfg["duration"] / count
    cart_yaw = initial_cart[2]
    axle = np.array(
        [
            initial_cart[0] + AXLE_OFFSET * math.cos(cart_yaw),
            initial_cart[1] + AXLE_OFFSET * math.sin(cart_yaw),
            cart_yaw + HEADING_OFFSET,
        ]
    )
    motor_response = CartResponse.load(cfg["minimumSpeed"])
    speeds = np.zeros(2)
    distances = np.zeros(2)
    records = []
    for index, item in enumerate(schedule):
        expected_time = index * dt
        if not math.isclose(float(item["time"]), expected_time, abs_tol=1e-10, rel_tol=0):
            raise ValueError("Compiled cart packets must cover one uniform finite timeline")
        commands = np.asarray(item["commands"], dtype=float)
        if commands.shape != (2,) or uart_pair(*commands) != item["wire"]:
            raise ValueError("Compiled cart packet does not equal its two-decimal wire value")
        target = np.asarray(motor_response.speeds_for(commands))
        records.append(
            dict(
                time=expected_time,
                axle=axle.copy(),
                speeds=speeds.copy(),
                distances=distances.copy(),
                desired=target.copy(),
                raw=commands.copy(),
                commands=commands.copy(),
                target=target,
                wire=item["wire"],
            )
        )
        axle, speeds, distances = segment(
            axle, speeds, distances, target, dt, cfg["trackWidth"], cfg["responseTime"], cfg["brakeTime"]
        )
    return dict(
        records=records,
        dt=dt,
        cfg=cfg,
        final=(axle, speeds, distances),
        response=motor_response.describe(),
        source="reviewed_quantized_wire_schedule",
        initial_cart=initial_cart.tolist(),
    )


def sample(trace, time):
    cfg = trace["cfg"]
    dt = trace["dt"]
    records = trace["records"]
    i = min(len(records) - 1, max(0, int(time / dt)))
    r = records[i]
    axle, speeds, distances = segment(
        r["axle"],
        r["speeds"],
        r["distances"],
        r["target"],
        min(dt, max(0, time - r["time"])),
        cfg["trackWidth"],
        cfg["responseTime"],
        cfg["brakeTime"],
    )
    # At the end of the requested shot the next wire message is explicitly stop.
    ended = time >= cfg["duration"]
    if ended and cfg["brakeTime"] == 0:
        speeds = np.zeros(2)
    linear, yaw = body_velocity(*speeds, cfg["trackWidth"])
    swivel_speeds = speeds
    if np.linalg.norm(swivel_speeds) < 1e-9:
        # A stopped caster holds its last direction; it does not snap back.
        for previous in reversed(records[: i + 1]):
            if np.linalg.norm(previous["target"]) > 1e-9:
                swivel_speeds = previous["target"]
                break
    swivel_v, swivel_w = body_velocity(*swivel_speeds, cfg["trackWidth"])
    caster_yaw = [
        math.atan2(swivel_w * FORWARD_SIGN * (CASTER_OFFSET - AXLE_OFFSET), swivel_v - swivel_w * y)
        if abs(swivel_v) + abs(swivel_w) > 1e-9
        else 0.0
        for y in [CASTER_TRACK / 2, -CASTER_TRACK / 2]
    ]
    requested = axle if trace.get("source") != "settings_reference" else reference(cfg, time)[0]
    return dict(
        axle=axle.tolist(),
        cart=cart_from_axle(axle).tolist(),
        wheelAngles=(distances / WHEEL_RADIUS).tolist(),
        wheelAxisSign=-FORWARD_SIGN,
        wheelSpeeds=speeds.tolist(),
        speed=linear,
        yawRate=yaw,
        casterYaw=caster_yaw,
        commands=([0.0, 0.0] if ended else r["commands"].tolist()),
        wire=("0.00,0.00\n" if ended else r["wire"]),
        referenceAxle=requested.tolist(),
        referenceCart=cart_from_axle(requested).tolist(),
        pathError=float(np.linalg.norm(axle[:2] - requested[:2])),
        yawError=float(abs(axle[2] - requested[2])),
    )


def summary(trace):
    cfg = trace["cfg"]
    records = trace["records"]
    samples = [sample(trace, t) for t in np.linspace(0, cfg["duration"], 321)]
    axle, speeds, distances = trace["final"]
    stop_delta = speeds * cfg["brakeTime"]
    stop_axle = integrate(axle, *stop_delta, cfg["trackWidth"])
    stalled = sum(np.any((abs(r["desired"]) > 1e-6) & (r["target"] == 0)) for r in records) / len(records)
    clipped = any(np.any(abs(r["raw"]) > COMMAND_CAP) for r in records)
    max_error = max(s["pathError"] for s in samples)
    max_yaw = max(s["yawError"] for s in samples)
    return dict(
        type="differential-drive UART prediction",
        version=5,
        scheduleSource=trace.get("source", "settings_reference"),
        initialStagingCart=trace.get("initial_cart"),
        desiredAverageWheelSpeeds=trace.get("desired_average_speeds"),
        desiredAverageWireCommands=trace.get("desired_average_commands"),
        wheelDiameter=2 * WHEEL_RADIUS,
        wheelWidth=WHEEL_WIDTH,
        trackWidth=cfg["trackWidth"],
        axleOffset=AXLE_OFFSET,
        forwardAxis="+X" if FORWARD_SIGN == 1 else "-X",
        commandDirection="reverse" if DIRECTION_SIGN == -1 else "forward",
        commandSign=DIRECTION_SIGN,
        responseModel=trace["response"],
        casterOffset=CASTER_OFFSET,
        wheelLayout="powered front wheels; passive rear swivel casters",
        minimumCommand=MIN_COMMAND,
        commandCap=COMMAND_CAP,
        minimumSpeed=cfg["minimumSpeed"],
        speedAtCapEstimate=(
            cfg["minimumSpeed"] * COMMAND_CAP / MIN_COMMAND
            if trace["response"]["mode"] == "provisional_symmetric"
            else None
        ),
        samplePeriod=trace["dt"],
        responseTime=cfg["responseTime"],
        brakeTime=cfg["brakeTime"],
        baseTurnDegrees=math.degrees(samples[-1]["axle"][2] - samples[0]["axle"][2]),
        peakYawRateDegrees=max(abs(math.degrees(s["yawRate"])) for s in samples),
        maxPathError=max_error,
        finalPathError=samples[-1]["pathError"],
        maxYawErrorDegrees=math.degrees(max_yaw),
        stalledFraction=stalled,
        commandClipped=clipped,
        reproducesRequestedPath=max_error < 0.02 and max_yaw < math.radians(1) and not clipped,
        wheelTravel=distances.tolist(),
        predictedStopTravel=float(np.linalg.norm(stop_axle[:2] - axle[:2])),
        validatedOnHardware=False,
        assumptions=[
            "55 cm / 4 s provisionally mapped to command magnitude 0.04 on both motors",
            "Wheel separation and axle offset estimated until measured",
            trace["response"]["evidence"],
            "Ideal powered-wheel rolling; passive casters align to pivot velocity without drag or swivel delay",
            "reverse_enabled selects negative planned and UART commands; physical polarity remains unverified",
            "Response/brake times are user-adjustable assumptions, zero means instantaneous",
            "50 Hz command loop assumed; UART code itself does not specify a send rate",
        ],
        unknowns=[
            "ESP32 command mode / firmware",
            "encoder speeds",
            "loaded acceleration and braking",
            "motor asymmetry and direction response",
            "mass / center of gravity",
            "floor friction / tire slip / caster drag",
        ],
    )
