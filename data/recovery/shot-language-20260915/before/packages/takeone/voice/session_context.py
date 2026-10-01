"""The bounded production-state block pushed into a live session at connect and resume.

This block — not the conversation — is the session's memory. It is regenerated
from the database whenever it is requested and never appended to, so its size
cannot grow with conversation length. Context-window compression may drop old
turns at any time; nothing is lost because every durable decision was committed
through a tool and reappears here.
"""

import json
import threading

PRODUCTION_STATE_MAX_BYTES = 16 * 1_024
MAX_VERDICTS = 3
_CACHE_ENTRIES = 8

_cache_lock = threading.Lock()
_cache = {}  # (session_id, document_digest, provenance_digest) -> serialized block


def _catalog_block(catalog):
    """The movement catalog trimmed to what a director needs to choose and bound moves.

    Parameter names repeat heavily across templates. Store each distinct list
    once and let ``parameter_set`` index it so the complete 38-template catalog
    still fits inside the fixed live-session context budget.
    """
    parameter_sets = []
    parameter_set_indexes = {}
    templates = []
    for entry in catalog["templates"]:
        parameters = tuple(entry["parameters"])
        if parameters not in parameter_set_indexes:
            parameter_set_indexes[parameters] = len(parameter_sets)
            parameter_sets.append(list(parameters))
        templates.append(
            {key: entry[key] for key in ("id", "name", "intent", "route", "aim")}
            | {"parameter_set": parameter_set_indexes[parameters]}
        )
    return {
        "coordinate_frame": catalog["coordinate_frame"],
        "grid_m": catalog["grid_m"],
        "fields": catalog["fields"],
        "lens_field": catalog["lens_field"],
        "parameter_sets": parameter_sets,
        "parameter_set_note": "templates[].parameter_set indexes parameter_sets; ranges are in fields.",
        "templates": templates,
        "timing": catalog["timing"],
        "tracking": catalog["tracking"],
    }


def _script_block(document):
    if document is None:
        return {"available": False, "reason": "no_script_yet"}
    scenes = []
    for scene in document.get("scenes", []):
        shots = []
        for shot in scene.get("shots", []):
            shots.append(
                {
                    "shot_id": shot["shot_id"],
                    "start_ms": shot["start_ms"],
                    "end_ms": shot["end_ms"],
                    "actor_id": shot["actor_id"],
                    "mark_id": shot["mark_id"],
                    "framing": shot["framing"],
                    "action": shot["action"],
                    "dialogue": shot["lines"][shot["selected_line"]]["text"],
                    "movement": shot.get("movement"),
                    "primitive": shot.get("primitive"),
                }
            )
        scenes.append({"scene_id": scene["scene_id"], "title": scene["title"], "shots": shots})
    return {
        "available": True,
        "title": document.get("title"),
        "logline": document.get("logline"),
        "scenes": scenes,
        "questions": document.get("questions", []),
    }


def _refusal_vocabulary():
    from takeone.previs.diagnostics import CODES

    return {
        "diagnostic_codes": {code: severity for code, severity in sorted(CODES.items())},
        "style": "A refusal names the parameter, the observed value and the allowed range.",
    }


def build_production_state(
    *,
    session_id,
    brief,
    document,
    document_digest,
    skill=None,
    verdicts=(),
    catalog=None,
):
    """One bounded dict, asserted under the ceiling. Fails loudly rather than trimming."""
    if catalog is None:
        from takeone.director.studio import movement_catalog

        catalog = movement_catalog()
    document = document if isinstance(document, dict) else None
    state = {
        "kind": "takeone_production_state",
        "schema_version": 1,
        "session_id": session_id,
        "brief": brief,
        "movement_catalog": _catalog_block(catalog),
        "script": _script_block(document),
        "marks": (document or {}).get("marks", []),
        "actors": (document or {}).get("actors", []),
        "skill": {
            key: skill[key]
            for key in ("id", "name", "speaking_beats", "observable_cues", "tone", "limitations")
        }
        if skill
        else None,
        "recent_take_verdicts": list(verdicts)[-MAX_VERDICTS:],
        "refusals": _refusal_vocabulary(),
        "document_digest": document_digest,
    }
    serialized = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    size = len(serialized.encode("utf-8"))
    if size > PRODUCTION_STATE_MAX_BYTES:
        raise ValueError(
            f"Production state is {size} bytes; the ceiling is {PRODUCTION_STATE_MAX_BYTES}. "
            "Trim the script or catalog block; never raise the ceiling casually."
        )
    return state


def cached_production_state(key, build):
    """Content-keyed cache: (session_id, document_digest, provenance_digest) -> block.

    The key already names everything the block is derived from, so a stale entry
    is impossible; the bound only limits memory.
    """
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None:
        return json.loads(cached)
    state = build()
    with _cache_lock:
        _cache[key] = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        while len(_cache) > _CACHE_ENTRIES:
            _cache.pop(next(iter(_cache)))
    return state
