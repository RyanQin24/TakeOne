"""Wheel feedforward identified outside the command loop; no hardware dependencies.

The provisional model is an explicit operating mode, never a fallback for invalid
measurements. A table models signed wheel travel versus transmitted command for
one verified wiring convention. It cannot establish traction or close a pose loop.
"""

import math
from dataclasses import dataclass

from takeone.config import finite, read_json
from takeone.paths import CONFIGS
from takeone.protocol import COMMAND_CAP, MIN_COMMAND, uart_pair


@dataclass(frozen=True)
class WheelResponse:
    points: tuple[tuple[float, float], ...]

    def __post_init__(self):
        if not self.points:
            raise ValueError("A measured wheel table needs at least one point")
        for command, speed in self.points:
            finite(command, "Measured command")
            finite(speed, "Measured speed")
            if not MIN_COMMAND <= abs(command) <= COMMAND_CAP:
                raise ValueError("Measured moving commands must respect the motor limits")
            if float(uart_pair(command, 0).split(",")[0]) != command:
                raise ValueError("Measure the actual two-decimal wire command")
            if speed * command <= 0:
                raise ValueError("Verify wire polarity before fitting a signed wheel response")
        ordered = sorted(self.points)
        if list(self.points) != ordered or any(
            a[0] >= b[0] or a[1] >= b[1] for a, b in zip(ordered, ordered[1:])
        ):
            raise ValueError("Wheel response points must have strictly increasing commands and speeds")

    def interpolate(self, value, inverse=False):
        if value == 0:
            return 0.0
        pairs = [(s, c) if inverse else (c, s) for c, s in self.points if c * value > 0]
        if not pairs:
            raise ValueError("This wheel direction has no measured response; no symmetry fallback")
        for x, y in pairs:
            if math.isclose(value, x, abs_tol=1e-12, rel_tol=0):
                return y
        for (x0, y0), (x1, y1) in zip(pairs, pairs[1:]):
            if x0 < value < x1:
                return y0 + (value - x0) * (y1 - y0) / (x1 - x0)
        # A sub-minimum requested speed can only choose stop or the minimum
        # measured moving command. Do not invent a linear deadband response.
        if inverse and abs(value) < min(abs(x) for x, _ in pairs):
            speed, command = min(pairs, key=lambda point: abs(point[0]))
            return command if abs(speed - value) < abs(value) else 0.0
        raise ValueError("Requested command/speed is outside the measured wheel response; no extrapolation")


@dataclass(frozen=True)
class CartResponse:
    mode: str
    evidence: str
    minimum_speed_m_s: float
    wheels: tuple[WheelResponse, WheelResponse] | None = None

    @classmethod
    def from_config(cls, document, minimum_speed_m_s):
        if (
            not isinstance(document, dict)
            or set(document) != {"schema_version", "mode", "evidence", "wheels"}
            or type(document["schema_version"]) is not int
            or document["schema_version"] != 1
        ):
            raise ValueError("Expected cart response schema 1 with mode, evidence and wheels")
        if not isinstance(document["evidence"], str) or not document["evidence"].strip():
            raise ValueError("Cart response requires measurement evidence or explicit assumptions")
        if finite(minimum_speed_m_s, "Minimum speed") <= 0:
            raise ValueError("Minimum speed must be positive")
        wheels = document["wheels"]
        if not isinstance(wheels, dict) or set(wheels) != {"left", "right"}:
            raise ValueError("Wheel response requires named left and right wheels")
        if document["mode"] == "provisional_symmetric":
            if wheels != {"left": [], "right": []}:
                raise ValueError("Provisional mode cannot contain ignored measurements")
            tables = None
        elif document["mode"] == "measured_table":
            for rows in wheels.values():
                if not isinstance(rows, list) or not rows or len(rows) > 24:
                    raise ValueError("A wheel table needs 1 to 24 signed wire-command points")
                if any(not isinstance(row, dict) or set(row) != {"command", "speed_m_s"} for row in rows):
                    raise ValueError("Each wheel point needs command and speed_m_s")
            tables = tuple(
                WheelResponse(tuple((r["command"], r["speed_m_s"]) for r in wheels[side]))
                for side in ("left", "right")
            )
        else:
            raise ValueError("Unknown cart response mode; no implicit provisional fallback")
        return cls(document["mode"], document["evidence"], minimum_speed_m_s, tables)

    @classmethod
    def load(cls, minimum_speed_m_s):
        return cls.from_config(read_json(CONFIGS / "cart-response.json"), minimum_speed_m_s)

    def commands_for(self, speeds):
        if len(speeds) != 2:
            raise ValueError("Expected exactly left and right wheel speeds")
        speeds = tuple(finite(speed, "Wheel speed") for speed in speeds)
        if self.wheels is None:
            return tuple(speed * MIN_COMMAND / self.minimum_speed_m_s for speed in speeds)
        return tuple(wheel.interpolate(speed, inverse=True) for wheel, speed in zip(self.wheels, speeds))

    def speeds_for(self, commands):
        if len(commands) != 2:
            raise ValueError("Expected exactly left and right wire commands")
        commands = tuple(finite(command, "Wire command") for command in commands)
        if tuple(map(float, uart_pair(*commands).strip().split(","))) != commands:
            raise ValueError("Predict only the capped, two-decimal transmitted commands")
        if self.wheels is None:
            return tuple(
                0.0 if abs(command) < MIN_COMMAND - 1e-12 else command / MIN_COMMAND * self.minimum_speed_m_s
                for command in commands
            )
        return tuple(wheel.interpolate(command) for wheel, command in zip(self.wheels, commands))

    def describe(self):
        return dict(
            mode=self.mode,
            evidence=self.evidence,
            wheelOrder=["left", "right"],
            commandPolarity="Positive wheel speed toward powered front; physical wiring must be verified",
            compensation=self.wheels is not None,
            interpolation="within each measured direction only"
            if self.wheels
            else "assumed linear symmetric",
            feedbackAvailable=False,
            physicalStraightnessVerified=False,
        )
