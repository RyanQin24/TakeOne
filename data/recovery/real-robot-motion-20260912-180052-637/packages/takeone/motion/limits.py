"""Explicit operating budgets and measured, role-specific motion envelopes."""

from dataclasses import dataclass

from takeone.calibration import ArmMapping, hardware_blockers
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

    def __post_init__(self):
        for key in self.__dataclass_fields__:
            values = joints(getattr(self, key))
            if any(v <= 0 for v in values):
                raise ValueError("Every joint limit must be finite and positive")
            object.__setattr__(self, key, values)

    def validate_plan(self, plan, role, timing, mapping=None):
        track = getattr(plan, role)
        if mapping is not None:
            for q in track:
                mapping.to_degrees(q)
        # Check both source segments and the actual zero-order command stream.
        # Acceleration here is a finite difference, not a continuous torque model.
        for times in (plan.times_s, plan.dispatch_times(timing.period_s)):
            previous_q = plan.arm_at(role, 0)
            previous_velocity = (0.0,) * 5
            for a, b in zip(times, times[1:]):
                q = plan.arm_at(role, b)
                velocity = tuple((y - x) / (b - a) for x, y in zip(previous_q, q))
                if any(abs(v) > cap for v, cap in zip(velocity, self.velocity_rad_s)):
                    raise ValueError(f"{role}: trajectory exceeds measured velocity limits")
                if any(abs(y - x) > cap for x, y, cap in zip(previous_q, q, self.step_rad)):
                    raise ValueError(f"{role}: trajectory exceeds joint step limits")
                if any(
                    abs(v - old) / (b - a) > cap
                    for v, old, cap in zip(velocity, previous_velocity, self.acceleration_rad_s2)
                ):
                    raise ValueError(f"{role}: trajectory exceeds acceleration limits")
                previous_q, previous_velocity = q, velocity
            if any(abs(v) / timing.period_s > cap for v, cap in zip(velocity, self.acceleration_rad_s2)):
                raise ValueError(f"{role}: terminal stop exceeds acceleration limits")


def simulated_limits():
    """Permissive numerical test envelope. Never selected for a live run."""
    return ArmLimits((5.0,) * 5, (500.0,) * 5, (0.30,) * 5, (0.02,) * 5, (0.12,) * 5, (0.02,) * 5)


def measured_limits(role):
    config = read_json(CONFIGS / "arm-execution.json")["live_limits"][role]
    if config["verified"] is not True:
        raise ValueError(f"{role}: loaded tracking, velocity, acceleration and step limits are unverified")
    registry = read_json(CALIBRATION / "registry.json")["arms"][role]
    mapping = (CALIBRATION / registry["mapping_path"]).resolve()
    if not mapping.is_relative_to(CALIBRATION.resolve()) or file_hash(mapping) != config["mapping_sha256"]:
        raise ValueError(f"{role}: measured limits are for a different alignment")
    evidence = (WORKSPACE / config["evidence_path"]).resolve()
    if not evidence.is_relative_to(WORKSPACE) or file_hash(evidence) != config["evidence_sha256"]:
        raise ValueError(f"{role}: loaded motion evidence hash/path mismatch")
    return ArmLimits(**config["limits"])


def preflight(plan, profile="windows"):
    """Offline only: return every known blocker without opening or enumerating ports."""
    blockers = hardware_blockers()
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
            mapping = ArmMapping.load(role)
            measured_limits(role).validate_plan(plan, role, timing, mapping)
        except (ValueError, OSError, KeyError, TypeError) as error:
            blockers.append(str(error))
        # Report the missing operating measurements even when calibration is absent.
        try:
            measured_limits(role)
        except (ValueError, OSError, KeyError, TypeError) as error:
            blockers.append(str(error))
    return dict(
        plan_id=plan.plan_id,
        software_plan_valid=True,
        live_execution_allowed=not blockers,
        serial_ports_opened=False,
        blockers=list(dict.fromkeys(blockers)),
        initial_pose_rad={role: plan.arm_at(role, 0) for role in ROLES},
        physical_tracking_verified=False,
        host_clock=clock_info(),
    )
