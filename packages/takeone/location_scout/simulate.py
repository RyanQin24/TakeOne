"""Simulation is the authority. A proposal is feasible only when the rig says so.

Every staging candidate goes through the existing TakeOne compiler — the same
``previs.templates.compile_template`` Shot Studio uses, with the same IK, joint
limits, cart response and lens curve. Nothing here relaxes a check to make a
location look better, and nothing here turns a simulated result into a physical
claim: the rig still needs local registration and its cart still has no
position feedback.

Failed candidates are kept. Why a location cannot hold a shot is as useful to a
director as which shot it can hold.
"""

from __future__ import annotations

import math
import time

from . import geometry
from .affordances import WorldIndex
from .candidates import ACTOR_RADIUS_M, PATH_MARGIN_M, ROBOT_RADIUS_M

# Subject distance bands the framing words mean, from previs.templates.
FRAMING_BANDS = {"wide": (2.2, 3.4), "medium": (1.0, 1.6), "close_up": (0.40, 0.70)}
# A tracking shot holds the subject at the standoff, not at portrait distance,
# so the band is checked as a ratio against what the staging asked for.
FRAMING_TOLERANCE = 0.35
MAX_SIMULATED = 8
UNKNOWN_REJECT_FRACTION = 0.5


class Verdict:
    """One candidate's result. Hard constraints first; scores never override them."""

    def __init__(self, candidate):
        self.candidate = candidate
        self.compiled = False
        self.failures = []
        self.advisories = []
        self.achieved = {}
        self.scores = {}
        self.preview = None
        self.plan_id = None
        self.skipped = False
        # The validated settings the compiler accepted. Shot Studio replays
        # exactly these, so what it rehearses is what World Scout simulated.
        self.settings = None

    @property
    def feasible(self):
        return self.compiled and not self.failures

    def wire(self, *, include_frames=False):
        body = {
            **self.candidate.wire(),
            "compiled": self.compiled,
            "feasible": self.feasible,
            "failures": list(self.failures),
            "advisories": list(self.advisories),
            "achieved": dict(self.achieved),
            "scores": dict(self.scores),
            "score": round(self.total, 4),
            "plan_id": self.plan_id,
            "settings": self.settings,
            "physical_feasibility": (
                "simulated_pass" if self.feasible else "not_simulated" if self.skipped else "rejected"
            ),
            "skipped": self.skipped,
            "physical_status": (
                "Simulated on the real rig model. Local registration on site is still required and the "
                "cart has no position feedback, so real-world straightness remains unqualified."
            ),
        }
        if include_frames and self.preview is not None:
            body["preview"] = self.preview
        return body

    @property
    def total(self):
        if not self.feasible:
            return 0.0
        weights = {
            "background_depth": 0.22,
            "clearance_headroom": 0.22,
            "framing": 0.20,
            "aim_accuracy": 0.14,
            "travel_accuracy": 0.10,
            "unknown_exposure": 0.12,
        }
        return sum(self.scores.get(key, 0.0) * weight for key, weight in weights.items())


def framing_for(distance_m):
    """Which framing word the achieved subject distance actually lands in."""
    for name, (low, high) in FRAMING_BANDS.items():
        if low <= distance_m <= high:
            return name
    return "wider_than_wide" if distance_m > FRAMING_BANDS["wide"][1] else "tighter_than_close_up"


def _filmed_frames(preview):
    start = preview.get("orbit_start_s", 0.0) - 1e-9
    frames = [frame for frame in preview["frames"] if frame["time_s"] >= start]
    return frames or preview["frames"]


