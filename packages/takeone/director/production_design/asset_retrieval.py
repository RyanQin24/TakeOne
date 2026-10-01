"""Semantic retrieval across the complete installed local 3D asset catalog."""

from __future__ import annotations

import re
from collections import Counter

from takeone.asset_library.catalog import AssetCatalog
from takeone.paths import WORKSPACE

from .contracts import AssetRequirement

CATEGORY_TERMS = {
    "architecture": {"wall", "door", "doorway", "window", "floor", "stairs", "arch", "bridge", "paneling"},
    "surface": {"desk", "table", "counter", "bar", "workbench", "plinth", "cabinet"},
    "seating": {"chair", "stool", "bench", "sofa", "lounge", "ottoman"},
    "lighting": {"lamp", "light", "lantern", "torch", "campfire"},
    "vegetation": {"tree", "plant", "bush", "grass", "flower", "cactus", "moss"},
    "technology": {
        "computer",
        "screen",
        "monitor",
        "laptop",
        "keyboard",
        "mouse",
        "television",
        "radio",
        "speaker",
    },
    "storage": {"shelf", "bookcase", "cabinet", "drawer", "rack"},
    "path": {"path", "ground", "bridge", "stairs", "floor", "road"},
    "landscape": {"rock", "stone", "cliff", "river", "waterfall", "log", "stump"},
    "food": {"food", "apple", "bread", "bowl", "cup", "burger", "fruit", "vegetable", "cake"},
    "product": {"bottle", "box", "package", "can", "jar", "carton"},
    "decor": {"rug", "pillow", "books", "mirror", "statue", "sign", "plant"},
}

QUERY_EXPANSIONS = {
    "workspace": {"desk", "table", "computer", "screen", "chair", "lamp", "shelf"},
    "workstation": {"desk", "computer", "screen", "keyboard", "chair"},
    "hacker": {"desk", "computer", "screen", "laptop", "chair", "lamp"},
    "office": {"desk", "chair", "computer", "shelf", "lamp"},
    "forest": {"tree", "plant", "bush", "rock", "path"},
    "outdoor": {"tree", "plant", "rock", "path"},
    "camp": {"campfire", "tent", "log", "rock"},
    "lounge": {"sofa", "chair", "table", "lamp", "plant"},
    "kitchen": {"kitchen", "table", "chair", "cabinet", "lamp"},
    "foreground": {"plant", "screen", "chair", "shelf", "rock"},
    "practical": {"lamp", "light"},
    "display": {"table", "cabinet", "shelf", "plinth"},
    "entrance": {"door", "doorway", "arch"},
}


def _tokens(value):
    return set(re.findall(r"[a-z0-9]+", str(value).lower()))


def inferred_categories(asset):
    text = " ".join([asset.get("name", ""), asset.get("pack_id", ""), *asset.get("tags", [])]).lower()
    tokens = _tokens(text)
    result = []
    for category, terms in CATEGORY_TERMS.items():
        if terms & tokens or any(term in text for term in terms if len(term) > 4):
            result.append(category)
    if asset.get("kind") == "character":
        result.append("character")
    return tuple(sorted(set(result)))


def expanded_query_terms(query):
    requested = _tokens(query)
    expanded = set(requested)
    for term in requested:
        expanded.update(QUERY_EXPANSIONS.get(term, ()))
    return requested, expanded


def _dimension_penalty(asset, requirement):
    dims = asset.get("dimensions_m")
    if not dims:
        return 0.0, False
    limits = (requirement.max_width_m, requirement.max_depth_m, requirement.max_height_m)
    penalty = 0.0
    for observed, maximum in zip(dims, limits):
        if maximum is not None and observed > maximum:
            penalty += 30.0 * (observed - maximum) / maximum
    return penalty, True


def rank_asset(asset, requirement):
    query = requirement.query
    requested, expanded = expanded_query_terms(query)
    ordered = re.findall(r"[a-z0-9]+", query.lower())
    name = asset.get("name", "").lower()
    name_tokens = _tokens(name)
    metadata_tokens = _tokens(" ".join(asset.get("tags", [])) + " " + asset.get("pack_id", ""))
    categories = set(inferred_categories(asset))
    score = 0.0
    score += 9.0 * len(requested & name_tokens)
    score += 4.0 * len(expanded & name_tokens)
    score += 2.0 * len(expanded & metadata_tokens)
    for index, term in enumerate(ordered[:4]):
        if term in name_tokens:
            score += max(0.0, 6.0 - 1.5 * index)
        if name.strip() == term:
            score += max(8.0, 22.0 - 3.0 * index)
    if query.lower().strip() and query.lower().strip() in name:
        score += 12.0
    if requirement.categories:
        matched_categories = categories & set(requirement.categories)
        score += 10.0 * len(matched_categories)
        if not matched_categories:
            score -= 12.0
    penalty, dimensions_known = _dimension_penalty(asset, requirement)
    score -= penalty
    if not requested:
        score += 1.0
    return score, categories, dimensions_known


