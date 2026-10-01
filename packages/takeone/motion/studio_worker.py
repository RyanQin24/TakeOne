"""Dedicated hardware process controlled by a present browser owner over stdin."""

import argparse
import json
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from takeone.paths import DATA

LEASE_S = 5.0


class BrowserControl:
    def __init__(self, stop, clock=time.monotonic):
        self.stop, self.clock = stop, clock
        self.last_seen = clock()
        self.reason = None

    def receive(self, line):
        try:
            command = json.loads(line).get("command")
        except (ValueError, AttributeError):
            command = None
        if command == "heartbeat":
            self.last_seen = self.clock()
        else:
            self.reason = (
                "Stopped from the simulator" if command == "stop" else "Browser control channel closed"
            )
            self.stop.set()

    def expired(self):
        if self.clock() - self.last_seen > LEASE_S:
            self.reason = "Browser connection lost; playback stopped"
            self.stop.set()
        return self.stop.is_set()


@contextmanager
def device_ownership():
    """One studio worker per workspace, including separate server instances."""
    path = DATA / "runtime/robot-owner.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    from takeone.motion.play import run
    from takeone.motion.studio_plan import validate
    from takeone.phone.capture import PhoneTake

    stop = threading.Event()
    control = BrowserControl(stop)
    finished = threading.Event()

    def emit(event):
        print(json.dumps(dict(event, source="studio_worker")), flush=True)

    def read():
        try:
            for line in sys.stdin:
                control.receive(line)
        finally:
            control.receive("")

    def watch():
        while not finished.wait(0.1):
            control.expired()

    threading.Thread(target=read, daemon=True).start()
    threading.Thread(target=watch, daemon=True).start()
    try:
        plan = validate(json.loads(args.plan.read_text(encoding="utf-8")))
        phone_config_path = args.plan.parent / "phone-capture-config.json"
        phone_take = None
        if phone_config_path.is_file():
            phone_config = json.loads(phone_config_path.read_text(encoding="utf-8"))
            phone_take = PhoneTake(phone_config, plan, args.plan.parent, stop)
        with device_ownership():
            report = run(
                plan,
                "windows",
                25.0,
                args.plan.parent,
                stop_event=stop,
                emit=emit,
                interactive=False,
                capture=phone_take,
            )
        error = control.reason
        if not report["completed"] and not error:
            error = (
                (report.get("phone_capture") or {}).get("error")
                or report.get("stop_error")
                or report["cart"].get("fault")
                or next(
                    (a.get("fault") for a in report["arms"].values() if a.get("fault")),
                    "Playback ended before completion",
                )
            )
        emit(
            dict(
                terminal=True,
                phase="finished" if report["completed"] else "stopped",
                elapsed_s=plan["duration_s"] if report["completed"] else None,
                error=error,
                recording_confirmed=(report.get("phone_capture") or {}).get("recording_confirmed"),
                physical_path_verified=False,
            )
        )
        return 0
    except Exception as error:  # noqa: BLE001 - report driver/configuration failures to the browser
        emit(dict(terminal=True, phase="failed", error=str(error)))
        return 1
    finally:
        finished.set()
        stop.set()


if __name__ == "__main__":
    raise SystemExit(main())
