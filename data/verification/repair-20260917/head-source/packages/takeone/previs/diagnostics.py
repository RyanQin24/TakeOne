"""What the simulator has to say about a shot, in one typed record.

Severity is the whole contract. `blocking` means the compiler itself refused the
shot — the same refusal the studio has always given, nothing new. `advisory`
means the shot compiles and plays exactly as asked, and the note is information
for the director. Nothing in this module may turn a shot the rig can perform
into one it cannot.
"""

from dataclasses import asdict, dataclass

BLOCKING = "blocking"
ADVISORY = "advisory"

CODES = {
    "unresolved_movement": BLOCKING,
    "unknown_parameter": BLOCKING,
    "out_of_range": BLOCKING,
    "compile_failed": BLOCKING,
    "duration_mismatch": ADVISORY,
    "framing_mismatch": ADVISORY,
    "aim_reach": ADVISORY,
    "height_reach": ADVISORY,
    "mark_placement": ADVISORY,
    "reposition_long": ADVISORY,
    "follow_distance_mismatch": ADVISORY,
    "scene_obstruction": ADVISORY,
}


@dataclass(frozen=True, slots=True)
class Diagnostic:
    shot_id: str
    code: str
    message: str
    parameter: str | None = None
    observed: float | None = None
    allowed: tuple[float, float] | None = None
    suggestion: str = ""

    def __post_init__(self):
        if self.code not in CODES:
            raise ValueError(f"Unknown diagnostic code: {self.code}")

    @property
    def severity(self):
        return CODES[self.code]

    @property
    def blocking(self):
        return CODES[self.code] == BLOCKING

    def wire(self):
        return {**asdict(self), "severity": self.severity, "allowed": list(self.allowed or ())}


def timing(shot_id, filming_s, slot_s):
    """Filming time comes from geometry; the edit slot comes from the script. They differ."""
    if slot_s <= 0 or abs(filming_s - slot_s) <= max(0.5, 0.15 * slot_s):
        return None
    longer = filming_s > slot_s
    return Diagnostic(
        shot_id,
        "duration_mismatch",
        f"Filming takes {filming_s:.1f} s, {'longer' if longer else 'shorter'} than its "
        f"{slot_s:.1f} s place in the edit. The rehearsal plays the full move; "
        + (
            "the edit must choose which part to use."
            if longer
            else "there is not enough recorded movement to fill that slot at normal speed."
        ),
        observed=filming_s,
        allowed=(slot_s * 0.85, slot_s * 1.15),
        suggestion=(
            f"To fit {slot_s:.1f} s of filming, shorten the route or raise the pace"
            if longer
            else f"To fill {slot_s:.1f} s of filming, lengthen the route or lower the pace"
        ),
    )


def framing(shot_id, declared, geometry):
    if declared is None or declared in geometry["implied"] or declared == geometry["nearest"]:
        return None
    start, end = geometry["frame_height_m"]
    return Diagnostic(
        shot_id,
        "framing_mismatch",
        f"This frames {start:.2f} m of the subject at the start and {end:.2f} m at the end, "
        f"closest to a {geometry['nearest'].replace('_', ' ')}, not the "
        f"{declared.replace('_', ' ')} the script declares.",
        parameter="focal_mm",
        observed=end,
        suggestion=(
            f"Frame height in metres is distance x 20.25 / focal_mm. "
            f"Change radius_m or focal_mm until it lands the {declared.replace('_', ' ')} band, "
            f"or declare the framing this geometry actually gives."
        ),
    )


def reach(shot_id, summary):
    """The compiler already played the shot. These say what it achieved, never that it refused."""
    found = []
    aim = summary.get("max_aim_error_deg")
    if aim is not None and aim > 3:
        found.append(
            Diagnostic(
                shot_id,
                "aim_reach",
                f"The phone misses the requested aim by up to {aim:.1f} degrees, after the intentional pan/tilt. "
                "Review the camera view and revise this setup.",
                observed=aim,
                suggestion="A larger radius_m or a different camera height usually reduces it",
            )
        )
    achieved = summary.get("camera_height_start_m", summary.get("camera_height_m"))
    requested = summary.get("requested_camera_height_m")
    if achieved is not None and requested is not None and abs(achieved - requested) > 0.03:
        found.append(
            Diagnostic(
                shot_id,
                "height_reach",
                f"The arm reaches {achieved:.2f} m for the requested {requested:.2f} m camera height. "
                f"The preview shows the height it achieved.",
                parameter="height_start_m",
                observed=achieved,
                suggestion="A larger radius_m usually lets the arm reach the requested height",
            )
        )
    return found


def placement(shot_id, origin_m, limit_m):
    if max(abs(origin_m[0]), abs(origin_m[1])) <= limit_m:
        return None
    return Diagnostic(
        shot_id,
        "mark_placement",
        f"This mark sits at ({origin_m[0]:.1f}, {origin_m[1]:.1f}) m, outside the "
        f"{limit_m:.0f} m set the studio draws. The shot rehearses; the set dressing does not reach it.",
        parameter="position_m",
        suggestion=f"Keep marks within {limit_m:.0f} m of the set origin",
    )


def long_move(shot_id, duration_s, limit_s):
    if duration_s <= limit_s:
        return None
    return Diagnostic(
        shot_id,
        "reposition_long",
        f"Moving to this mark takes at least {duration_s:.1f} s of dead time between takes; the reset route is unestimated.",
        observed=duration_s,
        suggestion="Reuse the previous mark, or place this one closer",
    )
