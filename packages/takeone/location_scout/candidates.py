"""Bounded, deterministic staging candidates for one shot at one location.

The enumeration is combinatorial but capped and ordered: three axes, two robot
sides, a small movement set, deduplicated, then truncated. Nothing here is a
creative judgement and nothing here is a feasibility claim — a candidate is a
proposal that the existing TakeOne compiler will accept or refuse in
``simulate.py``.

Cheap planning-world screening happens first so the expensive compiler only
ever runs on staging the metre world already agrees with. Candidates the world
rejects are kept, with the reason, because "why not here" is worth showing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import geometry
from .affordances import WorldIndex, tracking_axes

MAX_CANDIDATES = 12
DEFAULT_TRAVEL_M = 4.0
ROBOT_RADIUS_M = 0.45
ACTOR_RADIUS_M = 0.36
PATH_MARGIN_M = 0.6
# previs_policy.cart_pace_max_m_s in configs/arm-execution.json, and the
# template field bound. World Scout never proposes a pace outside them; when a
# requested duration would need more, the compiler retimes and says so.
CART_PACE_MIN_M_S = 0.14
CART_PACE_MAX_M_S = 0.50

# Movement templates World Scout is allowed to propose, with the cart/actor
# relationship each one implies. Every id exists in previs.templates.PRESETS.
MOVEMENTS = (
    {
        "template_id": "side_track",
        "relation": "side",
        "needs_walk": True,
        "framing": "medium",
        "focal_mm": 35.0,
        "reason": "Travels beside the performer so the background slides across frame.",
    },
    {
        "template_id": "track_follow",
        "relation": "follow",
        "needs_walk": True,
        "framing": "medium",
        "focal_mm": 35.0,
        "reason": "Stays behind the performer; the destination stays unseen until they arrive.",
    },
    {
        "template_id": "track_lead",
        "relation": "lead",
        "needs_walk": True,
        "framing": "medium",
        "focal_mm": 50.0,
        "reason": "Leads the performer so the face carries the beat and the space opens behind them.",
    },
    {
        "template_id": "push_in",
        "relation": "push",
        "needs_walk": False,
        "framing": "medium",
        "focal_mm": 35.0,
        "reason": "Closes distance on a held performance; background depth compresses as it goes.",
    },
    {
        "template_id": "arc_left",
        "relation": "arc",
        "needs_walk": False,
        "framing": "medium",
        "focal_mm": 35.0,
        "reason": "Sweeps the background behind a stationary performer to reveal the space.",
    },
    {
        "template_id": "static",
        "relation": "static",
        "needs_walk": True,
        "framing": "wide",
        "focal_mm": 24.0,
        "reason": "A locked frame the performer moves through; the location does the work.",
    },
)
BY_TEMPLATE = {entry["template_id"]: entry for entry in MOVEMENTS}


@dataclass(slots=True)
class StagingCandidate:
    candidate_id: str
    axis_id: str
    template_id: str
    camera_relation: str
    actor_start_m: tuple
    actor_end_m: tuple
    actor_heading_rad: float
    robot_start_m: tuple
    standoff_m: float
    travel_m: float
    focal_mm: float
    framing: str
    duration_s: float
    reason: str
    world_screen: dict = field(default_factory=dict)
    rejected_reason: str = ""

    @property
    def feasible_so_far(self):
        return not self.rejected_reason

    @property
    def pace_m_s(self):
        """Cart pace for the requested length, clipped to the rig's policy.

        When the clip bites, the compiler retimes the shot and the result says
        the move is longer than asked for. That is the honest answer: the cart
        has one maximum pace and no amount of planning changes it.
        """
        wanted = self.travel_m / max(self.duration_s, 0.5)
        return min(CART_PACE_MAX_M_S, max(CART_PACE_MIN_M_S, wanted))

    @property
    def pace_clipped(self):
        return self.travel_m / max(self.duration_s, 0.5) > CART_PACE_MAX_M_S + 1e-9

    def template_settings(self, *, subject_height_m=1.72):
        """The exact settings handed to previs.templates.compile_template."""
        walking = BY_TEMPLATE[self.template_id]["needs_walk"]
        return {
            "mode": "template",
            "template_id": self.template_id,
            "radius_m": round(self.standoff_m, 3),
            "distance_m": round(max(0.3, self.travel_m), 3),
            "duration_s": round(self.duration_s, 2),
            "speed_m_s": round(self.pace_m_s, 3),
            "focal_mm": self.focal_mm,
            "subject_height_m": subject_height_m,
            "subject_motion": "walk" if walking else "hold",
            "actor_heading_rad": round(self.actor_heading_rad, 6),
            "actor_distance_m": round(max(0.3, self.travel_m), 3),
            "scene": {
                "actor_position_m": [round(self.actor_start_m[0], 3), round(self.actor_start_m[1], 3)],
                "cart_start_m": [round(self.robot_start_m[0], 3), round(self.robot_start_m[1], 3)],
                "route_rotation_rad": 0.0,
                "actor_facing": "opening",
                "actor_heading_rad": round(self.actor_heading_rad, 6),
                "filming_side": "phone",
                "actor_motion": "walk" if walking else "hold",
                "walk_distance_m": round(self.travel_m if walking else 0.0, 3),
                "walk_heading_rad": round(self.actor_heading_rad, 6),
            },
        }

    def wire(self):
        return {
            "candidate_id": self.candidate_id,
            "axis_id": self.axis_id,
            "template_id": self.template_id,
            "camera_relation": self.camera_relation,
            "actor_start_m": [round(v, 3) for v in self.actor_start_m],
            "actor_end_m": [round(v, 3) for v in self.actor_end_m],
            "actor_heading_rad": round(self.actor_heading_rad, 6),
            "robot_start_m": [round(v, 3) for v in self.robot_start_m],
            "standoff_m": round(self.standoff_m, 2),
            "travel_m": round(self.travel_m, 2),
            "focal_mm": self.focal_mm,
            "framing": self.framing,
            "duration_s": round(self.duration_s, 2),
            "reason": self.reason,
            "pace_m_s": round(self.pace_m_s, 3),
            "pace_clipped": self.pace_clipped,
            "world_screen": self.world_screen,
            "rejected_reason": self.rejected_reason,
            "physical_feasibility": "not_yet_evaluated" if self.feasible_so_far else "rejected_by_world",
        }


def _screen(index, candidate, min_clearance_m):
    """Cheap metre-world screening before the compiler is asked to do work."""
    issues = []
    actor_path = (candidate.actor_start_m, candidate.actor_end_m)
    robot_end = (
        candidate.robot_start_m[0] + math.cos(candidate.actor_heading_rad) * candidate.travel_m,
        candidate.robot_start_m[1] + math.sin(candidate.actor_heading_rad) * candidate.travel_m,
    )
    actor_clear = geometry.segment_clearance_to_rings(*actor_path, index.obstacles)
    robot_clear = geometry.segment_clearance_to_rings(candidate.robot_start_m, robot_end, index.obstacles)
    if index.surface_at(candidate.actor_start_m) is None:
        issues.append("The actor's opening mark is not on known walkable ground.")
    if index.surface_at(candidate.robot_start_m) is None:
        issues.append("The cart's opening mark is not on known walkable ground.")
    if actor_clear < ACTOR_RADIUS_M:
        issues.append(f"The actor's route passes within {max(actor_clear, 0):.2f} m of a mapped obstacle.")
    if robot_clear < ROBOT_RADIUS_M + PATH_MARGIN_M:
        issues.append(f"The cart's route leaves only {max(robot_clear, 0):.2f} m beside a mapped obstacle.")
    unknown_samples = 0
    steps = max(2, int(candidate.travel_m / 0.5))
    for step in range(steps + 1):
        t = step / steps
        point = (
            candidate.robot_start_m[0] + (robot_end[0] - candidate.robot_start_m[0]) * t,
            candidate.robot_start_m[1] + (robot_end[1] - candidate.robot_start_m[1]) * t,
        )
        if index.is_unknown(point):
            unknown_samples += 1
    unknown_fraction = unknown_samples / (steps + 1)
    if unknown_fraction > 0.5:
        issues.append(
            f"{unknown_fraction * 100:.0f}% of the cart route crosses ground with no surveyed or open-data "
            "coverage. That is unknown, not clear."
        )
    return {
        "actor_route_clearance_m": round(max(actor_clear, 0.0), 2),
        "cart_route_clearance_m": round(max(robot_clear, 0.0), 2),
        "cart_unknown_fraction": round(unknown_fraction, 3),
        "min_clearance_required_m": min_clearance_m,
        "issues": issues,
        "basis": "nominal_polygon_screening_not_physical_clearance",
    }


def generate(
    world,
    *,
    travel_m=DEFAULT_TRAVEL_M,
    duration_s=6.0,
    standoffs_m=(2.6, 1.8),
    limit=MAX_CANDIDATES,
    min_clearance_m=1.0,
    templates=None,
):
    """Enumerate staging candidates for one shot. Deterministic and capped."""
    index = WorldIndex(world)
    axes = tracking_axes(world, min_clearance_m=min_clearance_m, limit=3)
    allowed = [BY_TEMPLATE[t] for t in templates] if templates else list(MOVEMENTS)
    produced = []
    for axis in axes:
        usable = max(0.5, min(travel_m, axis.usable_length_m - 1.2))
        heading = axis.heading_rad
        # Start a little in from the axis end so the actor has run-off either side.
        slack = max(0.0, axis.usable_length_m - usable) / 2.0
        start = (
            axis.start_m[0] + math.cos(heading) * slack,
            axis.start_m[1] + math.sin(heading) * slack,
        )
        end = (start[0] + math.cos(heading) * usable, start[1] + math.sin(heading) * usable)
        normal = (-math.sin(heading), math.cos(heading))
        for side, side_name in ((1, "left"), (-1, "right")):
            for standoff in standoffs_m:
                robot_start = (
                    start[0] + normal[0] * standoff * side,
                    start[1] + normal[1] * standoff * side,
                )
                for movement in allowed:
                    if movement["relation"] == "follow":
                        robot_mark = (
                            start[0] - math.cos(heading) * standoff,
                            start[1] - math.sin(heading) * standoff,
                        )
                    elif movement["relation"] == "lead":
                        robot_mark = (
                            end[0] + math.cos(heading) * standoff,
                            end[1] + math.sin(heading) * standoff,
                        )
                    else:
                        robot_mark = robot_start
                    walking = movement["needs_walk"]
                    candidate = StagingCandidate(
                        candidate_id=(
                            f"{axis.affordance_id}-{side_name}-{standoff:.1f}-{movement['template_id']}"
                        ),
                        axis_id=axis.affordance_id,
                        template_id=movement["template_id"],
                        camera_relation=movement["relation"],
                        actor_start_m=start,
                        actor_end_m=end if walking else start,
                        actor_heading_rad=heading,
                        robot_start_m=robot_mark,
                        standoff_m=standoff,
                        travel_m=usable if walking else min(usable, 1.6),
                        focal_mm=movement["focal_mm"],
                        framing=movement["framing"],
                        duration_s=duration_s,
                        reason=movement["reason"],
                    )
                    candidate.world_screen = _screen(index, candidate, min_clearance_m)
                    if candidate.world_screen["issues"]:
                        candidate.rejected_reason = candidate.world_screen["issues"][0]
                    produced.append(candidate)
    # Prefer candidates the metre world accepts, then roomier ones, then a
    # stable id so the same world always enumerates the same way.
    produced.sort(
        key=lambda c: (
            bool(c.rejected_reason),
            -c.world_screen["cart_route_clearance_m"],
            c.world_screen["cart_unknown_fraction"],
            c.candidate_id,
        )
    )
    kept, seen = [], set()
    for candidate in produced:
        key = (candidate.axis_id, candidate.template_id, round(candidate.standoff_m, 1))
        if key in seen:
            continue
        seen.add(key)
        kept.append(candidate)
        if len(kept) >= limit:
            break
    return kept
