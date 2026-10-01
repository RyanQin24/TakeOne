"""Creative proposals are bounded data, never executable robot plans."""

import copy
import hashlib

from .contracts import encode, fields, integer, text


def string(maximum=800):
    return {"type": "string", "minLength": 1, "maxLength": maximum}


def array(items, minimum=0, maximum=12):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


def obj(**properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


PRIMITIVES = {
    "static": "Fixed framing. Camera position still needs placement in the simulator.",
    "arm_pan_tilt": "Aim with the phone arm. Joint limits, clearance and reach need solver validation.",
    "straight_dolly": "Travel along the wheel heading. Cart path and loaded arm motion need validation.",
    "orbit": "An orbit needs coordinated steering and arm motion; it is not an approved primitive yet.",
    "strafe": "The differential-drive cart cannot travel sideways without turning its base.",
    "stairs": "This cart cannot drive on stairs. Keep the cart on a level surface.",
    "optical_zoom": "No controllable optical zoom is registered for this phone.",
    "other_requested": "This requested move has no registered rig primitive. Clarify or revise it explicitly.",
}
SUPPORTED = frozenset(("static", "arm_pan_tilt", "straight_dolly"))
LINE_SCHEMA = obj(text=string(), tone=string(80), fact_ids=array(string(40)))
LINES_SCHEMA = obj(lines=array(LINE_SCHEMA, 2, 3))
SHOT_SCHEMA = obj(
    shot_id=string(40),
    start_ms={"type": "integer", "minimum": 0, "maximum": 300000},
    end_ms={"type": "integer", "minimum": 1, "maximum": 300000},
    actor_id=string(40),
    mark_id=string(40),
    action=string(),
    framing={"type": "string", "enum": ["wide", "medium", "close_up"]},
    primitive={"type": "string", "enum": list(PRIMITIVES)},
    camera_intent=string(),
    light_intent=string(),
    edit_intent=string(),
    lines=array(LINE_SCHEMA, 1, 3),
    selected_line={"type": "integer", "minimum": 0, "maximum": 2},
)
PLAN_SCHEMA = obj(
    title=string(120),
    logline=string(),
    audience=string(200),
    tone=string(200),
    actors=array(obj(actor_id=string(40), name=string(80)), 1, 6),
    marks=array(obj(mark_id=string(40), description=string(400)), 1, 12),
    questions=array(string(400), 0, 8),
    scenes=array(
        obj(scene_id=string(40), title=string(120), location=string(200), shots=array(SHOT_SCHEMA, 1, 12)),
        1,
        6,
    ),
)


def validate(value, schema, path="proposal"):
    """Validate the same deliberately small JSON Schema subset sent to the provider."""
    key = path.rsplit(".", 1)[-1]
    label = {
        "text": "Dialogue" if ".lines." in path else "Fact",
        "start_ms": "Shot start in milliseconds",
        "end_ms": "Shot end in milliseconds",
        "selected_line": "Selected line",
        "actor_id": "Actor",
        "mark_id": "Stage mark",
        "primitive": "Camera move",
    }.get(key, key.replace("_", " ").capitalize())
    kind = schema["type"]
    if kind == "object":
        fields(value, schema["required"])
        for key, child in schema["properties"].items():
            validate(value[key], child, f"{path}.{key}")
    elif kind == "array":
        if not isinstance(value, list) or not schema["minItems"] <= len(value) <= schema["maxItems"]:
            raise ValueError(f"{label} must contain {schema['minItems']}–{schema['maxItems']} items")
        for item in value:
            validate(item, schema["items"], path)
    elif kind == "integer":
        integer(value, label, schema["minimum"], schema["maximum"])
    else:
        text(value, label, schema.get("maxLength", 800))
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{label} is not an allowed choice")


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def all_shots(document):
    return [shot for scene in document["scenes"] for shot in scene["shots"]]


def validate_context(value):
    fields(value, ("skill_id", "audience", "tone", "facts"))
    from .skills import SKILLS

    if value["skill_id"] not in SKILLS:
        raise ValueError("Choose a registered filming skill")
    text(value["audience"], "Audience", 200)
    text(value["tone"], "Tone", 200)
    validate(value["facts"], array(obj(fact_id=string(40), text=string(400)), 0, 12), "facts")
    unique(value["facts"], "fact_id")
    return copy.deepcopy(value)


def unique(items, key):
    ids = [item[key] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate {key}")
    return set(ids)


def validate_lines(lines, context):
    facts = {fact["fact_id"] for fact in context["facts"]}
    for line in lines:
        if not set(line["fact_ids"]).issubset(facts):
            raise ValueError("Dialogue cites an unknown product fact")


def validate_plan(document, brief, context):
    validate(document, PLAN_SCHEMA)
    actors, marks = unique(document["actors"], "actor_id"), unique(document["marks"], "mark_id")
    unique(document["scenes"], "scene_id")
    shots = all_shots(document)
    unique(shots, "shot_id")
    if len(shots) > 24:
        raise ValueError("Keep a production to 24 shots or fewer")
    last_end = 0
    for shot in shots:
        if not last_end <= shot["start_ms"] < shot["end_ms"] <= brief.duration_ms:
            raise ValueError("Proposed shots must be ordered, non-overlapping and fit the brief duration")
        last_end = shot["end_ms"]
        if shot["actor_id"] not in actors or shot["mark_id"] not in marks:
            raise ValueError("Each shot must reference a named actor and stage mark")
        if shot["selected_line"] >= len(shot["lines"]):
            raise ValueError("Selected dialogue line does not exist")
        validate_lines(shot["lines"], context)
    return copy.deepcopy(document)


def constraints(document):
    return [
        {
            "shot_id": shot["shot_id"],
            "primitive": shot["primitive"],
            "status": "needs_simulation" if shot["primitive"] in SUPPORTED else "unsupported",
            "reason": PRIMITIVES[shot["primitive"]],
        }
        for shot in all_shots(document)
    ]
