"""Opt-in cart-only worker; same device lock and CartRunner as existing hardware paths."""

import argparse
import json
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

from takeone.cart.nudge_plan import validate_nudge
from takeone.cart.runtime import CartRunner, Timing, check_commissioning, host_timing_priority
from takeone.motion.studio_worker import device_ownership


class NudgeControl:
    """No movement before explicit browser execute; EOF/Stop/lease loss latch cancellation."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.last_seen = None
        self.execute = threading.Event()
        self.stop = threading.Event()

    def receive(self, line):
        try:
            command = json.loads(line).get("command")
        except (ValueError, AttributeError):
            command = None
        if command in ("heartbeat", "execute") and not self.stop.is_set():
            self.last_seen = self.clock()
            if command == "execute":
                self.execute.set()
        else:
            self.stop.set()

    def cancelled(self):
        if self.last_seen is None or self.clock() - self.last_seen > 0.75:
            self.stop.set()
        return self.stop.is_set()


def run_plan(plan, transport, control, *, runner_factory=CartRunner, timing=None):
    """Injectable for tests. No arm owner is ever constructed."""
    runner = runner_factory(transport, timing or Timing.load(), cancelled=control.cancelled)
    try:
        if not control.execute.is_set() or control.cancelled():
            raise InterruptedError("No fresh browser execution approval")
        transport.connect()
        if control.cancelled():
            raise InterruptedError("Browser execution approval expired during connection")
        runner.run(plan)
        return runner.report()
    finally:
        transport.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--confirm-plan", required=True)
    parser.add_argument("--operator-ready", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.operator_ready or not args.execute:
        parser.error("Requires explicit --operator-ready and --execute")
    control = NudgeControl()

    def emit(**event):
        print(json.dumps(dict(source="nudge_worker", **event)), flush=True)

    def read():
        try:
            for line in sys.stdin:
                control.receive(line)
        finally:
            control.receive("")

    threading.Thread(target=read, daemon=True).start()
    report = dict(physical_motion_verified=False, physical_stop_confirmed=False, arms_commanded=False)
    try:
        document = json.loads(args.plan.read_text(encoding="utf-8"))
        plan = validate_nudge(document)
        if args.confirm_plan != plan.plan_id:
            raise ValueError("Execution approval does not match this plan")
        report.update(plan_id=plan.plan_id, envelope=check_commissioning(plan))
        # Import the physical adapter only in an explicitly launched execution worker.
        from takeone.adapters.identity import identify_port
        from takeone.adapters.uart import MotorUART

        with device_ownership():
            report["identity"] = identify_port(document["device"]["port"], document["device"]["usb_serial"])
            emit(phase="ready_for_execute")
            if not control.execute.wait(5) or control.cancelled():
                raise InterruptedError("Execution approval was not received in time")
            # Revalidate AFTER review and waiting, before connecting the serial port.
            plan = validate_nudge(document)
            timing = Timing.load()
            transport = MotorUART(
                document["device"]["port"],
                baudrate=document["device"]["baudrate"],
                timeout=timing.write_timeout_s,
                write_timeout=timing.write_timeout_s,
                polarity=document["wire_polarity"],
            )
            emit(phase="executing")
            with host_timing_priority() as priority:
                # Capture fault reports as well as successful schedules.
                runners = []

                def factory(*a, **kw):
                    runner = CartRunner(*a, **kw)
                    runners.append(runner)
                    return runner

                try:
                    report.update(run_plan(plan, transport, control, runner_factory=factory, timing=timing))
                finally:
                    if runners:
                        report.update(runners[0].report())
                    report.update(timing=asdict(timing), host_priority=priority)
        report["phase"] = "commands_completed"
    except Exception as error:
        report.update(phase="stopped" if isinstance(error, InterruptedError) else "failed", error=str(error))
    finally:
        control.stop.set()
    (args.plan.parent / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    emit(
        terminal=True, **{k: v for k, v in report.items() if k not in ("events", "identity", "host_priority")}
    )
    return int(report["phase"] != "commands_completed")


if __name__ == "__main__":
    raise SystemExit(main())
