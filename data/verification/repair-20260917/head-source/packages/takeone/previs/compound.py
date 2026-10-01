"""Continuous compound ground routes in the subject's radial/tangent basis."""

import math

import numpy as np

ROUTES = {"spiral", "s_curve", "arc_push", "pass_by", "three_beat"}


def points(route, radial, radius, distance, sweep):
    radial = np.asarray(radial)
    tangent = np.array([-radial[1], radial[0]])
    u = np.linspace(0.0, 1.0, 97)
    if route == "spiral":
        r = radius + distance * (1 - u)
        x, y = r * np.cos(sweep * u), r * np.sin(sweep * u)
    elif route in ("s_curve", "pass_by"):
        # A broad S keeps curvature reversal well beyond the 2.2 s wire slew.
        x = radius + (0.45 * np.sin(math.tau * u) if route == "s_curve" else np.zeros_like(u))
        y = distance * (u - 0.5)
    else:
        # Arc joins a cubic with matching tangent, then finishes radially inward.
        # Its control polygon stays outside the subject's stand-off circle.
        angle = sweep
        arc = np.column_stack(
            (
                (radius + distance) * np.cos(angle * u[:49] * 2),
                (radius + distance) * np.sin(angle * u[:49] * 2),
            )
        )
        direction = np.array([math.cos(angle), math.sin(angle)])
        sideways = np.array([-direction[1], direction[0]])
        a = arc[-1]
        d = direction * radius + sideways * distance
        b, c = a + sideways * distance * 0.6, d + direction * distance * 0.6
        curve = [
            (1 - v) ** 3 * a + 3 * (1 - v) ** 2 * v * b + 3 * (1 - v) * v * v * c + v**3 * d
            for v in np.linspace(0, 1, 49)[1:]
        ]
        local = np.vstack((arc, curve))
        x, y = local[:, 0], local[:, 1]
    return (x[:, None] * radial + y[:, None] * tangent).tolist()
