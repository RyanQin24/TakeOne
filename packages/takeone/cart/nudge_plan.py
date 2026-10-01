"""Exact finite commissioning proposal. No localization or distance promises."""

import hashlib
import json

from takeone.cart.plan import CartPlan
from takeone.cart.runtime import check_commissioning
from takeone.config import provenance, read_json, rig_config
from takeone.paths import CONFIGS
from takeone.protocol import uart_pair

DURATION_S = 0.5
COMMAND = 0.04


def prepare_nudge(direction):
    configured = "backward" if rig_config()["cart"]["reverse_enabled"] else "forward"
    if direction != configured:
        raise ValueError(
            f"This commissioning setup permits {configured} only; direction configuration is unchanged"
        )
    runtime = read_json(CONFIGS / "cart-runtime.json")
    polarity = runtime.get("wire_polarity", 1)
    if type(polarity) is not int or polarity not in (-1, 1):
        raise ValueError("Invalid configured wire polarity")
    devices = read_json(CONFIGS / "devices/windows.json")
    if devices.get("hardware_enabled") is not True:
        raise ValueError("Windows hardware profile is disabled")
    command = COMMAND if direction == "forward" else -COMMAND
    body = dict(
        schema="takeone.cart-nudge.v1",
        direction=direction,
        duration_s=DURATION_S,
        command_magnitude=COMMAND,
        logical_commands=[command, command],
        wire_polarity=polarity,
        transmitted_wire=uart_pair(command * polarity, command * polarity),
        device=devices["cart"],
        provenance=provenance(),
        predicted_distance_m=None,
        physical_motion_verified=False,
        arms_commanded=False,
    )
    identity = hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False).encode()).hexdigest()
    payload = json.dumps(dict(body, plan_id=identity), sort_keys=True, allow_nan=False).encode()
    plan = CartPlan(payload, (0.0, DURATION_S), ((command, command), (0.0, 0.0)), DURATION_S, identity)
    check_commissioning(plan)
    return plan


def validate_nudge(document):
    if not isinstance(document, dict) or document.get("schema") != "takeone.cart-nudge.v1":
        raise ValueError("Expected an exact cart nudge proposal")
    plan = prepare_nudge(document.get("direction"))
    if plan.to_dict() != document:
        raise ValueError("Nudge plan or source/configuration changed; prepare and review again")
    return plan
