"""Verified stationary activation shared by commissioning and the live bus owner."""

from takeone.clock import monotonic
from takeone.contracts import JOINTS


def acknowledged_write(bus, register, values, *, trace=None, clock=monotonic):
    if set(values) != set(JOINTS) or register not in ("Goal_Position", "Torque_Enable"):
        raise ValueError("Expected one explicit goal or torque value per joint")
    for name in JOINTS:
        event = dict(
            register=register, joint=name, raw_value=values[name], write_start_s=clock(), acknowledged=False
        )
        if trace is not None:
            trace.append(event)
        try:
            bus.write(register, name, values[name], normalize=False, num_retry=0)
            event.update(write_end_s=clock(), acknowledged=True)
        except BaseException as error:
            event.update(write_end_s=clock(), error=str(error))
            raise


def activate_fixed_pose(
    bus, targets, read, positions, max_drift_deg, report, *, clock=monotonic, cancelled=lambda: False
):
    """Capture is supplied once. Never refresh the target from sagging feedback.

    Caller owns support and cleanup policy. A failure after enable does not
    silently remove torque from a loaded production arm.
    """
    seeded = clock()
    trace = report.setdefault("activation_writes", [])
    acknowledged_write(bus, "Goal_Position", targets, trace=trace, clock=clock)
    report["goal_writes_acknowledged"] = True
    if read("Goal_Position") != targets:
        raise RuntimeError("Current-position goals were not confirmed; torque remains off")
    current = positions()
    if any(abs(current[n] - targets[n]) * 360 / 4095 > max_drift_deg for n in JOINTS):
        raise RuntimeError("Arm moved while goals were being prepared; torque remains off")
    if clock() - seeded > 0.1 or cancelled():
        raise RuntimeError("Prepared goals are stale or activation cancelled; torque remains off")
    report["torque_enable_attempted"] = True
    started = clock()
    acknowledged_write(bus, "Torque_Enable", dict.fromkeys(JOINTS, 1), trace=trace, clock=clock)
    if any(v != 1 for v in read("Torque_Enable").values()):
        raise RuntimeError("Torque-enabled state was not confirmed")
    report["torque_on_confirmed"] = True
    if clock() - started > 0.1:
        raise RuntimeError("Active target preparation exceeded 100 ms")
    acknowledged_write(bus, "Goal_Position", targets, trace=trace, clock=clock)
    report["active_goal_writes_acknowledged"] = True
    if read("Goal_Position") != targets:
        raise RuntimeError("Active current-position targets were not confirmed")
    report["active_target_confirmed"] = True
    return started
