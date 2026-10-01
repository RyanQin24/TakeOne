"""Non-actuating analysis of measured constant-command drift trials.

Distance is signed arc length of the POWERED AXLE MIDPOINT, not straight-line
displacement or a mark on the offset chassis. Heading is signed CCW in radians
internally. Wheel travel inferred here assumes rolling without slip.
"""

import csv
import hashlib
import io
import math
from dataclasses import dataclass
from pathlib import Path

from takeone.config import finite
from takeone.protocol import COMMAND_CAP, MIN_COMMAND, uart_pair


@dataclass(frozen=True)
class DriftTrial:
    trial_id: str
    left_command: float
    right_command: float
    duration_s: float
    axle_travel_m: float
    heading_change_deg: float
    track_width_m: float
    source: str
    conditions: str

    def __post_init__(self):
        for name in ("trial_id", "source", "conditions"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"Drift trial requires {name}")
        for name in self.__dataclass_fields__:
            if name not in ("trial_id", "source", "conditions"):
                finite(getattr(self, name), name)
        if self.duration_s <= 0 or self.track_width_m <= 0 or self.axle_travel_m == 0:
            raise ValueError("Duration and track width must be positive; signed axle travel must be nonzero")
        commands = (self.left_command, self.right_command)
        if commands[0] != commands[1] or not MIN_COMMAND <= abs(commands[0]) <= COMMAND_CAP:
            raise ValueError("Drift analysis requires equal constant moving wire commands within limits")
        if tuple(map(float, uart_pair(*commands).strip().split(","))) != commands:
            raise ValueError("Record the two-decimal transmitted commands, not an untransmitted trim")
        if abs(self.heading_change_deg) >= 180:
            raise ValueError("A straight commissioning trial must turn less than 180 degrees")


def analyze_trial(trial: DriftTrial):
    angle = math.radians(trial.heading_change_deg)
    half_difference = trial.track_width_m * angle / 2
    left_distance = trial.axle_travel_m - half_difference
    right_distance = trial.axle_travel_m + half_difference
    left_speed, right_speed = left_distance / trial.duration_s, right_distance / trial.duration_s
    if left_speed * right_speed <= 0:
        raise ValueError("Inferred wheels oppose or stall; verify geometry, signs and wheel motion first")
    commands = (trial.left_command, trial.right_command)
    polarity_matches = trial.axle_travel_m * commands[0] > 0
    slower = min(abs(left_speed), abs(right_speed))
    # Diagnostic only: one average-speed trial cannot identify a motor curve.
    raw = tuple(c * slower / abs(v) for c, v in zip(commands, (left_speed, right_speed)))
    wire = uart_pair(*raw)
    quantized = tuple(map(float, wire.strip().split(",")))
    original_wire = uart_pair(*commands)
    # Stable sinc limit permits exact straight trials without a division by zero.
    chord = trial.axle_travel_m * (math.sin(angle / 2) / (angle / 2) if angle else 1)
    return dict(
        trial_id=trial.trial_id,
        measured_inputs=dict(
            duration_s=trial.duration_s,
            axle_travel_m=trial.axle_travel_m,
            heading_change_deg=trial.heading_change_deg,
            track_width_m=trial.track_width_m,
            source=trial.source,
            conditions=trial.conditions,
            wire=original_wire,
        ),
        inferred_under_no_slip=dict(
            left_travel_m=left_distance,
            right_travel_m=right_distance,
            left_average_speed_m_s=left_speed,
            right_average_speed_m_s=right_speed,
            faster_wheel=("left" if abs(left_speed) > abs(right_speed) else "right")
            if abs(left_speed) != abs(right_speed)
            else None,
            speed_difference_percent=100
            * abs(left_speed - right_speed)
            / abs(trial.axle_travel_m / trial.duration_s),
            yaw_rate_rad_s=angle / trial.duration_s,
            axle_end_x_m=chord * math.cos(angle / 2),
            axle_end_y_m=chord * math.sin(angle / 2),
        ),
        polarity_matches_simulator=polarity_matches,
        proportional_trim_hypothesis=dict(
            raw_commands=list(raw),
            wire_commands=list(quantized),
            wire=wire,
            changes_transmitted_command=wire != original_wire,
            below_minimum_raw=any(abs(c) < MIN_COMMAND - 1e-12 for c in raw),
            below_minimum_wire=any(0 < abs(c) < MIN_COMMAND - 1e-12 for c in quantized),
            enabled_for_execution=False,
            assumption="Local proportional speed response; unmeasured and not a recommended live command",
        ),
        hardware_qualified=False,
    )


def analyze_measurements(path):
    path = Path(path)
    with path.open("rb") as source:
        content = source.read(1_000_001)
    if len(content) > 1_000_000:
        raise ValueError("Drift measurements must be at most 1 MB")
    with io.StringIO(content.decode("utf-8-sig"), newline="") as source:
        rows = csv.DictReader(source)
        if set(rows.fieldnames or []) != set(DriftTrial.__dataclass_fields__) or len(rows.fieldnames) != len(
            DriftTrial.__dataclass_fields__
        ):
            raise ValueError("Use docs/templates/cart-drift-measurements.csv with all documented fields")
        reports, identifiers = [], set()
        for line, row in enumerate(rows, 2):
            if len(reports) >= 1000:
                raise ValueError("At most 1000 drift trials per analysis")
            try:
                trial = DriftTrial(
                    **{
                        name: value if name in ("trial_id", "source", "conditions") else float(value)
                        for name, value in row.items()
                    }
                )
                if trial.trial_id in identifiers:
                    raise ValueError("Duplicate trial_id")
                reports.append(analyze_trial(trial))
                identifiers.add(trial.trial_id)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Drift CSV line {line}: {error}") from error
    if not reports:
        raise ValueError("Add measured trials; the template deliberately contains no fabricated measurements")
    return dict(
        schema="takeone.cart-drift-analysis.v1",
        source_sha256=hashlib.sha256(content).hexdigest(),
        trials=reports,
        conclusion="Equal packets do not imply equal wheel speeds; identify each loaded wheel and verify wiring",
        limitations=[
            "Wheel travel is inferred from axle arc length and heading under no slip, not encoder telemetry",
            "Start-to-stop average speeds are not steady-state motor response data",
            "Two-decimal UART quantization and the moving deadband limit available trim",
            "Feedforward tables cannot correct changing caster drag, load, floor slip or disturbances",
            "A pose or encoder feedback loop is needed for ongoing path correction; UART provides neither",
        ],
        changes_active_calibration=False,
        hardware_qualified=False,
    )
