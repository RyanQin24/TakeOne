"""Film movements expanded into one cart/arms/lens program. No device IO."""

import copy
import math

from .camera import MAX_FOCAL_MM, apply_camera, validate_camera
from .camera import defaults as camera_defaults
from .choreography import validate_choreography
from .compiler import orbit_pose

DEG = math.pi / 180
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
    distance_m=1.5,
    duration_s=10.0,
    angle_rad=30 * DEG,
    focal_end_mm=70.0,
    subject_motion="hold",
    actor_distance_m=1.5,
    actor_heading_rad=0.0,
    light_height_start_m=1.5,
    light_height_end_m=1.65,
    hand_amplitude_rad=1.5 * DEG,
    hand_frequency_hz=0.45,
    camera=camera_defaults(),
)


def preset(id, name, family, intent, route="hold", aim="face", sign=1, **defaults):
    return dict(
        id=id, name=name, family=family, intent=intent, route=route, aim=aim, sign=sign, overrides=defaults
    )


# Each entry composes real channels. It does not substitute an orbit for another move.
PRESETS = [
    preset(
        "static",
        "Static · locked frame",
        "Hold & reveal",
        "Let performance carry a still frame.",
        aim="locked",
    ),
    preset(
        "pan_left",
        "Pan left",
        "Hold & reveal",
        "Reveal the space horizontally with a measured camera turn.",
        aim="pan",
    ),
    preset(
        "pan_right",
        "Pan right",
        "Hold & reveal",
        "Follow attention across the scene without moving the cart.",
        aim="pan",
        sign=-1,
    ),
    preset(
        "tilt_up",
        "Tilt up",
        "Hold & reveal",
        "Reveal body to face while keeping the camera at one height.",
        aim="tilt",
    ),
    preset(
        "tilt_down",
        "Tilt down",
        "Hold & reveal",
        "Move attention from face to a detail below.",
        aim="tilt",
        sign=-1,
    ),
    preset(
        "whip_pan",
        "Whip pan",
        "Hold & reveal",
        "A quick horizontal reveal with a hold on either side; actual speed follows the arm trajectory.",
        aim="pan",
        duration_s=4.0,
        angle_rad=28 * DEG,
        rise_start=0.15,
        rise_end=0.85,
    ),
    preset(
        "push_in",
        "Dolly in · push in",
        "Dolly & lens",
        "Move closer to emphasize a thought or realization.",
        route="in",
    ),
    preset(
        "pull_out",
        "Dolly out · pull out",
        "Dolly & lens",
        "Move away to reveal context and space around the actor.",
        route="out",
    ),
    preset(
        "zoom_in",
        "Zoom in",
        "Dolly & lens",
        "Tighten the lens framing while the camera position holds.",
        aim="zoom",
        focal_mm=24.0,
        focal_end_mm=70.0,
    ),
    preset(
        "zoom_out",
        "Zoom out",
        "Dolly & lens",
        "Reveal the surroundings through a widening lens.",
        aim="zoom",
        focal_mm=70.0,
        focal_end_mm=24.0,
    ),
    preset(
        "dolly_zoom_in",
        "Dolly Zoom · move in / zoom out",
        "Dolly & lens",
        "Keep the actor's image size steady while approaching and widening the lens.",
        route="in",
        aim="dolly_zoom",
        focal_mm=50.0,
    ),
    preset(
        "dolly_zoom_out",
        "Dolly Zoom · move out / zoom in",
        "Dolly & lens",
        "Keep the actor's image size steady while retreating and tightening the lens.",
        route="out",
        aim="dolly_zoom",
        focal_mm=35.0,
    ),
    preset(
        "track_follow",
        "Tracking · follow a walking actor",
        "Follow & travel",
        "Travel behind a walking actor and stay with the action.",
        route="follow",
        subject_motion="walk",
        actor_heading_rad=math.pi / 2,
    ),
    preset(
        "track_lead",
        "Tracking · lead a walking actor",
        "Follow & travel",
        "Travel ahead of the actor with the lens facing back toward them.",
        route="lead",
        subject_motion="walk",
        actor_heading_rad=math.pi / 2,
    ),
    preset(
        "truck_left",
        "Truck left",
        "Follow & travel",
        "Travel laterally across the scene while aiming toward the actor.",
        route="truck",
        sign=-1,
    ),
    preset(
        "truck_right",
        "Truck right",
        "Follow & travel",
        "Reveal depth and parallax along a forward ground route.",
        route="truck",
    ),
    preset(
        "side_track",
        "Side tracking · walk alongside",
        "Follow & travel",
        "Match a walking actor from the side.",
        route="side",
        subject_motion="walk",
    ),
    preset(
        "arc_left",
        "Arc · counterclockwise",
        "Arc & orbit",
        "Change perspective around the actor while retaining face aim.",
        route="arc",
    ),
    preset(
        "arc_right",
        "Arc · clockwise",
        "Arc & orbit",
        "Circle the other way, starting with the powered wheels facing that tangent.",
        route="arc",
        sign=-1,
    ),
    preset(
        "orbit_360",
        "Orbit · full 360°",
        "Arc & orbit",
        "Explore the space all around the actor with continuous face aim.",
        route="arc",
        sweep_rad=math.tau,
    ),
    preset(
        "hero_orbit",
        "Hero reveal · rising orbit",
        "Arc & orbit",
        "Begin at chest height looking up, then rise toward eye level during the orbit.",
        route="arc",
        height_start_m=1.25,
        height_end_m=1.59,
        light_height_start_m=1.5,
        light_height_end_m=1.65,
    ),
    preset(
        "boom_up",
        "Pedestal / boom up",
        "Height & perspective",
        "Raise the optical origin while retaining face aim.",
        height_start_m=1.25,
        height_end_m=1.59,
        duration_s=24.0,
    ),
    preset(
        "boom_down",
        "Pedestal / boom down",
        "Height & perspective",
        "Lower the camera into a more grounded composition.",
        height_start_m=1.59,
        height_end_m=1.25,
        duration_s=24.0,
    ),
    preset(
        "crane_reveal",
        "Jib-style reveal · travel and rise",
        "Height & perspective",
        "Combine an approaching cart and arm lift to reveal height and depth on this rig.",
        route="in",
        height_start_m=1.25,
        height_end_m=1.59,
        distance_m=3.0,
    ),
    preset(
        "high_angle",
        "High-angle reveal",
        "Height & perspective",
        "Lift and angle down toward the body. The preview shows the achieved viewpoint.",
        aim="high",
        height_start_m=1.50,
        height_end_m=1.62,
        angle_rad=15 * DEG,
        duration_s=24.0,
    ),
    preset(
        "roll_left",
        "Roll left · Dutch transition",
        "Roll & handheld",
        "Rotate the horizon to introduce unease while keeping the actor as the target.",
        aim="roll",
        angle_rad=25 * DEG,
    ),
    preset(
        "roll_right",
        "Roll right · Dutch transition",
        "Roll & handheld",
        "Build a tilted composition in the opposite direction.",
        aim="roll",
        sign=-1,
        angle_rad=25 * DEG,
    ),
    preset(
        "handheld",
        "Handheld-style · subtle drift",
        "Roll & handheld",
        "Layer repeatable small pan, tilt and roll movements around a face-directed frame.",
        aim="handheld",
    ),
]
BY_ID = {p["id"]: p for p in PRESETS}


