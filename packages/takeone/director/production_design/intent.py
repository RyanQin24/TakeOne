"""Local semantic draft used for offline proof and UI fallback.

The AI Director may later emit the same contracts directly. This module does not
contain complete scene templates or object coordinates.
"""

from __future__ import annotations

import re

from .contracts import ProductionDesignRequest

ROLE_RULES = (
    (
        "entrance",
        {"enter", "entrance", "arrival", "arrive", "door", "doorway"},
        "doorway architecture",
        ["architecture"],
        "Defines an entrance or threshold.",
    ),
    (
        "surface",
        {"desk", "workspace", "workbench", "table", "hacker", "office", "product", "kitchen", "lab"},
        "desk workbench table surface",
        ["surface"],
        "Primary action or discovery surface.",
    ),
    (
        "technology",
        {"hacker", "robot", "prototype", "computer", "technology", "tech", "monitor", "screen", "laptop"},
        "computer screen laptop technology",
        ["technology"],
        "Technical story detail.",
    ),
    (
        "practical",
        {"night", "lamp", "light", "warm", "workspace", "campfire"},
        "floor lamp practical light",
        ["lighting"],
        "Motivated practical lighting.",
    ),
    (
        "seating",
        {"dialogue", "conversation", "chair", "office", "lounge", "cafe", "sit"},
        "chair seating",
        ["seating"],
        "Supports human blocking without defining the shot.",
    ),
    (
        "storage",
        {"workspace", "office", "hacker", "lab", "shelf", "storage"},
        "shelf bookcase storage",
        ["storage"],
        "Background structure and depth.",
    ),
    (
        "foreground",
        {"foreground", "reveal", "discover", "cinematic", "depth"},
        "small potted plant foreground",
        ["vegetation", "decor"],
        "Foreground depth or reveal element.",
    ),
    (
        "vegetation",
        {"forest", "nature", "outdoor", "garden", "woods"},
        "tree plant vegetation nature",
        ["vegetation"],
        "Environmental vegetation.",
    ),
    (
        "landscape",
        {"forest", "nature", "outdoor", "rock", "river", "camp"},
        "rock stone landscape",
        ["landscape"],
        "Environmental depth and terrain detail.",
    ),
    (
        "path",
        {"walk", "arrival", "forest", "outdoor", "path", "entrance"},
        "ground path",
        ["path"],
        "Readable route through the environment.",
    ),
    (
        "product",
        {"product", "bottle", "package"},
        "product bottle",
        ["product"],
        "Primary object or insert target.",
    ),
    (
        "story_object",
        {"artifact", "relic", "old"},
        "statue stone box",
        ["decor", "landscape"],
        "Discoverable story object with visual character.",
    ),
)


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _need(role_id, query, categories, purpose, required=False, **limits):
    return {
        "role_id": role_id,
        "query": query,
        "categories": categories,
        "purpose": purpose,
        "required": required,
        **limits,
    }


