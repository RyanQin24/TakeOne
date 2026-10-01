"""Language-to-motion contract: continuous vectors, not a catalogue of phrases."""

import math


def vector_schema():
    return dict(type="array", items=dict(type="number"), minItems=3, maxItems=3)


PROGRAM_TOOL = dict(
    type="function",
    name="prepare_arm_motion",
    description="Prepare a camera/light arm motion program for rehearsal, never execute hardware. "
    "Use arbitrary signed translation and axis-angle rotation vectors, not named motion presets. "
    "Each segment applies translation and rotation together; sequential segments run in order. "
    "A target label is not a measured target. Do not supply motor positions or permissions.",
    strict=True,
    parameters=dict(
        type="object",
        properties=dict(
            role=dict(type="string", enum=["phone", "light", "unspecified"]),
            segments=dict(
                type="array",
                minItems=1,
                maxItems=16,
                items=dict(
                    type="object",
                    properties=dict(
                        translation_m=vector_schema(),
                        rotation_rad=vector_schema(),
                        frame=dict(type="string", enum=["world", "chassis", "optical", "unspecified"]),
                        duration_s=dict(type=["number", "null"]),
                        aim_target=dict(type=["string", "null"]),
                    ),
                    required=["translation_m", "rotation_rad", "frame", "duration_s", "aim_target"],
                    additionalProperties=False,
                ),
            ),
            questions=dict(type="array", items=dict(type="string"), maxItems=8),
            assumptions=dict(type="array", items=dict(type="string"), maxItems=8),
        ),
        required=["role", "segments", "questions", "assumptions"],
        additionalProperties=False,
    ),
)

PROGRAM_INSTRUCTIONS = """
For camera/phone arm or light-arm motion use prepare_arm_motion. It accepts general vectors,
not a phrase lookup or a list of prerecorded moves. Camera means role phone.
Frames are right handed: world XYZ with Z up; chassis X backward, Y right, Z up
(chassis forward is -X); optical X right, Y down, Z forward.
Rotation is an axis-angle vector in radians, NOT Euler angles or joint angles.
Optical tilt up = positive X, tilt down = negative X; pan left = negative Y,
pan right = positive Y; clockwise image roll = positive Z.
World lowering 2 cm = translation [0,0,-0.02], rotation [0,0,0], frame world.
Diagonal/simultaneous movement uses one vector segment. 'Then' means separate ordered segments.
Do not rotate the cart to satisfy an arm request. All coordinates are relative increments;
never invent current encoder values, world positions, target depth, or calibration.
Convert explicit units faithfully, including inches to metres and degrees to radians.
For 'a little' propose 0.02 m or 5 degrees and disclose it in assumptions. Unspecified timing
is null: the local planner proposes a duration from joint-motion policy. Do not fabricate timing.
For ambiguous arm, viewpoint or tilt direction put the unresolved question in questions;
use unspecified role/frame or a zero vector for the unresolved part. Never guess the direction.
For 'face us/me/the selected person', preserve a label in aim_target, use zero rotation and
do not invent coordinates. The operator chose a selected person in the camera view.
Negations, explanations, hypotheticals and quoted movement are not motion requests.
Corrections replace a proposal, not an extra reversal. Stop immediately uses stop_robot.
Rehearsal is simulated, not measured movement. A rejected path is not proof no path exists.
The page cannot execute arms; cart Run never executes arms. State the returned limitations.
"""


def prepare_program(request):
    schema = PROGRAM_TOOL["parameters"]
    if not isinstance(request, dict) or set(request) != set(schema["properties"]):
        raise ValueError("Expected role, segments, questions and assumptions only")
    role = request["role"]
    if role not in ("phone", "light", "unspecified"):
        raise ValueError("Unknown arm role")
    texts = {}
    for key in ("questions", "assumptions"):
        values = request[key]
        if (
            not isinstance(values, list)
            or len(values) > 8
            or any(not isinstance(v, str) or not 1 <= len(v.strip()) <= 240 for v in values)
        ):
            raise ValueError(f"Invalid {key}")
        texts[key] = list(values)
    if role == "unspecified":
        texts["questions"].append("Which arm: camera or light?")
    segments = request["segments"]
    if not isinstance(segments, list) or not 1 <= len(segments) <= 16:
        raise ValueError("A finite program needs 1 to 16 segments")
    normalized = []
    for i, segment in enumerate(segments):
        if not isinstance(segment, dict) or set(segment) != {
            "translation_m",
            "rotation_rad",
            "frame",
            "duration_s",
            "aim_target",
        }:
            raise ValueError("Unexpected segment fields")
        row = dict(segment)
        for key, bound in (("translation_m", 2.0), ("rotation_rad", math.pi)):
            vector = row[key]
            if (
                not isinstance(vector, list)
                or len(vector) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
            ):
                raise ValueError(f"{key} must contain three finite numbers")
            if math.sqrt(sum(v * v for v in vector)) > bound + 1e-12:
                raise ValueError(f"{key} exceeds the finite planner domain, not a physical safety limit")
            row[key] = list(vector)
        if row["frame"] not in ("world", "chassis", "optical", "unspecified"):
            raise ValueError("Unknown coordinate frame")
        if row["frame"] == "unspecified":
            texts["questions"].append(f"Segment {i + 1}: relative to which frame?")
        duration = row["duration_s"]
        if duration is not None and (
            type(duration) not in (int, float) or not math.isfinite(duration) or not 0.04 <= duration <= 120
        ):
            raise ValueError("Duration must be 0.04 to 120 seconds, or unspecified")
        target = row["aim_target"]
        if target is not None and (not isinstance(target, str) or not 1 <= len(target.strip()) <= 120):
            raise ValueError("Aim target must be a short label")
        if target and any(row["rotation_rad"]):
            raise ValueError("Separate explicit rotation and target aiming into ordered segments")
        normalized.append(row)
    return dict(
        ok=True,
        code="clarification_required" if texts["questions"] else "arm_program_prepared",
        program=dict(role=role, segments=normalized, **texts),
        hardware_commands_sent=False,
        physical_motion_verified=False,
        executable=False,
        message="Motion program prepared, not executed. Rehearsal needs an explicit starting pose; "
        "selected-person aiming needs a connected, calibrated perception source.",
    )
