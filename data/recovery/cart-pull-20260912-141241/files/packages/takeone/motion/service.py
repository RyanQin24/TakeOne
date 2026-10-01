"""Application entry points shared by operator CLI, replay and future orchestration."""

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from takeone.adapters.simulated import SimulatedArm, SimulatedCart, VirtualClock
from takeone.calibration import ArmMapping
from takeone.cart.runtime import CartRunner, Timing
from takeone.config import read_json
from takeone.execution import RobotRunner
from takeone.paths import CONFIGS, DATA

from .arm import ArmRunner
from .devices import DeviceFactory
from .limits import ArmTiming, measured_limits, preflight, simulated_limits
from .plan import ROLES, load_plan


def replay(plan):
    """Fast deterministic feedback rehearsal, distinct from host scheduling tests."""
    timing = ArmTiming.load()
    limit = simulated_limits()
    roles = {}
    for role in ROLES:
        limit.validate_plan(plan, role, timing)
        clock = VirtualClock()
        arm = SimulatedArm(plan.arm_at(role, 0), clock.now)
        runner = ArmRunner(arm, role, plan, limit, timing, clock=clock.now, sleep=clock.sleep)
        runner.ready()
        runner.run(clock.now() + 0.2)
        arm.disconnect()
        roles[role] = runner.report()
    clock = VirtualClock()
    cart = CartRunner(SimulatedCart(), Timing.load(), clock.now, clock.sleep)
    cart.run(
        SimpleNamespace(times_s=plan.cart_times_s, duration_s=plan.duration_s, command_at=plan.command_at),
        start_epoch=lambda _: 100.2,
    )
    roles["cart"] = cart.report()
    return dict(
        plan_id=plan.plan_id,
        mode="virtual-time-replay",
        completed=True,
        roles=roles,
        serial_ports_opened=False,
        physical_commands_sent=False,
        scope="Numeric trajectory/feedback verification; not host scheduling or physical qualification",
    )


def execute_plan(plan, *, mode, profile="windows", confirm_plan=None, operator_ready=False):
    """The single public playback boundary. Every live blocker is checked before IO."""
    plan = load_plan(plan.to_dict())
    if mode not in ("replay", "timing", "live"):
        raise ValueError("Choose replay, timing or live explicitly")
    if mode == "live":
        if confirm_plan != plan.plan_id or not operator_ready:
            raise ValueError("Live execution requires the full reviewed plan ID and operator readiness")
        readiness = preflight(plan, profile)
        if readiness["blockers"]:
            raise ValueError("Physical execution blocked: " + "; ".join(readiness["blockers"]))
        limits = {r: measured_limits(r) for r in ROLES}
        factory = DeviceFactory(
            False,
            read_json(CONFIGS / "devices" / f"{profile}.json"),
            {r: ArmMapping.load(r) for r in ROLES},
        )
    else:
        limits = {r: simulated_limits() for r in ROLES}
        factory = DeviceFactory(True)
    folder = (
        DATA
        / "runs"
        / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-robot-" + uuid.uuid4().hex[:8])
    )
    folder.mkdir(parents=True)
    (folder / "plan.json").write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    result = replay(plan) if mode == "replay" else RobotRunner(plan, factory, limits).run(folder)
    (folder / "report.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    summary = {k: v for k, v in result.items() if k != "roles"}
    summary["arms"] = {r: {k: v for k, v in result["roles"][r].items() if k != "events"} for r in ROLES}
    return summary | {"directory": str(folder)}
