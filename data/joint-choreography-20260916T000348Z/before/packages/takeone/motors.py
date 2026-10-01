"""Per-motor encoder inspection: set any of the ten motors, see where the arms go.

This is the simulator's counterpart to what the hardware player sends. Both use
the same ArmMapping, so a count typed here is the same count written to
Goal_Position, and the pose drawn here is the pose that count produces.

Direction is one-way on purpose: encoder counts in, link poses out. There is no
inverse kinematics here, so a slider can never fail to solve.
"""

import math
import threading
from functools import lru_cache

import mujoco

from takeone.calibration import ArmMapping
from takeone.contracts import JOINTS
from takeone.direct import ROLES, calibrated_positions
from takeone.planning.settings import DEFAULTS
from takeone.simulation.robot import load_model, model_hash, model_path, pose_frame

_pose_lock = threading.Lock()

# The actor stands at the world origin, so parking the panel's cart there draws
# the robot inside them. Stand it off by the same radius the shot compiler uses.
STANDOFF_CART = (-DEFAULTS["radius"], 0.0, -math.pi / 2)


def _geom_label(model, *geom_ids):
    """Name a contact by its geom, or by the link it belongs to.

    The imported SO-101 collision meshes are unnamed, so a raw geom lookup
    reports "? / ?" for exactly the arm-on-arm contacts worth seeing.
    """
    labels = []
    for geom_id in geom_ids:
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
        if not name:
            body = model.geom_bodyid[geom_id]
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body) or f"geom {geom_id}"
        labels.append(name)
    return labels


def _contacts(model, data):
    """Report real interpenetration from MuJoCo's own collision pass.

    A slider can reach poses the hardware cannot: links driven through the cart
    uprights or through each other. mj_forward has already computed contacts, so
    this reads them rather than re-deriving any geometry.
    """
    pairs = {}
    for index in range(data.ncon):
        contact = data.contact[index]
        depth = float(contact.dist)
        if depth >= 0:
            continue
        key = " / ".join(sorted(_geom_label(model, contact.geom1, contact.geom2)))
        pairs[key] = min(pairs.get(key, 0.0), depth)
    ordered = sorted(pairs.items(), key=lambda item: item[1])
    return dict(
        colliding=bool(ordered),
        pairs=[dict(geoms=name, penetration_mm=round(-depth * 1000, 2)) for name, depth in ordered[:8]],
        pair_count=len(ordered),
        worst_penetration_mm=round(-ordered[0][1] * 1000, 2) if ordered else 0.0,
    )


@lru_cache(maxsize=4)
def _scene(light_type, track_width):
    """Compile each variant once. Recompiling per slider frame cost 214 ms a move."""
    model = load_model(light_type, track_width)
    return model, mujoco.MjData(model)


@lru_cache(maxsize=4)
def _mapping(role):
    return ArmMapping.load(role, require_motion=False)


def motor_table():
    """Every motor's live calibration: id, usable counts, midpoint and its angle."""
    roles = {}
    for role in ROLES:
        mapping, ranges, midpoints = calibrated_positions(role)
        joints = {}
        for index, name in enumerate(JOINTS):
            lower, upper = ranges[name]
            joints[name] = dict(
                id=mapping.raw_calibration[name]["id"],
                min=lower,
                max=upper,
                midpoint=midpoints[name],
                # Counts are what the servo takes; degrees are what the model turns.
                degrees_per_count=360 / 4095,
                axis_sign=mapping.signs[index],
                zero_offset_deg=mapping.offsets_deg[index],
            )
        roles[role] = dict(
            port_role=role,
            joints=joints,
            midpoints=midpoints,
        )
    return dict(
        schema="takeone.motor-table.v1",
        joint_order=list(JOINTS),
        roles=roles,
        source="calibration/registry.json via ArmMapping, including operator range overrides",
    )


def _counts(request, role, table):
    """Take whatever the panel sent for one arm, clamped to that motor's range."""
    supplied = (request or {}).get(role) or {}
    if not isinstance(supplied, dict):
        raise ValueError(f"{role}: motor positions must be an object")
    unknown = set(supplied) - set(JOINTS)
    if unknown:
        raise ValueError(f"{role}: unknown motors {sorted(unknown)}")
    joints = table["roles"][role]["joints"]
    result = {}
    for name in JOINTS:
        value = supplied.get(name, joints[name]["midpoint"])
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{role}/{name}: motor position must be a number")
        result[name] = max(joints[name]["min"], min(joints[name]["max"], int(value)))
    return result


def pose_from_counts(request=None):
    """Pose the robot from ten raw encoder counts. No IK, no trajectory, no solve."""
    request = request or {}
    light_type = request.get("lightType", DEFAULTS["lightType"])
    if light_type not in ("ring", "panel", "tube"):
        raise ValueError("Unknown light type")
    table = motor_table()
    raw_by_role = {}
    q_arms = []
    degrees_by_role = {}
    for role in ROLES:
        mapping = _mapping(role)
        counts = _counts(request.get("motors"), role, table)
        raw_by_role[role] = counts
        # The identical conversion the hardware player uses, read in reverse.
        q_rad = mapping.from_raw(counts)
        q_arms.extend(q_rad)
        degrees_by_role[role] = {
            name: round((counts[name] - table["roles"][role]["joints"][name]["midpoint"]) * 360 / 4095, 2)
            for name in JOINTS
        }

    # The cart stays put so the panel answers "what does this motor do to the
    # arm". It parks at the shot's own starting pose, not the world origin: the
    # origin is where the actor stands, and the robot would be drawn inside them.
    cart = request.get("cart") or STANDOFF_CART
    if len(cart) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in cart):
        raise ValueError("Cart pose must be three numbers")
    # One MjData per variant, so concurrent slider requests are serialized rather
    # than interleaving writes into the same qpos buffer.
    model, data = _scene(light_type, DEFAULTS["trackWidth"])
    with _pose_lock:
        frame = pose_frame(model, data, (*map(float, cart), *q_arms), 0.0, None)
        contacts = _contacts(model, data)
    frame["rawByRole"] = raw_by_role
    frame["degreesFromMidpoint"] = degrees_by_role
    frame["contacts"] = contacts
    return dict(
        schema="takeone.motor-pose.v1",
        lightType=light_type,
        frame=frame,
        motors=raw_by_role,
        degreesFromMidpoint=degrees_by_role,
        jointRadians={role: list(q_arms[i * 5 : i * 5 + 5]) for i, role in enumerate(ROLES)},
        modelHash=model_hash(model_path(light_type), DEFAULTS["trackWidth"]),
        contacts=frame["contacts"],
        cart=list(cart),
        ikSolves=0,
        hardwareCommandsSent=False,
    )
