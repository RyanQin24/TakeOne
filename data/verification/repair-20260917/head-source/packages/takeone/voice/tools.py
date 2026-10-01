"""Voice tool declarations and their loopback dispatcher.

Every durable decision the director persona makes arrives here as a tool call;
prose is never the record. The dispatcher validates ownership with the same
envelope as every other voice route, refuses with the offending field named (so
TO can say why, not just no), and keeps every spoken result under 600
characters because it is about to be read aloud.

The model sees only goal-level embodied controls. Physical motion still requires
an independently armed local BehaviorManager and its supervised actuator; these
tools never expose wheel PWM, UART, servo counts, joint angles or serial ports.
"""

import threading
import time
from uuid import NAMESPACE_URL, uuid5

from takeone.director.studio import MovementError
from takeone.embodied import BehaviorError, FilmingGoal
from takeone.perception import PerceptionState, PersonDetection, PersonTracker
from takeone.recording.contracts import ZoomRamp

from .api import parse_owned_request

# Tool-call ids from the model are free-form; Director operations need canonical
# UUIDs. The mapping is deterministic so a reconnect retry replays, not repeats.
TOOL_OPERATIONS = uuid5(NAMESPACE_URL, "takeone:voice-tools")

RESULT_MAX_CHARS = 600
MIN_TAKE_SECONDS = 0.25
MAX_TAKE_SECONDS = 10.0
EDITABLE_TEXT_FIELDS = ("action", "framing", "camera_intent", "light_intent")

# The browser speaks the preamble before dispatching any compile-class tool, so
# dead air is masked while the server works. Fast tools answer directly.
LATENCY = {
    "propose_shot": "compile",
    "revise_script": "fast",
    "approve_script": "fast",
    "rehearse": "compile",
    "start_take": "fast",
    "stop_take": "fast",
    "inspect_scene": "browser",
    "select_subject": "fast",
    "prepare_filming_behavior": "compile",
    "start_filming_behavior": "fast",
    "adjust_filming_behavior": "fast",
    "hold_filming_behavior": "fast",
    "stop_filming_behavior": "fast",
    "describe_frame": "browser",
}
PREAMBLES = {
    "propose_shot": "Setting that up now.",
    "rehearse": "Loading the rehearsal.",
    "prepare_filming_behavior": "Planning that move now.",
}

_FILMING_GOAL_SCHEMA = {
    "type": "OBJECT",
    "description": "High-level filming goal. Never raw motor, wheel, UART or joint commands.",
    "properties": {
        "subject_track_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
        "subject_relation": {"type": "STRING", "enum": ["one_person", "pair", "group", "object"]},
        "camera_relation": {"type": "STRING", "enum": ["approach", "retreat", "follow", "lead", "arc", "hold"]},
        "framing": {"type": "STRING", "enum": ["full", "medium", "medium_close", "close", "custom"]},
        "screen_target_uv": {"type": "ARRAY", "items": {"type": "NUMBER"}},
        "desired_subject_size_range": {"type": "ARRAY", "items": {"type": "NUMBER"}},
        "recording_policy": {"type": "STRING", "enum": ["after_settle", "immediate", "manual"]},
        "max_duration_s": {"type": "NUMBER"},
        "lost_target_policy": {"type": "STRING", "enum": ["hold", "stop"]},
    },
    "required": ["subject_track_ids", "subject_relation", "camera_relation", "framing"],
}

_MOVEMENT_SCHEMA = {
    "type": "OBJECT",
    "description": "A movement-catalog choice with explicit numeric parameters.",
    "properties": {
        "template_id": {"type": "STRING", "description": "A template_id from the movement catalog."},
        "subject_motion": {"type": "STRING", "enum": ["hold", "walk"]},
        "parameters": {
            "type": "ARRAY",
            "description": "Unique {name, value} entries; omitted values use catalog defaults.",
            "items": {
                "type": "OBJECT",
                "properties": {"name": {"type": "STRING"}, "value": {"type": "NUMBER"}},
                "required": ["name", "value"],
            },
        },
    },
    "required": ["template_id", "subject_motion", "parameters"],
}


