"""Generate a governor trace from the PYTHON implementation.

tests/governor.test.mjs replays the same inputs through dist/governor.js and
requires them to agree. The browser must not run a different time law from the
one the plan was validated against, and this is how that is checked rather than
assumed.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from takeone.timing import GovernorLimits, PhaseGovernor

CASES = [
    dict(
        name="nominal",
        limits=dict(max_rate=0.12, max_accel=0.35, max_jerk=2.4, tau_accel=0.12, tau_jerk=0.06),
        duration=8.0,
        dt=0.01,
        steps=1200,
        schedule=[(0.0, 0.12)],
    ),
    dict(
        name="pause_and_resume",
        limits=dict(max_rate=0.2, max_accel=0.5, max_jerk=3.0, tau_accel=0.12, tau_jerk=0.06),
        duration=5.0,
        dt=0.008,
        steps=1000,
        schedule=[(0.0, 0.2), (1.5, 0.0), (3.0, 0.2)],
    ),
    dict(
        name="pace_change",
        limits=dict(max_rate=0.3, max_accel=0.4, max_jerk=2.0, tau_accel=0.15, tau_jerk=0.05),
        duration=4.0,
        dt=0.005,
        steps=1400,
        schedule=[(0.0, 0.3), (2.0, 0.1), (4.0, 0.25)],
    ),
    dict(
        name="tracking_loss",
        limits=dict(max_rate=0.15, max_accel=0.3, max_jerk=1.5, tau_accel=0.1, tau_jerk=0.08),
        duration=7.0,
        dt=0.01,
        steps=1100,
        schedule=[(0.0, 0.15), (2.5, 0.0), (5.0, 0.15)],
    ),
]


def rate_at(schedule, t):
    value = schedule[0][1]
    for when, rate in schedule:
        if t >= when:
            value = rate
    return value


def main():
    out = []
    for case in CASES:
        governor = PhaseGovernor(GovernorLimits(**case["limits"]), case["duration"])
        trace = []
        for i in range(case["steps"]):
            # Time is i * dt, not an accumulated sum: accumulating in floating
            # point makes the two implementations cross a schedule boundary one
            # step apart and disagree by a whole jerk step. Both sides compute
            # the identical expression instead.
            s, sdot, sddot, sdddot = governor.step(case["dt"], rate_at(case["schedule"], i * case["dt"]))
            trace.append([s, sdot, sddot, sdddot])
        corridor = governor.stopping_corridor()
        out.append(
            dict(
                name=case["name"],
                limits=case["limits"],
                duration=case["duration"],
                dt=case["dt"],
                schedule=case["schedule"],
                trace=trace,
                stopping_corridor=dict(phase=corridor["phase"], seconds=corridor["seconds"]),
            )
        )
    path = Path(__file__).resolve().parent / "governor-trace.json"
    path.write_text(json.dumps(out))
    print(f"wrote {path.name}: {len(out)} cases, {sum(len(c['trace']) for c in out)} steps")


if __name__ == "__main__":
    main()
