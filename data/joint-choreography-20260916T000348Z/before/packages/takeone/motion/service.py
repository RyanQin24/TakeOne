"""Offline analysis and the single explicitly authorized physical execution boundary."""

import json
import queue
import sys
import threading
import uuid
from datetime import datetime, timezone

from takeone.config import read_json
from takeone.execution import RobotRunner
from takeone.paths import CONFIGS, DATA

from .checked import record_check, require_checked
from .devices import DeviceFactory
from .limits import execution_limits, execution_mapping, preflight
from .plan import ROLES, load_plan, reconstruct


def check_plan(plan):
    """Mathematics only; no synthetic motors, fake clock or movement completion."""
    plan = reconstruct(load_plan(plan.to_dict()))
    receipt = record_check(plan)
    document = plan.to_dict()
    extrema = {}
    for derivative, label in enumerate(
        ("position_rad", "velocity_rad_s", "acceleration_rad_s2", "jerk_rad_s3")
    ):
        lower, upper = plan.curve.extrema(derivative)
        extrema[label] = dict(minimum=lower, maximum=upper)
    return dict(
        plan_id=plan.plan_id,
        mode="offline-plan-check",
        checked_receipt=receipt,
        plan_valid=document["plan_valid"],
        shot_fidelity_passed=document["shot_fidelity_passed"],
        rest_boundaries=plan.curve.rest_boundaries(),
        analytic_extrema=extrema,
        preview={k: v for k, v in document["execution_preview"].items() if k != "frames"},
        serial_ports_opened=False,
        physical_commands_sent=False,
        robot_movement_verified=False,
        scope="Canonical plan, continuous reference and dispatch arithmetic only",
    )


def console_commands():
    if not sys.stdin.isatty():
        raise ValueError(
            "Live motion requires an interactive operator terminal for abort and supported release"
        )
    messages = queue.SimpleQueue()

    def read():
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    messages.put("detach")
                    return
                value = line.strip().lower()
                if value in ("release", "abort"):
                    messages.put(value)
        except (EOFError, OSError):
            messages.put("detach")

    threading.Thread(target=read, name="takeone-operator-input", daemon=True).start()

    def poll():
        try:
            return messages.get_nowait()
        except queue.Empty:
            return None

    return poll


def execute_plan(
    plan,
    *,
    mode,
    profile="windows",
    confirm_plan=None,
    operator_ready=False,
    execution_mode="commissioning",
    from_current=True,
):
    """Old harmless commands remain offline. Only live can open real ports."""
    plan = load_plan(plan.to_dict())
    if mode in ("check", "replay", "timing"):
        return check_plan(plan) | {"retired_alias": mode if mode != "check" else None}
    if mode != "live":
        raise ValueError("Choose check or live explicitly")
    if confirm_plan != plan.plan_id or not operator_ready:
        raise ValueError("Live execution requires the full reviewed plan ID and current operator readiness")

    def emit(event):
        print(json.dumps(event), flush=True)

    emit(dict(phase="validating_saved_plan", execution_mode=execution_mode, plan_id=plan.plan_id))
    plan = require_checked(plan)
    readiness = preflight(plan, profile, execution_mode=execution_mode)
    if readiness["blockers"]:
        raise ValueError("Physical execution blocked: " + "; ".join(readiness["blockers"]))
    operator = console_commands()
    limits = {r: execution_limits(r, execution_mode) for r in ROLES}
    factory = DeviceFactory(
        read_json(CONFIGS / "devices" / f"{profile}.json"),
        {r: execution_mapping(r, execution_mode) for r in ROLES},
        execution_mode,
    )
    folder = (
        DATA
        / "runs"
        / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-robot-" + uuid.uuid4().hex[:8])
    )
    folder.mkdir(parents=True)
    emit(
        dict(
            phase="preflight_passed",
            run_directory=str(folder),
            qualification="unmeasured commissioning" if execution_mode == "commissioning" else "qualified",
            missing_qualification_records=len(readiness["qualification_warnings"]),
        )
    )
    (folder / "requested-plan.json").write_bytes(plan.payload)
    if execution_mode == "commissioning" and from_current:
        from .staging import capture_approach

        try:
            plan = capture_approach(plan, profile, folder, emit)
            readiness = preflight(plan, profile, execution_mode=execution_mode)
        except (ValueError, OSError, RuntimeError) as error:
            (folder / "startup-error.json").write_text(json.dumps(dict(error=str(error))), encoding="utf-8")
            raise
    if operator() is not None:
        raise ValueError("Operator cancelled before activation; no motion commands sent")
    execution_frame = dict(
        schema="takeone.run-local-frame.v1",
        plan_id=plan.plan_id,
        cart_start=dict(frame="run_local_Z_up_cart_start_origin", x_m=0.0, y_m=0.0, yaw_rad=0.0),
        planning_world_cart_start=plan.to_dict()["initial_cart_pose"],
        interpretation=(
            "The timed wheel schedule starts wherever the cart is placed. Physical x/y/yaw are defined "
            "as zero at dispatch start; planned poses and independent observations are expressed relative "
            "to the compiled planning-world cart start."
        ),
    )
    for name, document in (
        ("plan", plan.to_dict()),
        ("execution-frame", execution_frame),
        ("preflight", readiness),
    ):
        (folder / f"{name}.json").write_text(
            json.dumps(document, indent=2, allow_nan=False), encoding="utf-8"
        )
    print(
        json.dumps(
            dict(
                run_directory=str(folder),
                commands="abort: stop travel/retain arm goals; release: BOTH arms supported, release torque",
            )
        ),
        flush=True,
    )
    result = RobotRunner(plan, factory, limits).run(folder, operator_command=operator, emit=emit)
    result["requested_plan_id"] = confirm_plan
    (folder / "report.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    summary = {k: v for k, v in result.items() if k != "roles"}
    summary["arms"] = {
        r: {k: v for k, v in result["roles"][r].items() if k not in ("events", "terminal_hold")}
        for r in ROLES
    }
    return summary | {"directory": str(folder)}
