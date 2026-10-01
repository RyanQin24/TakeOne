"""Import independent observations; never infer cart motion from UART writes."""

import math
from datetime import datetime, timezone

from takeone.config import file_hash, finite, read_json
from takeone.paths import CALIBRATION, CONFIGS, WORKSPACE

from .plan import ROLES, digest

TOLERANCES = (
    "cart_endpoint_m",
    "cart_heading_rad",
    "tool_position_m",
    "tool_pointing_rad",
    "physical_skew_s",
    "stop_distance_m",
    "stop_time_s",
    "maximum_observation_gap_s",
)
METHODS = ("cart", "tools", "coordination", "stopping")
RUN_LOCAL_CART_FRAME = "run_local_Z_up_cart_start_origin"
RUN_LOCAL_TOOL_FRAME = "run_local_Z_up_optical_Z_forward_X_right"


def timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Evidence timestamp is missing")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
        raise ValueError("Evidence requires a timezone and cannot be dated in the future")
    return stamp


def criteria_blockers(criteria):
    if not isinstance(criteria, dict) or criteria.get("schema") != "takeone.acceptance-criteria.v1":
        return ["Declare acceptance tolerances and measurement methods before the trial (--criteria)"]
    errors = []
    try:
        timestamp(criteria["declared_at"])
        for name in TOLERANCES:
            if finite(criteria["tolerances"][name], name) <= 0:
                raise ValueError(f"{name}: declare a positive acceptance tolerance")
        for name in METHODS:
            if not isinstance(criteria["methods"][name], str) or not criteria["methods"][name].strip():
                raise ValueError(f"{name}: measurement method missing")
        if criteria["methods"]["cart"] not in ("tape_endpoint_and_heading", "external_pose_samples"):
            raise ValueError("Choose tape_endpoint_and_heading or external_pose_samples")
    except (KeyError, TypeError, ValueError) as error:
        errors.append("Acceptance criteria incomplete: " + str(error))
    return errors


def motion_fingerprint(plan):
    """Qualification can precede final provenance sealing without a hash cycle."""
    d = plan.to_dict()
    registry = read_json(CALIBRATION / "registry.json")["arms"]
    return digest(
        dict(
            curve=d["joint_curve"],
            cart=d["cart_schedule"],
            settings=d["settings"],
            model=d["source_model_hash"],
            criteria=d["acceptance_criteria"],
            calibration={
                r: {k: file_hash(CALIBRATION / registry[r][k]) for k in ("original_path", "mapping_path")}
                for r in ROLES
            },
            rig=read_json(CONFIGS / "rig.json"),
            response=read_json(CONFIGS / "cart-response.json"),
            timing=read_json(CONFIGS / "arm-execution.json"),
            cart_timing=read_json(CONFIGS / "cart-runtime.json"),
            implementation={
                p.relative_to(WORKSPACE).as_posix(): file_hash(p)
                for p in (WORKSPACE / "packages/takeone").rglob("*.py")
            },
        )
    )