def field(key, label, low, high, step, unit="", scale=1.0):
    return dict(key=key, label=label, min=low, max=high, step=step, unit=unit, scale=scale)


# Canonical SI values and their display conversions are shared with the UI.
FIELDS = {
    f["key"]: f
    for f in [
        field("radius_m", "Actor to cart", 0.8, 10, 0.1, "m"),
        field("sweep_rad", "Orbit sweep", 15, 360, 5, "°", 1 / DEG),
        field("bearing_rad", "Starting position angle", -360, 360, 5, "°", 1 / DEG),
        field("speed_m_s", "Cart pace", 0.14, 0.35, 0.01, "m/s"),
        field("distance_m", "Cart travel", 0.2, 10, 0.1, "m"),
        field("duration_s", "Shot duration", 2, 120, 0.5, "s"),
        field("angle_rad", "Angle change", 1, 90, 1, "°", 1 / DEG),
        field("height_start_m", "Start camera height", 0.7, 1.8, 0.01, "m"),
        field("height_end_m", "End camera height", 0.7, 1.8, 0.01, "m"),
        field("rise_start", "Begin change", 0, 95, 5, "%", 100),
        field("rise_end", "Finish change", 5, 100, 5, "%", 100),
        field("focal_end_mm", "End focal length", 13, MAX_FOCAL_MM, 1, "mm"),
        field("actor_distance_m", "Actor walking distance", 0.2, 10, 0.1, "m"),
        field("actor_heading_rad", "Actor walking direction", -360, 360, 5, "°", 1 / DEG),
        field("subject_height_m", "Actor height", 0.8, 2.2, 0.01, "m"),
        field("light_height_start_m", "Start light height", 0.7, 1.8, 0.01, "m"),
        field("light_height_end_m", "End light height", 0.7, 1.8, 0.01, "m"),
        field("hand_amplitude_rad", "Handheld amount", 0.1, 5, 0.1, "°", 1 / DEG),
        field("hand_frequency_hz", "Handheld pace", 0.1, 1, 0.05, "Hz"),
    ]
}


