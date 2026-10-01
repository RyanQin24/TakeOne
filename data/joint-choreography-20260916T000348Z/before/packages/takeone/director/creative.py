"""Creative proposals are bounded data, never executable robot plans."""

import copy
import hashlib
import math

from takeone.previs.diagnostics import Diagnostic

from .contracts import encode, fields, integer, text
from .shot_design import FRAMINGS


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
    "orbit": "Select an arc, full orbit or rising Hero template to rehearse coordinated steering and arm motion.",
    "template": "Exact movement-library settings, ready for the simulator to calculate.",
    "strafe": "The differential-drive cart cannot travel sideways without turning its base.",
    "stairs": "This cart cannot drive on stairs. Keep the cart on a level surface.",
    "optical_zoom": "No controllable optical zoom is registered for this phone.",
    "other_requested": "This requested move has no registered rig primitive. Clarify or revise it explicitly.",
}
SUPPORTED = frozenset(("static", "arm_pan_tilt", "straight_dolly", "orbit", "template"))
MARK_SCHEMA = obj(
    mark_id=string(40),
    description=string(400),
    position_m={"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
    facing_rad={"type": "number"},
)
# Scripts written before marks carried coordinates stay valid; only new proposals must place them.
MARK_SCHEMA["required"] = ["mark_id", "description"]
LINE_SCHEMA = obj(text=string(), tone=string(80), fact_ids=array(string(40)))
LINES_SCHEMA = obj(lines=array(LINE_SCHEMA, 2, 3))
SHOT_SCHEMA = obj(
    shot_id=string(40),
    start_ms={"type": "integer", "minimum": 0, "maximum": 300000},
    end_ms={"type": "integer", "minimum": 1, "maximum": 300000},
    actor_id=dict(type="string", minLength=0, maxLength=40),
    mark_id=string(40),
    action=string(),
    framing={"type": "string", "enum": list(FRAMINGS)},
    primitive={"type": "string", "enum": list(PRIMITIVES)},
    camera_intent=string(),
    light_intent=string(),
    edit_intent=string(),
    lines=array(LINE_SCHEMA, 0, 3),
    selected_line={"type": "integer", "minimum": 0, "maximum": 2},
)
PLAN_SCHEMA = obj(
    title=string(120),
    logline=string(),
    audience=string(200),
    tone=string(200),
    actors=array(obj(actor_id=string(40), name=string(80)), 0, 6),
    marks=array(MARK_SCHEMA, 1, 12),
    questions=array(string(400), 0, 8),
    scenes=array(
        obj(scene_id=string(40), title=string(120), location=string(200), shots=array(SHOT_SCHEMA, 1, 12)),
        1,
        6,
    ),
)


def plan_schema(require_movement=True, require_marks=None):
    """`require_marks` defaults to `require_movement`. Generation asks for placed marks;
    accepting a proposal does not refuse one that arrived without them."""
    from .scenes import scene_properties, shot_properties
    from .shot_design import schema as design_schema
    from .shot_design import style_schema
    from .studio import movement_schema

    schema = copy.deepcopy(PLAN_SCHEMA)
    schema["properties"]["visual_style"] = style_schema()
    from .performers import appearance_schema, performance_schema

    actor = schema["properties"]["actors"]["items"]
    actor["properties"]["appearance"] = appearance_schema()
    if require_movement:
        actor["required"] = list(actor["properties"])
    shot = schema["properties"]["scenes"]["items"]["properties"]["shots"]["items"]
    shot["properties"]["movement"] = movement_schema(require_cinematic=require_movement)
    shot["properties"].update(shot_properties())
    shot["properties"]["design"] = design_schema(require_visibility=require_movement)
    shot["properties"]["performers"] = performance_schema()
    scene = schema["properties"]["scenes"]["items"]
    scene["properties"].update(scene_properties(require_inventory=require_movement))
    mark = schema["properties"]["marks"]["items"]
    mark["properties"]["scene_id"] = string(40)
    if require_movement:
        schema["required"] = list(schema["properties"])
        shot["required"] = list(shot["properties"])
        scene["required"] = list(scene["properties"])
    if require_movement if require_marks is None else require_marks:
        # A strict provider schema lists every property, so a new proposal places its marks.
        mark["required"] = list(mark["properties"])
    return schema


def repair_schema(require_cinematic=False):
    """A repair may only replace movement objects. Dialogue and timing are not re-generated."""
    from .studio import movement_schema

    return obj(
        repairs=array(
            obj(shot_id=string(40), explanation=string(400), movement=movement_schema(require_cinematic)),
            1,
            12,
        )
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
        fields(value, schema["required"], set(schema["properties"]) - set(schema["required"]))
        for key, child in schema["properties"].items():
            if key in value:
                validate(value[key], child, f"{path}.{key}")
    elif kind == "array":
        if not isinstance(value, list) or not schema["minItems"] <= len(value) <= schema["maxItems"]:
            raise ValueError(f"{label} must contain {schema['minItems']}–{schema['maxItems']} items")
        for item in value:
            validate(item, schema["items"], path)
    elif kind == "integer":
        integer(value, label, schema["minimum"], schema["maximum"])
    elif kind == "number":
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number")
        if not schema.get("minimum", -math.inf) <= value <= schema.get("maximum", math.inf):
            raise ValueError(f"{label} is outside the supported range")
    elif kind == "boolean":
        if type(value) is not bool:
            raise ValueError(f"{label} must be true or false")
    else:
        if schema.get("minLength") == 0:
            if not isinstance(value, str) or len(value) > schema.get("maxLength", 800):
                raise ValueError(f"Invalid {label}")
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


def validate_plan(document, brief, context, refused=None):
    """With `refused`, a movement the rig cannot take is marked unresolved and collected
    instead of discarding the whole proposal. Without it, behaviour is unchanged."""
    validate(document, plan_schema(require_movement=False))
    from .scenes import validate_scene_links

    validate_scene_links(document)
    from .performers import validate_links as validate_performers

    validate_performers(document)
    from .screen_contracts import validate_links as validate_screen_contracts

    validate_screen_contracts(document)
    from .shot_design import validate_links

    validate_links(document)
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
        product = shot.get("movement", {}).get("subject_motion") == "none"
        if (shot["actor_id"] not in actors and not (product and shot["actor_id"] == "")) or shot[
            "mark_id"
        ] not in marks:
            raise ValueError("Each shot must reference a named actor and stage mark")
        if product and (shot["actor_id"] or shot.get("camera_target", {}).get("kind") != "object"):
            raise ValueError("Product-only shots need no actor and a scene object as their target")
        if shot["selected_line"] >= max(1, len(shot["lines"])):
            raise ValueError("Selected dialogue line does not exist")
        validate_lines(shot["lines"], context)
        if shot.get("movement", {}).get("template_id") not in (None, "unresolved"):
            from .studio import shot_settings

            if refused is None:
                shot_settings(shot)
                continue
            try:
                shot_settings(shot)
            except ValueError as error:
                from .studio import MovementError

                refused.append(
                    error.diagnostic(shot["shot_id"])
                    if isinstance(error, MovementError)
                    else Diagnostic(shot["shot_id"], "compile_failed", str(error))
                )
                # One refused number must not cost the whole script. Keep the shot,
                # keep the numbers the model chose, and make the gap visible.
                shot["movement"]["template_id"] = "unresolved"
                shot["primitive"] = "other_requested"
    return copy.deepcopy(document)


def constraints(document):
    result = []
    for shot in all_shots(document):
        unresolved = shot.get("movement", {}).get("template_id") == "unresolved"
        result.append(
            {
                "shot_id": shot["shot_id"],
                "primitive": shot["primitive"],
                "status": "needs_simulation"
                if shot["primitive"] in SUPPORTED and not unresolved
                else "unsupported",
                "reason": "Choose a simulator movement for this shot."
                if unresolved
                else PRIMITIVES[shot["primitive"]],
            }
        )
    return result
