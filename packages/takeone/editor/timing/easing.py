"""Easing shapes and their exact antiderivatives.

A speed curve interpolates a *rate* between two control points. Rendering needs the integral
of that rate, so every easing here provides both the shape `E(x)` on 0..1 and its
antiderivative `A(x)` with `A(0) = 0`. Analytic antiderivatives keep the source-duration
identity exact rather than approximately true.
"""

from ..errors import ValidationError

NAMES = ("linear", "ease_in", "ease_out", "ease_in_out", "hold", "bezier")


def _linear(x):
    return x


def _linear_area(x):
    return 0.5 * x * x


def _ease_in(x):
    return x * x


def _ease_in_area(x):
    return x * x * x / 3.0


def _ease_out(x):
    return 2.0 * x - x * x


def _ease_out_area(x):
    return x * x - x * x * x / 3.0


def _ease_in_out(x):
    return x * x * (3.0 - 2.0 * x)


def _ease_in_out_area(x):
    return x * x * x - 0.5 * x * x * x * x


def _hold(x):
    return 1.0 if x >= 1.0 else 0.0


def _hold_area(x):
    return 0.0


SHAPES = {
    "linear": (_linear, _linear_area),
    "ease_in": (_ease_in, _ease_in_area),
    "ease_out": (_ease_out, _ease_out_area),
    "ease_in_out": (_ease_in_out, _ease_in_out_area),
    "hold": (_hold, _hold_area),
}

_SIMPSON_INTERVALS = 64


def _bezier_y(x, control):
    """One-dimensional cubic Bezier easing y(x) with control points (x1, y1, x2, y2).

    Solves for the parameter with bisection. The curve is monotonic in x for control
    abscissae inside 0..1, which `validate_bezier` enforces.
    """
    x1, y1, x2, y2 = control
    low, high = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (low + high)
        inverse = 1.0 - mid
        value = 3.0 * inverse * inverse * mid * x1 + 3.0 * inverse * mid * mid * x2 + mid * mid * mid
        if value < x:
            low = mid
        else:
            high = mid
    t = 0.5 * (low + high)
    inverse = 1.0 - t
    return 3.0 * inverse * inverse * t * y1 + 3.0 * inverse * t * t * y2 + t * t * t


def _bezier_area(x, control):
    """Composite Simpson integration of the Bezier shape on 0..x."""
    if x <= 0.0:
        return 0.0
    steps = _SIMPSON_INTERVALS
    h = x / steps
    total = _bezier_y(0.0, control) + _bezier_y(x, control)
    for index in range(1, steps):
        weight = 4.0 if index % 2 else 2.0
        total += weight * _bezier_y(index * h, control)
    return total * h / 3.0


def validate_bezier(control):
    if control is None:
        raise ValidationError("Bezier easing requires four control values")
    if len(control) != 4:
        raise ValidationError("Bezier easing takes exactly x1, y1, x2, y2")
    values = tuple(float(value) for value in control)
    if not 0.0 <= values[0] <= 1.0 or not 0.0 <= values[2] <= 1.0:
        raise ValidationError("Bezier control abscissae must lie in 0..1 to stay monotonic")
    return values


def shape(name, x, control=None):
    """Eased fraction at normalised position `x` in 0..1."""
    x = min(1.0, max(0.0, float(x)))
    if name == "bezier":
        return _bezier_y(x, validate_bezier(control))
    if name not in SHAPES:
        raise ValidationError(f"Unknown easing '{name}'")
    return SHAPES[name][0](x)


def area(name, x, control=None):
    """Integral of the eased fraction from 0 to `x`, with A(0) = 0."""
    x = min(1.0, max(0.0, float(x)))
    if name == "bezier":
        return _bezier_area(x, validate_bezier(control))
    if name not in SHAPES:
        raise ValidationError(f"Unknown easing '{name}'")
    return SHAPES[name][1](x)