def defaults_for(template_id):
    if not isinstance(template_id, str) or template_id not in BY_ID:
        raise ValueError("Choose a camera movement from the template library.")
    return (
        DEFAULTS
        | dict(
            template_id=template_id,
            height_start_m=1.59,
            height_end_m=1.59,
            light_height_start_m=1.6,
            light_height_end_m=1.6,
        )
        | BY_ID[template_id]["overrides"]
    )


def validate_settings(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Expected named shot template settings.")
    s = defaults_for(value.get("template_id", "hero_orbit")) | value
    if s["mode"] != "template" or s["subject_motion"] not in ("hold", "walk"):
        raise ValueError("Choose template mode and a stationary or walking actor.")
    for key, meta in FIELDS.items():
        v, scale = s[key], meta["scale"]
        if (
            type(v) not in (int, float)
            or not math.isfinite(v)
            or not meta["min"] / scale - 1e-9 <= v <= meta["max"] / scale + 1e-9
        ):
            raise ValueError(
                f"{meta['label']} must be between {meta['min']:g} and {meta['max']:g} {meta['unit']}."
            )
        s[key] = float(v)
    v = s["focal_mm"]
    if type(v) not in (int, float) or not math.isfinite(v) or not 13 <= v <= MAX_FOCAL_MM:
        raise ValueError(f"Starting focal length must be between 13 and {MAX_FOCAL_MM:g} mm.")
    s["focal_mm"] = float(v)
    s["camera"] = validate_camera(s["camera"])
    s.update(
        validate_choreography({k: s[k] for k in ("height_start_m", "height_end_m", "rise_start", "rise_end")})
    )
    return s


def path_settings(settings):
    s = validate_settings(settings)
    p = BY_ID[s["template_id"]]
    start = orbit_pose(s | {"ease": "linear"}, 0, 0)[1]
    radial = start / s["radius_m"]
    tangent = [-radial[1], radial[0]]
    route = p["route"]
    if route == "arc":
        count = max(12, math.ceil(s["radius_m"] * s["sweep_rad"] / 0.15))
        points = [
            orbit_pose(s | {"ease": "linear", "sweep_rad": s["sweep_rad"] * p["sign"]}, i / count, 0)[
                1
            ].tolist()
            for i in range(count + 1)
        ]
    elif route == "in":
        # Radius is the near mark. Travel can vary without passing through the actor.
        points = [(start + radial * s["distance_m"]).tolist(), start.tolist()]
    elif route == "out":
        points = [start.tolist(), (start + radial * s["distance_m"]).tolist()]
    elif route == "truck":
        delta = [x * s["distance_m"] * p["sign"] for x in tangent]
        points = [[start[j] - delta[j] / 2 for j in (0, 1)], [start[j] + delta[j] / 2 for j in (0, 1)]]
    elif route in ("follow", "lead", "side"):
        direction = [math.cos(s["actor_heading_rad"]), math.sin(s["actor_heading_rad"])]
        offset = [direction[1], -direction[0]] if route == "side" else direction
        sign = -1 if route == "follow" else 1
        origin = [x * s["radius_m"] * sign for x in offset]
        points = [origin, [origin[j] + direction[j] * s["distance_m"] for j in (0, 1)]]
    else:
        points = [start.tolist()]
    return dict(
        mode="path",
        points_m=points,
        speed_m_s=s["speed_m_s"],
        height_m=s["height_start_m"],
        focal_mm=s["focal_mm"],
        subject_height_m=s["subject_height_m"],
        choreography={k: s[k] for k in ("height_start_m", "height_end_m", "rise_start", "rise_end")},
        program=s | dict(aim=p["aim"], route=route, sign=p["sign"]),
    )


# A 35 mm-equivalent pinhole with a 16:9 crop: this is the vertical frame extent
# the simulated camera already uses. Everything below is advisory reporting only.
FRAME_HEIGHT_MM = 36 / (16 / 9)
FRAMING_BANDS = {"wide": (2.2, 3.4), "medium": (1.0, 1.6), "close_up": (0.40, 0.70)}


def route_filming_time_s(settings):
    """Seconds of filming the geometry implies, excluding calibrated arm setup."""
    s = validate_settings(settings)
    route = BY_ID[s["template_id"]]["route"]
    if route == "hold":
        return s["duration_s"]
    if route == "arc":
        return s["radius_m"] * abs(s["sweep_rad"]) / s["speed_m_s"]
    return s["distance_m"] / s["speed_m_s"]


def subject_distances_m(settings):
    """Actor-to-camera distance at the opening and closing of the move."""
    s = validate_settings(settings)
    route = BY_ID[s["template_id"]]["route"]
    far = s["radius_m"] + s["distance_m"]
    if route == "in":
        return (far, s["radius_m"])
    if route == "out":
        return (s["radius_m"], far)
    if route == "truck":
        edge = math.hypot(s["radius_m"], s["distance_m"] / 2)
        return (edge, edge)
    return (s["radius_m"], s["radius_m"])


def screen_geometry(settings):
    """Metres of the world filling the frame height at each end, and the bands they fall in."""
    s = validate_settings(settings)
    aim = BY_ID[s["template_id"]]["aim"]
    focals = (s["focal_mm"], s["focal_end_mm"] if aim == "zoom" else s["focal_mm"])
    heights = [d * FRAME_HEIGHT_MM / f for d, f in zip(subject_distances_m(s), focals)]
    # A move that travels between bands legitimately reads as every band it passes through.
    low_h, high_h = min(heights), max(heights)
    implied = [name for name, (low, high) in FRAMING_BANDS.items() if low <= high_h and high >= low_h]
    nearest = min(FRAMING_BANDS, key=lambda n: min(abs(h - b) for h in heights for b in FRAMING_BANDS[n]))
    return dict(
        frame_height_m=heights,
        focal_mm=list(focals),
        implied=implied,
        nearest=implied[0] if implied else nearest,
    )


def compile_template(value):
    from .path import compile_scene

    settings = validate_settings(value)
    p = BY_ID[settings["template_id"]]
    motion = path_settings(settings)
    # Lens/output edits reuse the exact same IK and motor samples. The camera
    # channel below evaluates the authored focal lengths on the solved clock.
    motion["focal_mm"] = 24.0
    motion["program"] = {k: v for k, v in motion["program"].items() if k != "camera"}
    motion["program"].update(focal_mm=24.0, focal_end_mm=24.0)
    result = compile_scene(motion)
    plan, preview = result["plan"], result["preview"]
    plan["settings"] = settings
    plan["summary"]["scope"] = (
        f"{p['name']}: shared cart and arm motor timeline. Phone recording and zoom remain manual."
    )
    preview.update(
        kind="takeone_template_previs",
        settings=settings,
        plan_id=plan["plan_id"],
        template=dict(id=p["id"], name=p["name"], intent=p["intent"], family=p["family"], aim=p["aim"]),
    )
    apply_camera(preview, plan)
    return result


def catalog():
    entries = []
    for p in PRESETS:
        controls = ["radius_m"]
        controls += (
            ["sweep_rad", "bearing_rad", "speed_m_s"]
            if p["route"] == "arc"
            else ["duration_s", "bearing_rad"]
            if p["route"] == "hold"
            else ["distance_m", "speed_m_s", "bearing_rad"]
        )
        if p["aim"] in ("pan", "tilt", "roll", "high"):
            controls += ["angle_rad"]
        if p["aim"] == "zoom":
            controls += ["focal_end_mm"]
        if p["aim"] == "handheld":
            controls += ["hand_amplitude_rad", "hand_frequency_hz"]
        controls += [
            "height_start_m",
            "height_end_m",
            "rise_start",
            "rise_end",
            "light_height_start_m",
            "light_height_end_m",
            "subject_height_m",
            "actor_distance_m",
            "actor_heading_rad",
        ]
        entries.append(
            dict(
                id=p["id"],
                name=p["name"],
                family=p["family"],
                intent=p["intent"],
                status="implemented",
                defaults=defaults_for(p["id"]),
                route=p["route"],
                aim=p["aim"],
                parameters=controls,
                components=[p["route"], p["aim"], "camera_height", "light_height", "actor"],
            )
        )
    return copy.deepcopy(
        dict(schema_version=1, defaults=defaults_for("hero_orbit"), fields=FIELDS, templates=entries)
    )
