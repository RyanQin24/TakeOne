"""Prepare immutable wheel-command schedules using the simulator's drive equations."""

import hashlib
import json
from bisect import bisect_right
from dataclasses import dataclass

import numpy as np

from takeone.cart.response import CartResponse
from takeone.config import finite, provenance
from takeone.planning.settings import parameters
from takeone.protocol import COMMAND_CAP, MIN_COMMAND, uart_pair
from takeone.simulation import drive


@dataclass(frozen=True)
class CartPlan:
    """Private JSON bytes bind settings, commands, prediction and source hashes together."""

    payload: bytes
    times_s: tuple[float, ...]
    commands: tuple[tuple[float, float], ...]
    duration_s: float
    plan_id: str

    def to_dict(self):
        return json.loads(self.payload)

    def command_at(self, elapsed_s):
        elapsed_s = finite(elapsed_s, "Plan elapsed time")
        if elapsed_s < 0 or elapsed_s >= self.duration_s:
            return (0.0, 0.0)
        return self.commands[bisect_right(self.times_s, elapsed_s) - 1]


def prepare_cart(request=None):
    """Calculate the base path; do not load MuJoCo, solve arms or touch a serial port."""
    settings = parameters({} if request is None else request)
    trace = drive.simulate(settings)
    report = drive.summary(trace)
    if not report["reproducesRequestedPath"] or report["stalledFraction"] > 0:
        raise ValueError("Requested cart path fails quantized wheel prediction; revise the shot")
    records = [
        {"time_s": float(r["time"]), "wire": r["wire"], "commands": r["commands"].tolist()}
        for r in trace["records"]
    ]
    records.append({"time_s": settings["duration"], "wire": "0.00,0.00\n", "commands": [0.0, 0.0]})
    body = dict(
        schema="takeone.cart-plan.v1",
        scope="cart-only open-loop prediction; arms excluded; not a qualified physical shot",
        settings=settings,
        provenance=provenance(),
        prediction=report,
        schedule=records,
        initial_axle_pose=trace["records"][0]["axle"].tolist(),
        final_axle_pose=trace["final"][0].tolist(),
        hardware_ready=False,
    )
    return _seal_plan(body)


def prepare_command_test(command_magnitude, duration_s=2.0):
    """Prepare an explicit equal-command experiment, preserving response assumptions."""
    magnitude = finite(command_magnitude, "Command magnitude")
    if not MIN_COMMAND <= magnitude <= COMMAND_CAP:
        raise ValueError(f"Command magnitude must be between {MIN_COMMAND:g} and {COMMAND_CAP:g}")
    command = drive.DIRECTION_SIGN * magnitude
    wire = uart_pair(command, command)
    if float(wire.split(",")[0]) != command:
        raise ValueError("Choose an exact two-decimal wire command; no implicit rounding")
    settings = parameters({"duration": duration_s, "driveProfile": "arms"})
    duration = settings["duration"]
    motor_response = CartResponse.load(settings["minimumSpeed"])
    initial = drive.reference(settings, 0)[0]
    # A command experiment does not manufacture a new speed calibration from
    # the one approximate shared .04 observation, or assume reverse symmetry.
    identified = motor_response.wheels is not None
    final = speeds = distances = None
    if identified:
        targets = motor_response.speeds_for((command, command))
        final, speeds, distances = drive.segment(
            initial,
            np.zeros(2),
            np.zeros(2),
            targets,
            duration,
            settings["trackWidth"],
            settings["responseTime"],
            settings["brakeTime"],
        )
    records = [
        {"time_s": 0.0, "wire": wire, "commands": [command, command]},
        {"time_s": duration, "wire": "0.00,0.00\n", "commands": [0.0, 0.0]},
    ]
    return _seal_plan(
        dict(
            schema="takeone.cart-command-test.v1",
            scope="Cart-only explicit wire-command experiment; arms excluded; physical response unverified",
            command_test={"command_magnitude": magnitude, "duration_s": duration},
            settings=settings,
            provenance=provenance(),
            prediction={
                "type": "Configured wheel-response prediction for explicit commands",
                "commandDirection": "forward" if drive.DIRECTION_SIGN == 1 else "reverse",
                "commandSign": drive.DIRECTION_SIGN,
                "commandMagnitude": magnitude,
                "wire": wire,
                "wheelTravel": distances.tolist() if identified else None,
                "endWheelSpeeds": speeds.tolist() if identified else None,
                "predictedCoastTravel": (speeds * settings["brakeTime"]).tolist() if identified else None,
                "responseModel": motor_response.describe(),
                "validatedOnHardware": False,
                "note": "Independent wheel response unavailable unless a measured table is supplied. Observe actual travel; do not infer higher-command speed or reverse symmetry from the shared .04 trial.",
            },
            schedule=records,
            initial_axle_pose=initial.tolist(),
            final_axle_pose=final.tolist() if identified else None,
            hardware_ready=False,
        )
    )


def _seal_plan(body):
    """Bind either calculated path or explicit experiment to the complete source snapshot."""
    records = body["schedule"]
    identity = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    body["plan_id"] = identity
    return CartPlan(
        json.dumps(body, sort_keys=True).encode(),
        tuple(r["time_s"] for r in records),
        tuple(tuple(r["commands"]) for r in records),
        body["settings"]["duration"],
        identity,
    )


def load_cart_plan(document):
    """Recompile before connection; stale sources or edited schedules cannot be replayed."""
    if not isinstance(document, dict):
        raise ValueError("Expected a TakeOne cart plan")
    if document.get("schema") == "takeone.cart-plan.v1":
        plan = prepare_cart(document["settings"])
    elif document.get("schema") == "takeone.cart-command-test.v1":
        plan = prepare_command_test(**document["command_test"])
    else:
        raise ValueError("Expected a TakeOne cart plan")
    if plan.to_dict() != document:
        raise ValueError("Cart plan changed or sources are stale; prepare and review a new plan")
    return plan


def cart_from_shot(document):
    """Import the actual compiled UART timeline, never infer motion from rendered pixels."""
    if not isinstance(document, dict) or document.get("schema") != "take-one.shot.v2":
        raise ValueError("Expected a simulator shot export")
    if document.get("provenance") != provenance():
        raise ValueError("Simulator export has stale provenance; recalculate and export again")
    supplied = document.get("motorCommands", [])
    if len(supplied) < 2 or supplied[-1].get("wire") != "0.00,0.00\n":
        raise ValueError("Exported motor timeline must contain motion packets and a terminal stop")
    records = []
    for item in supplied:
        commands = item.get("commands")
        if commands is None:
            commands = [float(value) for value in item["wire"].strip().split(",")]
        if len(commands) != 2 or uart_pair(*commands) != item.get("wire"):
            raise ValueError("Exported cart values must equal their two-decimal wire packets")
        records.append(dict(time_s=float(item["time"]), wire=item["wire"], commands=list(commands)))
    frames = document.get("frames", [])
    if not frames:
        raise ValueError("Exported coordinated cart path needs its FK frames")
    body = dict(
        schema="takeone.cart-plan.v1",
        scope="Coordinated quantized cart schedule imported from the canonical whole-robot solve",
        settings=document["settings"],
        provenance=document["provenance"],
        prediction=document["drive"],
        schedule=records,
        initial_axle_pose=frames[0]["drive"]["axle"],
        final_axle_pose=frames[-1]["drive"]["axle"],
        hardware_ready=False,
    )
    return _seal_plan(body)
