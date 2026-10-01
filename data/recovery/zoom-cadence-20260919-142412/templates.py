"""Film movements expanded into one cart/arms/lens program. No device IO."""

import copy
import math

from .camera import MAX_FOCAL_MM, MIN_FOCAL_MM, apply_camera, validate_camera
from .camera import defaults as camera_defaults
from .channels import ramp, validate_breath, validate_channels, validate_texture
from .choreography import validate_choreography
from .compiler import orbit_pose
from .compound import ROUTES as COMPOUND_ROUTES
from .compound import points as compound_points
from .placement import defaults as scene_defaults
from .placement import validate_scene
from .policy import motion_policy

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
    scene=scene_defaults(),
    camera_target=dict(kind="actor", position_m=[0.0, 0.0, 0.0]),
    channels={},
    texture=dict(enabled=False, amplitude_rad=1.5 * DEG, frequency_hz=0.45),
    breath=dict(pre_hold_s=0.0, post_hold_s=0.0, entry_s=0.0, exit_s=0.0),
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
        focal_mm=48.0,
    ),
    preset(
        "dolly_zoom_out",
        "Dolly Zoom · move out / zoom in",
        "Dolly & lens",
        "Keep the actor's image size steady while retreating and tightening the lens.",
        route="out",
        aim="dolly_zoom",
        focal_mm=24.0,
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

# New presets use independent channels; legacy defaults retain their old adapter.
BREATH = dict(pre_hold_s=0.6, post_hold_s=1.0, entry_s=1.4, exit_s=1.4)
PRESETS.extend(
    [
        preset(
            "spiral",
            "Spiral · circle and approach",
            "Compound routes",
            "Circle while closing the distance, with a gentle organic drift.",
            route="spiral",
            distance_m=1.2,
            breath=BREATH,
            texture=dict(enabled=True, amplitude_rad=0.5 * DEG, frequency_hz=0.2),
        ),
        preset(
            "s_curve",
            "S-curve · flowing parallax",
            "Compound routes",
            "Two broad bends change parallax with room for the cart to settle.",
            route="s_curve",
            distance_m=6.0,
            breath=BREATH,
        ),
        preset(
            "arc_push",
            "Arc into push · discover then approach",
            "Compound routes",
            "A continuous tangent joins the arc to an inward finishing gesture.",
            route="arc_push",
            distance_m=1.5,
            breath=BREATH,
        ),
        preset(
            "pass_by",
            "Pass-by · hold attention",
            "Compound routes",
            "Pass the subject at constant ground stand-off while the lens retains attention.",
            route="pass_by",
            distance_m=4.0,
            breath=BREATH,
        ),
        preset(
            "three_beat",
            "Three-beat oner · reveal, turn, settle",
            "Compound routes",
            "One setup and one continuous take carry three independently timed visual beats.",
            route="three_beat",
            distance_m=1.5,
            breath=BREATH,
            channels=dict(
                camera_height_m=ramp(1.4, 1.59, 0.05, 0.3),
                pan_rad=ramp(-4 * DEG, 0, 0.35, 0.65),
                light_height_m=ramp(1.5, 1.65, 0.65, 0.95),
            ),
        ),
    ]
)
for id, name, intent, route, extra in [
    (
        "product_highlight",
        "Highlight walk · light across an object",
        "Hold the camera while the light changes its target across the product.",
        "hold",
        dict(
            duration_s=8,
            channels=dict(
                light_target_m=ramp([0, -0.18, 1.4], [0, 0.18, 1.4]), light_height_m=ramp(1.5, 1.65)
            ),
        ),
    ),
    (
        "product_macro",
        "Macro-style pass-by · detail study",
        "A tight lens studies a product at constant cart stand-off. Minimum focus and depth of field need checking on the phone.",
        "pass_by",
        dict(distance_m=1.0, focal_mm=120.0, breath=BREATH),
    ),
    (
        "product_orbit",
        "Object orbit · shape and reflection",
        "Circle a static product with its centre as the aim target.",
        "arc",
        dict(sweep_rad=math.pi / 3, breath=BREATH),
    ),
    (
        "product_reveal",
        "Foreground reveal · uncover a product",
        "Move past a foreground screen to reveal the product on its plinth.",
        "pass_by",
        dict(distance_m=3.0, breath=BREATH),
    ),
    (
        "product_drift",
        "Negative-space drift · room for a title",
        "Shift attention beside the object to leave clear space in the final frame.",
        "pass_by",
        dict(distance_m=1.5, breath=BREATH, channels=dict(camera_target_m=ramp([0, 0, 1.4], [0, 0.6, 1.4]))),
    ),
]:
    PRESETS.append(
        preset(
            id,
            name,
            "Product study",
            intent,
            route=route,
            subject_motion="none",
            camera_target=dict(kind="point", position_m=[0.0, 0.0, 1.4]),
            focal_mm=extra.pop("focal_mm", 70.0),
            height_start_m=1.5,
            height_end_m=1.5,
            **extra,
        )
    )
BY_ID = {p["id"]: p for p in PRESETS}


def field(key, label, low, high, step, unit="", scale=1.0):
    return dict(key=key, label=label, min=low, max=high, step=step, unit=unit, scale=scale)


# Canonical SI values and their display conversions are shared with the UI.
#
# Travel bounds are planning limits, not room measurements. They were widened on
# 2026-09-19 so a long tracking or reveal shot compiles at all: cart travel to
# 30 m, actor-to-cart stand-off to 20 m, a held shot to 300 s. The real ceiling
# is still the 600 s total clock `previs/path.py` refuses to exceed, and a long
# route at the minimum pace approaches it — a 30 m travel at 0.14 m/s is about
# 214 s of filming before setup. Nothing here asserts the floor is that long.
FIELDS = {
    f["key"]: f
    for f in [
        field("radius_m", "Actor to cart", 0.8, 20, 0.1, "m"),
        field("sweep_rad", "Orbit sweep", 15, 360, 5, "°", 1 / DEG),
        field("bearing_rad", "Starting position angle", -360, 360, 5, "°", 1 / DEG),
        field("speed_m_s", "Cart pace", 0.14, motion_policy().cart_pace_max_m_s, 0.01, "m/s"),
        field("distance_m", "Cart travel", 0.2, 30, 0.1, "m"),
        field("duration_s", "Filming duration", 0.5, 300, 0.5, "s"),
        field("angle_rad", "Angle change", 1, 90, 1, "°", 1 / DEG),
        field("height_start_m", "Start camera height", 0.7, 1.8, 0.01, "m"),
        field("height_end_m", "End camera height", 0.7, 1.8, 0.01, "m"),
        field("rise_start", "Begin change", 0, 95, 5, "%", 100),
        field("rise_end", "Finish change", 5, 100, 5, "%", 100),
        field("focal_end_mm", "End focal length", 13, MAX_FOCAL_MM, 1, "mm"),
        field("actor_distance_m", "Actor walking distance", 0.2, 30, 0.1, "m"),
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
    return copy.deepcopy(
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
    if s["mode"] != "template" or s["subject_motion"] not in ("hold", "walk", "none"):
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
    s["scene"] = validate_scene(s["scene"])
    s["channels"] = validate_channels(s["channels"])
    if s["subject_motion"] == "none" and any(
        key in s["channels"]
        for key in ("actor_position_m", "actor_heading_rad", "gaze_yaw_rad", "gaze_pitch_rad")
    ):
        raise ValueError("Actor blocking and head cues need an actor; remove them from a product-only shot.")
    s["texture"] = validate_texture(s["texture"])
    s["breath"] = validate_breath(s["breath"])
    target = s["camera_target"]
    if (
        not isinstance(target, dict)
        or set(target) != {"kind", "position_m"}
        or target["kind"] not in ("actor", "point")
        or not isinstance(target["position_m"], list)
        or len(target["position_m"]) != 3
        or any(
            type(v) not in (float, int) or not math.isfinite(v) or abs(v) > 100 for v in target["position_m"]
        )
    ):
        raise ValueError("Camera target needs an actor or a finite shot-local 3D point.")
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
    route_sign = p["sign"]
    if s["scene"]["filming_side"] == "phone" and route in ("arc", "truck"):
        route_sign = 1
    if route in COMPOUND_ROUTES:
        points = compound_points(route, radial, s["radius_m"], s["distance_m"], s["sweep_rad"])
    elif route == "arc":
        count = max(12, math.ceil(s["radius_m"] * s["sweep_rad"] / 0.15))
        points = [
            orbit_pose(s | {"ease": "linear", "sweep_rad": s["sweep_rad"] * route_sign}, i / count, 0)[
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
        delta = [x * s["distance_m"] * route_sign for x in tangent]
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
        scene=s["scene"],
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
    if route in COMPOUND_ROUTES:
        points = path_settings(s)["points_m"]
        return sum(math.dist(a, b) for a, b in zip(points, points[1:])) / s["speed_m_s"]
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
    """Metres of the world filling the frame height at each end, and the bands they fall in.

    The closing focal length is the one the move actually ends on, which is not
    always the one the settings name. A Dolly Zoom holds image size by driving
    the lens in proportion to optical depth, so its closing focal is the opening
    focal scaled by the distance ratio — reading `focal_mm` at both ends said a
    Dolly Zoom travels from one shot size to another, which is the exact thing
    the move exists not to do.
    """
    s = validate_settings(settings)
    aim = BY_ID[s["template_id"]]["aim"]
    distances = subject_distances_m(s)
    if aim == "zoom":
        closing = s["focal_end_mm"]
    elif aim == "dolly_zoom":
        closing = min(
            MAX_FOCAL_MM,
            max(MIN_FOCAL_MM, s["focal_mm"] * distances[1] / max(distances[0], 1e-8)),
        )
    else:
        closing = s["focal_mm"]
    focals = (s["focal_mm"], closing)
    heights = [d * FRAME_HEIGHT_MM / f for d, f in zip(distances, focals)]
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


def preview_geometry(preview):
    """Actual optical depth and lens at each filmed sample, including actor motion."""
    import numpy as np
    from scipy.spatial.transform import Rotation

    heights = []
    for frame in preview["frames"]:
        if frame["time_s"] < preview["orbit_start_s"] - 1e-8:
            continue
        forward = Rotation.from_quat(frame["camera"]["quat"]).as_matrix()[:, 2]
        target = frame.get("camera_target_m", frame["face"])
        depth = float(forward @ (np.asarray(target) - frame["camera"]["pos"]))
        heights.append(max(0.0, depth) * FRAME_HEIGHT_MM / frame["focal_mm"])
    low, high = min(heights), max(heights)
    implied = [name for name, (a, b) in FRAMING_BANDS.items() if a <= high and b >= low]
    nearest = min(FRAMING_BANDS, key=lambda n: min(abs(h - b) for h in heights for b in FRAMING_BANDS[n]))
    return dict(
        frame_height_m=[heights[0], heights[-1]], implied=implied, nearest=nearest, range_m=[low, high]
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
    adapted = (
        settings["scene"]["filming_side"] == "phone" and p["route"] in ("arc", "truck") and p["sign"] < 0
    )
    preview["template"]["route_adapted"] = adapted
    preview["summary"]["route_adapted"] = adapted
    if adapted:
        actual = "counterclockwise" if p["route"] == "arc" else "the opposite travel direction"
        preview["notes"].insert(
            0,
            f"Phone-side setup: {p['name']} is adapted to {actual} so the powered wheels lead and the phone arm is nearest the actor. Choose Keep requested direction to use the original route.",
        )
        plan["summary"]["scope"] += f" Phone-side adaptation: {actual}."
    apply_camera(preview, plan)
    if settings["subject_motion"] == "none":
        x, y, z = settings["camera_target"]["position_m"]
        objects = [
            dict(
                object_id="study-product",
                asset_id="product",
                label="Product study",
                position_m=[x, y, z],
                size_m=[0.16, 0.16, 0.3],
                yaw_rad=0,
            ),
            dict(
                object_id="study-plinth",
                asset_id="plinth",
                label="Display plinth",
                position_m=[x, y, (z - 0.15) / 2],
                size_m=[0.6, 0.6, max(0.1, z - 0.15)],
                yaw_rad=0,
            ),
        ]
        if settings["template_id"] == "product_reveal":
            opening = next(f for f in preview["frames"] if f["time_s"] >= preview["orbit_start_s"])
            camera = opening["camera"]["pos"]
            objects.append(
                dict(
                    object_id="foreground-screen",
                    asset_id="wall",
                    label="Foreground screen",
                    position_m=[x + (camera[0] - x) * 0.45, y + (camera[1] - y) * 0.45, z],
                    size_m=[0.35, 0.35, 0.7],
                    yaw_rad=0,
                )
            )
        preview["set_scene"] = dict(atmosphere="studio", objects=objects, cast=[])
    return result


def catalog():
    from .channels import catalog as channel_catalog

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
        if p["route"] in ("spiral", "arc_push", "three_beat"):
            controls += ["sweep_rad"]
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
                setup_note=(
                    "Phone-side setup reverses this route; keep requested direction is available."
                    if p["route"] in ("arc", "truck") and p["sign"] < 0
                    else "Powered wheels lead."
                ),
                status="implemented",
                defaults=defaults_for(p["id"]),
                route=p["route"],
                aim=p["aim"],
                parameters=controls,
                components=[p["route"], p["aim"], "camera_height", "light_height", "actor"],
            )
        )
    return copy.deepcopy(
        dict(
            schema_version=1,
            defaults=defaults_for("hero_orbit"),
            fields=FIELDS,
            templates=entries,
            channels=channel_catalog(),
        )
    )
