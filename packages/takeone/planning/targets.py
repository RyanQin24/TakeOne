"""Pure motion intent: independent arm programs produce world-space tool targets."""

import math
from bisect import bisect_right
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import numpy as np
from scipy.spatial.transform import Rotation


class ArmRole(str, Enum):
    PHONE = "phone"
    LIGHT = "light"


@dataclass(frozen=True, slots=True)
class ArmSpec:
    role: ArmRole
    model_prefix: str
    qpos_start: int

    @property
    def qpos_slice(self) -> slice:
        return slice(self.qpos_start, self.qpos_start + 5)


ARMS = (ArmSpec(ArmRole.PHONE, "cam", 3), ArmSpec(ArmRole.LIGHT, "light", 8))


def ease(phase: float) -> float:
    return 10 * phase**3 - 15 * phase**4 + 6 * phase**5


def actor_target(settings: dict, phase: float) -> np.ndarray:
    scale = settings["actorHeight"] / 1.72
    yaw = np.pi - np.deg2rad(settings["orbit"]) / 2 + np.deg2rad(settings["turn"]) * ease(phase)
    return np.array([0.085 * scale * np.cos(yaw), 0.085 * scale * np.sin(yaw), 1.6 * scale])


@dataclass(frozen=True, slots=True)
class ToolTarget:
    position_m: tuple[float, float, float]
    look_at_m: tuple[float, float, float]
    right_axis: tuple[float, float, float] | None = None

    def __post_init__(self) -> None:
        for name in ("position_m", "look_at_m"):
            vector = tuple(getattr(self, name))
            if len(vector) != 3 or not all(math.isfinite(value) for value in vector):
                raise ValueError("Tool target must contain two finite world-space vectors")
            object.__setattr__(self, name, vector)
        if np.linalg.norm(np.subtract(self.look_at_m, self.position_m)) < 1e-9:
            raise ValueError("Tool position and look-at point must differ")
        if self.right_axis is not None:
            right = np.asarray(self.right_axis, dtype=float)
            if right.shape != (3,) or not np.isfinite(right).all() or np.linalg.norm(right) < 1e-9:
                raise ValueError("Explicit optical right axis must be a finite nonzero vector")
            direction = np.subtract(self.look_at_m, self.position_m)
            if np.linalg.norm(np.cross(right, direction)) < 1e-9:
                raise ValueError("Optical right axis cannot be parallel to aim")
            object.__setattr__(self, "right_axis", tuple(right / np.linalg.norm(right)))


class TargetStrategy(Protocol):
    def at(self, phase: float, cart_pose: np.ndarray, subject_m: np.ndarray) -> ToolTarget: ...


@dataclass(frozen=True, slots=True)
class TrackingMotion:
    """Compose subject tracking with independent cart-relative sweep and lift."""

    height_m: float
    forward_m: float
    sweep_m: float
    lift_m: float
    aim_drop_m: float
    direction_sign: int = 1

    def __post_init__(self) -> None:
        values = (self.height_m, self.forward_m, self.sweep_m, self.lift_m, self.aim_drop_m)
        if any(isinstance(value, bool) or not math.isfinite(value) for value in values):
            raise ValueError("Tracking motion values must be finite metres")
        if self.sweep_m < 0 or self.lift_m < 0:
            raise ValueError("Sweep and lift distances must be nonnegative")
        if type(self.direction_sign) is not int or self.direction_sign not in (-1, 1):
            raise ValueError("Tracking direction sign must be -1 or 1")

    def offset(self, phase: float) -> np.ndarray:
        if not math.isfinite(phase) or not 0 <= phase <= 1:
            raise ValueError("Motion phase must be in [0, 1]")
        progress = ease(phase)
        return np.array(
            [
                self.direction_sign * self.sweep_m * (progress - 0.5),
                0.0,
                self.lift_m * math.sin(np.pi * progress) ** 2,
            ]
        )

    def at(self, phase: float, cart_pose: np.ndarray, subject_m: np.ndarray) -> ToolTarget:
        local_position = np.array([0.02, self.forward_m, self.height_m]) + self.offset(phase)
        position = (
            Rotation.from_euler("z", cart_pose[2]).as_matrix() @ local_position + np.r_[cart_pose[:2], 0.0]
        )
        aim = subject_m.copy()
        aim[2] -= self.aim_drop_m
        return ToolTarget(tuple(position), tuple(aim))


@dataclass(frozen=True, slots=True)
class FixedWorldTarget:
    """Hold one explicit world-space target; no substitution on a failed solve."""

    target: ToolTarget

    def at(self, phase: float, cart_pose: np.ndarray, subject_m: np.ndarray) -> ToolTarget:
        return self.target


