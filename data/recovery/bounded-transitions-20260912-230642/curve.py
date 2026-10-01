"""Finite joint polynomials shared by planning, preview and physical dispatch.

Coefficients use ascending powers of local time in seconds, in model radians.
Evaluation requires no simulator or numerical library in a device worker.
"""

import math
from bisect import bisect_right
from dataclasses import dataclass

from takeone.config import finite


def dispatch_times(duration, period):
    if not math.isfinite(period) or not 0 < period <= 0.1:
        raise ValueError("Invalid arm command period")
    count = math.ceil(duration / period)
    if count > 20000:
        raise ValueError("Finite command stream exceeds 20,001 samples")
    return tuple(i * period for i in range(count)) + (duration,)


@dataclass(frozen=True)
class JointCurve:
    knots_s: tuple
    coefficients: tuple

    def __post_init__(self):
        knots = tuple(finite(t, "Curve knot") for t in self.knots_s)
        if not 2 <= len(knots) <= 2002 or knots[0] != 0 or any(a >= b for a, b in zip(knots, knots[1:])):
            raise ValueError("Joint curve needs increasing knots starting at zero")
        if not 0 < knots[-1] <= 120 or len(self.coefficients) != len(knots) - 1:
            raise ValueError("Invalid finite joint curve duration/segments")
        coefficients = tuple(tuple(tuple(row) for row in segment) for segment in self.coefficients)
        for segment in coefficients:
            if len(segment) != 6 or any(len(row) != 10 for row in segment):
                raise ValueError("Each joint segment needs six powers and all ten joints")
            for row in segment:
                for value in row:
                    finite(value, "Joint coefficient")
        object.__setattr__(self, "knots_s", knots)
        object.__setattr__(self, "coefficients", coefficients)
        for i in range(1, len(knots) - 1):
            for derivative in range(3):
                left = self._segment(i - 1, knots[i] - knots[i - 1], derivative)
                right = self._segment(i, 0.0, derivative)
                if any(abs(a - b) > 1e-7 for a, b in zip(left, right)):
                    raise ValueError("Joint curve must be continuous in position, velocity and acceleration")

    @property
    def duration_s(self):
        return self.knots_s[-1]

    def _segment(self, index, local_s, derivative):
        result = [0.0] * 10
        for power in range(5, derivative - 1, -1):
            multiplier = 1
            for factor in range(power - derivative + 1, power + 1):
                multiplier *= factor
            result = [a * local_s + multiplier * b for a, b in zip(result, self.coefficients[index][power])]
        return tuple(result)

    def at(self, elapsed_s, derivative=0):
        if type(derivative) is not int or not 0 <= derivative <= 3:
            raise ValueError("Only position, velocity, acceleration and jerk are supported")
        elapsed_s = finite(elapsed_s, "Curve time")
        if derivative and not 0 <= elapsed_s <= self.duration_s:
            return (0.0,) * 10
        t = min(self.duration_s, max(0.0, elapsed_s))
        index = min(len(self.coefficients) - 1, max(0, bisect_right(self.knots_s, t) - 1))
        return self._segment(index, t - self.knots_s[index], derivative)

    def to_dict(self):
        return dict(
            knots_s=list(self.knots_s), coefficients=[[list(row) for row in s] for s in self.coefficients]
        )

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"knots_s", "coefficients"}:
            raise ValueError("Expected the complete joint polynomial")
        return cls(value["knots_s"], value["coefficients"])

    def extrema(self, derivative=0):
        """Analytic candidates at segment boundaries and real stationary roots."""
        import numpy as np

        minima, maxima = [float("inf")] * 10, [float("-inf")] * 10
        for i, segment in enumerate(self.coefficients):
            duration = self.knots_s[i + 1] - self.knots_s[i]
            for j in range(10):
                coefficients = np.polynomial.polynomial.polyder([row[j] for row in segment], derivative)
                stationary = np.polynomial.polynomial.polyder(coefficients)
                roots = np.polynomial.polynomial.polyroots(stationary)
                times = [0.0, duration] + [
                    float(r.real) for r in roots if abs(r.imag) < 1e-9 and 0 < r.real < duration
                ]
                values = [float(np.polynomial.polynomial.polyval(t, coefficients)) for t in times]
                minima[j], maxima[j] = min(minima[j], *values), max(maxima[j], *values)
        return tuple(minima), tuple(maxima)

    def rest_boundaries(self, tolerance=1e-8):
        return all(abs(v) <= tolerance for t in (0.0, self.duration_s) for d in (1, 2) for v in self.at(t, d))

    def with_transitions(self, duration_s, initial_rad=None):
        """Explicit new revision: stationary-cart arm approach and departure.

        This constructs a proposed path only. Its excursion, derivatives and
        clearance still need validation and review before any physical command.
        """
        duration = finite(duration_s, "Transition duration")
        if not 0 < duration <= 20 or self.duration_s + 2 * duration > 120:
            raise ValueError("Transitions must be positive, at most 20 seconds, within a 120-second plan")
        start = tuple(initial_rad) if initial_rad is not None else self.at(0)
        if len(start) != 10:
            raise ValueError("Approach needs all ten initial model joint angles")
        zeros = (0.0,) * 10
        before = quintic(start, zeros, zeros, self.at(0), self.at(0, 1), self.at(0, 2), duration)
        after = quintic(
            self.at(self.duration_s),
            self.at(self.duration_s, 1),
            self.at(self.duration_s, 2),
            self.at(self.duration_s),
            zeros,
            zeros,
            duration,
        )
        return JointCurve(
            (0.0, *(t + duration for t in self.knots_s), self.duration_s + 2 * duration),
            (before, *self.coefficients, after),
        )


def quintic(p0, v0, a0, p1, v1, a1, duration):
    """Hermite boundary constraints, ascending powers of local seconds."""
    rows = [[] for _ in range(6)]
    for x0, u0, w0, x1, u1, w1 in zip(p0, v0, a0, p1, v1, a1):
        delta = x1 - x0
        values = (
            x0,
            u0,
            w0 / 2,
            (20 * delta - (12 * u0 + 8 * u1) * duration - (3 * w0 - w1) * duration**2) / (2 * duration**3),
            (-30 * delta + (16 * u0 + 14 * u1) * duration + (3 * w0 - 2 * w1) * duration**2)
            / (2 * duration**4),
            (12 * delta - 6 * (u0 + u1) * duration - (w0 - w1) * duration**2) / (2 * duration**5),
        )
        for row, value in zip(rows, values):
            row.append(value)
    return tuple(tuple(row) for row in rows)
