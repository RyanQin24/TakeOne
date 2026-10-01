"""Editable orbit assumptions, photographic lens presets and rig joint inventory."""

import math

from takeone.calibration import ArmMapping
from takeone.contracts import JOINTS

from .camera import PROFILE, defaults

DEFAULTS = dict(
    radius_m=2.5,
    duration_s=20.0,
    sweep_rad=math.tau,
    bearing_rad=0.0,
    height_m=1.5,
    focal_mm=48.0,
    subject_height_m=1.72,
    ease="smooth",
    camera=defaults(),
)
LENSES = [
    {"name": "0.5× · Ultra Wide", "mm": 13, "type": "physical_lens"},
    {"name": "1× · Main", "mm": 24, "type": "physical_lens"},
    {"name": "2× · Main crop", "mm": 48, "type": "sensor_crop"},
    {"name": "4× · Telephoto", "mm": 100, "type": "physical_lens"},
    {"name": "8× · Telephoto crop", "mm": 200, "type": "sensor_crop"},
    {"name": "15× · Digital video (approx.)", "mm": 360, "type": "digital_crop"},
]


def capabilities():
    arms = {}
    for role in ("phone", "light"):
        mapping = ArmMapping.load(role, require_motion=False)
        arms[role] = [
            {
                "name": name,
                "motor_id": mapping.raw_calibration[name]["id"],
                "raw_min": mapping.raw_calibration[name]["range_min"],
                "raw_max": mapping.raw_calibration[name]["range_max"],
                "range_rad": bounds,
            }
            for name, bounds in zip(JOINTS, mapping.safe_ranges_rad)
        ]
    return {
        "mode": "kinematic_previs",
        "arms": arms,
        "frame": "world: X/Y floor, Z up; cart drive +X, mounts facing +Y",
        "camera_model": "iPhone 17 Pro Max equivalent framing, 16:9 pinhole crop",
        "cart_model": "Circular powered-axle path with tangent steering; ideal forward or reverse travel",
        "tracking_source": "simulated static actor face",
        "assumptions": [
            "Ideal traction and cart response",
            "Configured joint ranges and existing tool geometry",
            "Kinematics only",
        ],
    }


def catalog():
    return {"defaults": DEFAULTS, "lenses": LENSES, "camera_profile": dict(PROFILE), "capabilities": capabilities()}
