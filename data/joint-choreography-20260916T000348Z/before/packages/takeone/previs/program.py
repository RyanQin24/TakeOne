"""Camera and subject channels evaluated on one shot clock. SI/world Z up."""

import math

import numpy as np

from .channels import channel, smooth


def change_progress(program, fraction):
    return smooth((fraction - program["rise_start"]) / (program["rise_end"] - program["rise_start"]))


def subject(program, fraction, height, scene=None):
    """The face target includes the same body bob displayed by the walking figure."""
    walking = program is not None and program["subject_motion"] == "walk"
    distance = program["actor_distance_m"] * fraction if walking else 0.0
    heading = program["actor_heading_rad"] if walking else 0.0
    if scene and scene["actor_motion"] != "preset":
        walking = scene["actor_motion"] == "walk"
        distance = scene["walk_distance_m"] * fraction if walking else 0.0
        heading = scene["walk_heading_rad"] if walking else 0.0
    phase = math.tau * distance / 0.9
    envelope = smooth(fraction / 0.06) * smooth((1 - fraction) / 0.06) if walking else 0.0
    bob = 0.014 * math.sin(phase) ** 2 * envelope
    position = [math.cos(heading) * distance, math.sin(heading) * distance, bob]
    keys = (program or {}).get("channels", {}).get("actor_position_m")
    if keys:
        position = list(channel(program, "actor_position_m", fraction))
        before = channel(program, "actor_position_m", max(0, fraction - 0.001))
        after = channel(program, "actor_position_m", min(1, fraction + 0.001))
        walking = math.dist(before, after) > 1e-7
        heading = math.atan2(after[1] - before[1], after[0] - before[0]) if walking else heading
        distance = 0.0
        for a, b in zip(keys, keys[1:]):
            if fraction >= b["at"]:
                distance += math.dist(a["value"], b["value"])
            elif fraction > a["at"]:
                distance += math.dist(a["value"], position)
                break
            else:
                break
        phase = math.tau * distance / 0.9
        envelope = min(1.0, math.dist(before, after) / 0.002) if walking else 0.0
        bob = 0.014 * math.sin(phase) ** 2 * envelope
        position[2] = bob
    actor = dict(
        position_m=position, heading_rad=heading, phase_rad=phase, gait_weight=envelope, walking=walking
    )
    for key in ("gaze_yaw_rad", "gaze_pitch_rad"):
        if key in (program or {}).get("channels", {}):
            actor[key] = channel(program, key, fraction, 0.0)
    if "actor_heading_rad" in (program or {}).get("channels", {}):
        actor["heading_rad"] = channel(program, "actor_heading_rad", fraction, heading)
        actor["authored_heading"] = True
    face = np.array([*position[:2], height * 0.925 + bob])
    if scene:
        from .placement import place_actor

        return place_actor(actor, face, scene)
    return actor, face


def aim_offsets(program, fraction, travel_s):
    if program is None:
        return (0.0, 0.0, 0.0)
    u = change_progress(program, fraction)
    aim, angle = program["aim"], program["angle_rad"] * program["sign"]
    offsets = [0.0, 0.0, 0.0]
    if aim == "pan":
        offsets[0] += angle * (u - 0.5)
    if aim == "tilt":
        offsets[1] += angle * (u - 1 if angle > 0 else u)
    if aim == "high":
        offsets[1] -= angle * u
    if aim == "roll":
        offsets[2] += angle * u
    texture = program.get("texture", {})
    # The handheld preset supplies one contribution; an enabled overlay does
    # not accidentally double it. Other aims and routes can all carry texture.
    if aim == "handheld" or texture.get("enabled"):
        frequency = texture["frequency_hz"] if texture.get("enabled") else program["hand_frequency_hz"]
        amplitude = texture["amplitude_rad"] if texture.get("enabled") else program["hand_amplitude_rad"]
        phase = math.tau * frequency * travel_s * fraction
        amount = amplitude * math.sin(math.pi * fraction) ** 2
        offsets[0] += amount * math.sin(phase)
        offsets[1] += 0.7 * amount * math.sin(phase * 1.37)
        offsets[2] += 0.5 * amount * math.sin(phase * 0.73)
    for i, name in enumerate(("pan_rad", "tilt_rad", "roll_rad")):
        offsets[i] += channel(program, name, fraction, 0.0)
    return tuple(offsets)


def camera_target(program, face, fraction=0.0):
    """A landmark target is independent of the actor's head and walking path."""
    target = (program or {}).get("camera_target", {})
    offset = np.asarray(target.get("position_m", [0.0, 0.0, 0.0]), dtype=float)
    point = offset if target.get("kind") == "point" else face + offset
    return np.asarray(channel(program, "camera_target_m", fraction, point), dtype=float)


def light_target(program, face, fraction=0.0):
    """Light follows the subject until its own target keys override that aim."""
    target = (program or {}).get("camera_target", {})
    point = target["position_m"] if target.get("kind") == "point" else face
    return np.asarray(channel(program, "light_target_m", fraction, point), dtype=float)


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
