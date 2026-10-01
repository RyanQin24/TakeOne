"""Speed as a time-dependent rate function, and the exact time map it implies.

`rate` is source seconds consumed per timeline second. 1.0 is real time, 0.42 is slow
motion, 2.0 is double speed. A curve is a list of control points in *timeline* time
measured from the start of the clip; the easing on a point describes how the rate arrives
at that point from the previous one.

The single identity this module guarantees:

    integral of rate over the whole timeline span == the source span the clip consumes

Every other operation (frame-accurate trimming, beat alignment, audio synchronisation)
depends on that identity holding exactly, so it is computed analytically rather than by
sampling.
"""

from dataclasses import dataclass, replace
from typing import ClassVar

from ..contracts import choice, fields, number, seconds
from ..errors import ValidationError
from . import easing

MIN_RATE = 0.01
MAX_RATE = 20.0


@dataclass(frozen=True, slots=True)
class SpeedPoint:
    time_s: float
    rate: float
    easing: str = "linear"
    bezier: tuple[float, ...] | None = None

    def __post_init__(self):
        object.__setattr__(self, "time_s", seconds(self.time_s, "Speed point time"))
        object.__setattr__(self, "rate", number(self.rate, "Speed rate", MIN_RATE, MAX_RATE))
        choice(self.easing, "Speed easing", easing.NAMES)
        if self.easing == "bezier":
            object.__setattr__(self, "bezier", easing.validate_bezier(self.bezier))
        elif self.bezier is not None:
            raise ValidationError("Only bezier easing carries control values")

    def wire(self):
        document = {"time_s": self.time_s, "rate": self.rate, "easing": self.easing}
        if self.bezier is not None:
            document["bezier"] = list(self.bezier)
        return document

    @classmethod
    def parse(cls, value):
        data = dict(fields(value, ("time_s", "rate"), ("easing", "bezier")))
        if data.get("bezier") is not None:
            data["bezier"] = tuple(data["bezier"])
        return cls(**data)


