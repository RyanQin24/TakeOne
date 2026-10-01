"""Select one reviewed shot window from a compiled motor plan. No device IO."""

import copy
import math

from takeone.calibration import ArmMapping
from takeone.config import finite
from takeone.motion.plan import digest
from takeone.motion.studio_plan import ARM_PERIOD, CART_PERIOD, ROLES, prepare, validate
from takeone.previs.start_pose import aiming_counts
from takeone.protocol import uart_pair


def prepare_shot(settings, window):
    source = prepare(settings)
    if not isinstance(window, dict) or window.get("plan_id") != source["plan_id"]:
        raise ValueError("The selected shot changed. Reload its preview before filming.")
    start = finite(window.get("start_s"), "Shot start")
    requested = finite(window.get("duration_s"), "Shot duration")
    if start < 0 or requested <= 0 or start + requested > source["duration_s"] + 1e-6:
        raise ValueError("The selected shot is outside its reviewed motor timeline.")
    setup = source["orbit_start_s"]
    if start and start < setup - 1e-6:
        raise ValueError("A shot cannot begin partway through the starting pose sequence.")
    if not start and requested <= setup:
        raise ValueError("The selected shot contains only setup, with no filming movement.")
    # A cropped continuation is a separate take: approach its first arm pose
    # with the cart stationary, then execute only its source interval.
    offset = setup if start else 0.0
    duration = math.ceil((requested + offset) / ARM_PERIOD - 1e-8) * ARM_PERIOD
    plan = copy.deepcopy(source)
    mappings = {role: ArmMapping.load(role, require_motion=False) for role in ROLES}

    def source_raw(stamp):
        index = min(round(stamp / ARM_PERIOD), len(source["samples"]) - 1)
        return copy.deepcopy(source["samples"][index]["raw_by_role"])

    first = source_raw(start)
    samples = []
    for index in range(round(duration / ARM_PERIOD) + 1):
        stamp = index * ARM_PERIOD
        raw = (
            aiming_counts(source["initial_raw"], first, stamp / offset)
            if offset and stamp < offset
            else source_raw(min(start + requested, start + max(0, stamp - offset)))
        )
        samples.append(
            dict(
                time_s=stamp,
                raw_by_role=raw,
                arms={role: mappings[role].from_raw(raw[role]) for role in ROLES},
            )
        )
    schedule = []
    for index in range(round(duration / CART_PERIOD)):
        stamp = index * CART_PERIOD
        if stamp < offset or stamp >= offset + requested:
            pair = [0.0, 0.0]
        else:
            source_index = min(
                int((start + stamp - offset) / CART_PERIOD + 1e-8), len(source["cart_schedule"]) - 1
            )
            pair = list(source["cart_schedule"][source_index]["commands"])
        schedule.append(dict(time_s=stamp, commands=pair, wire=uart_pair(*pair)))
    schedule.append(dict(time_s=duration, commands=[0.0, 0.0], wire=uart_pair(0, 0)))
    cues = source["camera_cues"]

    def focal_at(stamp):
        for a, b in zip(cues, cues[1:]):
            if stamp <= b["time_s"]:
                mix = max(0, (stamp - a["time_s"]) / (b["time_s"] - a["time_s"]))
                return a["focal_mm"] + mix * (b["focal_mm"] - a["focal_mm"])
        return cues[-1]["focal_mm"]

    camera_cues = [dict(time_s=0.0, focal_mm=focal_at(start))]
    if offset:
        camera_cues.append(dict(time_s=offset, focal_mm=focal_at(start)))
    camera_cues.extend(
        dict(time_s=offset + cue["time_s"] - start, focal_mm=cue["focal_mm"])
        for cue in cues
        # Browser and motor clocks can represent the same boundary a few
        # floating-point bits apart. Boundary cues are supplied explicitly;
        # retain only interior cues, including after shifting to the shot clock.
        if start + 1e-7 < cue["time_s"] < start + requested - 1e-7
        and offset + cue["time_s"] - start < duration - 1e-7
    )
    camera_cues.append(dict(time_s=duration, focal_mm=focal_at(start + requested)))
    plan.update(
        duration_s=duration,
        orbit_start_s=setup,
        orbit_duration_s=duration - setup,
        samples=samples,
        cart_schedule=schedule,
        raw_goals=samples[-1]["raw_by_role"],
        camera_cues=camera_cues,
        record_shot=dict(
            source_plan_id=source["plan_id"], start_s=start, duration_s=requested, preview_offset_s=offset
        ),
    )
    plan["summary"].update(
        duration_s=duration,
        orbit_duration_s=duration - setup,
        setup_duration_s=setup,
        requested_duration_s=requested,
    )
    plan["plan_id"] = digest({key: value for key, value in plan.items() if key != "plan_id"})
    return validate(plan)
