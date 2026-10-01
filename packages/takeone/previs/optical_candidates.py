"""Bounded alternative base placements for an explicit fixed-frame optical path.

Every candidate uses the existing compiler, identical actor/lens/timing intent,
and unchanged world-space optical keys. Nothing selects/applies itself. This is
an offline placement search, not a new compiler or live controller.
"""

import copy
import math

from takeone.motion.plan import digest

from .cache import compile_preview
from .templates import path_settings, validate_settings


def candidates(body):
    if not isinstance(body, dict) or set(body) != {"settings", "offsets_m"}:
        raise ValueError("Candidate search needs settings and explicit permitted base offsets_m.")
    settings = validate_settings(body["settings"])
    optical = settings["channels"].get("camera_position_m")
    if not optical:
        raise ValueError("Author a fixed-frame optical path before searching base placements.")
    offsets = body["offsets_m"]
    if not isinstance(offsets, list) or not 1 <= len(offsets) <= 5:
        raise ValueError("Try one to five explicitly allowed base offsets.")
    for offset in offsets:
        if (
            not isinstance(offset, list)
            or len(offset) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 0.3 for v in offset)
        ):
            raise ValueError("Each base offset needs two finite metres within +/-0.3 m.")
    start = settings["scene"]["cart_start_m"] or path_settings(settings)["points_m"][0]
    rows = []
    for offset in offsets:
        candidate = copy.deepcopy(settings)
        candidate["scene"]["cart_start_m"] = [a + b for a, b in zip(start, offset)]
        try:
            preview = compile_preview(candidate)
        except ValueError as error:
            rows.append(dict(offset_m=offset, status="unavailable", reason=str(error), settings=candidate))
            continue
        summary = preview["summary"]
        position = summary.get("max_camera_position_error_m")
        aim = summary["max_aim_error_deg"]
        rows.append(
            dict(
                offset_m=offset,
                status="task_corridor_met"
                if position is not None and position <= 0.03 and aim <= 1
                else "needs_revision",
                max_position_error_m=position,
                max_aim_error_deg=aim,
                plan_id=preview["plan_id"],
                source_duration_s=preview["orbit_duration_s"],
                settings=candidate,
            )
        )
    return dict(
        source="bounded_offline_placement_search",
        optical_intent_digest=digest(optical),
        candidates=rows,
        applied=False,
        scope="Position/aim corridors only. Actor timing, lens and desired path were not changed. "
        "Inspect clearance, joint derivatives and the achieved phone view before explicitly applying a candidate. No hardware qualification.",
    )
