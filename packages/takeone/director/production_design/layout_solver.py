"""Deterministic bounded layout solver for semantic production-design graphs."""

from __future__ import annotations

import hashlib
import math
import random

from .scene_graph import stable_digest

SOLVER_VERSION = 1
HARD = 1_000_000.0


def _half(node):
    return node["size_m"][0] / 2, node["size_m"][1] / 2


def _distance_point_segment(point, a, b):
    px, py = point
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 1e-12:
        return math.hypot(px - ax, py - ay)
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


def _route_clearance(node, position, route):
    radius = math.hypot(node["size_m"][0], node["size_m"][1]) / 2
    return (
        min(_distance_point_segment(position, a, b) for a, b in zip(route["points_m"], route["points_m"][1:]))
        - radius
    )


def _overlap(a, pa, b, pb, margin=0.05):
    ahx, ahy = _half(a)
    bhx, bhy = _half(b)
    return abs(pa[0] - pb[0]) < ahx + bhx + margin and abs(pa[1] - pb[1]) < ahy + bhy + margin


def _inside(node, position, bounds):
    hx, hy = _half(node)
    width, depth = bounds
    return (
        -width / 2 + hx <= position[0] <= width / 2 - hx and -depth / 2 + hy <= position[1] <= depth / 2 - hy
    )


def _relation_penalty(relation, source_pos, target_pos, source, target, bounds):
    kind = relation["kind"]
    weight = relation.get("weight", 1.0)
    sx, sy = source_pos
    tx, ty = target_pos if target_pos is not None else (0.0, 0.0)
    distance = math.hypot(sx - tx, sy - ty)
    minimum = relation.get("minimum_m")
    maximum = relation.get("maximum_m")
    penalty = 0.0
    if kind == "near":
        limit = maximum if maximum is not None else 1.5
        penalty = max(0.0, distance - limit) ** 2
    elif kind == "far_from":
        limit = minimum if minimum is not None else 2.0
        penalty = max(0.0, limit - distance) ** 2
    elif kind == "left_of":
        penalty = max(0.0, sx - tx + (minimum or 0.3)) ** 2
    elif kind == "right_of":
        penalty = max(0.0, tx - sx + (minimum or 0.3)) ** 2
    elif kind in ("in_front_of", "foreground_of"):
        gap = minimum if minimum is not None else (0.7 if kind == "foreground_of" else 0.3)
        penalty = max(0.0, sy - ty + gap) ** 2
    elif kind in ("behind", "background_of"):
        gap = minimum if minimum is not None else (0.7 if kind == "background_of" else 0.3)
        penalty = max(0.0, ty - sy + gap) ** 2
    elif kind == "aligned_with":
        penalty = min(abs(sx - tx), abs(sy - ty)) ** 2
    elif kind == "against_wall":
        hx, hy = _half(source)
        width, depth = bounds
        wall_distance = min(
            abs((sx - hx) + width / 2),
            abs((sx + hx) - width / 2),
            abs((sy - hy) + depth / 2),
            abs((sy + hy) - depth / 2),
        )
        penalty = wall_distance**2
    elif kind in ("camera_targetable", "visible_from", "motivates_light", "facing", "facing_toward"):
        penalty = 0.0
    elif kind in ("must_clear", "route_clear_of"):
        limit = minimum if minimum is not None else 0.6
        penalty = max(0.0, limit - distance) ** 2
    elif kind == "occludes_initially":
        # Detailed screen-space proof belongs to shot review. At layout time
        # preserve the intended depth ordering and moderate lateral separation.
        penalty = max(0.0, sy - ty + 0.6) ** 2 + max(0.0, abs(sx - tx) - 1.2) ** 2
    elif kind in ("on_top_of", "under", "between"):
        penalty = 0.0
    return weight * penalty


def _tie(seed, node_id, x, y):
    value = f"{seed}:{node_id}:{x:.3f}:{y:.3f}".encode()
    return int(hashlib.sha256(value).hexdigest()[:12], 16)


def _grid(bounds, step=0.5):
    width, depth = bounds
    xs = []
    x = -width / 2 + step
    while x <= width / 2 - step + 1e-9:
        xs.append(round(x, 6))
        x += step
    ys = []
    y = -depth / 2 + step
    while y <= depth / 2 - step + 1e-9:
        ys.append(round(y, 6))
        y += step
    return [(x, y) for y in ys for x in xs]


def _dependency_order(nodes, relations):
    by_id = {node["node_id"]: node for node in nodes}
    # Place semantic targets before their dependents so relation costs are
    # available when each source chooses its position. Cycles fall back
    # deterministically below instead of inventing coordinates.
    edges = [
        (relation["target"], relation["source"])
        for relation in relations
        if relation.get("target") in by_id and relation["source"] in by_id
    ]
    result = []
    pending = set(by_id)
    while pending:
        ready = sorted(
            node_id
            for node_id in pending
            if all(source != node_id or target not in pending for target, source in edges)
        )
        if not ready:
            ready = [sorted(pending)[0]]
        for node_id in ready:
            result.append(by_id[node_id])
            pending.remove(node_id)
    return result