def _polyline_check(index, points, radius_m, margin_m):
    """Achieved path against the metre world. Nominal screening, not safety."""
    worst = math.inf
    unknown = 0
    for point in points:
        worst = min(worst, index.clearance(point))
        if index.is_unknown(point):
            unknown += 1
    for start, end in zip(points, points[1:]):
        if math.dist(start, end) > 1e-6:
            worst = min(worst, geometry.segment_clearance_to_rings(start, end, index.obstacles))
    return {
        "min_clearance_m": round(max(worst, 0.0) if math.isfinite(worst) else 99.0, 3),
        "required_m": round(radius_m + margin_m, 3),
        "unknown_fraction": round(unknown / max(1, len(points)), 3),
        "clear": (worst if math.isfinite(worst) else 99.0) >= radius_m + margin_m,
    }


def _score_band(value, best, worst):
    if best == worst:
        return 1.0
    return max(0.0, min(1.0, (value - worst) / (best - worst)))


def evaluate(candidate, world, index=None, *, include_frames=False, subject_height_m=1.72):
    """Compile one candidate on the real rig model and judge the result."""
    from takeone.previs.templates import compile_template

    index = index or WorldIndex(world)
    verdict = Verdict(candidate)
    if candidate.rejected_reason:
        verdict.failures.append(candidate.rejected_reason)
        return verdict
    try:
        result = compile_template(candidate.template_settings(subject_height_m=subject_height_m))
    except (ValueError, KeyError, ArithmeticError) as error:
        verdict.failures.append(f"The rig compiler refused this staging: {error}")
        return verdict
    except Exception as error:  # noqa: BLE001 - the compiler's own refusal is the answer
        verdict.failures.append(f"The rig compiler could not solve this staging: {type(error).__name__}")
        return verdict

    verdict.compiled = True
    preview = result["preview"]
    summary = preview["summary"]
    verdict.plan_id = preview.get("plan_id")
    verdict.settings = preview.get("settings")
    frames = _filmed_frames(preview)
    cart_path = [tuple(frame["axle_m"][:2]) for frame in frames]
    actor_path = [tuple(frame["actor"]["position_m"][:2]) for frame in frames]

    cart = _polyline_check(index, cart_path, ROBOT_RADIUS_M, PATH_MARGIN_M)
    actor = _polyline_check(index, actor_path, ACTOR_RADIUS_M, 0.0)

    # ---- hard constraints, in the order a director would ask about them ----
    if not summary.get("within_joint_ranges", False):
        verdict.failures.append("The camera arm cannot hold this framing inside its joint ranges.")
    if summary.get("lens_clamped"):
        requested = summary.get("requested_focal_mm", [])
        verdict.failures.append(
            f"The shot needs a focal length outside the phone's {summary.get('lens_range_mm')} mm range "
            f"(asked for {requested})."
        )
    if not cart["clear"]:
        verdict.failures.append(
            f"The cart's achieved path comes within {cart['min_clearance_m']:.2f} m of mapped geometry; "
            f"it needs {cart['required_m']:.2f} m."
        )
    if not actor["clear"]:
        verdict.failures.append(
            f"The performer's achieved path comes within {actor['min_clearance_m']:.2f} m of mapped geometry."
        )
    if cart["unknown_fraction"] > UNKNOWN_REJECT_FRACTION:
        verdict.failures.append(
            f"{cart['unknown_fraction'] * 100:.0f}% of the achieved cart path crosses ground with no "
            "coverage. Unknown ground is not clear ground."
        )

    # ---- advisories: true, worth saying, not disqualifying ----
    achieved_distance = float(summary.get("subject_distance_m", 0.0))
    achieved_framing = framing_for(achieved_distance)
    framing_error = abs(achieved_distance - candidate.standoff_m) / max(candidate.standoff_m, 0.1)
    if framing_error > FRAMING_TOLERANCE:
        verdict.advisories.append(
            f"The camera settles {achieved_distance:.2f} m from the performer, not the {candidate.standoff_m:.2f} m "
            "the staging asked for."
        )
    if summary.get("retimed") or candidate.pace_clipped:
        verdict.advisories.append(
            f"The cart cannot cover {candidate.travel_m:.1f} m in {candidate.duration_s:.1f} s. At its "
            f"policy maximum of {candidate.pace_m_s:.2f} m/s the move runs "
            f"{summary.get('orbit_duration_s', 0):.1f} s."
        )
    if summary.get("max_command", 0) >= 0.15 - 1e-9:
        verdict.advisories.append(
            "The cart runs at its UART command ceiling for part of this move; there is no speed headroom."
        )
    if cart["unknown_fraction"] > 0:
        verdict.advisories.append(
            f"{cart['unknown_fraction'] * 100:.0f}% of the cart path crosses unsurveyed ground."
        )

    verdict.achieved = {
        "shot_duration_s": round(float(summary.get("orbit_duration_s", 0.0)), 2),
        "total_duration_s": round(float(summary.get("duration_s", 0.0)), 2),
        "cart_travel_m": round(float(summary.get("distance_m", 0.0)), 3),
        "requested_travel_m": round(float(summary.get("requested_distance_m", 0.0)), 3),
        "endpoint_error_m": round(float(summary.get("endpoint_error_m", 0.0)), 4),
        "subject_distance_m": round(achieved_distance, 3),
        "requested_framing": candidate.framing,
        "achieved_framing": achieved_framing,
        "max_aim_error_deg": round(float(summary.get("max_aim_error_deg", 0.0)), 3),
        "camera_height_m": round(float(summary.get("camera_height_m", 0.0)), 3),
        "peak_speed_m_s": round(float(summary.get("peak_speed_m_s", 0.0)), 4),
        "max_command": summary.get("max_command"),
        "focal_start_mm": summary.get("focal_start_mm"),
        "focal_end_mm": summary.get("focal_end_mm"),
        "lens_range_mm": summary.get("lens_range_mm"),
        "within_joint_ranges": bool(summary.get("within_joint_ranges", False)),
        "lens_clamped": bool(summary.get("lens_clamped", False)),
        "physical_path_verified": bool(summary.get("physical_path_verified", False)),
        "cart_path_screen": cart,
        "actor_path_screen": actor,
        "frame_count": len(frames),
    }
    verdict.scores = {
        "background_depth": _score_band(_axis_depth(index, candidate), 40.0, 4.0),
        "clearance_headroom": _score_band(cart["min_clearance_m"], 3.0, cart["required_m"]),
        "framing": _score_band(-framing_error, 0.0, -FRAMING_TOLERANCE * 2),
        "aim_accuracy": _score_band(-float(summary.get("max_aim_error_deg", 0.0)), 0.0, -3.0),
        "travel_accuracy": _score_band(-float(summary.get("endpoint_error_m", 0.0)), 0.0, -0.25),
        "unknown_exposure": 1.0 - min(1.0, cart["unknown_fraction"] * 2),
    }
    if include_frames:
        verdict.preview = preview
    return verdict


def _axis_depth(index, candidate):
    """How far the camera can see past the performer along the shot's own axis."""
    return index.ray_depth(candidate.actor_end_m, candidate.actor_heading_rad)


def evaluate_all(candidates, world, *, limit=MAX_SIMULATED, budget_s=90.0, subject_height_m=1.72):
    """Compile the shortlist, keep every verdict, best feasible result first."""
    index = WorldIndex(world)
    verdicts = []
    started = time.monotonic()
    simulated = 0
    for candidate in candidates:
        if candidate.rejected_reason:
            verdicts.append(evaluate(candidate, world, index))
            continue
        if simulated >= limit or time.monotonic() - started > budget_s:
            verdict = Verdict(candidate)
            verdict.skipped = True
            verdict.failures.append(
                "Not simulated: the shortlist's simulation budget was spent on higher-ranked staging. "
                "Raise the limit to evaluate this one."
            )
            verdicts.append(verdict)
            continue
        simulated += 1
        verdicts.append(evaluate(candidate, world, index, subject_height_m=subject_height_m))
    verdicts.sort(key=lambda v: (not v.feasible, v.skipped, -v.total, v.candidate.candidate_id))
    return verdicts