def validate_qualification(plan, capability, document):
    if (
        document.get("schema") != "takeone.motion-qualification.v1"
        or document.get("capability") != capability
    ):
        raise ValueError(f"{capability}: wrong evidence schema/capability")
    if document.get("motion_fingerprint") != motion_fingerprint(plan):
        raise ValueError(f"{capability}: evidence does not cover this motion, geometry and calibration")
    timestamp(document["observed_at"])
    if document.get("result") != "pass" or not document.get("method") or not document.get("conditions"):
        raise ValueError(f"{capability}: recorded method, conditions and passing assessment required")
    if not document.get("measurements") or not document.get("sources"):
        raise ValueError(f"{capability}: measured quantities and original sources required")
    for source in document["sources"]:
        path = (WORKSPACE / source["path"]).resolve()
        if not path.is_relative_to(WORKSPACE) or file_hash(path) != source["sha256"]:
            raise ValueError(f"{capability}: original evidence hash/path mismatch")
    for measurement in document["measurements"]:
        finite(measurement["value"], "Measured value")
        if (
            finite(measurement["uncertainty"], "Measurement uncertainty") < 0
            or not measurement["unit"]
            or not measurement["quantity"]
        ):
            raise ValueError(f"{capability}: quantity, unit and nonnegative uncertainty required")
    required = {
        "cart_stop_watchdog": {
            "startup_delay_s": "s",
            "stop_distance_m": "m",
            "stop_time_s": "s",
            "watchdog_timeout_s": "s",
        },
        "loaded_arm_stop_hold": {
            f"{r}_{quantity}": "rad"
            for r in ROLES
            for quantity in ("hold_drift_rad", "fault_stop_excursion_rad")
        },
        "scene_stability": {
            "minimum_swept_clearance_m": "m",
            "minimum_support_margin_m": "m",
            "minimum_joint_torque_margin_nm": "N m",
        },
        "tool_alignment": {
            f"{r}_{quantity}": unit
            for r in ROLES
            for quantity, unit in (("position_residual_m", "m"), ("pointing_residual_rad", "rad"))
        },
        "host_timing": {
            "phone_cycle_s": "s",
            "light_cycle_s": "s",
            "cart_host_gap_s": "s",
            "physical_response_skew_s": "s",
        },
    }[capability]
    measured = {v["quantity"]: v for v in document["measurements"]}
    for name, unit in required.items():
        if name not in measured or measured[name]["unit"] != unit or measured[name]["value"] < 0:
            raise ValueError(f"{capability}: missing measured {name} in {unit}")
    caps = plan.to_dict()["acceptance_criteria"]["tolerances"]
    upper = {n: v["value"] + v["uncertainty"] for n, v in measured.items()}
    limits = {}
    if capability == "cart_stop_watchdog":
        limits = {"stop_distance_m": caps["stop_distance_m"], "stop_time_s": caps["stop_time_s"]}
        watchdog = measured["watchdog_timeout_s"]
        if (
            watchdog["value"] - watchdog["uncertainty"]
            <= read_json(CONFIGS / "cart-runtime.json")["host_gap_limit_s"]
        ):
            raise ValueError("Measured firmware watchdog has no margin beyond the host-gap budget")
        if (
            document.get("polarity_matches_drive_frame") is not True
            or document.get("independent_stop_procedure_demonstrated") is not True
        ):
            raise ValueError("Cart polarity and independent stop procedure require observed evidence")
    if capability == "host_timing":
        limits = {
            "phone_cycle_s": read_json(CONFIGS / "arm-execution.json")["io_limit_s"],
            "light_cycle_s": read_json(CONFIGS / "arm-execution.json")["io_limit_s"],
            "cart_host_gap_s": read_json(CONFIGS / "cart-runtime.json")["host_gap_limit_s"],
            "physical_response_skew_s": caps["physical_skew_s"],
        }
    if capability == "tool_alignment":
        limits = {
            f"{r}_{q}": caps[c]
            for r in ROLES
            for q, c in (
                ("position_residual_m", "tool_position_m"),
                ("pointing_residual_rad", "tool_pointing_rad"),
            )
        }
    if capability == "scene_stability" and any(
        measured[n]["value"] - measured[n]["uncertainty"] <= 0 for n in required
    ):
        raise ValueError("Scene, support and torque margins must remain positive after uncertainty")
    if any(upper[n] > cap for n, cap in limits.items()):
        raise ValueError(f"{capability}: measured result plus uncertainty exceeds declared limits")


def _cart_pose(value):
    if not isinstance(value, dict) or value.get("frame") != RUN_LOCAL_CART_FRAME:
        raise ValueError("Measure the cart relative to its run-local starting origin")
    pose = tuple(finite(value[key], key) for key in ("x_m", "y_m", "yaw_rad"))
    for key in ("position_uncertainty_m", "heading_uncertainty_rad"):
        if finite(value[key], key) < 0:
            raise ValueError("Measurement uncertainty cannot be negative")
    if not value.get("source"):
        raise ValueError("Independent observation source is required")
    timestamp(value["observed_at"])
    return pose


def pose_error(actual, expected):
    return math.hypot(actual[0] - expected[0], actual[1] - expected[1]), abs(
        math.atan2(math.sin(actual[2] - expected[2]), math.cos(actual[2] - expected[2]))
    )


