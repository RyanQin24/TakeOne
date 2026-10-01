"""Check named boom intent against achieved optical samples, without another solve.

Height keys explicitly override the preset within their full-take intervals.
Reports use edit-local seconds plus source ranges; setup and unused tails cannot
satisfy a filmed move. The millimetre tolerance detects numerical no-ops, not
cinematic quality, mechanical accuracy or physical readiness.
"""

import math
from bisect import bisect_right
from dataclasses import asdict, dataclass
from typing import Literal

from .channels import channel
from .choreography import camera_height

EPSILON_M = 0.001
TIME_EPSILON_S = 1e-8
BOOM_DIRECTIONS = {"boom_up": 1, "boom_down": -1}


@dataclass(frozen=True, slots=True)
class MotionIssue:
    code: str
    severity: Literal["revision", "manual"]
    time_range_s: tuple[float, float]
    observation: str
    evidence: dict
    recommendation: str

    def wire(self):
        return {**asdict(self), "time_range_s": list(self.time_range_s)}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def optical_height(frame):
    position = (frame.get("camera") or {}).get("pos")
    if not isinstance(position, (list, tuple)) or len(position) != 3:
        return None
    return float(position[2]) if all(finite(v) for v in position) else None


def requested_height(settings, fraction):
    # Reuse the compiler's actual choreography and override evaluators.
    position = channel(settings, "camera_position_m", fraction)
    if position is not None:
        return position[2]
    fallback = camera_height(settings, fraction, settings["height_start_m"])
    return channel(settings, "camera_height_m", fraction, fallback)


def direction(delta):
    return "up" if delta > EPSILON_M else "down" if delta < -EPSILON_M else "hold"


