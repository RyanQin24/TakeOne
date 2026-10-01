"""Versioned, validated configuration. No hardware discovery or connection."""

import hashlib
import json
import math

from .paths import CONFIGS, WORKSPACE


def read_json(path):
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
    ):
        raise ValueError(f"Unsupported configuration schema: {path}")
    return value


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def rig_config():
    config = read_json(CONFIGS / "rig.json")
    cart = config["cart"]
    for key in [
        "wheel_diameter_m",
        "wheel_width_m",
        "minimum_command",
        "command_cap",
        "track_width_m",
        "minimum_speed_m_s",
        "caster_track_width_m",
        "caster_radius_m",
        "caster_width_m",
        "caster_trail_m",
    ]:
        if finite(cart[key], key) <= 0:
            raise ValueError(f"{key} must be positive")
    if cart["minimum_command"] > cart["command_cap"] or cart["command_cap"] > 0.15:
        raise ValueError("Invalid or expanded motor command limits")
    finite(cart["axle_offset_m"], "axle offset")
    finite(cart["caster_offset_m"], "caster offset")
    if type(cart["drive_forward_sign"]) is not int or cart["drive_forward_sign"] not in (-1, 1):
        raise ValueError("Drive forward sign must be -1 or 1 in the cart frame")
    if type(cart.get("reverse_enabled")) is not bool:
        raise ValueError("reverse_enabled must be exactly true or false")
    if cart["drive_forward_sign"] * cart["axle_offset_m"] <= 0:
        raise ValueError("Powered axle must be ahead of the cart origin")
    if cart["drive_forward_sign"] * cart["caster_offset_m"] >= 0:
        raise ValueError("Passive casters must be behind the cart origin")
    upper = config["upper"]
    if finite(config["tools"]["ring"]["outside_diameter_m"], "Ring outside diameter") <= 0:
        raise ValueError("Ring outside diameter must be positive")
    for key in ("mount_height_m", "maximum_extended_height_m", "horizontal_extension_m"):
        if finite(upper[key], key) <= 0:
            raise ValueError(f"{key} must be positive")
    if upper["maximum_extended_height_m"] <= upper["mount_height_m"]:
        raise ValueError("Maximum extended height must exceed the arm platform")
    for role in ("phone", "light"):
        mount = upper[f"{role}_mount_m"]
        if len(mount) != 3 or any(not math.isfinite(value) for value in mount):
            raise ValueError(f"{role} mount must contain three finite metres")
        if not math.isclose(mount[2], upper["mount_height_m"]):
            raise ValueError(f"{role} mount height must match the arm platform")
    return config


def shot_defaults():
    return read_json(CONFIGS / "shots/arm-led.json")["settings"].copy()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance():
    roots = [WORKSPACE / "configs", WORKSPACE / "calibration", WORKSPACE / "assets/robots/takeone"]
    paths = [p for root in roots for p in root.rglob("*") if p.is_file()]
    paths += sorted((WORKSPACE / "packages/takeone").rglob("*.py"))
    paths += [WORKSPACE / "assets/robots/reference/rig_5dof.xml"]
    paths += [p for p in (WORKSPACE / "assets/robots/reference/upstream").rglob("*") if p.is_file()]
    snapshot = {p.relative_to(WORKSPACE).as_posix(): file_hash(p) for p in sorted(paths)}
    loaded = {key: value for key, value in snapshot.items() if _is_process_input(key)}
    if loaded != _PROCESS_INPUTS:
        raise ValueError(
            "Planner process has stale code or drive settings; restart it before preparing motion"
        )
    return snapshot


def _is_process_input(key):
    if key.startswith("packages/takeone/"):
        # These services do not participate in motion calculation. Their source
        # hashes remain in plan provenance, but editing a recording or Director
        # service must not invalidate the planner's loaded geometry/constants.
        return key.split("/")[2] not in ("director", "editor", "recording", "voice")
    return key in (
        "configs/rig.json",
        "configs/shots/arm-led.json",
        "configs/cart-response.json",
    )


def current_process_inputs():
    """Hash, from disk right now, exactly the files whose constants this process captured."""
    return {
        p.relative_to(WORKSPACE).as_posix(): file_hash(p)
        for p in [
            *sorted((WORKSPACE / "packages/takeone").rglob("*.py")),
            CONFIGS / "rig.json",
            CONFIGS / "shots/arm-led.json",
            CONFIGS / "cart-response.json",
        ]
        if _is_process_input(p.relative_to(WORKSPACE).as_posix())
    }


# Some geometry and shot constants are captured at import. Never attach current
# disk hashes to a plan made with an older process's constants after git pull.
_PROCESS_INPUTS = current_process_inputs()


LIGHT_TYPES = ("ring", "panel", "tube")
