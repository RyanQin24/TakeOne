"""Illustrative straight acceleration, deliberately without a motor response map."""

import math

import numpy as np

from takeone.motion.studio_plan import CART_PERIOD
from takeone.protocol import uart_pair


def forward_target(axle, height):
    return np.array([axle[0] + 100 * math.cos(axle[2]), axle[1] + 100 * math.sin(axle[2]), height])


def simulated_route(settings):
    duration = settings["program"]["duration_s"]
    count = round(duration / (2 * CART_PERIOD)) * 2
    duration = count * CART_PERIOD
    peak = settings["speed_m_s"]
    ramp = duration * 0.2
    start, end = (np.asarray(p) for p in settings["points_m"])
    direction = (end - start) / np.linalg.norm(end - start)
    heading = math.atan2(direction[1], direction[0])
    poses, travel, speeds = [], [], []
    for index in range(count + 1):
        t = index * CART_PERIOD
        if t <= ramp:
            speed, distance = peak * t / ramp, peak * t * t / (2 * ramp)
        elif t <= duration - ramp:
            speed, distance = peak, peak * (t - ramp / 2)
        else:
            remaining = duration - t
            speed = peak * remaining / ramp
            distance = peak * (duration - ramp) - peak * remaining**2 / (2 * ramp)
        poses.append([*(start + direction * distance), heading])
        travel.append([distance, distance])
        speeds.append(speed)
    return dict(
        rows=[dict(commands=[0.0, 0.0], wire=uart_pair(0, 0)) for _ in range(count)],
        poses=poses,
        wheel_travel=travel,
        speeds=speeds,
        reference=[start.tolist(), end.tolist()],
        distance_m=travel[-1][0],
        endpoint_error_m=float(np.linalg.norm(np.asarray(poses[-1][:2]) - end)),
        response_mode="illustrative_simulation_only",
    )
