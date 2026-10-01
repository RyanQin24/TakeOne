"""Compile the orbit study into a finite, calibrated, open-loop robot take. No device IO."""

import math

from takeone.calibration import ArmMapping
from takeone.cart.response import CartResponse
from takeone.config import finite, provenance, rig_config
from takeone.contracts import JOINTS
from takeone.motion.plan import digest
from takeone.protocol import COMMAND_CAP, MIN_COMMAND, uart_pair

ROLES = ("phone", "light")
SCHEMA = "takeone.studio-motion.v1"
ARM_PERIOD = 0.04
CART_PERIOD = 0.02


def progress(settings, fraction):
    u = max(0.0, min(1.0, fraction))
    return u * u * (3 - 2 * u) if settings["ease"] == "smooth" else u


def prepare(settings):
    from takeone.previs.compiler import compile_orbit

    preview = compile_orbit(settings)
    settings = preview["settings"]
    cart = rig_config()["cart"]
    response = CartResponse.load(cart["minimum_speed_m_s"])
    radius, sweep = settings["radius_m"], settings["sweep_rad"]
    wheel_travel = [
        (-radius - cart["track_width_m"] / 2) * sweep,
        (-radius + cart["track_width_m"] / 2) * sweep,
    ]
    # Use only wire values the configured response can actually describe.
    choices = []
    for index, travel in enumerate(wheel_travel):
        sign = math.copysign(1, travel)
        wheel = [(0.0, 0.0)]
        for magnitude in range(round(MIN_COMMAND * 100), round(COMMAND_CAP * 100) + 1):
            command = sign * magnitude / 100
            try:
                speeds = response.speeds_for((command, command)) if response.wheels is None else None
                speed = speeds[index] if speeds else response.wheels[index].interpolate(command)
                wheel.append((command, speed))
            except ValueError:
                continue
        if len(wheel) < 2:
            raise ValueError("The configured wheel response has no commands for this direction.")
        choices.append(wheel)
    peak = 1.5 if settings["ease"] == "smooth" else 1.0
    duration = max(
        settings["duration_s"],
        *(peak * abs(d) / max(abs(v) for _, v in c) for d, c in zip(wheel_travel, choices)),
    )
    duration = math.ceil(duration / ARM_PERIOD - 1e-9) * ARM_PERIOD
    if duration > 600:
        raise ValueError(
            f"This orbit needs {duration:.0f} s at the cart command cap. Use a smaller radius or sweep."
        )
    total = [0.0, 0.0]
    schedule = []
    count = round(duration / CART_PERIOD)
    # Error diffusion keeps the integrated wheel travel close to the requested
    # circle despite the controller's two-decimal commands and deadband.
    for i in range(count):
        target = [d * progress(settings, (i + 1) / count) for d in wheel_travel]
        selected = [
            min(c, key=lambda pair: abs(goal - (old + pair[1] * CART_PERIOD)))
            for c, goal, old in zip(choices, target, total)
        ]
        commands = [pair[0] for pair in selected]
        total = [old + pair[1] * CART_PERIOD for old, pair in zip(total, selected)]
        schedule.append(dict(time_s=i * CART_PERIOD, commands=commands, wire=uart_pair(*commands)))
    schedule.append(dict(time_s=duration, commands=[0.0, 0.0], wire=uart_pair(0, 0)))
    # Both calibrated arm poses are fixed relative to the turning cart for this template.
    arms = {r: preview["frames"][0]["q"][3 + i * 5 : 8 + i * 5] for i, r in enumerate(ROLES)}
    raw = {r: ArmMapping.load(r, require_motion=False).to_raw(arms[r]) for r in ROLES}
    body = dict(
        schema=SCHEMA,
        provenance=provenance(),
        settings=settings,
        roles=list(ROLES),
        joint_order=list(JOINTS),
        arm_period_s=ARM_PERIOD,
        duration_s=duration,
        samples=[dict(time_s=i * ARM_PERIOD, arms=arms) for i in range(round(duration / ARM_PERIOD) + 1)],
        cart_schedule=schedule,
        raw_goals=raw,
        summary=dict(
            requested_duration_s=settings["duration_s"],
            duration_s=duration,
            retimed=abs(duration - settings["duration_s"]) > 1e-6,
            distance_m=radius * abs(sweep),
            max_command=max(abs(v) for s in schedule for v in s["commands"]),
            wheel_travel_m=total,
            requested_wheel_travel_m=wheel_travel,
            predicted_sweep_rad=(total[1] - total[0]) / cart["track_width_m"],
            response_mode=response.mode,
            physical_path_verified=False,
            scope="Cart and both arms; phone recording and lens selection remain manual.",
        ),
    )
    return validate(body | {"plan_id": digest(body)})


def validate(document):
    """Validate a prepared artifact again before opening any hardware."""
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ValueError("Expected a studio motion plan")
    body = {k: v for k, v in document.items() if k != "plan_id"}
    if document.get("plan_id") != digest(body) or document.get("provenance") != provenance():
        raise ValueError("The robot plan changed. Prepare this orbit again.")
    if document["roles"] != list(ROLES) or document["joint_order"] != list(JOINTS):
        raise ValueError("Both calibrated five-motor arms are required")
    duration = finite(document["duration_s"], "Duration")
    if not 0 < duration <= 600 or document["arm_period_s"] != ARM_PERIOD:
        raise ValueError("Invalid robot playback clock")
    samples = document["samples"]
    expected = [i * ARM_PERIOD for i in range(round(duration / ARM_PERIOD) + 1)]
    if [s["time_s"] for s in samples] != expected or abs(expected[-1] - duration) > 1e-8:
        raise ValueError("Arm samples must share the complete playback clock")
    for role in ROLES:
        mapping = ArmMapping.load(role, require_motion=False)
        first = samples[0]["arms"][role]
        raw = mapping.to_raw(first)
        if raw != document["raw_goals"][role]:
            raise ValueError("Preview angles and calibrated motor goals differ")
        if any(sample["arms"][role] != first for sample in samples):
            raise ValueError("The orbit template holds both aiming poses")
    schedule = document["cart_schedule"]
    expected = [i * CART_PERIOD for i in range(round(duration / CART_PERIOD))] + [duration]
    if [s["time_s"] for s in schedule] != expected or schedule[-1]["commands"] != [0, 0]:
        raise ValueError("Cart schedule must share the clock and end with zero")
    for row in schedule:
        pair = row["commands"]
        if len(pair) != 2 or any(abs(finite(v, "Wheel command")) > COMMAND_CAP for v in pair):
            raise ValueError("Wheel command exceeds the configured cap")
        if row["wire"] != uart_pair(*pair) or list(map(float, row["wire"].split(","))) != pair:
            raise ValueError("Wheel commands must match transmitted precision")
        if any(0 < abs(v) < MIN_COMMAND - 1e-9 for v in pair):
            raise ValueError("Moving commands must clear the configured deadband")
    return document
