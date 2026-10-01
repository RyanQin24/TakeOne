"""Small deterministic 2D helpers in metres. No numpy: this is core TakeOne code.

Everything here is plain planar geometry on the site's local metre frame. It is
nominal clearance screening, the same class of evidence as
``previs.scene_checks`` — useful for rejecting a staging idea, never a physical
safety qualification.
"""

from __future__ import annotations

import math


def polygon_area(ring):
    total = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def centroid(ring):
    area = polygon_area(ring)
    if abs(area) < 1e-9:
        return (
            sum(p[0] for p in ring) / len(ring),
            sum(p[1] for p in ring) / len(ring),
        )
    cx = cy = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % len(ring)]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return (cx / (6 * area), cy / (6 * area))


def point_in_polygon(point, ring):
    x, y = point
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i - 1) % n]
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
    return inside


def point_segment_distance(point, a, b):
    px, py = point
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    if length < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def point_polygon_distance(point, ring):
    """Signed distance: negative inside the ring, positive outside."""
    best = min(point_segment_distance(point, ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring)))
    return -best if point_in_polygon(point, ring) else best


def segments_intersect(a, b, c, d):
    def orient(p, q, r):
        value = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
        return 0 if abs(value) < 1e-12 else (1 if value > 0 else 2)

    def on_segment(p, q, r):
        return min(p[0], r[0]) - 1e-12 <= q[0] <= max(p[0], r[0]) + 1e-12 and (
            min(p[1], r[1]) - 1e-12 <= q[1] <= max(p[1], r[1]) + 1e-12
        )

    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and on_segment(a, c, b))
        or (o2 == 0 and on_segment(a, d, b))
        or (o3 == 0 and on_segment(c, a, d))
        or (o4 == 0 and on_segment(c, b, d))
    )


def segment_polygon_distance(a, b, ring):
    """Signed distance from a segment to a ring: negative if it crosses or is inside."""
    for i in range(len(ring)):
        if segments_intersect(a, b, ring[i], ring[(i + 1) % len(ring)]):
            return -0.0
    if point_in_polygon(a, ring) or point_in_polygon(b, ring):
        return -min(abs(point_polygon_distance(a, ring)), abs(point_polygon_distance(b, ring)))
    # For two disjoint segments the closest pair always involves an endpoint of
    # one of them, so four point-to-segment tests per edge are exact. Testing
    # only the ring's vertices against the segment is not: a short segment
    # beside a long wall would measure the distance to the wall's far corner.
    best = math.inf
    for i in range(len(ring)):
        c, d = ring[i], ring[(i + 1) % len(ring)]
        best = min(
            best,
            point_segment_distance(c, a, b),
            point_segment_distance(d, a, b),
            point_segment_distance(a, c, d),
            point_segment_distance(b, c, d),
        )
    return best


def buffer_polyline(points, width_m):
    """A rectangle strip per segment, merged as a list of rings.

    Deliberately simple: a strip per segment plus a square cap at each joint.
    Overlapping rings are fine — every consumer asks "is this point inside any
    region", never "what is the union area".
    """
    half = max(0.2, width_m / 2.0)
    rings = []
    for i in range(len(points) - 1):
        (ax, ay), (bx, by) = points[i], points[i + 1]
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        nx, ny = -dy / length * half, dx / length * half
        rings.append(
            (
                (ax + nx, ay + ny),
                (bx + nx, by + ny),
                (bx - nx, by - ny),
                (ax - nx, ay - ny),
            )
        )
    return rings


def circle_ring(center, radius_m, segments=24):
    cx, cy = center
    return tuple(
        (
            cx + radius_m * math.cos(2 * math.pi * i / segments),
            cy + radius_m * math.sin(2 * math.pi * i / segments),
        )
        for i in range(segments)
    )


def bounds(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def clearance_to_rings(point, rings):
    """Smallest signed distance from a point to any ring. inf when there are none."""
    best = math.inf
    for ring in rings:
        best = min(best, point_polygon_distance(point, ring))
    return best


def segment_clearance_to_rings(a, b, rings):
    best = math.inf
    for ring in rings:
        best = min(best, segment_polygon_distance(a, b, ring))
    return best