def declarations(template_ids=None):
    """Gemini function declarations. Passing the live template ids locks the enum."""
    movement = {"type": "OBJECT", **{k: v for k, v in _MOVEMENT_SCHEMA.items() if k != "type"}}
    if template_ids:
        movement = {
            **movement,
            "properties": {
                **movement["properties"],
                "template_id": {
                    "type": "STRING",
                    "enum": list(template_ids),
                    "description": "A template_id from the movement catalog.",
                },
            },
        }
    return [
        {
            "name": "propose_shot",
            "description": (
                "Compile one camera movement in the simulator and report whether the rig can film "
                "it. Use this before promising any shot. The result carries a plan_id."
            ),
            "parameters": movement,
        },
        {
            "name": "revise_script",
            "description": (
                "Change one field of one shot in the current script. This is the durable record "
                "of the decision; saying it aloud does not change the script."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "shot_id": {"type": "STRING"},
                    "field": {
                        "type": "STRING",
                        "enum": [*EDITABLE_TEXT_FIELDS, "selected_line", "movement"],
                    },
                    "value_text": {"type": "STRING", "description": "For text fields."},
                    "value_number": {"type": "NUMBER", "description": "For selected_line."},
                    "value_movement": movement,
                },
                "required": ["shot_id", "field"],
            },
        },
        {
            "name": "approve_script",
            "description": "Approve the current script exactly as written, if every shot translates.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "rehearse",
            "description": (
                "Warm every approved shot's preview and hand the operator the Shot Studio "
                "rehearsal link. Does not move the robot."
            ),
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "start_take",
            "description": (
                "Start one offline recorded take. You must then stay completely silent until "
                "stop_take. plan_id links the take to the shot it films."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "plan_id": {"type": "STRING", "description": "The compiled plan being filmed."},
                    "duration_s": {"type": "NUMBER", "description": "Take length, 0.25 to 10 seconds."},
                },
                "required": ["duration_s"],
            },
        },
        {
            "name": "stop_take",
            "description": "Stop the running take and release the quiet gate.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"take_id": {"type": "STRING"}},
                "required": ["take_id"],
            },
        },
        {
            "name": "inspect_scene",
            "description": (
                "Request current visual grounding before choosing a subject or embodied move. "
                "The browser sends one bounded semantic frame; this tool never moves the robot."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {"reason": {"type": "STRING"}},
                "required": ["reason"],
            },
        },
        {
            "name": "select_subject",
            "description": (
                "Bind one or more server-issued transient visual track IDs to the user's semantic "
                "reference after inspect_scene. This selects a target but does not move the robot."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "track_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "semantic_reason": {"type": "STRING"},
                },
                "required": ["track_ids", "semantic_reason"],
            },
        },
        {
            "name": "prepare_filming_behavior",
            "description": (
                "Validate and compile one subject-relative filming goal. This prepares simulation/local "
                "behavior only; physical movement still requires independent operator arming."
            ),
            "parameters": _FILMING_GOAL_SCHEMA,
        },
        {
            "name": "start_filming_behavior",
            "description": (
                "Start a previously prepared behavior only if the local Live Director is armed and a "
                "supervised actuator is connected. Never use this before prepare_filming_behavior."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {"behavior_id": {"type": "STRING"}},
                "required": ["behavior_id"],
            },
        },
        {
            "name": "adjust_filming_behavior",
            "description": (
                "Adjust only the current behavior's screen target or subject-size range. "
                "Changing subjects or camera relation requires a new prepared behavior."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "behavior_id": {"type": "STRING"},
                    "screen_target_uv": {"type": "ARRAY", "items": {"type": "NUMBER"}},
                    "desired_subject_size_range": {"type": "ARRAY", "items": {"type": "NUMBER"}},
                },
                "required": ["behavior_id"],
            },
        },
        {
            "name": "hold_filming_behavior",
            "description": "Hold the current local filming behavior without inventing a new target.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "stop_filming_behavior",
            "description": "Stop the current local filming behavior. This is a local fail-closed action.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "describe_frame",
            "description": (
                "Ask for one camera frame to look at. Handled in the browser; use only when "
                "you genuinely need to see framing, a mark or an eyeline."
            ),
            "parameters": {"type": "OBJECT", "properties": {}},
        },
    ]


