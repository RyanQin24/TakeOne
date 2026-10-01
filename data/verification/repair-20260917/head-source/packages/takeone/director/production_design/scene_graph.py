"""Semantic graph assembly. Graph nodes keep asset identity separate from placement."""

from __future__ import annotations

import hashlib
import json

from .asset_retrieval import fulfill_requirements, inferred_categories
from .contracts import ProductionDesignRequest

CATEGORY_DEFAULT_SIZE_M = {
    "architecture": [2.2, 0.24, 2.4],
    "surface": [1.5, 0.75, 0.78],
    "seating": [0.65, 0.65, 0.9],
    "lighting": [0.42, 0.42, 1.55],
    "vegetation": [0.75, 0.75, 1.45],
    "technology": [0.52, 0.24, 0.34],
    "storage": [1.25, 0.45, 1.75],
    "path": [2.0, 1.0, 0.08],
    "landscape": [1.0, 0.9, 0.85],
    "food": [0.22, 0.22, 0.22],
    "product": [0.28, 0.28, 0.42],
    "decor": [0.6, 0.6, 0.65],
}


def stable_digest(value):
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest()


def _authored_size(selection):
    asset = selection["selected"]
    if asset and asset.get("dimensions_m"):
        return [float(v) for v in asset["dimensions_m"]]
    categories = asset.get("categories", []) if asset else selection["role"]["categories"]
    for category in categories:
        if category in CATEGORY_DEFAULT_SIZE_M:
            return list(CATEGORY_DEFAULT_SIZE_M[category])
    return [1.0, 1.0, 1.0]


def fixed_role_id(object_id):
    return ("fixed_" + "".join(ch for ch in str(object_id) if ch.isalnum() or ch in "_-"))[:40]


def _fixed_node(item, catalog):
    if not isinstance(item, dict):
        raise ValueError("Fixed production-design objects must be scene object dictionaries")
    required = {"object_id", "asset_id", "position_m", "size_m", "yaw_rad"}
    if not required.issubset(item):
        raise ValueError("Fixed production-design object is missing canonical scene fields")
    if str(item["asset_id"]).startswith("lib:"):
        asset = catalog.get(item["asset_id"])
        categories = list(inferred_categories(asset))
        name = item.get("label") or asset["name"]
        pack = asset["pack_id"]
    else:
        from takeone.director.scenes import OBJECTS

        if item["asset_id"] not in OBJECTS:
            raise ValueError(f"Unknown fixed scene asset: {item['asset_id']}")
        name = item.get("label") or OBJECTS[item["asset_id"]][0]
        categories = ["anchor"]
        pack = "takeone-procedural"
    role = fixed_role_id(item["object_id"])
    return {
        "node_id": role,
        "object_id": item["object_id"],
        "asset_id": item["asset_id"],
        "name": name,
        "pack_id": pack,
        "categories": categories or ["anchor"],
        "purpose": "Existing story/camera target preserved as a fixed world anchor.",
        "required": True,
        "size_m": [float(v) for v in item["size_m"]],
        "dimensions_source": "existing_scene_authored",
        "availability": item.get("availability", "unconfirmed"),
        "fixed_position_m": [float(v) for v in item["position_m"]],
        "fixed_yaw_rad": float(item.get("yaw_rad", 0.0)),
        "selection_evidence": {"source": "existing_scene_anchor"},
    }


def build_scene_graph(request, *, catalog=None, fixed_objects=()):
    if not isinstance(request, ProductionDesignRequest):
        request = ProductionDesignRequest.parse(request)
    from takeone.asset_library.catalog import AssetCatalog
    from takeone.paths import WORKSPACE

    catalog = catalog or AssetCatalog.from_project(WORKSPACE)
    selections = fulfill_requirements(request.requirements, catalog=catalog)
    nodes = [_fixed_node(item, catalog) for item in fixed_objects]
    for item in selections:
        selected = item["selected"]
        if selected is None:
            continue
        role = item["role"]
        nodes.append(
            {
                "node_id": role["role_id"],
                "asset_id": selected["asset_id"],
                "name": selected["name"],
                "pack_id": selected["pack_id"],
                "categories": selected["categories"],
                "purpose": role["purpose"],
                "required": role["required"],
                "size_m": _authored_size(item),
                "dimensions_source": "catalog" if selected.get("dimensions_known") else "authored_category_proxy",
                "availability": "unconfirmed" if request.intent.mode == "physical_reconstruction" else
                                "proposed" if request.intent.mode == "proposed_dressing" else "virtual_only",
                "selection_evidence": {
                    "query": role["query"],
                    "candidates": [candidate["asset_id"] for candidate in item["candidates"]],
                    "selected": selected["asset_id"],
                },
            }
        )
    node_ids = {node["node_id"] for node in nodes}
    relations = [
        relation.wire()
        for relation in request.relations
        if relation.source in node_ids and (relation.target is None or relation.target in node_ids)
    ]
    graph = {
        "schema_version": 1,
        "intent": request.intent.wire(),
        "bounds_m": list(request.bounds_m),
        "seed": request.seed,
        "nodes": nodes,
        "relations": relations,
        "routes": [route.wire() for route in request.routes],
        "coordinate_frame": "scene-local X/Y floor metres, Z up; canonical camera side is negative Y",
    }
    graph["graph_digest"] = stable_digest(graph)
    return graph


def graph_summary(graph):
    return {
        "graph_digest": graph["graph_digest"],
        "node_count": len(graph["nodes"]),
        "relation_count": len(graph["relations"]),
        "route_count": len(graph["routes"]),
        "asset_ids": [node["asset_id"] for node in graph["nodes"]],
        "packs": sorted({node["pack_id"] for node in graph["nodes"]}),
        "categories": sorted({category for node in graph["nodes"] for category in node["categories"]}),
    }
