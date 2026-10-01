"""Explicit operating budgets and measured, role-specific motion envelopes."""

import math
from dataclasses import dataclass

from takeone.calibration import ArmMapping
from takeone.clock import clock_info
from takeone.config import file_hash, finite, read_json
from takeone.contracts import JOINTS, joints
from takeone.paths import CALIBRATION, CONFIGS, WORKSPACE

from .plan import ROLES


@dataclass(frozen=True)
class ArmTiming:
    period_s: float
    lateness_limit_s: float
    io_limit_s: float
    feedback_age_s: float
    peer_lease_s: float
    supervisor_lease_s: float
    start_lead_s: float
    startup_timeout_s: float
    settle_timeout_s: float
    settle_duration_s: float

    def __post_init__(self):
        for key in self.__dataclass_fields__:
            if finite(getattr(self, key), key) <= 0:
                raise ValueError("Execution budgets must be positive")
        if self.io_limit_s + self.lateness_limit_s >= self.period_s:
            raise ValueError("Arm IO and dispatch budgets must fit inside the command period")
        if self.peer_lease_s <= self.period_s + self.io_limit_s:
            raise ValueError("Peer lease must allow one arm cycle")
        if self.settle_duration_s >= self.settle_timeout_s:
            raise ValueError("Settling timeout must exceed the stable observation window")
        if self.period_s > 0.1 or self.feedback_age_s > self.peer_lease_s:
            raise ValueError("Arm sampling and feedback freshness exceed the supported execution budgets")

    @classmethod
    def load(cls):
        config = read_json(CONFIGS / "arm-execution.json")
        return cls(**{k: config[k] for k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class ArmLimits:
    velocity_rad_s: tuple
    acceleration_rad_s2: tuple
    step_rad: tuple
    initial_tolerance_rad: tuple
    tracking_tolerance_rad: tuple
    final_tolerance_rad: tuple
    jerk_rad_s3: tuple
    basis: str = "measured"

    def __post_init__(self):
        for key in self.__dataclass_fields__:
            if key == "basis":
                if self.basis not in ("measured", "commissioning_policy"):
                    raise ValueError("Unknown limit basis")
                continue
            values = joints(getattr(self, key))
            if any(v <= 0 for v in values):
                raise ValueError("Every joint limit must be finite and positive")
            object.__setattr__(self, key, values)

    def validate_plan(self, plan, role, timing, mapping=None):
        track = getattr(plan, role)
        if not plan.curve.rest_boundaries():
            raise ValueError(f"{role}: explicit zero-velocity/acceleration approach and departure required")
        offset = ROLES.index(role) * 5
        for derivative, caps in (
            (1, self.velocity_rad_s),
            (2, self.acceleration_rad_s2),
            (3, self.jerk_rad_s3),
        ):
            low, high = plan.curve.extrema(derivative)
            if any(
                max(abs(a), abs(b)) > cap
                for a, b, cap in zip(low[offset : offset + 5], high[offset : offset + 5], caps)
            ):
                raise ValueError(f"{role}: continuous derivative {derivative} exceeds measured limits")
        if mapping is not None:
            for q in track:
                mapping.to_degrees(q)
            low, high = plan.curve.extrema()
            mapping.to_degrees(low[offset : offset + 5])
            mapping.to_degrees(high[offset : offset + 5])
        # Backward differences of actual encoded setpoints, including settling
        # to a stationary goal. These are command limits, not mechanical jerk.
        times = (*plan.dispatch_times(timing.period_s),)
        times += tuple(times[-1] + n * timing.period_s for n in (1, 2, 3))

        def encoded_q(t):
            q = plan.arm_at(role, min(t, plan.duration_s))
            return q if mapping is None else mapping.from_raw(mapping.to_raw(q))

        previous_q = encoded_q(0)
        previous_velocity = previous_acceleration = (0.0,) * 5
        for a, b in zip(times, times[1:]):
            q = encoded_q(b)
            velocity = tuple((y - x) / (b - a) for x, y in zip(previous_q, q))
            acceleration = tuple((v - old) / (b - a) for v, old in zip(velocity, previous_velocity))
            jerk = tuple((v - old) / (b - a) for v, old in zip(acceleration, previous_acceleration))
            if any(abs(y - x) > cap for x, y, cap in zip(previous_q, q, self.step_rad)):
                raise ValueError(f"{role}: encoded trajectory exceeds joint step limits")
            for name, values, caps in (
                ("velocity", velocity, self.velocity_rad_s),
                ("acceleration", acceleration, self.acceleration_rad_s2),
                ("jerk", jerk, self.jerk_rad_s3),
            ):
                # Integer position commands introduce finite-difference noise.
                # For truncation error in one encoder-count interval, the nth
                # difference is bounded by 2**(n-1) counts / dt**n.
                order = {"velocity": 1, "acceleration": 2, "jerk": 3}[name]
                allowance = (
                    2 ** (order - 1) * (2 * math.pi / 4095) / (b - a) ** order
                    if self.basis == "commissioning_policy" and mapping is not None
                    else 0.0
                )
                if any(abs(v) > cap + allowance + 1e-8 for v, cap in zip(values, caps)):
                    raise ValueError(f"{role}: encoded trajectory exceeds {self.basis} {name} limits")
            previous_q, previous_velocity, previous_acceleration = q, velocity, acceleration


def measured_limits(role):
    config = read_json(CONFIGS / "arm-execution.json")["live_limits"][role]
    if config["verified"] is not True:
        raise ValueError(
            f"{role}: loaded velocity, acceleration, jerk, step and tracking measurements are missing"
        )
    registry = read_json(CALIBRATION / "registry.json")["arms"][role]
    mapping = (CALIBRATION / registry["mapping_path"]).resolve()
    if not mapping.is_relative_to(CALIBRATION.resolve()) or file_hash(mapping) != config["mapping_sha256"]:
        raise ValueError(f"{role}: measured limits are for a different alignment")
    evidence = (WORKSPACE / config["evidence_path"]).resolve()
    if not evidence.is_relative_to(WORKSPACE) or file_hash(evidence) != config["evidence_sha256"]:
        raise ValueError(f"{role}: loaded motion evidence hash/path mismatch")
    return ArmLimits(**config["limits"])


def execution_mapping(role, execution_mode="qualified"):
    if execution_mode == "qualified":
        return ArmMapping.load(role)
    if execution_mode != "commissioning":
        raise ValueError("Unknown execution mode")
    registry = read_json(CALIBRATION / "registry.json")["arms"][role]
    path = (CALIBRATION / registry["mapping_path"]).resolve()
    if not path.is_relative_to(CALIBRATION.resolve()):
        raise ValueError("Mapping path escapes calibration directory")
    mapping = read_json(path)
    if mapping.get("verified") is not True and mapping.get("visual_pose_match_confirmed") is not True:
        raise ValueError(f"{role}: confirm the simulator joint axes/zero against the real arm first")
    return ArmMapping.load(role, require_motion=False)


def execution_limits(role, execution_mode="qualified"):
    if execution_mode == "qualified":
        return measured_limits(role)
    if execution_mode != "commissioning":
        raise ValueError("Unknown execution mode")
    config = read_json(CONFIGS / "arm-execution.json")["commissioning_limits"]
    return ArmLimits(**config, basis="commissioning_policy")


def preflight(plan, profile="windows", *, execution_mode="qualified"):
    """Offline only: return every known blocker without opening or enumerating ports."""
    from .measurements import criteria_blockers

    document = plan.to_dict()
    if execution_mode not in ("commissioning", "qualified"):
        raise ValueError("Unknown execution mode")
    blockers = []
    missing_evidence = criteria_blockers(document.get("acceptance_criteria"))
    if not document["plan_valid"]:
        blockers.append(
            "Candidate fails numerical motion screens; inspect revision_checks and simulator_checks"
        )
    if not document["shot_fidelity_passed"]:
        blockers.append(
            "Requested full phone/light position or orientation is not achieved; revise and review the shot"
        )
    envelope = document["execution_preview"].get("model_envelope")
    if not envelope or not envelope["conditional_clearance_proven"]:
        blockers.append(
            "Nominal swept geometry bound does not establish clearance; inspect model_envelope and refine/review geometry"
        )
    if envelope and envelope["assumed_static_support_margin_m"] <= 0:
        blockers.append("Assumed robot center of mass leaves the conservative static support polygon")
    if not plan.curve.rest_boundaries():
        blockers.append("Arm path has nonzero start/end derivatives; prepare explicit approach and departure")
    response = read_json(CONFIGS / "cart-response.json")
    if response["mode"] != "measured_table":
        missing_evidence.append(
            "Independent loaded left/right wire-command response measurements are missing"
        )
    evidence = read_json(CONFIGS / "motion-evidence.json")
    for capability, description in evidence["required"].items():
        record = evidence["records"].get(capability)
        try:
            if not isinstance(record, dict):
                raise ValueError(description)
            path = (WORKSPACE / record["path"]).resolve()
            if not path.is_relative_to(WORKSPACE) or file_hash(path) != record["sha256"]:
                raise ValueError(f"{capability}: evidence hash/path mismatch")
            from .measurements import validate_qualification

            validate_qualification(plan, capability, read_json(path))
        except (KeyError, TypeError, ValueError, OSError) as error:
            missing_evidence.append(str(error))
    timing = ArmTiming.load()
    devices = read_json(CONFIGS / "devices" / f"{profile}.json")
    if devices.get("hardware_enabled") is not True:
        blockers.append(f"{profile}: device profile is not enabled for physical execution")
    identities = []
    for role in (*ROLES, "cart"):
        device = devices["arms"][role] if role in ROLES else devices["cart"]
        if not device.get("port") or not device.get("usb_serial"):
            blockers.append(f"{role}: an explicit port and USB serial identity are required")
        identities.append(device.get("port"))
    if len(set(identities)) != 3:
        blockers.append("Every device must own a distinct serial port")
    for role in ROLES:
        expected_ids = dict(zip(JOINTS, (1, 2, 3, 4, 6 if role == "phone" else 5)))
        if devices["arms"][role].get("motor_ids") != expected_ids:
            blockers.append(f"{role}: configured motor identities do not match this rig")
        try:
            mapping = execution_mapping(role, execution_mode)
            execution_limits(role, execution_mode).validate_plan(plan, role, timing, mapping)
        except (ValueError, OSError, KeyError, TypeError) as error:
            blockers.append(str(error))
        # Report the missing operating measurements even when calibration is absent.
        try:
            ArmMapping.load(role)
        except (ValueError, OSError, KeyError, TypeError) as error:
            missing_evidence.append(str(error))
        try:
            measured_limits(role)
        except (ValueError, OSError, KeyError, TypeError) as error:
            missing_evidence.append(str(error))
    if execution_mode == "qualified":
        blockers.extend(missing_evidence)
    else:
        from takeone.config import rig_config
        from takeone.protocol import MIN_COMMAND

        cart = rig_config()["cart"]
        direction = -1 if cart["reverse_enabled"] else 1
        for pair in plan.commands:
            if any(
                v != 0 and not MIN_COMMAND <= direction * v <= min(cart["command_cap"], 0.05) for v in pair
            ):
                blockers.append("Commissioning wheel commands must be zero or forward 0.04–0.05")
                break
        if plan.duration_s > 120:
            blockers.append("Commissioning plan must be finite and at most 120 seconds")
    return dict(
        plan_id=plan.plan_id,
        execution_mode=execution_mode,
        qualification_warnings=list(dict.fromkeys(missing_evidence))
        if execution_mode == "commissioning"
        else [],
        software_plan_valid=document["plan_valid"],
        shot_fidelity_passed=document["shot_fidelity_passed"],
        live_execution_allowed=not blockers,
        serial_ports_opened=False,
        blockers=list(dict.fromkeys(blockers)),
        initial_pose_rad={role: plan.arm_at(role, 0) for role in ROLES},
        physical_tracking_verified=False,
        host_clock=clock_info(),
    )
