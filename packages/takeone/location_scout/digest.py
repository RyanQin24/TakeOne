"""The scene digest: what the planner is allowed to see.

Requirement one of this feature is that the language model never becomes a 3D
engine. It receives counts, lengths, clearances, depths and names — a few
kilobytes of structured filmmaking affordances — and never a mesh, a polygon
ring or a tile. Building the digest here, in one function, is what makes that
checkable: ``tests/test_location_planning.py`` asserts no coordinate ring can
appear in a request body.
"""

from __future__ import annotations

MAX_STORY_CHARS = 1200
MAX_CANDIDATES = 8


def _clip(value, limit):
    return str(value or "")[:limit]


def location_digest(candidates, *, query, story=None, rig=None):
    """Digest for "which of these places suits the story?"."""
    return {
        "question": "location_assessment",
        "search": {
            "kind": query.get("kind"),
            "text": _clip(query.get("text"), 300),
            "radius_m": query.get("radius_m"),
        },
        "candidates": [
            {
                "candidate_id": candidate["candidate_id"],
                "name": _clip(candidate["name"], 160),
                "type": _clip(candidate.get("primary_type") or ", ".join(candidate.get("types", [])), 120),
                "summary": _clip(candidate.get("summary"), 400),
                "straight_line_m": candidate.get("straight_line_m"),
                "distance_basis": "straight_line_not_walking_route",
            }
            for candidate in candidates[:MAX_CANDIDATES]
        ],
        "story": _story(story),
        "rig": rig or rig_digest(),
        "rules": [
            "Ratings are cinematic judgement only.",
            "Physical feasibility is decided later, by simulating the actual rig.",
        ],
    }


def staging_digest(world_summary, staging, *, location_name, story=None, rig=None, movement_catalog=()):
    """Digest for "which staging serves this story best at this place?"."""
    return {
        "question": "location_staging",
        "location": {"name": _clip(location_name, 160)},
        "world": {
            "walkable_regions": world_summary["walkable_regions"],
            "known_obstacles": world_summary["known_obstacles"],
            "unknown_regions": world_summary["unknown_regions"],
            "site_radius_m": world_summary["site_radius_m"],
            "turning_room_m": world_summary["turning_room_m"],
            "longest_axis_m": world_summary["longest_axis_m"],
            "best_background_depth_m": world_summary["best_background_depth_m"],
            "background_depth_limit_m": world_summary.get("background_depth_limit_m"),
            "geometry_basis": "open map or authored proxy outlines, nominal screening only",
            # Axis facts, not axis geometry: lengths and clearances, no rings.
            "candidate_axes": [
                {
                    "affordance_id": axis["affordance_id"],
                    "usable_length_m": axis["usable_length_m"],
                    "min_clearance_m": axis["min_clearance_m"],
                    "background_depth_m": axis["background_depth_m"],
                    "unknown_fraction": axis["unknown_fraction"],
                    "surface_kinds": axis["surface_kinds"],
                }
                for axis in world_summary.get("candidate_axes", [])[:6]
            ],
        },
        "staging_candidates": [
            {
                "candidate_id": candidate["candidate_id"],
                "axis_id": candidate["axis_id"],
                "movement": candidate["template_id"],
                "camera_relation": candidate["camera_relation"],
                "standoff_m": candidate["standoff_m"],
                "travel_m": candidate["travel_m"],
                "focal_mm": candidate["focal_mm"],
                "framing": candidate["framing"],
                "cart_route_clearance_m": candidate["world_screen"]["cart_route_clearance_m"],
                "cart_unknown_fraction": candidate["world_screen"]["cart_unknown_fraction"],
                "already_rejected": bool(candidate["rejected_reason"]),
            }
            for candidate in staging[:12]
        ],
        "movement_catalog": list(movement_catalog)[:12],
        "story": _story(story),
        "rig": rig or rig_digest(),
        "rules": [
            "Order the supplied candidate IDs. Do not invent one.",
            "Do not output coordinates, joint values, wheel commands or durations.",
            "Unknown ground is unknown, not clear.",
        ],
    }


def _story(story):
    if not isinstance(story, dict):
        return {"logline": "", "tone": "", "beats": []}
    return {
        "title": _clip(story.get("title"), 120),
        "logline": _clip(story.get("logline"), 600),
        "tone": _clip(story.get("tone"), 160),
        "audience": _clip(story.get("audience"), 160),
        "beats": [_clip(beat, 240) for beat in (story.get("beats") or [])][:6],
        "shot_intent": _clip(story.get("shot_intent"), MAX_STORY_CHARS),
    }


def rig_digest():
    """What this rig is, in the terms a cinematographer would ask about."""
    from takeone.config import read_json
    from takeone.paths import CONFIGS

    policy = read_json(CONFIGS / "arm-execution.json").get("previs_policy", {})
    return {
        "cart_drive": "differential, powered front wheels, rear swivel casters; it cannot strafe",
        "cart_pace_max_m_s": policy.get("cart_pace_max_m_s"),
        "cart_position_feedback": "none — travel is timed and can drift",
        "camera": "phone on an SO-101 arm; a second SO-101 arm carries a light",
        "lens_range_mm": [13, 360],
        "movement_families": [
            "static",
            "pan/tilt",
            "push/pull",
            "track follow, lead and side",
            "arc and orbit",
            "boom",
        ],
        "stairs": "not drivable",
    }
