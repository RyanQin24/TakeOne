"""Validated camera-space intent, never servo commands or hardware authority."""

import math

TRANSLATIONS = ("raise", "lower", "left", "right", "forward", "backward")
ROTATIONS = ("pan_left", "pan_right", "tilt_up", "tilt_down", "roll_left", "roll_right")
ACTIONS = (*TRANSLATIONS, *ROTATIONS, "face_target", "tilt_unspecified")
FRAMES = ("world", "chassis", "tool", "unspecified")

ARM_TOOL = dict(
    type="function",
    name="prepare_arm_adjustment",
    description="Interpret camera/phone or light ARM requests, not cart motion. "
    "Preserve all requested operations in order. This only prepares semantic intent, never moves. "
    "Amounts are metres for translations, radians for rotations, null when unspecified. "
    "Use tilt_unspecified for 'tilt it' without a direction. 'Face us' is face_target with target='us'; "
    "never invent where a person is. Do not supply joint angles, measured poses or permissions.",
    strict=True,
    parameters=dict(
        type="object",
        properties=dict(
            role=dict(type="string", enum=["phone", "light", "unspecified"]),
            operations=dict(
                type="array",
                minItems=1,
                maxItems=8,
                items=dict(
                    type="object",
                    properties=dict(
                        action=dict(type="string", enum=list(ACTIONS)),
                        amount=dict(type=["number", "null"]),
                        frame=dict(type="string", enum=list(FRAMES)),
                        target=dict(type=["string", "null"]),
                    ),
                    required=["action", "amount", "frame", "target"],
                    additionalProperties=False,
                ),
            ),
        ),
        required=["role", "operations"],
        additionalProperties=False,
    ),
)

ARM_INSTRUCTIONS = """
For camera/phone arm or light arm adjustments call prepare_arm_adjustment, not request_robot_move
or prepare_robot_shot. Camera arm means role phone; do not guess a role for 'the arm'.
Translate every clause in order: 'lower, tilt down, face us' is three operations, not just aiming.
Lower/raise without another explicit frame means world vertical. Horizontal left/right/forward/back
without a specified viewpoint has frame unspecified; never assume the speaker's left is robot left.
Pan/tilt/roll are optical rotations in tool frame unless specified otherwise.
Convert cm/mm/inches to metres and degrees to radians. Unspecified or 'little' amounts remain null;
the local compiler may propose a labelled small increment for review, never silently execute it.
'Tilt it' has no direction: tilt_unspecified. 'Face us/me/the actor' means face_target and preserves
that target label verbatim. A label is NOT a measured location. Never fabricate detections or a pose.
Negation, hypothetical questions, quoted speech and 'can you explain' are not permission to move.
Stop/cancel requests use stop_robot. A correction replaces the proposed intent, never adds an
unrequested opposite movement. A prepared/clarification result is not a physical arm movement.
Do not suggest that the cart Run button runs an arm request. The live arm controller is not connected.
"""


def prepare_arm_intent(request):
    if not isinstance(request, dict) or set(request) != {"role", "operations"}:
        raise ValueError("Arm request requires only role and operations")
    role, operations = request["role"], request["operations"]
    if role not in ("phone", "light", "unspecified"):
        raise ValueError("Unknown arm role")
    if not isinstance(operations, list) or not 1 <= len(operations) <= 8:
        raise ValueError("Specify one to eight arm operations")
    questions, normalized, defaults = [], [], []
    if role == "unspecified":
        questions.append("Which arm: camera or light?")
    translation_total = rotation_total = 0.0
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict) or set(operation) != {"action", "amount", "frame", "target"}:
            raise ValueError("Invalid arm operation fields")
        action, amount, frame, target = (operation[k] for k in ("action", "amount", "frame", "target"))
        if action not in ACTIONS or frame not in FRAMES:
            raise ValueError("Unsupported arm action or coordinate frame")
        if target is not None and (not isinstance(target, str) or not 1 <= len(target.strip()) <= 120):
            raise ValueError("Target must be a short, nonempty label")
        if amount is not None and (
            type(amount) not in (int, float) or not math.isfinite(amount) or amount <= 0
        ):
            raise ValueError("Amount must be a finite positive SI value or null")
        if action in ("face_target", "tilt_unspecified"):
            if amount is not None:
                raise ValueError("This operation does not accept a magnitude")
            if action == "tilt_unspecified":
                questions.append("Tilt up or down, and by how much?")
            elif target is None:
                questions.append("Who or what should the arm face?")
        elif target is not None:
            raise ValueError("Only face_target accepts a target label")
        unit = "m" if action in TRANSLATIONS else "rad" if action in ROTATIONS else None
        if unit:
            if amount is None:
                amount = 0.02 if unit == "m" else math.radians(5)
                defaults.append(dict(operation=index, proposed_amount=amount, unit=unit))
            maximum = 0.10 if unit == "m" else math.radians(15)
            if amount > maximum + 1e-12:
                raise ValueError("Increment exceeds the preview envelope: 10 cm or 15 degrees per operation")
            if unit == "m":
                translation_total += amount
            else:
                rotation_total += amount
            if frame == "unspecified":
                questions.append(f"Operation {index + 1}: relative to the chassis, camera, or world?")
            if frame == "world" and action not in ("raise", "lower"):
                questions.append(
                    f"Operation {index + 1}: world left/forward/rotation needs an explicit axis; use chassis or tool frame."
                )
            if action in ROTATIONS and frame != "tool":
                questions.append(
                    f"Operation {index + 1}: this preview supports optical rotations in tool frame only."
                )
        normalized.append(dict(action=action, amount=amount, unit=unit, frame=frame, target=target))
    if translation_total > 0.10 + 1e-12 or rotation_total > math.radians(30) + 1e-12:
        raise ValueError("Compound request exceeds the total 10 cm / 30 degree preview envelope")
    return dict(
        ok=True,
        code="clarification_required" if questions else "arm_intent_prepared",
        intent=dict(role=role, operations=normalized),
        questions=list(dict.fromkeys(questions)),
        proposed_defaults=defaults,
        target_labels=[o["target"] for o in normalized if o["action"] == "face_target" and o["target"]],
        hardware_commands_sent=False,
        executable=False,
        physical_motion_verified=False,
        blockers=[
            "Fresh arm feedback and a supervised arm owner are not connected to this page.",
            "Named targets require a selected, localized subject; no camera perception is sent here.",
            "A solved endpoint is not a collision-checked trajectory or physical qualification.",
        ],
        message="Arm intent interpreted only. Resolve questions and review proposed increments. "
        "Do not use the cart Run button for this request; no arm movement has been sent.",
    )
