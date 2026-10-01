"""Immutable replay of the simulator's solved joints; no IK or hardware in playback."""

import hashlib
import json
import math
from bisect import bisect_right
from dataclasses import dataclass

from takeone.config import finite, provenance
from takeone.contracts import JOINTS, joints
from takeone.protocol import uart_pair

ROLES = ("phone", "light")


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


@dataclass(frozen=True)
class RobotPlan:
    payload: bytes
    times_s: tuple
    phone: tuple
    light: tuple
    cart_times_s: tuple
    commands: tuple
    duration_s: float
    plan_id: str

    def to_dict(self):
        return json.loads(self.payload)

    def arm_at(self, role, elapsed_s):
        if role not in ROLES:
            raise ValueError("Unknown arm role")
        t = max(0.0, min(self.duration_s, finite(elapsed_s, "Elapsed time")))
        track = getattr(self, role)
        index = min(len(self.times_s) - 2, max(0, bisect_right(self.times_s, t) - 1))
        fraction = (t - self.times_s[index]) / (self.times_s[index + 1] - self.times_s[index])
        return tuple(a + (b - a) * fraction for a, b in zip(track[index], track[index + 1]))

    def command_at(self, elapsed_s):
        t = finite(elapsed_s, "Elapsed time")
        if t < 0 or t >= self.duration_s:
            return (0.0, 0.0)
        return self.commands[bisect_right(self.cart_times_s, t) - 1]

    def dispatch_times(self, period_s):
        count = math.ceil(self.duration_s / period_s)
        return tuple(i * period_s for i in range(count)) + (self.duration_s,)


def _times(values, duration):
    values = tuple(finite(v, "Sample time") for v in values)
    if (
        len(values) < 2
        or values[0] != 0
        or values[-1] != duration
        or any(a >= b for a, b in zip(values, values[1:]))
    ):
        raise ValueError("Timeline must increase strictly from zero to duration")
    return values


def load_plan(document, *, current_sources=True):
    """Validate the entire reviewed artifact before any device is opened.

    The digest detects accidental edits, not a signature or operator authorization.
    Physical execution additionally validates every target against measured limits.
    """
    if not isinstance(document, dict) or document.get("schema") != "takeone.robot-plan.v1":
        raise ValueError("Expected a prepared robot plan")
    body = {k: v for k, v in document.items() if k != "plan_id"}
    if document.get("plan_id") != digest(body):
        raise ValueError("Robot plan content changed; prepare and review it again")
    if current_sources and document["provenance"] != provenance():
        raise ValueError("Robot plan sources are stale; recalculate and review it again")
    if document["joint_order"] != list(JOINTS) or document["coordinate_frame"] != "reference_urdf_rad":
        raise ValueError("Unsupported joint order or frame")
    if document["interpolation"] != "linear_joint_angles" or document["hardware_ready"] is not False:
        raise ValueError("Invalid execution semantics")
    duration = finite(document["duration_s"], "Duration")
    if not 0 < duration <= 120:
        raise ValueError("A robot run must be finite and at most 120 seconds")
    samples = document["samples"]
    if not 2 <= len(samples) <= 20001:
        raise ValueError("Invalid arm sample count")
    times = _times([s["time_s"] for s in samples], duration)
    if any(set(s["arms"]) != set(ROLES) for s in samples):
        raise ValueError("Both named arms are required in every sample")
    tracks = {role: tuple(joints(s["arms"][role]) for s in samples) for role in ROLES}
    cart = document["cart_schedule"]
    if not 2 <= len(cart) <= 20001:
        raise ValueError("Invalid cart sample count")
    cart_times = _times([s["time_s"] for s in cart], duration)
    commands = []
    for sample in cart:
        pair = tuple(sample["commands"])
        if len(pair) != 2 or any(abs(finite(v, "Wheel command")) > 0.15 for v in pair):
            raise ValueError("Invalid wheel commands")
        if uart_pair(*pair) != sample["wire"] or tuple(map(float, sample["wire"].split(","))) != pair:
            raise ValueError("Cart values must equal the quantized wire commands")
        commands.append(pair)
    if commands[-1] != (0.0, 0.0):
        raise ValueError("Robot plan must finish with a cart stop")
    return RobotPlan(
        encoded(document),
        times,
        tracks["phone"],
        tracks["light"],
        cart_times,
        tuple(commands),
        duration,
        document["plan_id"],
    )


def prepare_shot(shot):
    """Import an actual preview export, verifying its solved joints before preparation."""
    from takeone.cart.plan import cart_from_shot
    from takeone.planning.compiler import compile_shot

    cart = cart_from_shot(shot)
    canonical = compile_shot(shot["settings"])
    if not canonical["playable"]:
        raise ValueError("Shot fails the simulator's motion screens; revise it first")
    supplied = shot.get("frames", [])
    if [f["q"] for f in supplied] != [f["q"] for f in canonical["frames"]]:
        raise ValueError("Exported arm trajectory differs from the simulator's solved joints")
    duration = canonical["settings"]["duration"]
    samples = []
    for i, frame in enumerate(supplied):
        stamp = i * duration / (len(supplied) - 1)
        if "time" in frame and frame["time"] != stamp:
            raise ValueError("Exported arm timestamps were changed")
        samples.append(dict(time_s=stamp, arms=dict(phone=frame["q"][3:8], light=frame["q"][8:13])))
    body = dict(
        schema="takeone.robot-plan.v1",
        source_shot_id=canonical["planId"],
        source_model_hash=canonical["modelHash"],
        provenance=canonical["provenance"],
        settings=canonical["settings"],
        joint_order=list(JOINTS),
        coordinate_frame="reference_urdf_rad",
        interpolation="linear_joint_angles",
        duration_s=duration,
        samples=samples,
        cart_schedule=cart.to_dict()["schedule"],
        simulator_checks=canonical["checks"],
        hardware_ready=False,
    )
    return load_plan(body | {"plan_id": digest(body)})
