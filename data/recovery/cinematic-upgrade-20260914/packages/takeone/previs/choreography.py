"""Camera-height choreography in world metres, separate from cart travel.

The subject is stationary in this first template. The phone stays aimed at its
face as the optical origin rises, so the upward pitch naturally approaches zero.
"""

import math


def validate_choreography(value):
    if value is None:
        return None
    keys = {"height_start_m", "height_end_m", "rise_start", "rise_end"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("Camera choreography needs both heights and a rise interval.")
    result = {}
    for key in keys:
        low, high = (0.7, 1.8) if key.startswith("height") else (0.0, 1.0)
        v = value[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f"{key} must be between {low:g} and {high:g}.")
        result[key] = float(v)
    if result["rise_end"] - result["rise_start"] < 0.05:
        raise ValueError("Give the camera rise at least 5% of the travel time.")
    return result


def camera_height(choreography, fraction, fallback):
    if choreography is None:
        return fallback
    u = max(
        0.0,
        min(
            1.0,
            (fraction - choreography["rise_start"]) / (choreography["rise_end"] - choreography["rise_start"]),
        ),
    )
    # Quintic smoothstep: zero lift speed and acceleration at both ends.
    s = u * u * u * (10 + u * (-15 + 6 * u))
    return choreography["height_start_m"] + s * (
        choreography["height_end_m"] - choreography["height_start_m"]
    )


def light_height(choreography, fraction):
    if choreography is None:
        return 1.6
    # Move the fill with the reveal while independently keeping its beam on face.
    low, high = choreography["height_start_m"], choreography["height_end_m"]
    return 1.5 + 0.15 * (
        (camera_height(choreography, fraction, low) - low) / (high - low) if high != low else 0
    )
