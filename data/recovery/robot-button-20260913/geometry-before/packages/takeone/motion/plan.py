"""Finite immutable simulator-to-device contract. No device IO or IK in evaluation."""

import hashlib
import json
from bisect import bisect_right
from dataclasses import dataclass

from takeone.config import finite, provenance, read_json
from takeone.contracts import JOINTS, joints
from takeone.paths import CONFIGS
from takeone.planning.curve import JointCurve
from takeone.protocol import uart_pair

ROLES = ("phone", "light")
FRAMES = dict(
    world="right_handed_Z_up",
    cart="X_rear_casters_Y_filming_side_Z_up",
    drive="X_cart_minus_X_Y_cart_minus_Y_Z_up",
    optical="Z_forward_X_right_Y_down",
    quaternion="xyzw_active_local_to_world",
    joints="reference_urdf_rad",
)


def encoded(value):
    def canonical(item):
        if isinstance(item, dict):
            return {k: canonical(v) for k, v in item.items()}
        if isinstance(item, (tuple, list)):
            return [canonical(v) for v in item]
        # Browser JSON.parse/stringify writes 0.0/-0.0 as 0 and 1.0 as 1.
        # Bind numeric meaning, so downloading/reviewing cannot invalidate it.
        if isinstance(item, float) and item.is_integer():
            item = int(item)
        if type(item) is int and abs(item) > 2**53 - 1:
            raise ValueError("Plan integer exceeds exact browser JSON representation")
        return item

    return json.dumps(canonical(value), sort_keys=True, allow_nan=False, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


@dataclass(frozen=True)
class RobotPlan:
    payload: bytes
    curve: JointCurve
    period_s: float
    times_s: tuple
    phone: tuple
    light: tuple
    cart_times_s: tuple
    commands: tuple
    duration_s: float
    plan_id: str

    def to_dict(self):
        return json.loads(self.payload)

    def arm_at(self, role, elapsed_s, derivative=0):
        if role not in ROLES:
            raise ValueError("Unknown arm role")
        offset = ROLES.index(role) * 5
        return self.curve.at(elapsed_s, derivative)[offset : offset + 5]

    def command_at(self, elapsed_s):
        t = finite(elapsed_s, "Elapsed time")
        if t < 0 or t >= self.duration_s:
            return (0.0, 0.0)
        return self.commands[bisect_right(self.cart_times_s, t) - 1]

    def dispatch_times(self, period_s=None):
        from takeone.planning.curve import dispatch_times

        if period_s is not None and period_s != self.period_s:
            raise ValueError("Dispatch period changed; prepare and review a new plan")
        return dispatch_times(self.duration_s, self.period_s)


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
    """Digest is identity, not authorization. Preflight and reconstruction precede IO."""
    if not isinstance(document, dict) or document.get("schema") != "takeone.robot-plan.v2":
        raise ValueError("Expected robot-plan.v2; prepare old artifacts again")
    body = {k: v for k, v in document.items() if k != "plan_id"}
    if document.get("plan_id") != digest(body):
        raise ValueError("Robot plan content changed; prepare and review it again")
    if current_sources and document["provenance"] != provenance():
        raise ValueError("Robot plan sources are stale; recalculate and review it again")
    if (
        document["joint_order"] != list(JOINTS)
        or document["roles"] != list(ROLES)
        or document["frames"] != FRAMES
    ):
        raise ValueError("Unsupported roles, joint order or coordinate frames")
    if (
        document["interpolation"] != "local_seconds_polynomial_ascending_powers"
        or document["hardware_ready"] is not False
    ):
        raise ValueError("Invalid execution semantics")
    curve = JointCurve.from_dict(document["joint_curve"])
    duration = finite(document["duration_s"], "Duration")
    if duration != curve.duration_s:
        raise ValueError("Curve and robot duration differ")
    period = finite(document["arm_period_s"], "Arm period")
    if not 0 < period <= 0.1:
        raise ValueError("Invalid dispatch period")
    samples = document["samples"]
    if not 2 <= len(samples) <= 20001:
        raise ValueError("Invalid arm sample count")
    times = _times([s["time_s"] for s in samples], duration)
    tracks = {r: [] for r in ROLES}
    for sample in samples:
        if set(sample["arms"]) != set(ROLES):
            raise ValueError("Both five-joint roles required")
        reference = curve.at(sample["time_s"])
        for index, role in enumerate(ROLES):
            q = joints(sample["arms"][role])
            if any(abs(a - b) > 1e-10 for a, b in zip(q, reference[5 * index : 5 * index + 5])):
                raise ValueError("Preview samples differ from the authoritative curve")
            tracks[role].append(q)
    cart = document["cart_schedule"]
    if not 2 <= len(cart) <= 20001:
        raise ValueError("Invalid cart schedule")
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
    plan = RobotPlan(
        encoded(document),
        curve,
        period,
        times,
        tuple(tracks["phone"]),
        tuple(tracks["light"]),
        cart_times,
        tuple(commands),
        duration,
        document["plan_id"],
    )
    if times != plan.dispatch_times():
        raise ValueError("Reviewed samples must be the complete dispatch timeline including endpoint")
    return plan


def prepare_shot(shot, *, transition_s=0.0, initial_rad=None, criteria=None):
    """Keep failed candidates inspectable. Explicit transitions produce a new identity."""
    from takeone.cart.plan import cart_from_shot
    from takeone.planning.compiler import compile_shot
    from takeone.planning.preview import execution_preview

    canonical = compile_shot(shot["settings"])
    cart = cart_from_shot(canonical)
    supplied = shot.get("frames", [])
    if (
        [f["q"] for f in supplied] != [f["q"] for f in canonical["frames"]]
        or shot.get("joint_curve") != canonical["joint_curve"]
        or shot.get("motorCommands") != canonical["motorCommands"]
    ):
        raise ValueError("Exported trajectory differs from the simulator's solved joints")
    for a, b in zip(supplied, canonical["frames"]):
        if a.get("time_s", a.get("time", b["time_s"])) != b["time_s"]:
            raise ValueError("Exported timestamps changed")
    curve = JointCurve.from_dict(canonical["joint_curve"])
    transition_s = finite(transition_s, "Transition duration")
    if transition_s:
        from takeone.calibration import ArmMapping

        ranges = [
            bounds for role in ROLES for bounds in ArmMapping.load(role, require_motion=False).safe_ranges_rad
        ]
        curve = curve.with_transitions(transition_s, initial_rad, joint_ranges=ranges)
    elif initial_rad is not None:
        raise ValueError("An initial pose requires an explicit approach duration")
    period = read_json(CONFIGS / "arm-execution.json")["period_s"]
    from takeone.simulation import drive

    trace = drive.simulate_wire_schedule(
        canonical["settings"], canonical["initialCartPose"], canonical["motorCommands"][:-1]
    )
    preview = execution_preview(
        canonical["settings"],
        curve,
        period,
        transition_s,
        include_envelope=True,
        trace=trace,
    )
    schedule = [dict(s, time_s=s["time_s"] + transition_s) for s in cart.to_dict()["schedule"]]
    if transition_s:
        schedule.insert(0, dict(time_s=0.0, commands=[0.0, 0.0], wire="0.00,0.00\n"))
        schedule.append(dict(time_s=curve.duration_s, commands=[0.0, 0.0], wire="0.00,0.00\n"))
    body = dict(
        schema="takeone.robot-plan.v2",
        source_shot_id=canonical["planId"],
        source_model_hash=canonical["modelHash"],
        provenance=canonical["provenance"],
        settings=canonical["settings"],
        requested_world_targets=canonical["requestedWorldTargets"],
        coordination=canonical["coordination"],
        task_metrics=canonical["taskMetrics"],
        roles=list(ROLES),
        joint_order=list(JOINTS),
        frames=FRAMES,
        interpolation="local_seconds_polynomial_ascending_powers",
        joint_curve=curve.to_dict(),
        units=dict(position="m", angle="rad", time="s", drive_command="dimensionless"),
        arm_period_s=period,
        duration_s=curve.duration_s,
        revision=dict(transition_s=transition_s, initial_rad=initial_rad),
        samples=[
            dict(time_s=f["time_s"], arms=dict(phone=f["q"][3:8], light=f["q"][8:13]))
            for f in preview["frames"]
        ],
        execution_preview=preview,
        cart_schedule=schedule,
        cart_prediction=cart.to_dict()["prediction"],
        initial_cart_pose=preview["frames"][0]["q"][:3],
        final_cart_pose=preview["frames"][-1]["q"][:3],
        simulator_checks=canonical["checks"],
        plan_valid=canonical["planValid"] and all(c["passed"] for c in preview["revision_checks"]),
        shot_fidelity_passed=canonical["shotFidelityPassed"],
        rest_boundaries=curve.rest_boundaries(),
        acceptance_criteria=criteria,
        hardware_ready=False,
    )
    return load_plan(body | {"plan_id": digest(body)})


def reconstruct(plan):
    """Reject rehashed edits, omitted checks and altered FK before physical execution."""
    from takeone.planning.compiler import compile_shot

    document = plan.to_dict()
    if document.get("staging"):
        from .staging import reconstruct_approach

        expected = reconstruct_approach(document)
    else:
        expected = prepare_shot(
            compile_shot(document["settings"]),
            **document["revision"],
            criteria=document["acceptance_criteria"],
        )
    if expected.to_dict() != document:
        raise ValueError("Plan differs from its canonical preparation; prepare and review again")
    return expected