@dataclass(frozen=True, slots=True)
class SpeedCurve:
    schema_version: ClassVar[int] = 1
    points: tuple[SpeedPoint, ...]

    def __post_init__(self):
        points = tuple(self.points)
        if len(points) < 2:
            raise ValidationError("A speed curve needs at least a start and an end point")
        if len(points) > 64:
            raise ValidationError("A speed curve is limited to 64 control points")
        if points[0].time_s != 0.0:
            raise ValidationError("A speed curve starts at the clip's first frame")
        for previous, current in zip(points, points[1:]):
            if current.time_s <= previous.time_s:
                raise ValidationError("Speed curve times must strictly increase")
        object.__setattr__(self, "points", points)

    # -- shape -------------------------------------------------------------

    @property
    def duration_s(self):
        """Timeline duration the curve describes."""
        return self.points[-1].time_s

    def rate_at(self, time_s):
        time_s = min(self.duration_s, max(0.0, float(time_s)))
        for previous, current in zip(self.points, self.points[1:]):
            if time_s <= current.time_s:
                span = current.time_s - previous.time_s
                fraction = 0.0 if span == 0.0 else (time_s - previous.time_s) / span
                eased = easing.shape(current.easing, fraction, current.bezier)
                return previous.rate + (current.rate - previous.rate) * eased
        return self.points[-1].rate

    def source_offset_at(self, time_s):
        """Source seconds consumed by timeline time `time_s`. Strictly increasing."""
        time_s = min(self.duration_s, max(0.0, float(time_s)))
        total = 0.0
        for previous, current in zip(self.points, self.points[1:]):
            span = current.time_s - previous.time_s
            if time_s >= current.time_s:
                total += span * (
                    previous.rate
                    + (current.rate - previous.rate) * easing.area(current.easing, 1.0, current.bezier)
                )
                continue
            if time_s <= previous.time_s:
                break
            fraction = (time_s - previous.time_s) / span
            partial = span * fraction * previous.rate + span * (current.rate - previous.rate) * easing.area(
                current.easing, fraction, current.bezier
            )
            # easing.area integrates over the normalised variable, so scale by the span once.
            total += partial
            break
        return total

    @property
    def source_duration_s(self):
        return self.source_offset_at(self.duration_s)

    def timeline_time_at(self, source_offset_s, tolerance_s=1e-9):
        """Inverse map. The rate is strictly positive, so the map is strictly increasing."""
        target = number(source_offset_s, "Source offset", 0.0, self.source_duration_s)
        low, high = 0.0, self.duration_s
        for _ in range(80):
            mid = 0.5 * (low + high)
            if self.source_offset_at(mid) < target:
                low = mid
            else:
                high = mid
            if high - low < tolerance_s:
                break
        return 0.5 * (low + high)

    # -- derivation --------------------------------------------------------

    def scaled_to(self, timeline_duration_s):
        """The same shape stretched to a different timeline duration."""
        target = seconds(timeline_duration_s, "Timeline duration", 1e-6)
        factor = target / self.duration_s
        return SpeedCurve(tuple(replace(point, time_s=point.time_s * factor) for point in self.points))

    def fitted_to_source(self, source_span_s):
        """The same rate shape, stretched so it consumes exactly `source_span_s` of source.

        A rate shape fixes the *ratio* of source to timeline time; the clip's source span
        fixes the absolute amount. Scaling timeline time by k scales the integral by k, so
        the required timeline duration follows in closed form.
        """
        span = seconds(source_span_s, "Source span", 1e-6)
        return self.scaled_to(self.duration_s * span / self.source_duration_s)

    def segments(self, tolerance=0.02, max_segments=96):
        """Split into spans of near-constant rate for a backend that retimes by segment.

        Returns `(start_s, end_s, rate)` triples whose rates reproduce the exact source
        span: the final rates are rescaled so the sum of `rate * span` equals
        `source_duration_s`, which is the identity the renderer depends on.
        """
        number(tolerance, "Segment tolerance", 1e-4, 1.0)
        cuts = [0.0]
        for previous, current in zip(self.points, self.points[1:]):
            if abs(current.rate - previous.rate) < 1e-12 and current.easing != "hold":
                cuts.append(current.time_s)
                continue
            steps = max(1, min(max_segments, int(abs(current.rate - previous.rate) / tolerance) + 1))
            span = current.time_s - previous.time_s
            for index in range(1, steps + 1):
                cuts.append(previous.time_s + span * index / steps)
        cuts = sorted(set(round(value, 9) for value in cuts))
        spans = []
        for start, end in zip(cuts, cuts[1:]):
            width = end - start
            if width <= 0.0:
                continue
            consumed = self.source_offset_at(end) - self.source_offset_at(start)
            spans.append((start, end, consumed / width))
        if not spans:
            raise ValidationError("A speed curve must produce at least one segment")
        return tuple(spans)

    # -- wire --------------------------------------------------------------

    def wire(self):
        return {"schema_version": 1, "points": [point.wire() for point in self.points]}

    @classmethod
    def parse(cls, value):
        data = fields(value, ("points",), ("schema_version",))
        if "schema_version" in data and data["schema_version"] != 1:
            raise ValidationError("Unsupported speed curve schema")
        if not isinstance(data["points"], list):
            raise ValidationError("Speed curve points must be a list")
        return cls(tuple(SpeedPoint.parse(item) for item in data["points"]))

    @classmethod
    def constant(cls, duration_s, rate=1.0):
        return cls((SpeedPoint(0.0, rate), SpeedPoint(seconds(duration_s, "Duration", 1e-6), rate)))

    @classmethod
    def ramp(cls, duration_s, slow_rate=0.42, hold_start_s=None, hold_end_s=None, shape="ease_in_out"):
        """The cinematic ramp: real time, decelerate, hold slow, accelerate back."""
        total = seconds(duration_s, "Duration", 4e-2)
        number(slow_rate, "Slow rate", MIN_RATE, 1.0)
        start = total * 0.25 if hold_start_s is None else seconds(hold_start_s, "Hold start")
        end = total * 0.65 if hold_end_s is None else seconds(hold_end_s, "Hold end")
        if not 0.0 < start < end < total:
            raise ValidationError("A ramp needs 0 < hold start < hold end < duration")
        return cls(
            (
                SpeedPoint(0.0, 1.0),
                SpeedPoint(start, slow_rate, shape),
                SpeedPoint(end, slow_rate, "linear"),
                SpeedPoint(total, 1.0, shape),
            )
        )
