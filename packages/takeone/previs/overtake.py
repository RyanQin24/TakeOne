"""Timed straight pass integrated from the actual bounded wheel packets."""

import math

import numpy as np

from takeone.cart.response import CartResponse
from takeone.config import rig_config
from takeone.motion.studio_plan import ARM_PERIOD, CART_PERIOD
from takeone.protocol import COMMAND_CAP, MIN_COMMAND, uart_pair
from takeone.simulation.drive import integrate

from .policy import motion_policy

CONTROL_PERIOD = 0.2


def forward_target(axle, height):
    return np.array([axle[0] + 100 * math.cos(axle[2]), axle[1] + 100 * math.sin(axle[2]), height])


def motor_route(settings, response=None):
    cfg = rig_config()["cart"]
    response = response or CartResponse.load(cfg["minimum_speed_m_s"])
    count = math.ceil(settings["program"]["duration_s"] / ARM_PERIOD) * 2
    block_ticks = round(CONTROL_PERIOD / CART_PERIOD)
    blocks = math.ceil(count / block_ticks)
    demand = min(settings["speed_m_s"], motion_policy().cart_pace_max_m_s)
    start, end = (np.asarray(p) for p in settings["points_m"])
    heading = math.atan2(*(end - start)[::-1])
    axle = np.array([*start, heading])
    # Keep the existing deadband and two-decimal wire precision. Measured
    # response tables are never extrapolated, even for an editable pace.
    choices = []
    for side in range(2):
        wheel = [(0.0, 0.0)]
        for value in range(round(MIN_COMMAND * 100), round(COMMAND_CAP * 100) + 1):
            command = value / 100
            try:
                speed = (
                    response.speeds_for((command, command))[side]
                    if response.wheels is None
                    else response.wheels[side].interpolate(command)
                )
                wheel.append((command, speed))
            except ValueError:
                continue
        choices.append(wheel)
    pairs = [
        (np.array([lc, rc]), np.array([lv, rv]))
        for lc, lv in choices[0]
        for rc, rv in choices[1]
        if (lc == 0) == (rc == 0) and max(lv, rv) <= demand + 1e-9
    ]
    if not any(max(c) > 0 for c, _ in pairs):
        raise ValueError("The wheel response has no supported forward command at this pace.")
    previous = np.zeros(2)
    rows, poses, travel = [], [axle.tolist()], [[0.0, 0.0]]
    distances = np.zeros(2)
    for block in range(blocks):
        # Reserve enough 200 ms blocks to ramp back to zero before the end.
        remaining = blocks - 1 - block
        cap = 0.0 if block == 0 or remaining == 0 else MIN_COMMAND + 0.01 * (remaining - 1)
        allowed = [
            (c, v)
            for c, v in pairs
            if max(c) <= cap + 1e-9
            and all(
                abs(new - old) <= 0.010001 or (min(new, old) == 0 and max(new, old) <= MIN_COMMAND + 1e-9)
                for new, old in zip(c, previous)
            )
        ]
        if not allowed:
            raise ValueError(
                "The measured wheel response cannot ramp to a stop within this shot. Add measured neighbouring commands."
            )
        commands, speeds = min(
            allowed,
            key=lambda pair: (float(sum(pair[1])) / 2 - demand) ** 2
            + 100 * float(pair[1][1] - pair[1][0]) ** 2,
        )
        previous = commands
        for _ in range(min(block_ticks, count - len(rows))):
            rows.append(dict(commands=commands.tolist(), wire=uart_pair(*commands)))
            axle = integrate(axle, *(speeds * CART_PERIOD), cfg["track_width_m"])
            distances += speeds * CART_PERIOD
            poses.append(axle.tolist())
            travel.append(distances.tolist())
    if max(distances) <= 0:
        raise ValueError("The requested duration is too short to accelerate and stop at this pace.")
    distance = float(sum(distances)) / 2
    target_end = start + distance * np.array([math.cos(heading), math.sin(heading)])
    return dict(
        rows=rows,
        poses=poses,
        wheel_travel=travel,
        reference=[start.tolist(), target_end.tolist()],
        distance_m=distance,
        endpoint_error_m=float(np.linalg.norm(axle[:2] - target_end)),
        response_mode=response.mode,
    )