@dataclass(frozen=True, slots=True)
class FrozenWorldProgram:
    """Materialized world-space intent that cannot follow a candidate cart pose."""

    phases: tuple[float, ...]
    targets: tuple[ToolTarget, ...]
    source_frame: str = "world"

    def __post_init__(self) -> None:
        phases = tuple(float(value) for value in self.phases)
        targets = tuple(self.targets)
        if (
            len(phases) < 2
            or len(phases) != len(targets)
            or phases[0] != 0.0
            or phases[-1] != 1.0
            or any(not math.isfinite(value) for value in phases)
            or any(a >= b for a, b in zip(phases, phases[1:]))
        ):
            raise ValueError("Frozen target phases must increase from zero to one")
        if self.source_frame != "world":
            raise ValueError("Frozen tool programs must use the world frame")
        object.__setattr__(self, "phases", phases)
        object.__setattr__(self, "targets", targets)

    def at(self, phase: float, cart_pose: np.ndarray, subject_m: np.ndarray) -> ToolTarget:
        if not math.isfinite(phase) or not 0 <= phase <= 1:
            raise ValueError("Motion phase must be in [0, 1]")
        index = min(len(self.phases) - 2, max(0, bisect_right(self.phases, phase) - 1))
        start, finish = self.phases[index], self.phases[index + 1]
        alpha = (phase - start) / (finish - start)
        a, b = self.targets[index], self.targets[index + 1]
        position = (1 - alpha) * np.asarray(a.position_m) + alpha * np.asarray(b.position_m)
        look_at = (1 - alpha) * np.asarray(a.look_at_m) + alpha * np.asarray(b.look_at_m)
        return ToolTarget(tuple(position), tuple(look_at))

    def to_dict(self) -> dict:
        return dict(
            frame=self.source_frame,
            interpolation="linear_between_materialized_world_samples",
            samples=[
                dict(phase=phase, position_m=list(target.position_m), look_at_m=list(target.look_at_m))
                for phase, target in zip(self.phases, self.targets)
            ],
        )


def tracking_programs(settings: dict, direction_sign: int = 1) -> dict[ArmRole, TrackingMotion]:
    return {
        ArmRole.PHONE: TrackingMotion(
            settings["cameraHeight"],
            0.38,
            settings["armTravel"],
            settings["armLift"],
            0.0,
            direction_sign,
        ),
        ArmRole.LIGHT: TrackingMotion(
            settings["cameraHeight"] - 0.04,
            -0.12,
            settings["lightTravel"],
            settings["lightLift"],
            0.15,
            direction_sign,
        ),
    }


def freeze_world_programs(
    settings: dict,
    reference_motion: dict,
    programs: dict[ArmRole, TargetStrategy],
    samples: int = 321,
) -> dict[ArmRole, FrozenWorldProgram]:
    """Resolve cart-relative authoring once against the reviewed reference cart.

    Candidate base planning must consume this result. Re-evaluating ``programs``
    with a candidate cart would move the requested world path with the robot.
    """
    if set(programs) != {arm.role for arm in ARMS} or not 2 <= samples <= 20001:
        raise ValueError("Both arm programs and a finite target sample count are required")
    from takeone.simulation import drive

    phases = tuple(float(value) for value in np.linspace(0, 1, samples))
    result = {}
    for role, program in programs.items():
        targets = []
        for phase in phases:
            cart = np.asarray(drive.sample(reference_motion, phase * settings["duration"])["cart"])
            targets.append(program.at(phase, cart, actor_target(settings, phase)))
        result[role] = FrozenWorldProgram(phases, tuple(targets))
    return result


def serialize_world_programs(programs: dict[ArmRole, FrozenWorldProgram]) -> dict:
    if set(programs) != {arm.role for arm in ARMS}:
        raise ValueError("Both frozen arm programs are required")
    return {role.value: program.to_dict() for role, program in programs.items()}


def movement_outline(programs: dict[ArmRole, TrackingMotion]) -> list[dict]:
    return [
        dict(
            role=role.value,
            target="track subject",
            frame="cart-relative translation; world-space aim",
            sweep_m=program.sweep_m,
            lift_m=program.lift_m,
            phases=[
                f"start at {'-' if program.direction_sign == 1 else '+'}half sweep",
                "track and rise to mid-shot",
                f"finish at {'+' if program.direction_sign == 1 else '-'}half sweep and return to starting height",
            ],
            joints=["pan", "shoulder lift", "elbow flex", "wrist pitch", "wrist roll"],
            orientation="point at target with horizon preference; five-joint IK",
            boundary="continuous tracking segment; physical start/stop unqualified",
        )
        for role, program in programs.items()
    ]
