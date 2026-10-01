"""Independent actor and powered-axle placement, in the planner's world frame.

Routes rotate about their opening mark and can then be translated to a new cart
start. Actor coordinates never translate the cart. These are inputs to IK, not
display transforms. Hand-drawn routes use absolute world points.
"""

import math

import numpy as np


def defaults():
    return dict(
        actor_position_m=[0.0, 0.0],
        cart_start_m=None,
        route_rotation_rad=0.0,
        actor_facing="opening",
        actor_heading_rad=0.0,
        filming_side="phone",
        actor_motion="preset",
        walk_distance_m=1.5,
        walk_heading_rad=0.0,
    )


def validate_scene(value=None):
    if value is None:
        return defaults()
    if not isinstance(value, dict) or set(value) - set(defaults()):
        raise ValueError("Expected actor and cart placement settings.")
    result = defaults() | value
    for key in ("actor_position_m", "cart_start_m"):
        point = result[key]
        if point is None and key == "cart_start_m":
            continue
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 100 for v in point)
        ):
            raise ValueError("Actor and cart marks need finite X/Y coordinates within 100 metres.")
        result[key] = [float(v) for v in point]
    for key, bound in (
        ("route_rotation_rad", math.tau),
        ("actor_heading_rad", math.tau),
        ("walk_heading_rad", math.tau),
        ("walk_distance_m", 30),
    ):
        v = result[key]
        if type(v) not in (int, float) or not math.isfinite(v) or abs(v) > bound:
            raise ValueError(f"Invalid placement value: {key}.")
        result[key] = float(v)
    if result["walk_distance_m"] < 0:
        raise ValueError("Walking distance must be positive or zero.")
    for key, choices in (
        ("actor_facing", ("opening", "fixed", "camera")),
        ("filming_side", ("phone", "direction")),
        ("actor_motion", ("preset", "hold", "walk")),
    ):
        if result[key] not in choices:
            raise ValueError(f"Unknown {key} choice.")
    return result


def place_route(points, scene):
    """Keep route shape and units; rotate at START, then place START explicitly."""
    points = np.asarray(points, dtype=float)
    angle = scene["route_rotation_rad"]
    c, s = math.cos(angle), math.sin(angle)
    rotation = np.array([[c, -s], [s, c]])
    start = points[0] if scene["cart_start_m"] is None else np.array(scene["cart_start_m"])
    return ((points - points[0]) @ rotation.T + start).tolist()


def needs_path_solver(scene):
    """An off-centre or moving actor invalidates the circular symmetry shortcut."""
    return (
        scene["actor_position_m"] != [0, 0]
        or scene["cart_start_m"] is not None
        or scene["route_rotation_rad"] != 0
        or scene["actor_motion"] == "walk"
    )


def place_actor(actor, face, scene):
    origin = scene["actor_position_m"]
    actor["position_m"][:2] = [actor["position_m"][i] + origin[i] for i in (0, 1)]
    face[:2] += origin
    return actor, face


def face_actor(frames, start_s, scene):
    """A standing actor holds their opening facing unless explicitly told to turn."""
    opening = next(f for f in frames if f["time_s"] >= start_s - 1e-8)
    p, a = opening["camera"]["pos"], opening["actor"]["position_m"]
    heading = math.atan2(p[1] - a[1], p[0] - a[0])
    for frame in frames:
        actor = frame["actor"]
        if actor["walking"] or actor.get("authored_heading"):
            continue
        if scene["actor_facing"] == "fixed":
            actor["heading_rad"] = scene["actor_heading_rad"]
        elif scene["actor_facing"] == "camera":
            p, a = frame["camera"]["pos"], actor["position_m"]
            actor["heading_rad"] = math.atan2(p[1] - a[1], p[0] - a[0])
        else:
            actor["heading_rad"] = heading
