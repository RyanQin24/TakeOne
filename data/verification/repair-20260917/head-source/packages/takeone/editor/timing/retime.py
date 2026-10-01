"""Turning a speed curve into something a frame-based backend can execute.

Two ways exist to retime with FFmpeg: cut the clip into many constant-rate pieces and
concatenate them, or hand `setpts` a single expression for the time map. The second is one
filter instead of dozens, so it is what this module produces — but a `setpts` expression is
piecewise linear, so the knots are chosen adaptively until the linear interpolant is within
a quarter of a frame of the true map everywhere. The approximation is then bounded and
measurable rather than assumed.
"""

from ..errors import ValidationError

MAX_KNOTS = 96


def time_map_knots(curve, frame_s, tolerance_frames=0.25, max_knots=MAX_KNOTS):
    """Knots `(source_s, timeline_s)` whose linear interpolant tracks the true time map.

    Returns the knots and the measured worst-case deviation in seconds.
    """
    if frame_s <= 0.0:
        raise ValidationError("Frame duration must be positive")
    tolerance = frame_s * tolerance_frames
    count = 2
    while True:
        knots = _sample(curve, count)
        deviation = _deviation(curve, knots)
        if deviation <= tolerance or count >= max_knots:
            return knots, deviation
        count = min(max_knots, count * 2)


def _sample(curve, count):
    step = curve.duration_s / (count - 1)
    return tuple((curve.source_offset_at(index * step), index * step) for index in range(count))


def _deviation(curve, knots):
    """Worst distance, in timeline seconds, between the interpolant and the true map."""
    worst = 0.0
    probes = 8
    for (source_a, time_a), (source_b, time_b) in zip(knots, knots[1:]):
        if source_b <= source_a:
            continue
        for index in range(1, probes):
            fraction = index / probes
            source = source_a + (source_b - source_a) * fraction
            linear = time_a + (time_b - time_a) * (source - source_a) / (source_b - source_a)
            true = curve.timeline_time_at(source)
            worst = max(worst, abs(linear - true))
    return worst


def setpts_expression(knots):
    """A nested `if` chain evaluating the timeline time for an input timestamp `T`."""
    if len(knots) < 2:
        raise ValidationError("A time map needs at least two knots")
    pieces = []
    for (source_a, time_a), (source_b, time_b) in zip(knots, knots[1:]):
        span = source_b - source_a
        slope = 0.0 if span <= 0.0 else (time_b - time_a) / span
        pieces.append((source_b, f"({time_a:.9f}+({slope:.9f})*(T-{source_a:.9f}))"))
    expression = pieces[-1][1]
    for boundary, piece in reversed(pieces[:-1]):
        expression = f"if(lt(T,{boundary:.9f}),{piece},{expression})"
    return expression
