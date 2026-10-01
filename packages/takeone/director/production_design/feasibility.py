"""Scene-layout constraints derived from TakeOne's actual compiled shot geometry.

This module does no device IO. It uses the same deterministic preview/FK stack as
Shot Studio so production design reserves space for the camera system it will
actually rehearse, rather than for an invented omnidirectional robot.
"""

from __future__ import annotations

import math

from .contracts import RouteConstraint


def _sample(points, maximum=16):
    """Keep endpoints and evenly distributed interior points, preserving order."""
    if len(points) <= maximum:
        return points
    indices = sorted({round(i * (len(points) - 1) / (maximum - 1)) for i in range(maximum)})
    return [points[index] for index in indices]


def _dedupe(points, epsilon=0.025):
    result = []
    for point in points:
        value = [float(point[0]), float(point[1])]
        if not result or math.dist(value, result[-1]) >= epsilon:
            result.append(value)
    return result


def _placed(stage, point):
    from takeone.previs.sequence import place

    return place(stage, float(point[0]), float(point[1]))


def derive_scene_routes(document, scene_id, *, maximum_routes=8):
    """Reserve actor/cart corridors from shots that already compile.

    Exact arm geometry remains a later verification step. The cart corridor uses
    a conservative radius so generated dressing does not sit immediately beside
    the moving mobile manipulator.
    """
    from takeone.director.studio import shot_settings
    from takeone.previs.cache import compile_preview
    from takeone.previs.sequence import stage_for

    marks = {item["mark_id"]: item for item in document.get("marks", [])}
    scene = next((item for item in document.get("scenes", []) if item["scene_id"] == scene_id), None)
    if scene is None:
        raise ValueError("Unknown scene for production-design feasibility")

    candidates = []
    for shot_index, shot in enumerate(scene.get("shots", [])):
        try:
            settings, _ = shot_settings(shot)
            preview = compile_preview(settings)
        except (ValueError, KeyError, TypeError):
            continue
        mark = marks.get(shot.get("mark_id"), {})
        stage = stage_for(mark, preview)
        # Modern Director scenes express movement channels directly in scene
        # coordinates after placement on the mark.
        if scene.get("space_id"):
            stage["heading_rad"] = 0.0
        filmed = [
            frame
            for frame in preview.get("frames", [])
            if frame["time_s"] >= preview.get("orbit_start_s", 0.0) - 1e-8
        ]
        if len(filmed) < 2:
            continue
        cart = _dedupe([_placed(stage, frame["q"][:2]) for frame in filmed])
        if len(cart) >= 2 and math.dist(cart[0], cart[-1]) >= 0.08:
            candidates.append(
                (
                    math.dist(cart[0], cart[-1]),
                    RouteConstraint(
                        route_id=f"cart-{shot_index + 1}",
                        points_m=tuple(tuple(point) for point in _sample(cart)),
                        clearance_m=0.72,
                    ),
                )
            )
        actor = _dedupe(
            [_placed(stage, frame.get("actor", {}).get("position_m", [0.0, 0.0])[:2]) for frame in filmed]
        )
        if len(actor) >= 2 and math.dist(actor[0], actor[-1]) >= 0.08:
            candidates.append(
                (
                    math.dist(actor[0], actor[-1]),
                    RouteConstraint(
                        route_id=f"actor-{shot_index + 1}",
                        points_m=tuple(tuple(point) for point in _sample(actor)),
                        clearance_m=0.45,
                    ),
                )
            )

    # Protect the most spatially significant paths first if a large scene has
    # more shots than the production-design route contract intentionally allows.
    candidates.sort(key=lambda item: (-item[0], item[1].route_id))
    chosen = [route for _, route in candidates[:maximum_routes]]
    chosen.sort(key=lambda route: route.route_id)
    return tuple(chosen)


def verify_scene_against_shots(document, scene_id, candidate_scene):
    """Run the existing full-rig sampled clearance screen against a solved world."""
    from takeone.director.studio import shot_settings
    from takeone.previs.cache import compile_preview
    from takeone.previs.scene_checks import obstacles, sampled_scene_clearance
    from takeone.previs.sequence import stage_for

    marks = {item["mark_id"]: item for item in document.get("marks", [])}
    source_scene = next(
        (item for item in document.get("scenes", []) if item["scene_id"] == scene_id),
        None,
    )
    if source_scene is None:
        raise ValueError("Unknown scene for production-design verification")
    scene = {
        **candidate_scene,
        "scene_id": source_scene["scene_id"],
        "title": source_scene["title"],
        "location": source_scene["location"],
        "cast": source_scene.get("cast", []),
    }
    results = []
    for shot in source_scene.get("shots", []):
        try:
            settings, _ = shot_settings(shot)
            preview = compile_preview(settings)
            mark = marks.get(shot.get("mark_id"), {})
            stage = stage_for(mark, preview)
            if source_scene.get("space_id"):
                stage["heading_rad"] = 0.0
            blocked = obstacles(scene, preview, stage, shot["shot_id"])
            clearance = sampled_scene_clearance(shot, settings, scene, mark, preview)
            status = (
                "needs_revision"
                if blocked or clearance["status"] == "potential_intersection"
                else "sampled_clear"
            )
            results.append(
                {
                    "shot_id": shot["shot_id"],
                    "status": status,
                    "cart_obstructions": [item.wire() for item in blocked],
                    "full_rig_clearance": clearance,
                }
            )
        except (ValueError, KeyError, TypeError, ImportError) as error:
            results.append(
                {
                    "shot_id": shot.get("shot_id"),
                    "status": "unverified",
                    "reason": str(error)[:240],
                }
            )
    checked = [item for item in results if item["status"] != "unverified"]
    return {
        "source": "TakeOne compiled preview + conservative sampled full-rig envelopes",
        "status": "needs_revision"
        if any(item["status"] == "needs_revision" for item in checked)
        else "sampled_clear"
        if checked
        else "unverified",
        "shots": results,
        "verified_shot_count": len(checked),
        "unverified_shot_count": len(results) - len(checked),
        "physical_qualification": False,
        "scope": (
            "Offline nominal FK and bounding-envelope evidence only. "
            "No continuous swept-volume, cable, dynamics, measured-set or human-safety qualification."
        ),
    }
