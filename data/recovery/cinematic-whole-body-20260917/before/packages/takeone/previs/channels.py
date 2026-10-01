"""Independent shot channels. Positions are shot-local XYZ metres; angles are radians.

Arm/lens keys use normalized filming time, excluding calibrated setup. Pace keys
use normalized route distance, so changing speed cannot change their ordering.
The serialized contract stays JSON-only and has no device dependencies.
"""

import copy
import math
from dataclasses import dataclass

from .policy import motion_policy


@dataclass(frozen=True)
class Channel:
    label: str
    unit: str
    minimum: float
    maximum: float
    dimensions: int = 1


CHANNELS = {
    "camera_height_m": Channel("Camera height", "m", 0.7, 1.8),
    "camera_position_m": Channel("Optical path Â· fixed shot frame", "m", -100, 100, 3),
    "pan_rad": Channel("Added pan", "rad", -math.pi / 2, math.pi / 2),
    "tilt_rad": Channel("Added tilt", "rad", -math.pi / 2, math.pi / 2),
    "roll_rad": Channel("Added roll", "rad", -math.pi / 2, math.pi / 2),
    "camera_target_m": Channel("Camera target", "m", -100, 100, 3),
    "light_height_m": Channel("Light height", "m", 0.7, 1.8),
    "light_target_m": Channel("Light target", "m", -100, 100, 3),
    "pace_m_s": Channel("Cart pace · route progress", "m/s", 0.14, motion_policy().cart_pace_max_m_s),
    "actor_position_m": Channel("Actor blocking · floor position", "m", -100, 100, 3),
    "actor_heading_rad": Channel("Actor body turn", "rad", -math.tau, math.tau),
    "gaze_yaw_rad": Channel("Actor look left / right", "rad", -math.pi / 2, math.pi / 2),
    "gaze_pitch_rad": Channel("Actor look up / down", "rad", -math.pi / 3, math.pi / 3),
}


def smooth(u):
    u = min(1.0, max(0.0, float(u)))
    return u * u * u * (10 + u * (-15 + 6 * u))


def number(value, low, high, label):
    if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be between {low:g} and {high:g}.")
    return float(value)


def validate_channels(value):
    if not isinstance(value, dict) or set(value) - CHANNELS.keys():
        raise ValueError("Choose named camera, aim, light or pace channels.")
    if "camera_position_m" in value and "camera_height_m" in value:
        raise ValueError("Optical XYZ path already owns height; remove the separate camera-height track.")
    result = copy.deepcopy(value)
    for name, keys in result.items():
        spec = CHANNELS[name]
        if not isinstance(keys, list) or not 2 <= len(keys) <= 32:
            raise ValueError(f"{spec.label} needs 2 to 32 keys.")
        previous = -1.0
        for key in keys:
            if not isinstance(key, dict) or set(key) != {"at", "value", "ease"}:
                raise ValueError("Each channel key needs at, value and ease.")
            key["at"] = number(key["at"], 0, 1, "Key time")
            if key["at"] <= previous or key["ease"] not in ("smooth", "linear", "hold"):
                raise ValueError("Use increasing key times and smooth, linear or hold interpolation.")
            previous = key["at"]
            values = [key["value"]] if spec.dimensions == 1 else key["value"]
            if not isinstance(values, list) or len(values) != spec.dimensions:
                raise ValueError(f"{spec.label} needs {spec.dimensions} coordinates.")
            values = [number(v, spec.minimum, spec.maximum, spec.label) for v in values]
            key["value"] = values[0] if spec.dimensions == 1 else values
        if keys[0]["at"] != 0 or keys[-1]["at"] != 1:
            raise ValueError(f"{spec.label} needs keys at 0% and 100%.")
        if name == "camera_position_m":
            if any(not 0.7 <= key["value"][2] <= 1.8 for key in keys):
                raise ValueError("Optical path height must stay within the existing 0.7â€“1.8 m authoring range.")
            if any(a["ease"] == "hold" and a["value"] != b["value"] for a, b in zip(keys, keys[1:])):
                raise ValueError("Optical path cannot teleport; use continuous keys.")
        if name == "actor_position_m":
            if any(key["value"][2] != 0 for key in keys):
                raise ValueError("Actor blocking is on the floor; keep Z at zero.")
            if any(a["ease"] == "hold" and a["value"] != b["value"] for a, b in zip(keys, keys[1:])):
                raise ValueError(
                    "Actor blocking cannot teleport. Use a smooth or linear move between positions."
                )
    return result


def evaluate(keys, fraction, fallback=None):
    if not keys:
        return fallback
    if fraction <= keys[0]["at"]:
        return keys[0]["value"]
    for a, b in zip(keys, keys[1:]):
        if fraction < b["at"]:
            u = (fraction - a["at"]) / (b["at"] - a["at"])
            u = smooth(u) if a["ease"] == "smooth" else 0 if a["ease"] == "hold" else u
            if isinstance(a["value"], list):
                return [x + (y - x) * u for x, y in zip(a["value"], b["value"])]
            return a["value"] + (b["value"] - a["value"]) * u
    return keys[-1]["value"]


def channel(program, name, fraction, fallback=None):
    return evaluate((program or {}).get("channels", {}).get(name), fraction, fallback)


def ramp(start, end, begin=0.0, finish=1.0):
    points = [(0.0, start), (begin, start), (finish, end), (1.0, end)]
    return [dict(at=at, value=v, ease="smooth") for at, v in dict(points).items()]


def validate_texture(value):
    if not isinstance(value, dict) or set(value) != {"enabled", "amplitude_rad", "frequency_hz"}:
        raise ValueError("Organic drift needs enabled, amplitude_rad and frequency_hz.")
    if type(value["enabled"]) is not bool:
        raise ValueError("Organic drift enabled must be true or false.")
    return dict(
        enabled=value["enabled"],
        amplitude_rad=number(value["amplitude_rad"], 0, math.radians(5), "Drift amount"),
        frequency_hz=number(value["frequency_hz"], 0.1, 1, "Drift frequency"),
    )


def validate_breath(value):
    defaults = dict(pre_hold_s=0.0, post_hold_s=0.0, entry_s=0.0, exit_s=0.0)
    if not isinstance(value, dict) or set(value) - defaults.keys():
        raise ValueError("Cart breath needs pre/post holds and entry/exit durations.")
    return {k: number(v, 0, 10, k) for k, v in (defaults | value).items()}


def catalog():
    from dataclasses import asdict

    return {name: asdict(spec) for name, spec in CHANNELS.items()}
