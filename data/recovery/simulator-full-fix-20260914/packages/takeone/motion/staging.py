"""Read actual start encoders and prepend a checked stationary-cart approach."""

import json
import math

from takeone.contracts import JOINTS
from takeone.paths import DATA
from takeone.planning.curve import JointCurve, quintic

from .checked import record_check, require_checked
from .limits import execution_limits, execution_mapping, preflight
from .plan import ROLES, digest, load_plan


def with_approach(plan, initial_rad, duration_s):
    from takeone.planning.preview import execution_preview
    from takeone.simulation.drive import simulate_wire_schedule

    d = plan.to_dict()
    if d.get("staging") or not plan.curve.rest_boundaries():
        raise ValueError("Start from the original checked plan with stationary arm boundaries")
    if len(initial_rad) != 10 or not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("Approach requires ten angles and a positive finite duration")
    for i, role in enumerate(ROLES):
        execution_mapping(role, "commissioning").to_raw(initial_rad[i * 5 : i * 5 + 5])
    zeros = (0.0,) * 10
    before = quintic(initial_rad, zeros, zeros, plan.curve.at(0), zeros, zeros, duration_s)
    curve = JointCurve(
        (0.0, *(t + duration_s for t in plan.curve.knots_s)),
        (before, *plan.curve.coefficients),
    )
    transition = d["revision"]["transition_s"]
    packets = [
        dict(time=s["time_s"] - transition, commands=s["commands"], wire=s["wire"])
        for s in d["cart_schedule"]
        if transition <= s["time_s"] < transition + d["settings"]["duration"]
    ]
    trace = simulate_wire_schedule(d["settings"], d["initial_cart_pose"], packets)
    ranges = tuple(b for r in ROLES for b in execution_mapping(r, "commissioning").safe_ranges_rad)
    preview = execution_preview(
        d["settings"],
        curve,
        plan.period_s,
        transition + duration_s,
        include_envelope=True,
        trace=trace,
        joint_ranges=ranges,
    )
    schedule = [dict(s, time_s=s["time_s"] + duration_s) for s in d["cart_schedule"]]
    schedule.insert(0, dict(time_s=0.0, commands=[0.0, 0.0], wire="0.00,0.00\n"))
    d.update(
        staging=dict(source_plan_id=plan.plan_id, initial_rad=list(initial_rad), duration_s=duration_s),
        joint_curve=curve.to_dict(),
        duration_s=curve.duration_s,
        samples=[
            dict(time_s=f["time_s"], arms=dict(phone=f["q"][3:8], light=f["q"][8:13]))
            for f in preview["frames"]
        ],
        execution_preview=preview,
        cart_schedule=schedule,
        plan_valid=d["plan_valid"] and all(c["passed"] for c in preview["revision_checks"]),
        rest_boundaries=curve.rest_boundaries(),
    )
    del d["plan_id"]
    return load_plan(d | {"plan_id": digest(d)})


def capture_approach(plan, profile, folder, emit):
    """No register writes here. A worker rechecks the captured pose before enabling torque."""
    from .commission import inspect_arm

    require_checked(plan)
    initial = []
    errors = []
    captures = {}
    for role in ROLES:
        emit(dict(phase="reading_start", role=role))
        captured = inspect_arm(role, profile)
        captures[role] = captured
        if not captured["completed"]:
            errors.append(f"{role}: {captured.get('error', 'inspection failed')}")
            continue
        mapping = execution_mapping(role, "commissioning")
        raw = {}
        for name in JOINTS:
            joint = captured["joints"][name]
            registers = joint["registers_raw"]
            raw[name] = registers["Present_Position"]
            low, high = joint["configured_encoder_range"]
            if not low <= raw[name] <= high:
                errors.append(
                    f"{role} {name} ID {joint['motor_id']}: current encoder {raw[name]} outside "
                    f"calibration {low}..{high}. Support this arm and move the joint inside that range; "
                    "no torque enabled or motion sent."
                )
            if registers["Torque_Enable"] != 0 or registers["Operating_Mode"] != 0:
                errors.append(f"{role}/{name}: capture requires position mode and torque off")
        if not captured["configured_calibration_matches_hardware"]:
            errors.append(f"{role}: attached motor calibration differs from the saved calibration")
        if all(
            mapping.raw_calibration[n]["range_min"] <= raw[n] <= mapping.raw_calibration[n]["range_max"]
            for n in JOINTS
        ):
            initial.extend(mapping.from_raw(raw))
        emit(dict(phase="start_encoders", role=role, positions=raw))
    (folder / "start-inspection.json").write_text(json.dumps(captures, indent=2), encoding="utf-8")
    if errors:
        raise ValueError("; ".join(errors))
    tolerances = tuple(v for r in ROLES for v in execution_limits(r, "commissioning").initial_tolerance_rad)
    differences = [abs(a - b) for a, b in zip(initial, plan.curve.at(0))]
    if all(d <= tolerance for d, tolerance in zip(differences, tolerances)):
        emit(dict(phase="start_matches_plan"))
        return plan
    # Rest-to-rest quintic peaks: v=1.875*d/T, a=10/sqrt(3)*d/T², j=60*d/T³.
    # Choose 0.5 rad/s for this approach, below the shot's 0.8 rad/s policy.
    delta = max(differences)
    duration = max(
        2.0, 1.875 * delta / 0.5, math.sqrt(10 / math.sqrt(3) * delta / 1.8), (60 * delta / 12) ** (1 / 3)
    )
    duration = math.ceil(duration / plan.period_s) * plan.period_s
    emit(dict(phase="checking_approach", duration_s=duration, maximum_joint_travel_deg=math.degrees(delta)))
    staged = with_approach(plan, initial, duration)
    readiness = preflight(staged, profile, execution_mode="commissioning")
    for warning in readiness.get("geometry_warnings", []):
        emit(dict(phase="commissioning_geometry_advisory", message=warning))
    (folder / "approach-plan.json").write_bytes(staged.payload)
    (folder / "approach-preflight.json").write_text(json.dumps(readiness, indent=2), encoding="utf-8")
    if readiness["blockers"]:
        raise ValueError("Approach rejected: " + "; ".join(readiness["blockers"]))
    record_check(staged, "checked_approach")
    emit(dict(phase="approach_ready", plan_id=staged.plan_id, duration_s=staged.duration_s))
    return staged


def reconstruct_approach(document):
    from .plan import reconstruct

    staging = document["staging"]
    identity = staging["source_plan_id"]
    if (
        not isinstance(identity, str)
        or len(identity) != 64
        or any(c not in "0123456789abcdef" for c in identity)
    ):
        raise ValueError("Invalid approach source plan identity")
    source = DATA / "checked-plans" / f"{staging['source_plan_id']}.plan.json"
    plan = reconstruct(load_plan(json.loads(source.read_text(encoding="utf-8"))))
    return with_approach(plan, staging["initial_rad"], staging["duration_s"])
