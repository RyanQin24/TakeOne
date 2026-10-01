"""Camera and subject channels evaluated on one shot clock. SI/world Z up."""

import math

import numpy as np


def smooth(u):
    u = min(1.0, max(0.0, float(u)))
    return u * u * u * (10 + u * (-15 + 6 * u))


def change_progress(program, fraction):
    return smooth((fraction - program["rise_start"]) / (program["rise_end"] - program["rise_start"]))


def subject(program, fraction, height):
    """The face target includes the same body bob displayed by the walking figure."""
    walking = program is not None and program["subject_motion"] == "walk"
    distance = program["actor_distance_m"] * fraction if walking else 0.0
    heading = program["actor_heading_rad"] if walking else 0.0
    phase = math.tau * distance / 0.9
    envelope = smooth(fraction / 0.06) * smooth((1 - fraction) / 0.06) if walking else 0.0
    bob = 0.014 * math.sin(phase) ** 2 * envelope
    position = [math.cos(heading) * distance, math.sin(heading) * distance, bob]
    return dict(
        position_m=position, heading_rad=heading, phase_rad=phase, gait_weight=envelope, walking=walking
    ), np.array([*position[:2], height * 0.925 + bob])


def aim_offsets(program, fraction, travel_s):
    if program is None:
        return (0.0, 0.0, 0.0)
    u = change_progress(program, fraction)
    aim, angle = program["aim"], program["angle_rad"] * program["sign"]
    if aim == "pan":
        return (angle * (u - 0.5), 0.0, 0.0)
    if aim == "tilt":
        return (0.0, angle * (u - 1 if angle > 0 else u), 0.0)
    if aim == "high":
        return (0.0, -angle * u, 0.0)
    if aim == "roll":
        return (0.0, 0.0, angle * u)
    if aim == "handheld":
        phase = math.tau * program["hand_frequency_hz"] * travel_s * fraction
        amount = program["hand_amplitude_rad"] * math.sin(math.pi * fraction) ** 2
        return (
            amount * math.sin(phase),
            0.7 * amount * math.sin(phase * 1.37),
            0.5 * amount * math.sin(phase * 0.73),
        )
    return (0.0, 0.0, 0.0)


def aim_direction(position, target, yaw=0.0, pitch=0.0):
    direction = target - position
    if yaw == 0 and pitch == 0:
        return direction / max(1e-8, np.linalg.norm(direction))
    azimuth = math.atan2(direction[1], direction[0]) + yaw
    elevation = math.atan2(direction[2], math.hypot(direction[0], direction[1])) + pitch
    elevation = min(math.pi / 2 - 0.001, max(-math.pi / 2 + 0.001, elevation))
    return np.array(
        [
            math.cos(elevation) * math.cos(azimuth),
            math.cos(elevation) * math.sin(azimuth),
            math.sin(elevation),
        ]
    )


def focal_length(program, fraction, depth, opening_depth, fallback):
    if program is None:
        return fallback
    if program["aim"] == "zoom":
        return fallback + (program["focal_end_mm"] - fallback) * change_progress(program, fraction)
    if program["aim"] == "dolly_zoom":
        # Pinhole image scale is f / optical depth, not f / cart radius.
        return min(200.0, max(13.0, fallback * depth / max(opening_depth, 1e-8)))
    return fallback
