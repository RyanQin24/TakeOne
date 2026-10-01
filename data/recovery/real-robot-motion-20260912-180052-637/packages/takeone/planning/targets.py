"""Pure motion intent: independent arm programs produce world-space tool targets."""

import math
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

    def __post_init__(self) -> None:
        for name in ("position_m", "look_at_m"):
            vector = tuple(getattr(self, name))
            if len(vector) != 3 or not all(math.isfinite(value) for value in vector):
                raise ValueError("Tool target must contain two finite world-space vectors")
            object.__setattr__(self, name, vector)
        if np.linalg.norm(np.subtract(self.look_at_m, self.position_m)) < 1e-9:
            raise ValueError("Tool position and look-at point must differ")


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