def _procedural_assets():
    from takeone.director.scenes import OBJECTS

    records = []
    for asset_id, (name, dimensions) in OBJECTS.items():
        records.append(
            {
                "asset_id": asset_id,
                "name": name,
                "pack_id": "takeone-procedural",
                "kind": "prop",
                "tags": ["procedural", *_tokens(name)],
                "dimensions_m": list(dimensions),
                "sha256": f"procedural-v1:{asset_id}",
            }
        )
    return records


def _all_assets(catalog):
    return [*catalog.all(), *_procedural_assets()]


def search_assets(requirement, *, catalog=None, limit=8):
    if not isinstance(requirement, AssetRequirement):
        requirement = AssetRequirement.parse(requirement)
    if not 1 <= limit <= 30:
        raise ValueError("Production-design retrieval limit must be 1 to 30")
    catalog = catalog or AssetCatalog.from_project(WORKSPACE)
    ranked = []
    for asset in _all_assets(catalog):
        if asset.get("kind") != "prop":
            continue
        score, categories, dimensions_known = rank_asset(asset, requirement)
        if score <= 0:
            continue
        ranked.append(
            (
                -score,
                asset["asset_id"],
                {
                    "asset_id": asset["asset_id"],
                    "name": asset["name"],
                    "pack_id": asset["pack_id"],
                    "kind": asset["kind"],
                    "tags": list(asset.get("tags", [])),
                    "categories": sorted(categories),
                    "dimensions_m": asset.get("dimensions_m"),
                    "dimensions_known": dimensions_known,
                    "score": round(score, 4),
                    "sha256": asset["sha256"],
                },
            )
        )
    ranked.sort(key=lambda row: row[:2])
    return [item for _, _, item in ranked[:limit]]


def fulfill_requirements(requirements, *, catalog=None, limit=8):
    catalog = catalog or AssetCatalog.from_project(WORKSPACE)
    used = Counter()
    selections = []
    for requirement in requirements:
        candidates = search_assets(requirement, catalog=catalog, limit=limit)
        if not candidates and requirement.required:
            raise ValueError(
                f"No installed asset matches required production-design role {requirement.role_id!r}"
            )
        selected = None
        if candidates:
            # Prefer a good unused source, but allow repeated chairs/trees when
            # one asset is clearly the best semantic fit.
            selected = min(
                candidates,
                key=lambda item: (used[item["asset_id"]] * 3.0 - item["score"], item["asset_id"]),
            )
            used[selected["asset_id"]] += 1
        selections.append(
            {
                "role": requirement.wire(),
                "selected": selected,
                "candidates": candidates,
            }
        )
    return selections


def catalog_summary(*, catalog=None):
    catalog = catalog or AssetCatalog.from_project(WORKSPACE)
    packs = Counter()
    kinds = Counter()
    categories = Counter()
    dimensions = Counter()
    for asset in catalog.all():
        packs[asset.get("pack_id", "unknown")] += 1
        kinds[asset.get("kind", "unknown")] += 1
        for category in inferred_categories(asset):
            categories[category] += 1
        dimensions["known" if asset.get("dimensions_m") else "unknown"] += 1
    procedural = _procedural_assets()
    return {
        "schema_version": 1,
        "installed_count": len(catalog),
        "procedural_count": len(procedural),
        "searchable_count": len(catalog) + len(procedural),
        "packs": dict(sorted(packs.items())),
        "kinds": dict(sorted(kinds.items())),
        "categories": dict(sorted(categories.items())),
        "dimensions": dict(sorted(dimensions.items())),
    }


def search_request(value, *, catalog=None):
    if not isinstance(value, dict):
        raise ValueError("Asset search request must be an object")
    allowed = {"query", "categories", "limit", "max_width_m", "max_depth_m", "max_height_m"}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"Unknown asset search fields: {sorted(unknown)}")
    requirement = AssetRequirement.parse(
        {
            "role_id": "search",
            "query": value.get("query", ""),
            "purpose": "Interactive production-design asset search",
            "categories": value.get("categories", []),
            "required": False,
            **{key: value[key] for key in ("max_width_m", "max_depth_m", "max_height_m") if key in value},
        }
    )
    limit = value.get("limit", 12)
    if type(limit) is not int:
        raise ValueError("Asset search limit must be an integer")
    results = search_assets(requirement, catalog=catalog, limit=limit)
    return {
        "schema_version": 1,
        "query": requirement.query,
        "categories": list(requirement.categories),
        "results": results,
        "total_returned": len(results),
    }
