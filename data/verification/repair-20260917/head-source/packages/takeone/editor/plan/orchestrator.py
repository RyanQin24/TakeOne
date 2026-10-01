"""Pace planner operations so the interface can show each decision as it lands.

The delay is cosmetic. An operation is committed before the wait; the UI never animates a
change that has not already been folded.
"""

import time

from ..errors import PlanError

MAX_STEPS = 240


def run(next_operation, submit, pace_s=0.0, limit=MAX_STEPS):
    """Call `next_operation()` until it returns None, submitting each result.

    `next_operation` is a thunk so it can read the state *after* the previous submit.
    """
    applied = 0
    for _ in range(int(limit)):
        operation = next_operation()
        if operation is None:
            return applied
        submit(operation)
        applied += 1
        if pace_s > 0:
            time.sleep(pace_s)
    raise PlanError("The planner did not finish within the operation budget")
