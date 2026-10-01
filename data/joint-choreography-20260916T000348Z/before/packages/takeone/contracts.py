"""Units and timestamps are explicit; observations are never invented feedback."""

from dataclasses import dataclass
from typing import ClassVar, Protocol

from .config import finite
from .protocol import COMMAND_CAP

JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")


def joints(values):
    result = tuple(values)
    if len(result) != 5:
        raise ValueError("Expected five ordered URDF joint angles in radians")
    for value in result:
        finite(value, "Joint angle")
    return result


@dataclass(frozen=True)
class ArmObservation:
    q_rad: tuple[float, ...]
    captured_monotonic_s: float
    source: str  # measured or simulated; never interchangeable
    acquisition_start_s: float | None = None
    acquisition_end_s: float | None = None
    raw_positions: dict | None = None
    health_raw: dict | None = None

    def __post_init__(self):
        object.__setattr__(self, "q_rad", joints(self.q_rad))
        finite(self.captured_monotonic_s, "Observation time")
        if self.source not in ("measured", "simulated"):
            raise ValueError("Unknown observation source")
        if (self.acquisition_start_s is None) != (self.acquisition_end_s is None):
            raise ValueError("Both acquisition interval endpoints are required")
        if self.acquisition_start_s is not None:
            start = finite(self.acquisition_start_s, "Acquisition start")
            end = finite(self.acquisition_end_s, "Acquisition end")
            if not start <= self.captured_monotonic_s <= end:
                raise ValueError("Observation timestamp must lie inside acquisition interval")


@dataclass(frozen=True)
class MotionFrame:
    schema_version: ClassVar[int] = 1
    sequence: int
    issued_monotonic_s: float
    left_command: float
    right_command: float
    arms_rad: dict[str, tuple[float, ...]]

    def __post_init__(self):
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("Sequence must be a nonnegative integer")
        finite(self.issued_monotonic_s, "Command time")
        for value in (self.left_command, self.right_command):
            if abs(finite(value, "Command")) > COMMAND_CAP:
                raise ValueError("Command exceeds configured cap")
        if not isinstance(self.arms_rad, dict) or not self.arms_rad:
            raise ValueError("Arm roles are required")
        object.__setattr__(self, "arms_rad", {role: joints(q) for role, q in self.arms_rad.items()})


class CartAdapter(Protocol):
    simulated: bool
    connected: bool

    def connect(self) -> None: ...
    def set_speed(self, left: float, right: float) -> str: ...
    def stop(self) -> str: ...
    def disconnect(self) -> None: ...


class ArmAdapter(Protocol):
    simulated: bool
    connected: bool

    def connect(self) -> None: ...
    def read(self) -> ArmObservation: ...
    def validate(self, q_rad: tuple[float, ...]) -> None: ...
    def command(self, q_rad: tuple[float, ...]) -> dict: ...
    def hold(self, observation: ArmObservation) -> None: ...
    def disconnect(self) -> None: ...
