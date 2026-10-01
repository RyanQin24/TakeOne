"""Named, parameterized shot templates compiled through the shared motor plan.

First review slice: low-angle rising orbit. Further movement families and Dolly
Zoom semantics are documented in docs/camera-movement-library.md.
"""

import math

from takeone.motion.plan import digest

from .choreography import validate_choreography
from .compiler import orbit_pose

DEFAULTS = dict(
    mode="template",
    template_id="hero_orbit",
    radius_m=2.5,
    sweep_rad=math.pi / 2,
    bearing_rad=math.pi,
    speed_m_s=0.17,
    height_start_m=1.25,
    height_end_m=1.59,
    rise_start=0.1,
    rise_end=0.85,
    focal_mm=35.0,
    subject_height_m=1.72,
)


def validate_settings(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Expected named shot template settings.")
    s = DEFAULTS | value
    if s["mode"] != "template" or s["template_id"] != "hero_orbit":
        raise ValueError("Choose the rising orbit template.")
    for key, low, high in [
        ("radius_m", 0.8, 10),
        ("sweep_rad", math.pi / 12, math.tau),
        ("bearing_rad", -math.tau, math.tau),
        ("speed_m_s", 0.14, 0.35),
        ("focal_mm", 13, 200),
        ("subject_height_m", 0.8, 2.2),
    ]:
        v = s[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f"{key} must be between {low:g} and {high:g}.")
        s[key] = float(v)
    s.update(
        validate_choreography({k: s[k] for k in ("height_start_m", "height_end_m", "rise_start", "rise_end")})
    )
    return s


def path_settings(settings):
    s = validate_settings(settings)
    count = max(12, math.ceil(s["radius_m"] * s["sweep_rad"] / 0.15))
    points = [orbit_pose(s | {"ease": "linear"}, i / count, 0)[1].tolist() for i in range(count + 1)]
    return dict(
        mode="path",
        points_m=points,
        speed_m_s=s["speed_m_s"],
        height_m=s["height_start_m"],
        focal_mm=s["focal_mm"],
        subject_height_m=s["subject_height_m"],
        choreography={k: s[k] for k in ("height_start_m", "height_end_m", "rise_start", "rise_end")},
    )


def compile_template(value):
    from .path import compile_path

    settings = validate_settings(value)
    result = compile_path(path_settings(settings))
    plan, preview = result["plan"], result["preview"]
    plan["settings"] = settings
    plan["summary"]["scope"] = (
        "Rising orbit: coordinated cart and changing phone/light arm goals. Recording and lenses remain manual."
    )
    plan["plan_id"] = digest({k: v for k, v in plan.items() if k != "plan_id"})
    preview.update(kind="takeone_template_previs", settings=settings, plan_id=plan["plan_id"])
    return result


def catalog():
    return dict(
        schema_version=1,
        defaults=DEFAULTS,
        templates=[
            dict(
                id="hero_orbit",
                name="Hero reveal · rising orbit",
                status="implemented",
                intent="Establish presence from a low angle, then rise toward an eye-level connection.",
                components=["arc", "camera_lift", "face_aim"],
                parameters=list(DEFAULTS),
                subject_motion="stationary",
            )
        ],
    )