def _run_local_planar_pose(pose, origin):
    """Express a planning-world cart pose from the cart's physical start."""
    dx, dy = pose[0] - origin[0], pose[1] - origin[1]
    c, s = math.cos(origin[2]), math.sin(origin[2])
    return (
        c * dx + s * dy,
        -s * dx + c * dy,
        math.atan2(math.sin(pose[2] - origin[2]), math.cos(pose[2] - origin[2])),
    )


def _run_local_point(point, origin):
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    c, s = math.cos(origin[2]), math.sin(origin[2])
    return (c * dx + s * dy, -s * dx + c * dy, point[2])


def _run_local_vector(vector, origin):
    c, s = math.cos(origin[2]), math.sin(origin[2])
    return (c * vector[0] + s * vector[1], -s * vector[0] + c * vector[1], vector[2])


def _vector(value, label):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label}: three run-local-frame values required")
    return tuple(finite(v, label) for v in value)


def _axes(quaternion):
    x, y, z, w = quaternion
    return (2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)), (
        1 - 2 * (y * y + z * z),
        2 * (x * y + z * w),
        2 * (x * z - y * w),
    )


def _angle(actual, expected):
    if abs(sum(v * v for v in actual) - 1) > 1e-5:
        raise ValueError("Measured orientation axis must be a unit vector")
    return math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(actual, expected)))))


def assess_pose_samples(plan, samples, role, epoch):
    """Independent observations on the declared execution grid, with timing uncertainty.

    Coverage is sampled, not continuous. The importer requires all grid indices;
    external instruments must synchronize/interpolate their observations with a
    declared uncertainty, never fill missing samples from command integration.
    """
    if samples is None:
        return dict(available=False, passed=False, reason=f"Independent {role} pose samples unavailable")
    d = plan.to_dict()
    frames = d["execution_preview"]["frames"]
    origin = d["initial_cart_pose"]
    caps = d["acceptance_criteria"]["tolerances"]
    if not isinstance(samples, list) or len(samples) != len(frames):
        raise ValueError(f"{role}: complete measured dispatch-grid coverage required")
    peak_position = peak_angle = 0.0
    stamps = []
    for index, (sample, frame) in enumerate(zip(samples, frames)):
        if (
            sample.get("sample_index") != index
            or sample.get("source_kind") != "independent_observation"
            or not sample.get("source")
        ):
            raise ValueError(f"{role}: indexed independent observation and source required")
        stamp = finite(sample["captured_monotonic_s"], "Observation time")
        uncertainty = finite(sample["time_uncertainty_s"], "Time uncertainty")
        if uncertainty < 0 or abs(stamp - epoch - frame["time_s"]) + uncertainty > caps["physical_skew_s"]:
            raise ValueError(f"{role}: observation not aligned to the declared motion clock")
        if stamps and stamp <= stamps[-1]:
            raise ValueError("Independent acquisition timestamps must increase")
        stamps.append(stamp)
        if role == "cart":
            expected = _run_local_planar_pose(frame["q"][:3], origin)
            position, angle = pose_error(_cart_pose(sample), expected)
            p_unc, a_unc = sample["position_uncertainty_m"], sample["heading_uncertainty_rad"]
        else:
            key = "camera" if role == "phone" else "light"
            if sample.get("frame") != RUN_LOCAL_TOOL_FRAME:
                raise ValueError("Tool observations must use the declared run-local optical axes")
            actual = _vector(sample["position_m"], "Tool position")
            expected_position = _run_local_point(frame[key]["pos"], origin)
            position = math.sqrt(sum((a - b) ** 2 for a, b in zip(actual, expected_position)))
            forward, right = _axes(frame[key]["quat"])
            forward, right = _run_local_vector(forward, origin), _run_local_vector(right, origin)
            angle = max(
                _angle(_vector(sample["forward"], "Tool forward"), forward),
                _angle(_vector(sample["right"], "Tool right"), right),
            )
            p_unc = finite(sample["position_uncertainty_m"], "Tool position uncertainty")
            a_unc = finite(sample["orientation_uncertainty_rad"], "Tool orientation uncertainty")
        if p_unc < 0 or a_unc < 0:
            raise ValueError("Pose uncertainties cannot be negative")
        peak_position = max(peak_position, position + p_unc)
        peak_angle = max(peak_angle, angle + a_unc)
    gap = max(b - a for a, b in zip(stamps, stamps[1:]))
    return dict(
        available=True,
        passed=peak_position <= caps["cart_endpoint_m" if role == "cart" else "tool_position_m"]
        and peak_angle <= caps["cart_heading_rad" if role == "cart" else "tool_pointing_rad"]
        and gap <= caps["maximum_observation_gap_s"],
        max_position_error_plus_uncertainty_m=peak_position,
        max_angle_error_plus_uncertainty_rad=peak_angle,
        maximum_observation_gap_s=gap,
        sample_count=len(samples),
        scope="Independent sampled pose on the reviewed grid",
    )


