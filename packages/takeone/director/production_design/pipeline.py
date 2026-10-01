"""End-to-end offline production-design pipeline.

The planner may supply a structured ProductionDesignRequest directly. A small
local semantic draft exists for offline UI proof; it is not presented as AI.
"""

from __future__ import annotations

from takeone.asset_library.catalog import AssetCatalog
from takeone.paths import WORKSPACE

from .asset_retrieval import catalog_summary, search_request
from .contracts import ProductionDesignRequest
from .intent import draft_request
from .layout_solver import solve_layout
from .scene_graph import build_scene_graph, fixed_role_id, graph_summary


def design_world(value, *, catalog=None):
    if not isinstance(value, dict):
        raise ValueError("World design request must be an object")
    catalog = catalog or AssetCatalog.from_project(WORKSPACE)
    allowed = {"brief", "mode", "seed", "request", "fixed_objects"}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"Unknown world design fields: {sorted(unknown)}")
    fixed_objects = value.get("fixed_objects", [])
    if not isinstance(fixed_objects, list) or len(fixed_objects) > 30:
        raise ValueError("fixed_objects must be a list of at most 30 canonical scene objects")
    external_roles = tuple(fixed_role_id(item.get("object_id", "")) for item in fixed_objects)
    if "request" in value:
        if "brief" in value:
            raise ValueError("Choose either a semantic request or a local draft brief")
        request = ProductionDesignRequest.parse(value["request"], external_roles=external_roles)
        source = "structured_intent"
    else:
        request = draft_request(
            value.get("brief", ""),
            seed=value.get("seed", 1),
            mode=value.get("mode", "pure_previs"),
        )
        source = "local_semantic_draft"
    graph = build_scene_graph(request, catalog=catalog, fixed_objects=fixed_objects)
    layout = solve_layout(graph)
    return {
        "schema_version": 1,
        "source": source,
        "request": request.wire(),
        "graph": graph,
        "graph_summary": graph_summary(graph),
        "layout": layout,
        "catalog": {
            "installed_count": len(catalog),
            "asset_catalog_scope": "complete_local_catalog",
        },
        "evidence_boundary": (
            "Scene layout is offline simulation. Imported assets are visual references; "
            "solver clearance is not physical safety qualification."
        ),
    }


def production_design_status(*, catalog=None):
    catalog = catalog or AssetCatalog.from_project(WORKSPACE)
    return {
        "schema_version": 1,
        "available": True,
        "engine": "semantic_graph_v1",
        "layout_solver": "deterministic_bounded_v1",
        "catalog": catalog_summary(catalog=catalog),
        "scene_modes": ["physical_reconstruction", "proposed_dressing", "pure_previs"],
        "generation_order": [
            "scene_intent",
            "asset_requirements",
            "full_catalog_retrieval",
            "semantic_graph",
            "deterministic_layout",
            "geometric_evidence",
        ],
        "ai_integration": "structured_intent contract ready; local draft is deterministic and not claimed as AI",
    }


def search_world_assets(value, *, catalog=None):
    return search_request(value, catalog=catalog or AssetCatalog.from_project(WORKSPACE))