def _movement_settings(arguments, template, catalog_fields, lens_bounds):
    """Refuse with the field named, exactly as the studio translator does; then let
    validate_settings remain the authority. Only the template's advertised
    parameters (plus focal_mm) are accepted, matching studio.shot_settings."""
    subject_motion = arguments.get("subject_motion")
    if subject_motion not in ("hold", "walk"):
        raise MovementError(
            "out_of_range", "subject_motion must be hold or walk.", parameter="subject_motion"
        )
    parameters = arguments.get("parameters")
    if not isinstance(parameters, list):
        raise MovementError(
            "unknown_parameter", "parameters must be a list of {name, value}.", parameter="parameters"
        )
    allowed = set(template["parameters"]) | {"focal_mm"}
    overrides = {}
    for entry in parameters:
        if not isinstance(entry, dict) or set(entry) != {"name", "value"}:
            raise MovementError(
                "unknown_parameter", "Each parameter is exactly {name, value}.", parameter="parameters"
            )
        name, value = entry["name"], entry["value"]
        if name not in allowed or name in overrides:
            raise MovementError(
                "unknown_parameter",
                f"Unknown, unused or duplicate movement parameter: {name}.",
                parameter=name,
                suggestion=f"{template['id']} advertises: {', '.join(sorted(allowed))}",
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MovementError("out_of_range", f"{name} must be a finite number.", parameter=name)
        if name == "focal_mm":
            low, high = lens_bounds
        else:
            field = catalog_fields[name]
            low, high = field["minimum"], field["maximum"]
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
    return {"mode": "template", "template_id": template["id"], "subject_motion": subject_motion, **overrides}


def _refusal(error):
    message = str(error)
    if error.suggestion:
        message = f"{message} {error.suggestion}."
    result = {"ok": False, "code": error.code, "message": message}
    if error.parameter:
        result["parameter"] = error.parameter
    if error.allowed:
        result["allowed"] = list(error.allowed)
    return result


class VoiceTools:
    """Dispatches validated tool calls onto the director, previs and recorder surfaces."""

    def __init__(
        self,
        voice,
        director,
        recording=None,
        *,
        compilers=None,
        behavior_manager=None,
        perception_tracker=None,
        clock=time.monotonic_ns,
    ):
        self.voice = voice
        self.director = director
        self.recording = recording
        self.behavior_manager = behavior_manager
        self.perception_tracker = perception_tracker or PersonTracker()
        self.clock = clock
        self._compilers = compilers or {}

    # -- catalog access, deferred so this module imports without the simulation extra

    def _catalog(self):
        if "catalog" in self._compilers:
            return self._compilers["catalog"]()
        from takeone.director.studio import movement_catalog

        return movement_catalog()

    def _compile_preview(self, settings):
        if "compile_preview" in self._compilers:
            return self._compilers["compile_preview"](settings)
        from takeone.previs.cache import compile_preview

        return compile_preview(settings)

    def declarations(self):
        return declarations(entry["id"] for entry in self._catalog()["templates"])

    # -- HTTP surface

    def update_perception(self, body, token):
        envelope = parse_owned_request(body, ("perception",))
        authority = self.voice.live_authority(token, envelope)
        if self.behavior_manager is None:
            raise RuntimeError("Embodied behavior manager is unavailable")
        payload = body["perception"]
        if not isinstance(payload, dict) or set(payload) != {"source_frame_age_ms", "detections"}:
            raise ValueError("Invalid browser perception fields")
        age = payload["source_frame_age_ms"]
        if type(age) is not int or not 0 <= age <= 60_000:
            raise ValueError("source_frame_age_ms must be 0 to 60000")
        detections = payload["detections"]
        if not isinstance(detections, list) or len(detections) > 16:
            raise ValueError("detections must contain at most 16 people")
        parsed = []
        for detection in detections:
            if not isinstance(detection, dict) or set(detection) != {"bbox_uv", "confidence"}:
                raise ValueError("Each detection needs bbox_uv and confidence")
            parsed.append(PersonDetection(tuple(detection["bbox_uv"]), detection["confidence"]))
        received_ns = self.clock()
        captured_ns = max(0, received_ns - age * 1_000_000)
        people = self.perception_tracker.update(captured_ns, parsed)
        state = PerceptionState(received_ns, age, people)
        behavior = self.behavior_manager.update_perception(state)
        return {
            "schema_version": 1,
            "ok": True,
            "code": "perception_updated",
            "perception": state.wire(),
            "behavior": behavior,
            "snapshot": authority["snapshot"],
        }

    def post(self, body, token):
        envelope = parse_owned_request(body, ("tool", "request_id", "arguments"), ("speculative",))
        tool = body["tool"]
        if not isinstance(tool, str) or tool not in LATENCY:
            raise ValueError("Unknown voice tool")
        request_id = body["request_id"]
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
            raise ValueError("Request ID must contain 1 to 200 characters")
        arguments = body["arguments"]
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object")
        speculative = body.get("speculative", False)
        if type(speculative) is not bool:
            raise ValueError("speculative must be true or false")

        authority = self.voice.live_authority(token, envelope)
        snapshot = authority["snapshot"]
        # The recording latch is the hard silence invariant: while a take may be
        # rolling, the only permitted acts are stopping it and replaying a
        # start_take retry (the bridge's request-id dedup makes that safe; a
        # genuinely new start is refused there as take_unresolved). Broader quiet
        # reasons — scope refreshes, expired observations — govern the fixture
        # conversation path, not tool dispatch.
        if snapshot["recording_latch_active"] and tool not in (
            "stop_take", "start_take", "hold_filming_behavior", "stop_filming_behavior"
        ):
            return self._finish(
                {
                    "ok": False,
                    "code": "quiet",
                    "message": "Recording holds the conversation quiet. Only stop_take may run.",
                },
                snapshot,
            )
        if speculative:
            if tool != "propose_shot":
                raise ValueError("Only propose_shot supports speculative compilation")
            return self._finish(self._speculate(arguments), snapshot)

        scope = envelope[1]
        if tool == "propose_shot":
            result = self._propose(arguments)
        elif tool == "revise_script":
            result = self._revise(scope, envelope[3], request_id, arguments)
        elif tool == "approve_script":
            result = self._approve(scope, envelope[3], request_id)
        elif tool == "rehearse":
            result = self._rehearse(scope)
        elif tool == "select_subject":
            result = self._select_subject(arguments)
        elif tool == "prepare_filming_behavior":
            result = self._prepare_behavior(arguments)
        elif tool == "start_filming_behavior":
            result = self._start_behavior(arguments)
        elif tool == "adjust_filming_behavior":
            result = self._adjust_behavior(arguments)
        elif tool == "hold_filming_behavior":
            result = self._hold_behavior()
        elif tool == "stop_filming_behavior":
            result = self._stop_behavior()
        elif tool == "start_take":
            result = self._start_take(token, envelope, request_id, arguments)
        elif tool == "stop_take":
            result = self._stop_take(token, envelope, request_id, arguments)
        else:  # browser-side visual tools reaching the server is a wiring mistake
            result = {
                "ok": False,
                "code": "browser_tool",
                "message": "Visual inspection is answered by the browser from the current camera frame.",
            }
        return self._finish(result, snapshot)

    def _finish(self, result, snapshot):
        message = result.get("message", "")
        if len(message) > RESULT_MAX_CHARS:
            result["message"] = message[: RESULT_MAX_CHARS - 1] + "…"
        return {"schema_version": 1, "snapshot": snapshot, **result}

    # -- tools

    def _validated_settings(self, arguments):
        catalog = self._catalog()
        template_id = arguments.get("template_id")
        template = next((entry for entry in catalog["templates"] if entry["id"] == template_id), None)
        if template is None:
            raise MovementError(
                "unresolved_movement",
                "This movement is not in the simulator's template library.",
                parameter="template_id",
                suggestion="Use one of the template ids the catalog advertises",
            )
        lens = (catalog["lens_field"]["minimum"], catalog["lens_field"]["maximum"])
        return _movement_settings(arguments, template, catalog["fields"], lens)

    def _speculate(self, arguments):
        try:
            settings = self._validated_settings(arguments)
        except MovementError as error:
            return _refusal(error)
        threading.Thread(
            target=self._warm_quietly, args=(settings,), name="takeone-speculative", daemon=True
        ).start()
        return {"ok": True, "code": "warming", "message": ""}

    def _warm_quietly(self, settings):
        try:
            self._compile_preview(settings)
        except Exception:
            pass  # Speculation is free to fail; the real call reports the reason.

    def _propose(self, arguments):
        try:
            settings = self._validated_settings(arguments)
            started = self.clock()
            preview = self._compile_preview(settings)
        except MovementError as error:
            return _refusal(error)
        except ValueError as error:
            return {"ok": False, "code": "out_of_range", "message": str(error)[:RESULT_MAX_CHARS]}
        elapsed_ms = (self.clock() - started) // 1_000_000
        summary = preview.get("summary", {})
        name = preview.get("template", {}).get("name", settings["template_id"])
        parts = [f"{name} ready: {preview['duration_s']:.1f} s total"]
        if summary.get("distance_m") is not None:
            parts.append(f"{summary['distance_m']:.1f} m of travel")
        if summary.get("subject_distance_m") is not None:
            parts.append(f"subject at {summary['subject_distance_m']:.1f} m")
        notes = preview.get("notes") or []
        message = ", ".join(parts) + "." + (f" Note: {notes[0]}" if notes else "")
        return {
            "ok": True,
            "code": "shot_ready",
            "message": message,
            "plan_id": preview["plan_id"],
            "duration_s": preview["duration_s"],
            "compile_ms": elapsed_ms,
        }

    @staticmethod
    def _parse_filming_goal(arguments):
        required = {"subject_track_ids", "subject_relation", "camera_relation", "framing"}
        optional = {
            "screen_target_uv",
            "desired_subject_size_range",
            "recording_policy",
            "max_duration_s",
            "lost_target_policy",
        }
        if not isinstance(arguments, dict):
            raise ValueError("Filming goal must be an object")
        missing = required - arguments.keys()
        extra = arguments.keys() - required - optional
        if missing or extra:
            raise ValueError(f"Invalid filming goal fields; missing: {sorted(missing)}, unknown: {sorted(extra)}")
        return FilmingGoal(
            subject_track_ids=tuple(arguments["subject_track_ids"]),
            subject_relation=arguments["subject_relation"],
            camera_relation=arguments["camera_relation"],
            framing=arguments["framing"],
            screen_target_uv=tuple(arguments.get("screen_target_uv", (0.5, 0.5))),
            desired_subject_size_range=tuple(
                arguments.get("desired_subject_size_range", (0.2, 0.7))
            ),
            recording_policy=arguments.get("recording_policy", "after_settle"),
            max_duration_s=arguments.get("max_duration_s", 10.0),
            lost_target_policy=arguments.get("lost_target_policy", "hold"),
        )

    def _behavior_error(self, error):
        return {"ok": False, "code": error.code, "message": str(error)}

    def _select_subject(self, arguments):
        if self.behavior_manager is None:
            return {
                "ok": False,
                "code": "behavior_manager_unavailable",
                "message": "Embodied behavior is unavailable.",
            }
        if not isinstance(arguments, dict) or set(arguments) != {"track_ids", "semantic_reason"}:
            return {
                "ok": False,
                "code": "invalid_subject_selection",
                "message": "select_subject needs track_ids and semantic_reason.",
            }
        try:
            state = self.behavior_manager.select_subject(
                arguments["track_ids"], arguments["semantic_reason"]
            )
        except BehaviorError as error:
            return self._behavior_error(error)
        except (TypeError, ValueError) as error:
            return {"ok": False, "code": "invalid_subject_selection", "message": str(error)}
        return {
            "ok": True,
            "code": "subject_selected",
            "message": f"Bound {len(arguments['track_ids'])} transient subject track(s).",
            **state,
        }

    def _prepare_behavior(self, arguments):
        if self.behavior_manager is None:
            return {
                "ok": False,
                "code": "behavior_manager_unavailable",
                "message": "Embodied behavior is not connected on this TAKE ONE runtime.",
            }
        try:
            goal = self._parse_filming_goal(arguments)
            result = self.behavior_manager.prepare(goal)
        except BehaviorError as error:
            return self._behavior_error(error)
        except (TypeError, ValueError) as error:
            return {"ok": False, "code": "invalid_filming_goal", "message": str(error)}
        return {
            "ok": True,
            "code": "behavior_prepared",
            "message": (
                f"Prepared {goal.camera_relation} framing for {len(goal.subject_track_ids)} "
                "tracked subject(s). Physical motion has not started."
            ),
            **result,
        }

    def _start_behavior(self, arguments):
        if self.behavior_manager is None:
            return {"ok": False, "code": "behavior_manager_unavailable", "message": "Embodied behavior is unavailable."}
        behavior_id = arguments.get("behavior_id") if isinstance(arguments, dict) else None
        if not isinstance(behavior_id, str) or not behavior_id:
            return {"ok": False, "code": "invalid_behavior_id", "message": "start_filming_behavior needs behavior_id."}
        try:
            state = self.behavior_manager.start(behavior_id)
        except BehaviorError as error:
            return self._behavior_error(error)
        return {"ok": True, "code": "behavior_started", "message": "Local filming behavior accepted.", **state}

    def _adjust_behavior(self, arguments):
        if self.behavior_manager is None:
            return {"ok": False, "code": "behavior_manager_unavailable", "message": "Embodied behavior is unavailable."}
        if not isinstance(arguments, dict):
            return {"ok": False, "code": "invalid_behavior_adjustment", "message": "Adjustment must be an object."}
        allowed = {"behavior_id", "screen_target_uv", "desired_subject_size_range"}
        if set(arguments) - allowed:
            return {"ok": False, "code": "invalid_behavior_adjustment", "message": "Only screen target and subject-size range may be adjusted in place."}
        behavior_id = arguments.get("behavior_id")
        if not isinstance(behavior_id, str) or not behavior_id:
            return {"ok": False, "code": "invalid_behavior_id", "message": "adjust_filming_behavior needs behavior_id."}
        try:
            state = self.behavior_manager.adjust(
                behavior_id,
                screen_target_uv=arguments.get("screen_target_uv"),
                desired_subject_size_range=arguments.get("desired_subject_size_range"),
            )
        except BehaviorError as error:
            return self._behavior_error(error)
        except (TypeError, ValueError) as error:
            return {"ok": False, "code": "invalid_behavior_adjustment", "message": str(error)}
        return {"ok": True, "code": "behavior_adjusted", "message": "Updated the live framing goal locally.", **state}

    def _hold_behavior(self):
        if self.behavior_manager is None:
            return {"ok": False, "code": "behavior_manager_unavailable", "message": "Embodied behavior is unavailable."}
        return {
            "ok": True,
            "code": "behavior_holding",
            "message": "Holding the current filming behavior.",
            **self.behavior_manager.hold(reason="voice_hold_requested"),
        }

    def _stop_behavior(self):
        if self.behavior_manager is None:
            return {"ok": False, "code": "behavior_manager_unavailable", "message": "Embodied behavior is unavailable."}
        return {
            "ok": True,
            "code": "behavior_stopping",
            "message": "Stopping the current filming behavior locally.",
            **self.behavior_manager.stop(reason="voice_stop_requested"),
        }

    def _creative(self, scope, expires_ns, request_id, action, payload):
        detail = self.director.service.repository.inspect(scope.session_id)
        body = {
            "schema_version": 1,
            "operation_id": str(uuid5(TOOL_OPERATIONS, f"{scope.session_id}:{request_id}")),
            "runtime_epoch": scope.runtime_epoch,
            "expires_monotonic_ns": str(expires_ns),
            "scope": {
                "session_id": scope.session_id,
                "expected_revision": scope.revision,
                "cancellation_generation": scope.cancellation_generation,
                "take_id": scope.take_id,
                "plan_id": scope.plan_id,
            },
            "action": action,
            "payload": payload,
        }
        return detail, self.director.post("/api/director/creative", body)

    def _current_document(self, scope):
        detail = self.director.service.repository.inspect(scope.session_id)
        creative = detail.get("creative")
        if not creative:
            raise MovementError(
                "script_required",
                "There is no script yet. Draft one in the Director first.",
                parameter="script",
            )
        return detail, creative

    def _revise(self, scope, expires_ns, request_id, arguments):
        import copy

        shot_id = arguments.get("shot_id")
        field = arguments.get("field")
        if not isinstance(shot_id, str) or field not in (*EDITABLE_TEXT_FIELDS, "selected_line", "movement"):
            return {
                "ok": False,
                "code": "unknown_parameter",
                "message": "revise_script needs a shot_id and a supported field.",
            }
        try:
            _, creative = self._current_document(scope)
        except MovementError as error:
            return _refusal(error)
        document = copy.deepcopy(creative["document"])
        shot = next(
            (
                s
                for scene in document.get("scenes", [])
                for s in scene.get("shots", [])
                if s.get("shot_id") == shot_id
            ),
            None,
        )
        if shot is None:
            return {
                "ok": False,
                "code": "unknown_parameter",
                "message": f"No shot named {shot_id}.",
                "parameter": "shot_id",
            }
        if field == "selected_line":
            index = arguments.get("value_number")
            if (
                not isinstance(index, (int, float))
                or int(index) != index
                or not (0 <= int(index) < len(shot["lines"]))
            ):
                return {
                    "ok": False,
                    "code": "out_of_range",
                    "message": f"selected_line must be 0 to {len(shot['lines']) - 1}.",
                    "parameter": "selected_line",
                }
            shot["selected_line"] = int(index)
            described = f"line {int(index)}"
        elif field == "movement":
            try:
                settings = self._validated_settings(arguments.get("value_movement") or {})
            except MovementError as error:
                return _refusal(error)
            shot["movement"] = {
                "template_id": settings["template_id"],
                "subject_motion": settings["subject_motion"],
                "parameters": [
                    {"name": name, "value": value}
                    for name, value in settings.items()
                    if name not in ("mode", "template_id", "subject_motion")
                ],
            }
            shot["primitive"] = "template"
            described = settings["template_id"]
        else:
            value = arguments.get("value_text")
            if not isinstance(value, str) or not value.strip() or len(value) > 400:
                return {
                    "ok": False,
                    "code": "out_of_range",
                    "message": f"{field} needs 1 to 400 characters of text.",
                    "parameter": field,
                }
            shot[field] = value
            described = field
        receipt = self._creative_result(
            self._creative(scope, expires_ns, request_id, "save_document", {"document": document})[1]
        )
        if receipt is not None:
            return receipt
        return {"ok": True, "code": "script_revised", "message": f"Saved: {shot_id} now uses {described}."}

    def _approve(self, scope, expires_ns, request_id):
        try:
            _, creative = self._current_document(scope)
        except MovementError as error:
            return _refusal(error)
        receipt = self._creative_result(
            self._creative(
                scope, expires_ns, request_id, "approve_script", {"document_digest": creative["digest"]}
            )[1]
        )
        if receipt is not None:
            return receipt
        return {
            "ok": True,
            "code": "script_approved",
            "message": "Script approved exactly as written. Ready to rehearse.",
        }

    @staticmethod
    def _creative_result(outcome):
        """None on success; the spoken failure otherwise."""
        if outcome.get("ok"):
            return None
        return {
            "ok": False,
            "code": outcome.get("code", "rejected"),
            "message": outcome.get("message", "The Director rejected this change."),
        }

    def _rehearse(self, scope):
        try:
            _, creative = self._current_document(scope)
        except MovementError as error:
            return _refusal(error)
        manifest = self.director.get(f"/api/director/studio/{scope.session_id}/{creative['digest']}")
        translated = [shot for shot in manifest["shots"] if shot.get("settings")]
        blocked = [shot["shot_id"] for shot in manifest["shots"] if not shot.get("settings")]
        for shot in translated:
            threading.Thread(
                target=self._warm_quietly,
                args=(shot["settings"],),
                name="takeone-rehearse-warm",
                daemon=True,
            ).start()
        link = f"/?script={scope.session_id}"
        if blocked:
            message = (
                f"{len(translated)} of {len(manifest['shots'])} shots translate; "
                f"fix {', '.join(blocked[:3])} first. Rehearsal opens at {link}."
            )
        else:
            message = (
                f"All {len(translated)} shots translate. The operator can open the rehearsal "
                f"at {link}; previews are warming now."
            )
        return {
            "ok": True,
            "code": "rehearsal_ready",
            "message": message,
            "studio_link": link,
            "blocked_shot_ids": blocked,
        }

    def _start_take(self, token, envelope, request_id, arguments):
        if self.recording is None:
            return {
                "ok": False,
                "code": "recorder_unavailable",
                "message": "The offline recorder is not connected.",
            }
        duration = arguments.get("duration_s")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not MIN_TAKE_SECONDS <= duration <= MAX_TAKE_SECONDS
        ):
            return {
                "ok": False,
                "code": "out_of_range",
                "message": f"duration_s must be {MIN_TAKE_SECONDS:g} to {MAX_TAKE_SECONDS:g} seconds.",
                "parameter": "duration_s",
            }
        plan_id = arguments.get("plan_id")
        if plan_id is not None and not (
            isinstance(plan_id, str) and len(plan_id) == 64 and all(c in "0123456789abcdef" for c in plan_id)
        ):
            return {
                "ok": False,
                "code": "out_of_range",
                "message": "plan_id must be the 64-character id a compile returned.",
                "parameter": "plan_id",
            }
        zoom = ZoomRamp(start_factor=1.0, end_factor=1.0, duration_ms=int(duration * 1000))
        outcome = self.recording.mutate(
            "start", token, envelope, request_id, zoom=zoom, scenario="normal", plan_id=plan_id
        )
        take = outcome["take"]
        return {
            "ok": True,
            "code": "take_started",
            "take_id": take["take_id"],
            "plan_id": take["plan_id"],
            "message": "Recording. Stay completely silent until stop_take.",
        }

    def _stop_take(self, token, envelope, request_id, arguments):
        if self.recording is None:
            return {
                "ok": False,
                "code": "recorder_unavailable",
                "message": "The offline recorder is not connected.",
            }
        take_id = arguments.get("take_id")
        if not isinstance(take_id, str) or not take_id:
            return {
                "ok": False,
                "code": "unknown_parameter",
                "message": "stop_take needs the take_id start_take returned.",
                "parameter": "take_id",
            }
        outcome = self.recording.mutate("stop", token, envelope, request_id, take_id=take_id)
        take = outcome["take"]
        return {
            "ok": True,
            "code": "take_stopped",
            "take_id": take["take_id"],
            "message": "Cut. The take is finalizing; direction can continue.",
        }
