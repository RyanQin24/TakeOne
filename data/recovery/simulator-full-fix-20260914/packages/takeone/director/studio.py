"""Deterministic creative-script to current movement-library settings; no device IO."""

import copy
import math
from pathlib import Path

from .contracts import fields

SKILL_PATH = Path(__file__).with_name("robot-film-director") / "SKILL.md"


class MovementError(ValueError):
    """A translation refusal the compiler already makes today, with the field named."""

    def __init__(self, code, message, parameter=None, observed=None, allowed=None, suggestion=""):
        super().__init__(message)
        self.code, self.parameter = code, parameter
        self.observed, self.allowed, self.suggestion = observed, allowed, suggestion

    def diagnostic(self, shot_id):
        from takeone.previs.diagnostics import Diagnostic

        return Diagnostic(
            shot_id, self.code, str(self), self.parameter, self.observed, self.allowed, self.suggestion
        )


def skill_text():
    return SKILL_PATH.read_text(encoding="utf-8")


def movement_catalog():
    from takeone.previs.templates import FIELDS, catalog

    source = catalog()
    return {
        "version": 1,
        "coordinate_frame": "shot-local X/Y floor, Z up; tracked actor starts at (0,0)",
        "grid_m": 0.3048,
        "fields": {
            key: dict(label=f["label"], minimum=f["min"] / f["scale"], maximum=f["max"] / f["scale"])
            for key, f in FIELDS.items()
        },
        "templates": [
            {key: entry[key] for key in ("id", "name", "intent", "route", "aim", "parameters", "defaults")}
            for entry in source["templates"]
        ],
        "timing": "Shot-local takes; planned edit time excludes setup. Moving routes follow speed and geometry.",
        "tracking": "One scripted actor per shot; other people are performance directions.",
    }


def movement_schema():
    from takeone.previs.templates import BY_ID, FIELDS

    return {
        "type": "object",
        "properties": {
            "template_id": {"type": "string", "enum": [*BY_ID, "unresolved"]},
            "subject_motion": {"type": "string", "enum": ["hold", "walk"]},
            "parameters": {
                "type": "array", "minItems": 0, "maxItems": len(FIELDS) + 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "enum": [*FIELDS, "focal_mm"]},
                        "value": {"type": "number"},
                    },
                    "required": ["name", "value"], "additionalProperties": False,
                },
            },
        },
        "required": ["template_id", "subject_motion", "parameters"], "additionalProperties": False,
    }


def shot_settings(shot):
    from takeone.previs.templates import BY_ID, FIELDS, MAX_FOCAL_MM, catalog, validate_settings

    movement = shot.get("movement")
    if not movement or movement["template_id"] == "unresolved":
        raise MovementError(
            "unresolved_movement",
            "Choose an exact movement template for this shot before rehearsal.",
            parameter="template_id",
            suggestion="Pick a template_id from the movement catalog",
        )
    template_id = movement["template_id"]
    entry = next((e for e in catalog()["templates"] if e["id"] == template_id), None)
    if entry is None:
        raise MovementError(
            "unresolved_movement",
            "This movement is not in the simulator's template library.",
            parameter="template_id",
            suggestion="Use one of the template ids the catalog advertises",
        )
    overrides = {}
    allowed = set(entry["parameters"]) | {"focal_mm"}
    for parameter in movement["parameters"]:
        fields(parameter, ("name", "value"))
        name, value = parameter["name"], parameter["value"]
        if name not in allowed or name in overrides:
            raise MovementError(
                "unknown_parameter",
                f"Unknown, unused or duplicate movement parameter: {name}",
                parameter=name,
                suggestion=f"{template_id} advertises: {', '.join(sorted(allowed))}",
            )
        if type(value) not in (int, float) or not math.isfinite(value):
            raise MovementError(
                "out_of_range", f"Movement parameter {name} must be a finite number.", parameter=name
            )
        # The same bounds validate_settings enforces, checked here so a refusal
        # can name the field. validate_settings below remains the authority.
        low, high = (
            (FIELDS[name]["min"] / FIELDS[name]["scale"], FIELDS[name]["max"] / FIELDS[name]["scale"])
            if name in FIELDS
            else (13.0, MAX_FOCAL_MM)
        )
        if not low - 1e-9 <= value <= high + 1e-9:
            raise MovementError(
                "out_of_range",
                f"{name} is {value:g}; the rig accepts {low:g} to {high:g}.",
                parameter=name,
                observed=float(value),
                allowed=(low, high),
                suggestion=f"Choose a {name} between {low:g} and {high:g}",
            )
        overrides[name] = value
    duration = (shot["end_ms"] - shot["start_ms"]) / 1000
    if BY_ID[template_id]["route"] == "hold":
        if "duration_s" in overrides and not math.isclose(overrides["duration_s"], duration):
            raise MovementError(
                "out_of_range",
                "Shot duration must match its script start and end times.",
                parameter="duration_s",
                observed=float(overrides["duration_s"]),
                allowed=(duration, duration),
                suggestion="Omit duration_s on a stationary shot; it comes from start_ms and end_ms",
            )
        overrides["duration_s"] = duration
    try:
        settings = validate_settings({"mode": "template", "template_id": template_id,
                                      "subject_motion": movement["subject_motion"], **overrides})
    except ValueError as error:
        raise MovementError("out_of_range", str(error)) from None
    return settings, sorted(allowed - overrides.keys())


def shot_diagnostic(shot):
    """None when this shot translates. Otherwise the typed reason, ready for a repair."""
    try:
        shot_settings(shot)
    except MovementError as error:
        return error.diagnostic(shot["shot_id"])
    except ValueError as error:
        from takeone.previs.diagnostics import Diagnostic

        return Diagnostic(shot["shot_id"], "compile_failed", str(error))
    return None


def rehearsal_manifest(detail, expected_digest):
    from .creative import all_shots, digest, validate_plan
    from .contracts import ProductionBrief
    from takeone.previs.templates import BY_ID

    creative = detail.get("creative")
    if not creative or creative["digest"] != expected_digest:
        raise ValueError("The script changed. Reopen rehearsal from the current Director script.")
    doc = validate_plan(creative["document"], ProductionBrief.parse(detail["session"]["brief"]), creative["context"])
    shots = []
    for shot in all_shots(doc):
        item = {key: copy.deepcopy(shot[key]) for key in
                ("shot_id", "start_ms", "end_ms", "actor_id", "mark_id", "action", "framing",
                 "camera_intent", "light_intent")}
        item["dialogue"] = shot["lines"][shot["selected_line"]]["text"]
        try:
            item["settings"], item["defaulted_parameters"] = shot_settings(shot)
            item.update(name=BY_ID[item["settings"]["template_id"]]["name"], error=None)
        except ValueError as error:
            reason = error.diagnostic(shot["shot_id"]) if isinstance(error, MovementError) else None
            item.update(settings=None, name="Movement needs direction", error=str(error),
                        defaulted_parameters=[], diagnostic=reason.wire() if reason else None)
        shots.append(item)
    manifest = dict(kind="takeone_director_rehearsal", schema_version=1, title=doc["title"],
                    marks=copy.deepcopy(doc["marks"]), actors=copy.deepcopy(doc["actors"]),
                    session_id=detail["session"]["session_id"], document_digest=expected_digest,
                    revision=detail["session"]["revision"], shots=shots,
                    time_source="proposed_edit_timeline", take_setup="calibration_then_aim_each_shot",
                    coordinate_frame="Each shot places its tracked actor at the origin. Reposition at cuts.")
    return {**manifest, "manifest_digest": digest(manifest)}
