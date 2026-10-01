"""Installed visual assets in the existing Director contract; no network or hardware."""

import copy
from pathlib import Path

from takeone.asset_library.catalog import AssetCatalog
from takeone.paths import WORKSPACE

from .contracts import encode

GUIDANCE = Path(__file__).with_name("scene-dressing") / "SKILL.md"


def installed_catalog():
    return AssetCatalog.from_project(WORKSPACE)


def asset_choice(asset):
    # Explicit authored dimensions remain authoritative for both render and checks.
    # An unknown source scale is not presented as a measured real-world dimension.
    return {
        "id": asset["asset_id"],
        "name": asset["name"] + " · " + asset["pack_id"],
        "default_size_m": asset.get("dimensions_m") or [1.0, 1.0, 1.0],
        "kind": asset["kind"],
        "provenance": "Imported visualization; set dimensions and confirm physical availability",
    }


def catalog_choices(procedural):
    legacy = [dict(id=k, name=v[0], default_size_m=v[1]) for k, v in procedural.items()]
    # UI data only. Provider requests use the bounded, brief-specific shortlist below.
    return legacy + [asset_choice(asset) for asset in installed_catalog().all()]


def validate_assets(document, procedural):
    requested = {item["asset_id"] for scene in document["scenes"] for item in scene.get("objects", [])}
    imported = requested - set(procedural)
    if not imported:
        return  # A legacy production does not depend on an optional asset installation.
    catalog = installed_catalog()
    for asset_id in sorted(imported):
        if not asset_id.startswith("lib:"):
            raise ValueError(f"Unknown scene asset: {asset_id}. Select an installed model.")
        catalog.get(asset_id)


def provider_payload(payload, kind):
    """Bound model context, not the user's library or saved production vocabulary."""
    if kind not in ("creative_plan", "creative_repair") or "movement_catalog" not in payload:
        return payload
    result = copy.deepcopy(payload)
    factor_template_defaults(result["movement_catalog"])
    if result.get("redesign_shot_id"):
        existing = result["scene"]
        allowed = {o["asset_id"] for o in existing.get("objects", [])}
        scene_catalog = result["movement_catalog"]["scene_catalog"]
        scene_catalog["objects"] = [o for o in scene_catalog["objects"] if o["id"] in allowed]
        scene_catalog["asset_selection"] = (
            "This is a single-shot revision. Use only existing scene objects; do not add or replace assets."
        )
        result["marks"] = [m for m in result.get("marks", []) if m.get("scene_id") == existing["scene_id"]]
        return result
    brief = result.get("brief", {})
    query = " ".join(str(brief.get(key, "")) for key in ("title", "objective"))
    catalog = installed_catalog()
    candidates = catalog.search(query, limit=32, kind="prop")
    if not candidates:
        candidates = catalog.search("", limit=16, kind="prop")
    scene = result["movement_catalog"]["scene_catalog"]
    legacy = [item for item in scene["objects"] if not item["id"].startswith("lib:")]
    scene["objects"] = legacy + [asset_choice(asset) for asset in candidates]
    scene["installed_count"] = len(catalog)
    scene["asset_selection"] = (
        "Use only these advertised IDs. A digital model does not establish a physical prop or performer. "
        "Missing items are questions or proposed dressing, not invented IDs. Dimensions are authored metres."
    )
    return result


def factor_template_defaults(catalog):
    """Factor identical defaults only in the provider copy; keep every resolved value."""
    templates = catalog.get("templates", [])
    if not templates:
        return
    common = dict(templates[0]["defaults"])
    for template in templates[1:]:
        values = template["defaults"]
        common = {
            key: value
            for key, value in common.items()
            if key in values and encode(values[key]) == encode(value)
        }
    catalog["shared_template_defaults"] = catalog.get("shared_template_defaults", {}) | common
    for template in templates:
        template["defaults"] = {
            key: value for key, value in template["defaults"].items() if key not in common
        }
    catalog["defaults_rule"] = (
        "Each template inherits shared_template_defaults, then overrides them with its own defaults. "
        "All parameter names, bounds, movement IDs and default values are unchanged."
    )


def director_guidance():
    # Generation only: the existing live-voice persona has a separate fixed budget.
    return GUIDANCE.read_text(encoding="utf-8")