def review_motion(shot, settings, preview):
    template = settings["template_id"]
    if template not in BOOM_DIRECTIONS:
        return None
    setup = preview.get("orbit_start_s")
    available = preview.get("orbit_duration_s")
    source_in = preview.get("source_in_s", 0.0)
    source_duration = preview.get("source_duration_s", available)
    edit_duration = (shot["end_ms"] - shot["start_ms"]) / 1000
    keys = (
        settings.get("channels", {}).get("camera_position_m")
        or settings.get("channels", {}).get("camera_height_m")
        or []
    )
    result = dict(
        template_id=template,
        source="simulated_achieved_optical_pose",
        intent_source="camera_height_keyframes" if keys else "named_boom",
        tolerance_m=EPSILON_M,
        timebase="edit-local seconds, excluding setup",
        source_in_s=source_in if finite(source_in) else None,
        source_duration_s=source_duration if finite(source_duration) else None,
        status="reviewable",
        checks=[],
        issues=[],
    )

    def unavailable(message, interval=(0.0, edit_duration)):
        issue = MotionIssue(
            "boom_motion_evidence_missing",
            "manual",
            interval,
            message,
            dict(source="simulated_achieved_optical_pose"),
            "Recompile and inspect the achieved camera samples; missing evidence is not a pass.",
        )
        result["status"] = "unverified"
        result["issues"].append(issue.wire())
        return result

    if not all(finite(v) for v in (setup, available, source_in, source_duration)):
        return unavailable("The source timing needed for the boom check is missing or non-finite.")
    if setup < 0 or available <= 0 or source_duration <= 0 or source_in < 0 or edit_duration <= 0:
        return unavailable("The source timing does not define a positive filmed window.")
    duration = min(available, edit_duration)
    if source_in + duration > source_duration + TIME_EPSILON_S:
        return unavailable("The edited window exceeds its declared full-take source duration.")
    all_frames = preview.get("frames", [])
    if any(not finite(f.get("time_s")) for f in all_frames):
        return unavailable("An optical sample has no finite timestamp.")
    filmed = [
        f for f in all_frames if setup - TIME_EPSILON_S <= f["time_s"] <= setup + available + TIME_EPSILON_S
    ]
    stamps = [f["time_s"] - setup for f in filmed]
    if len(stamps) < 2 or any(b <= a for a, b in zip(stamps, stamps[1:])):
        return unavailable("At least two ordered, distinct filmed optical samples are required.")
    if stamps[0] > TIME_EPSILON_S or stamps[-1] < duration - TIME_EPSILON_S:
        return unavailable("The achieved samples do not cover both edited-window boundaries.")
    cuts = [0.0, duration]
    cuts += [
        k["at"] * source_duration - source_in
        for k in keys
        if TIME_EPSILON_S < k["at"] * source_duration - source_in < duration - TIME_EPSILON_S
    ]
    cuts = sorted(set(cuts))
    full_delta = requested_height(settings, 1.0) - requested_height(settings, 0.0)
    label_sign = BOOM_DIRECTIONS[template]
    for begin, end in zip(cuts, cuts[1:]):
        # Match capture.window's held real-FK boundary convention, never interpolate a new pose.
        left = bisect_right(stamps, begin + TIME_EPSILON_S) - 1
        right = bisect_right(stamps, end + TIME_EPSILON_S) - 1
        selected = filmed[left : right + 1]
        heights = [optical_height(f) for f in selected]
        if len(selected) < 2 or any(h is None for h in heights):
            return unavailable(
                "Achieved raw optical heights are missing or undersampled in this interval.", (begin, end)
            )
        requested = [requested_height(settings, (source_in + t) / source_duration) for t in (begin, end)]
        requested_delta = requested[1] - requested[0]
        achieved_delta = heights[-1] - heights[0]
        expected = direction(requested_delta)
        if not keys and label_sign * full_delta <= EPSILON_M:
            expected = "up" if label_sign > 0 else "down"
        check = dict(
            time_range_s=[begin, end],
            source_range_s=[source_in + begin, source_in + end],
            expected_direction=expected,
            requested_height_m=requested,
            achieved_height_m=[heights[0], heights[-1]],
            achieved_span_m=max(heights) - min(heights),
            requested_delta_m=requested_delta,
            achieved_delta_m=achieved_delta,
            samples_examined=len(selected),
            sample_source_range_s=[source_in + stamps[left], source_in + stamps[right]],
            boundary_sampling="held preceding filmed FK sample",
            status="reviewable",
        )
        result["checks"].append(check)
        code, observation = None, ""
        if not keys and abs(full_delta) <= EPSILON_M:
            code = "boom_authored_no_motion"
            observation = f"{template} names a vertical move, but the authored full-take height change is {full_delta:.4f} m."
        elif not keys and label_sign * full_delta < -EPSILON_M:
            code = "boom_authored_wrong_direction"
            observation = f"{template} disagrees with the authored {direction(full_delta)} height change."
        elif expected == "hold" and check["achieved_span_m"] > EPSILON_M:
            code = "boom_hold_not_realized"
            observation = (
                "This authored interval holds height, but the achieved optical trajectory changes height."
            )
        elif expected != "hold" and direction(achieved_delta) != expected:
            code = (
                "boom_motion_not_realized"
                if abs(achieved_delta) <= EPSILON_M
                else "boom_motion_wrong_direction"
            )
            observation = f"The authored {expected} move changes height by {requested_delta:.4f} m; the achieved optical change is {achieved_delta:.4f} m."
        if code:
            check["status"] = "needs_revision"
            result["status"] = "needs_revision"
            result["issues"].append(
                MotionIssue(
                    code,
                    "revision",
                    (begin, end),
                    observation,
                    dict(check),
                    "Review the height keys, achieved pose and solver limits. Author the intended move or explicitly choose a held interval; the review never renames or moves the camera.",
                ).wire()
            )
    result["scope"] = (
        "Height keys override the preset only on their full-take intervals. "
        "This checks sampled height direction, not exact path tracking, smoothness or hardware qualification."
        if keys
        else "Preset timing may hold height outside its rise interval. This checks sampled height direction, "
        "not exact path tracking, smoothness or hardware qualification."
    )
    return result