def _score_candidate(node, position, placed, graph):
    if not _inside(node, position, graph["bounds_m"]):
        return HARD
    score = 0.0
    for other_id, other in placed.items():
        if _overlap(node, position, other["node"], other["position"]):
            stacked = any(
                relation["kind"] in ("on_top_of", "under")
                and relation["source"] == node["node_id"]
                and relation.get("target") == other_id
                for relation in graph["relations"]
            )
            if not stacked:
                score += HARD
    for route in graph["routes"]:
        clearance = _route_clearance(node, position, route)
        if clearance < route["clearance_m"]:
            score += HARD + 1000 * (route["clearance_m"] - clearance)
    for relation in graph["relations"]:
        if relation["source"] != node["node_id"]:
            continue
        target_id = relation.get("target")
        target = placed.get(target_id) if target_id else None
        if target_id and target is None:
            continue
        score += 100.0 * _relation_penalty(
            relation,
            position,
            target["position"] if target else None,
            node,
            target["node"] if target else None,
            graph["bounds_m"],
        )
    # Mild compactness keeps unconstrained dressing from flying to corners.
    score += 0.02 * (position[0] ** 2 + position[1] ** 2)
    return score


def _stacked_position(node, relation, placed):
    target = placed.get(relation.get("target"))
    if target is None:
        return None
    base = target["node"]
    x, y = target["position"]
    if relation["kind"] == "on_top_of":
        z = target["z"] + base["size_m"][2] / 2 + node["size_m"][2] / 2
    else:
        z = max(node["size_m"][2] / 2, target["z"] - base["size_m"][2] / 2 - node["size_m"][2] / 2)
    return [x, y, z]


def _yaw_for(node_id, positions, relations, node=None):
    if node is not None and "fixed_yaw_rad" in node:
        return float(node["fixed_yaw_rad"])
    for relation in relations:
        if relation["source"] != node_id or relation["kind"] not in ("facing_toward", "facing"):
            continue
        target = positions.get(relation.get("target"))
        source = positions.get(node_id)
        if source and target:
            return math.atan2(target[1] - source[1], target[0] - source[0]) - math.pi / 2
    return 0.0


def _candidates_for(node, bounds, seed):
    candidates = _grid(bounds)
    hx, hy = _half(node)
    width, depth = bounds
    xs = sorted({point[0] for point in candidates} | {-width / 2 + hx, width / 2 - hx})
    ys = sorted({point[1] for point in candidates} | {-depth / 2 + hy, depth / 2 - hy})
    candidates.extend((x, -depth / 2 + hy) for x in xs)
    candidates.extend((x, depth / 2 - hy) for x in xs)
    candidates.extend((-width / 2 + hx, y) for y in ys)
    candidates.extend((width / 2 - hx, y) for y in ys)
    candidates = list(dict.fromkeys((round(x, 6), round(y, 6)) for x, y in candidates))
    random.Random(seed).shuffle(candidates)
    return candidates


