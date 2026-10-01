"""Nominal staging intersections; these are not hardware collision qualification."""

import math

from .diagnostics import Diagnostic


def obstacles(scene, preview, stage, shot_id):
    found = []
    c, s = math.cos(stage["heading_rad"]), math.sin(stage["heading_rad"])
    for obj in scene.get("objects", []):
        w, d, h = obj["size_m"]
        if obj["position_m"][2] - h / 2 > 1.1:
            continue
        yaw = obj["yaw_rad"]
        cy, sy = math.cos(yaw), math.sin(yaw)
        rects = (
            [(-w * 0.44, 0, w * 0.12, d), (w * 0.44, 0, w * 0.12, d)]
            if obj["asset_id"] in ("doorway", "arch")
            else [(0, 0, w, d)]
        )
        if obj["asset_id"] == "tree":
            rects = [(0, 0, w * 0.35, d * 0.35)]
        for frame in preview["frames"]:
            x, y = frame["q"][:2]
            x, y = stage["origin_m"][0] + c * x - s * y, stage["origin_m"][1] + s * x + c * y
            dx, dy = x - obj["position_m"][0], y - obj["position_m"][1]
            x, y = cy * dx + sy * dy, -sy * dx + cy * dy
            if any(
                math.hypot(max(abs(x - rx) - rw / 2, 0), max(abs(y - ry) - rd / 2, 0)) < 0.55
                for rx, ry, rw, rd in rects
            ):
                found.append(
                    Diagnostic(
                        shot_id,
                        "scene_obstruction",
                        f"The nominal cart footprint intersects {obj['label'] or obj['object_id']}. Move the prop or revise the route.",
                        suggestion="This staging screen uses a 0.55 m cart radius; inspect arms and real clearances separately.",
                    )
                )
                break
    return found