def draft_request(brief, *, seed=1, mode="pure_previs"):
    if not isinstance(brief, str) or not brief.strip() or len(brief) > 4000:
        raise ValueError("World brief must be 1 to 4000 characters")
    tokens = _tokens(brief)
    lower = brief.lower()
    requirements = []
    matched = set()
    for role_id, triggers, query, categories, purpose in ROLE_RULES:
        if tokens & triggers:
            matched.add(role_id)
            if role_id == "practical" and "campfire" in tokens:
                query, categories = "campfire", ["lighting"]
            limits = {"max_width_m": 1.0} if role_id in ("foreground", "story_object") else {}
            requirements.append(_need(role_id, query, categories, purpose, **limits))
    if not requirements:
        requirements.extend(
            [
                _need("surface", "table work surface", ["surface"], "Neutral action surface."),
                _need("practical", "floor lamp practical light", ["lighting"], "Lighting motivation."),
                _need(
                    "foreground",
                    "small plant foreground",
                    ["vegetation", "decor"],
                    "Optional foreground depth.",
                    max_width_m=1.0,
                ),
            ]
        )
        matched.update({"surface", "practical", "foreground"})

    relations = []
    if {"technology", "surface"} <= matched:
        relations.append({"kind": "on_top_of", "source": "technology", "target": "surface", "weight": 1.0})
    if {"product", "surface"} <= matched:
        relations.append({"kind": "on_top_of", "source": "product", "target": "surface", "weight": 1.0})
    if {"practical", "surface"} <= matched:
        relations.append(
            {"kind": "near", "source": "practical", "target": "surface", "maximum_m": 1.8, "weight": 1.0}
        )
    if {"seating", "surface"} <= matched:
        relations.extend(
            [
                {"kind": "near", "source": "seating", "target": "surface", "maximum_m": 1.4, "weight": 1.0},
                {"kind": "facing_toward", "source": "seating", "target": "surface", "weight": 1.0},
            ]
        )
    if "storage" in matched:
        relations.append({"kind": "against_wall", "source": "storage", "weight": 1.0})
    if "entrance" in matched:
        relations.append({"kind": "against_wall", "source": "entrance", "weight": 1.2})
    anchor = next(
        (
            role
            for role in (
                "surface",
                "product",
                "story_object",
                "technology",
                "seating",
                "practical",
                "vegetation",
                "landscape",
                "path",
                "entrance",
            )
            if role in matched
        ),
        sorted(matched)[0],
    )
    if "foreground" in matched and anchor != "foreground":
        relations.append(
            {
                "kind": "foreground_of",
                "source": "foreground",
                "target": anchor,
                "minimum_m": 0.8,
                "weight": 1.2,
            }
        )
    if "vegetation" in matched and anchor != "vegetation":
        relations.append(
            {
                "kind": "background_of",
                "source": "vegetation",
                "target": anchor,
                "minimum_m": 1.0,
                "weight": 0.8,
            }
        )

    camera_needs = []
    for phrase in ("foreground reveal", "side track", "tracking", "parallax", "hero push", "close up"):
        if phrase in lower:
            camera_needs.append(phrase.replace(" ", "_"))
    if "cinematic" in tokens and "foreground_reveal" not in camera_needs:
        camera_needs.append("foreground_depth")
    story_functions = [
        name
        for name, words in (
            ("arrival", {"arrive", "arrival", "enter", "entrance"}),
            ("discovery", {"discover", "notice", "find", "reveal"}),
            ("interaction", {"test", "use", "touch", "talk", "conversation"}),
            ("reaction", {"realize", "reaction", "excited", "surprised"}),
        )
        if tokens & words
    ]
    routes = []
    if tokens & {
        "walk",
        "arrive",
        "arrival",
        "enter",
        "enters",
        "entrance",
        "follow",
        "track",
        "tracking",
        "side",
    }:
        routes.append(
            {
                "route_id": "actor",
                "points_m": [[0.0, -3.0], [0.0, 1.5]],
                "clearance_m": 0.45,
            }
        )
    if tokens & {"track", "tracking", "follow", "side"}:
        routes.append(
            {
                "route_id": "cart",
                "points_m": [[-1.0, -3.0], [-1.0, 1.5]],
                "clearance_m": 0.65,
            }
        )
    request = {
        "intent": {
            "environment": brief.strip()[:200],
            "mood": "night"
            if "night" in tokens
            else "dusk"
            if tokens & {"dusk", "sunset"}
            else "day exterior"
            if tokens & {"forest", "outdoor", "outside"}
            else "interior",
            "story_functions": story_functions,
            "visual_needs": [item["purpose"] for item in requirements],
            "camera_needs": camera_needs,
            "actor_needs": ["clear actor route"]
            if any(route["route_id"] == "actor" for route in routes)
            else [],
            "mode": mode,
        },
        "requirements": requirements,
        "relations": relations,
        "routes": routes,
        "bounds_m": [8.0, 8.0],
        "seed": seed,
    }
    return ProductionDesignRequest.parse(request)


def draft_wire(brief, *, seed=1, mode="pure_previs"):
    return draft_request(brief, seed=seed, mode=mode).wire()