def solve_layout(graph):
    bounds = tuple(graph["bounds_m"])
    placed = {}
    fixed = sorted(
        (node for node in graph["nodes"] if "fixed_position_m" in node),
        key=lambda node: node["node_id"],
    )
    generated = [node for node in graph["nodes"] if "fixed_position_m" not in node]
    generated_ids = {node["node_id"] for node in generated}
    generated_relations = [
        relation
        for relation in graph["relations"]
        if relation["source"] in generated_ids
        and (relation.get("target") is None or relation.get("target") in generated_ids)
    ]
    order = [*fixed, *_dependency_order(generated, generated_relations)]
    for node in order:
        if "fixed_position_m" in node:
            x, y, z = node["fixed_position_m"]
            position = [float(x), float(y)]
            score = _score_candidate(node, position, placed, graph)
            placed[node["node_id"]] = {
                "node": node,
                "position": position,
                "z": float(z),
                "placement_score": float(score),
            }
            continue
        stack_relation = next(
            (
                relation
                for relation in graph["relations"]
                if relation["source"] == node["node_id"] and relation["kind"] in ("on_top_of", "under")
            ),
            None,
        )
        stacked = _stacked_position(node, stack_relation, placed) if stack_relation else None
        if stacked is not None:
            position = [stacked[0], stacked[1]]
            score = _score_candidate(node, position, placed, graph)
            z = stacked[2]
        else:
            candidates = _candidates_for(node, bounds, graph["seed"])
            scored = [
                (
                    _score_candidate(node, point, placed, graph),
                    _tie(graph["seed"], node["node_id"], *point),
                    point,
                )
                for point in candidates
            ]
            score, _, position = min(scored, key=lambda row: (row[0], row[1]))
            z = node["size_m"][2] / 2
        placed[node["node_id"]] = {
            "node": node,
            "position": [float(position[0]), float(position[1])],
            "z": float(z),
            "placement_score": float(score),
        }

    positions = {node_id: item["position"] for node_id, item in placed.items()}
    objects = []
    for index, node in enumerate(order):
        item = placed[node["node_id"]]
        object_id = node.get("object_id") or ("pd-" + node["node_id"])[:40]
        objects.append(
            {
                "object_id": object_id,
                "asset_id": node["asset_id"],
                "availability": node["availability"],
                "label": node["name"],
                "position_m": [*item["position"], item["z"]],
                "size_m": [float(v) for v in node["size_m"]],
                "yaw_rad": _yaw_for(node["node_id"], positions, graph["relations"], node),
                "production_role": node["node_id"],
            }
        )

    evidence = evaluate_layout(graph, placed)
    scene = {
        "space_id": "pd-" + graph["graph_digest"][:16],
        "atmosphere": _atmosphere(graph["intent"]),
        "location_notes": (
            f"AI production-design simulation for {graph['intent']['environment']}. "
            "Imported models and authored dimensions are visualization evidence, not a measured venue."
        ),
        "objects": objects,
        "cast": [],
    }
    layout = {
        "schema_version": 1,
        "solver_version": SOLVER_VERSION,
        "graph_digest": graph["graph_digest"],
        "scene": scene,
        "evidence": evidence,
    }
    layout["layout_digest"] = stable_digest(layout)
    return layout


def _atmosphere(intent):
    text = (intent.get("environment", "") + " " + intent.get("mood", "")).lower()
    if "night" in text:
        return (
            "exterior_night"
            if any(word in text for word in ("outside", "outdoor", "forest", "exterior"))
            else "interior_warm"
        )
    if "dusk" in text or "sunset" in text or "golden" in text:
        return "exterior_dusk"
    if any(word in text for word in ("outside", "outdoor", "forest", "exterior")):
        return "exterior_day"
    if "cool" in text:
        return "interior_cool"
    if "warm" in text:
        return "interior_warm"
    return "interior_day"


def evaluate_layout(graph, placed):
    overlaps = []
    ids = sorted(placed)
    for index, a_id in enumerate(ids):
        for b_id in ids[index + 1 :]:
            a, b = placed[a_id], placed[b_id]
            if _overlap(a["node"], a["position"], b["node"], b["position"]):
                # Stacked relations are intentional vertical overlaps.
                stacked = any(
                    relation["kind"] in ("on_top_of", "under")
                    and {relation["source"], relation.get("target")} == {a_id, b_id}
                    for relation in graph["relations"]
                )
                if not stacked:
                    overlaps.append([a_id, b_id])
    route_evidence = []
    for route in graph["routes"]:
        minimum = math.inf
        culprit = None
        for node_id, item in placed.items():
            clearance = _route_clearance(item["node"], item["position"], route)
            if clearance < minimum:
                minimum, culprit = clearance, node_id
        route_evidence.append(
            {
                "route_id": route["route_id"],
                "required_clearance_m": route["clearance_m"],
                "minimum_clearance_m": None if math.isinf(minimum) else round(minimum, 4),
                "closest_node": culprit,
                "passes": math.isinf(minimum) or minimum >= route["clearance_m"],
            }
        )

    relation_evidence = []
    for relation in graph["relations"]:
        source = placed.get(relation["source"])
        target = placed.get(relation.get("target")) if relation.get("target") else None
        if source is None:
            continue
        error = _relation_penalty(
            relation,
            source["position"],
            target["position"] if target else None,
            source["node"],
            target["node"] if target else None,
            graph["bounds_m"],
        )
        relation_evidence.append(
            {
                "kind": relation["kind"],
                "source": relation["source"],
                "target": relation.get("target"),
                "error": round(error, 6),
                "passes": error <= 1e-4
                or relation["kind"] in ("visible_from", "camera_targetable", "motivates_light"),
            }
        )
    hard_placement = [node_id for node_id, item in placed.items() if item["placement_score"] >= HARD]
    valid = (
        not overlaps
        and not hard_placement
        and all(item["passes"] for item in route_evidence)
        and all(item["passes"] for item in relation_evidence)
    )
    return {
        "status": "solver_verified" if valid else "needs_revision",
        "valid": valid,
        "object_overlaps": overlaps,
        "hard_placement_nodes": hard_placement,
        "routes": route_evidence,
        "relations": relation_evidence,
        "evidence_boundary": "offline geometric approximation; not physical safety qualification",
    }