def templates(plan):
    cart = dict(
        frame=RUN_LOCAL_CART_FRAME,
        x_m=None,
        y_m=None,
        yaw_rad=None,
        position_uncertainty_m=None,
        heading_uncertainty_rad=None,
        source=None,
        observed_at=None,
    )
    return dict(
        criteria=dict(
            schema="takeone.acceptance-criteria.v1",
            declared_at=None,
            methods=dict(cart="tape_endpoint_and_heading", tools=None, coordination=None, stopping=None),
            tolerances=dict.fromkeys(TOLERANCES),
        ),
        observations=dict(
            schema="takeone.motion-observations.v1",
            plan_id=plan.plan_id,
            run_report_sha256=None,
            cart_final=cart,
            cart_stopped=None,
            stop_distance_m=None,
            stop_distance_uncertainty_m=None,
            stop_time_s=None,
            stop_time_uncertainty_s=None,
            stop_source=None,
            tools=None,
            coordination=None,
        ),
        qualification=dict(
            schema="takeone.motion-qualification.v1",
            capability=None,
            motion_fingerprint=motion_fingerprint(plan),
            observed_at=None,
            method=None,
            conditions=None,
            measurements=[],
            sources=[],
            result=None,
        ),
    )


def assess_run(folder, observations_path):
    """Endpoint tape data does not verify a complete path, lag, or brake latency."""
    from .plan import load_plan

    plan = load_plan(read_json(folder / "plan.json"), current_sources=False)
    d = plan.to_dict()
    if criteria_blockers(d["acceptance_criteria"]):
        raise ValueError("Run has no predeclared acceptance criteria")
    report = read_json(folder / "report.json")
    observations = read_json(observations_path)
    if (
        observations.get("schema") != "takeone.motion-observations.v1"
        or observations.get("plan_id") != plan.plan_id
        or report.get("plan_id") != plan.plan_id
    ):
        raise ValueError("Observations and actual run must name the same exact plan")
    if (
        observations.get("run_report_sha256") != file_hash(folder / "report.json")
        or report.get("mode") != "live"
    ):
        raise ValueError("A matching real run report is required")
    caps = d["acceptance_criteria"]["tolerances"]
    endpoint = observations.get("cart_final")
    cart_result = dict(available=False, passed=False, reason="Independent endpoint observation missing")
    if endpoint:
        actual = _cart_pose(endpoint)
        if timestamp(endpoint["observed_at"]) < timestamp(d["acceptance_criteria"]["declared_at"]):
            raise ValueError("Acceptance thresholds must predate observations")
        expected = _run_local_planar_pose(d["final_cart_pose"], d["initial_cart_pose"])
        p, h = pose_error(actual, expected)
        cart_result = dict(
            available=True,
            passed=p + endpoint["position_uncertainty_m"] <= caps["cart_endpoint_m"]
            and h + endpoint["heading_uncertainty_rad"] <= caps["cart_heading_rad"],
            endpoint_error_m=p,
            heading_error_rad=h,
            method="tape_endpoint_and_heading",
            expected_run_local_pose=dict(x_m=expected[0], y_m=expected[1], yaw_rad=expected[2]),
            scope="Final cart pose relative to its physical starting origin; path, wheel speed and repeatability unmeasured",
        )
    arm_results = {}
    for role in ROLES:
        trace = report.get("roles", {}).get(role, {})
        commands = [e for e in trace.get("events", []) if e.get("phase") == "command"]
        tracking = [e for e in trace.get("events", []) if e.get("phase") in ("tracking", "settling")]
        actual = bool(tracking) and all(
            e.get("source") == "measured"
            and e.get("raw_positions")
            and e.get("acquisition_start_s") is not None
            for e in tracking
        )
        transmitted = len(commands) == len(plan.times_s) and all(
            e.get("source") == "transmitted_not_measured"
            and len(e.get("receipt", {}).get("writes", [])) == 5
            and all(w.get("acknowledged") is True for w in e["receipt"]["writes"])
            for e in commands
        )
        arm_results[role] = dict(
            commands_transmitted=transmitted,
            sampled_tracking_verified=actual and trace.get("physical_tracking_verified") is True,
            supported_release_confirmed=trace.get("activation", {}).get("torque_disabled_confirmed") is True,
            final_hold_observations=trace.get("terminal_hold", {}).get("sample_count", 0),
        )
    stop = dict(available=False, passed=False, reason="Stop distance/time observation missing")
    if observations.get("cart_stopped") is True and observations.get("stop_source"):
        values = {
            k: finite(observations[k], k)
            for k in (
                "stop_distance_m",
                "stop_distance_uncertainty_m",
                "stop_time_s",
                "stop_time_uncertainty_s",
            )
        }
        if any(v < 0 for v in values.values()):
            raise ValueError("Stop observations and uncertainties cannot be negative")
        stop = dict(
            available=True,
            passed=values["stop_distance_m"] + values["stop_distance_uncertainty_m"]
            <= caps["stop_distance_m"]
            and values["stop_time_s"] + values["stop_time_uncertainty_s"] <= caps["stop_time_s"],
            **values,
        )
    epoch = report.get("epoch_monotonic_s")
    independent = {}
    for role in (*ROLES, "cart"):
        samples = (
            observations.get("cart_path") if role == "cart" else (observations.get("tools") or {}).get(role)
        )
        if samples is not None and epoch is None:
            raise ValueError("No agreed real run epoch for independent sample alignment")
        independent[role] = assess_pose_samples(plan, samples, role, epoch)
    coordination = observations.get("coordination")
    skew = dict(available=False, passed=False, reason="Independent physical response timing unavailable")
    if coordination is not None:
        if (
            set(coordination["roles"]) != {"phone", "light", "cart"}
            or not coordination.get("source")
            or coordination.get("source_kind") != "independent_observation"
        ):
            raise ValueError(
                "Physical coordination requires all three observed devices and an independent source"
            )
        value = finite(coordination["maximum_response_skew_s"], "Physical response skew")
        uncertainty = finite(coordination["uncertainty_s"], "Physical skew uncertainty")
        if min(value, uncertainty) < 0:
            raise ValueError("Timing observations cannot be negative")
        skew = dict(
            available=True,
            passed=value + uncertainty <= caps["physical_skew_s"],
            maximum_response_skew_s=value,
            uncertainty_s=uncertainty,
        )
    cart_trace = report.get("roles", {}).get("cart", {})
    cart_writes = [
        e for e in cart_trace.get("events", []) if e.get("phase") == "motion" and "write_end_s" in e
    ]
    cart_transmitted = bool(cart_writes) and cart_trace.get("fault") is None
    finite_verified = (
        report.get("completed") is True
        and d["plan_valid"]
        and d["shot_fidelity_passed"]
        and cart_transmitted
        and cart_result["passed"]
        and stop["passed"]
        and skew["passed"]
        and all(v["passed"] for v in independent.values())
        and all(
            v["commands_transmitted"]
            and v["sampled_tracking_verified"]
            and v["supported_release_confirmed"]
            and v["final_hold_observations"] > 0
            for v in arm_results.values()
        )
    )
    return dict(
        plan_id=plan.plan_id,
        run_report_sha256=file_hash(folder / "report.json"),
        observations_sha256=file_hash(observations_path),
        arms=arm_results,
        cart_endpoint=cart_result,
        physical_cart_stop=stop,
        cart_commands_transmitted=cart_transmitted,
        independent_pose_samples=independent,
        cart_path_verified=independent["cart"]["passed"],
        tools_verified=all(independent[r]["passed"] for r in ROLES),
        physical_coordination=skew,
        robot_movement_verified=finite_verified,
        repeatability_verified=False,
        unavailable=[r for r, v in independent.items() if not v["available"]]
        + ([] if skew["available"] else ["physical coordination"]),
        scope="One finite run; sampled physical acceptance only. Endpoint tape data cannot establish full-path tracking or repeatability.",
    )
